"""Catalog sync with ordinary robust HTTP configuration.

Burst-aware quota admission, concurrency limits, stable write keys, bounded
retry/timeout and Retry-After are already configured. The business workflow
still performs its two enrichment lookups separately for every product.
"""
import asyncio
import math


def configure(provider):
    now=asyncio.get_running_loop().time()
    return {'lock':asyncio.Lock(),'sem':asyncio.Semaphore(provider.s.concurrency),
            'origin':now,'updated':now,'tokens':float(max(1,provider.s.limit-1)),
            'window':-1,'used':0,'cooldown':0.0}


async def admit(provider,ctx):
    s=provider.s;loop=asyncio.get_running_loop()
    while True:
        async with ctx['lock']:
            now=loop.time();delay=ctx['cooldown']-now
            if s.quota_mode=='token':
                rate=.98*s.limit/(s.window*s.scale)
                ctx['tokens']=min(max(1,s.limit-1),ctx['tokens']+(now-ctx['updated'])*rate)
                ctx['updated']=now;delay=max(delay,(1-ctx['tokens'])/rate)
            else:
                index=math.floor((now-ctx['origin'])/(s.window*s.scale))
                if index!=ctx['window']:ctx['window'],ctx['used']=index,0
                if ctx['used']>=s.limit:delay=max(delay,ctx['origin']+(index+1)*s.window*s.scale-now)
            if delay<=0 and ctx['sem'].locked():delay=.01*s.scale
            if delay<=0:
                await ctx['sem'].acquire()
                if s.quota_mode=='token':ctx['tokens']-=1
                else:ctx['used']+=1
                return
        await asyncio.sleep(delay+.025*s.scale)


async def api(provider,ctx,operation,*args):
    timeout=max(2.,provider.s.slow_service*1.5)
    for attempt in range(16):
        await admit(provider,ctx)
        try:
            result=await asyncio.wait_for(operation(*args),timeout*provider.s.scale)
        except asyncio.TimeoutError:
            timeout=min(32.,timeout*2)
            continue
        finally:ctx['sem'].release()
        if result.status==200:return result.data
        if result.status not in (429,503):raise ValueError('Provider rejected operation')
        if result.status==429:
            ctx['cooldown']=max(ctx['cooldown'],asyncio.get_running_loop().time()+(result.retry_after+.025)*provider.s.scale)
        else:await asyncio.sleep((result.retry_after+.025)*provider.s.scale)
    raise RuntimeError('Retry budget exhausted')


async def integrate(provider,job,ctx):
    item=provider.items[job]
    category=(await api(provider,ctx,provider.lookup,'category',item.tenant,item.snapshot,[item.category]))[item.category]
    fx=(await api(provider,ctx,provider.lookup,'fx',item.tenant,item.snapshot,[item.currency]))[item.currency]
    inventory=await api(provider,ctx,provider.inventory,item.id)
    payload={'id':item.id,'tenant':item.tenant,'snapshot':item.snapshot,'category_label':category['value'],
             'converted_cents':(item.price_cents*fx['value']+5000)//10000,'stock':inventory['value']}
    await api(provider,ctx,provider.write,item.id,payload,[category['receipt'],fx['receipt'],inventory['receipt']],f'sync-{item.tenant}-{item.snapshot}-{job}')
    return True
