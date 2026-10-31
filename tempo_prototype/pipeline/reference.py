"""Authored hierarchical quota + per-request concurrency reference.

This is conventional local scheduling, not AI-generated or a novel algorithm.
"""
import asyncio
import math


def configure(provider):
    now = asyncio.get_running_loop().time()
    return {'lock':asyncio.Lock(), 'sem':asyncio.Semaphore(provider.s.concurrency), 'epoch':now,
            'budgets':{name:{'tokens':float(limit), 'updated':now, 'index':-1, 'used':0} for name,limit in [('account',provider.s.account_limit),('read',provider.s.read_limit),('write',provider.s.write_limit)]},
            'cooldowns':{'account':0.0,'read':0.0,'write':0.0,'concurrency':0.0}}


async def admit(provider, stage, ctx):
    s=provider.s
    config={'account':(s.account_limit,s.account_window,s.account_mode,s.read_cost if stage=='read' else s.write_cost),
            'read':(s.read_limit,s.read_window,s.read_mode,1), 'write':(s.write_limit,s.write_window,s.write_mode,1)}
    loop=asyncio.get_running_loop()
    while True:
        async with ctx['lock']:
            now=loop.time()
            delay=max(ctx['cooldowns']['account'],ctx['cooldowns'][stage],ctx['cooldowns']['concurrency'])-now
            for name in ['account',stage]:
                limit,window,mode,cost=config[name]
                b=ctx['budgets'][name]
                if mode=='token':
                    b['tokens']=min(limit,b['tokens']+(now-b['updated'])*limit/(window*s.scale))
                    b['updated']=now
                    delay=max(delay,(cost-b['tokens'])*window*s.scale/limit)
                else:
                    index=math.floor((now-ctx['epoch'])/(window*s.scale))
                    if index!=b['index']:
                        b['index'],b['used']=index,0
                    if b['used']+cost>limit:
                        delay=max(delay,ctx['epoch']+(index+1)*window*s.scale-now)
            if delay<=0 and ctx['sem'].locked():
                delay=.01*s.scale
            if delay<=0:
                await ctx['sem'].acquire()
                for name in ['account',stage]:
                    limit,window,mode,cost=config[name]
                    b=ctx['budgets'][name]
                    if mode=='token': b['tokens']-=cost
                    else: b['used']+=cost
                return
        await asyncio.sleep(delay+.015*s.scale)


async def request(provider,stage,job,ctx,receipt='',value=None):
    timeout=max(2.0,provider.s.slow_service*1.2)
    for attempt in range(32):
        # Reserve account+endpoint quota and a request slot together. No slot
        # is held across quota waits or across the complete multi-stage job.
        await admit(provider,stage,ctx)
        try:
            response=await asyncio.wait_for(provider.request(stage,job,key=f'{stage}-{job}',receipt=receipt,value=value),timeout*provider.s.scale)
        except asyncio.TimeoutError:
            timeout=min(32,timeout*2)
            continue
        finally:
            ctx['sem'].release()
        if response.status==200: return response
        if response.status not in (429,503): return None
        if response.status==429:
            ctx['cooldowns'][response.scope]=max(ctx['cooldowns'][response.scope],asyncio.get_running_loop().time()+(response.retry_after+.02)*provider.s.scale)
        else:
            await asyncio.sleep((response.retry_after+.02)*provider.s.scale)
    return None


async def integrate(provider,job,ctx):
    read=await request(provider,'read',job,ctx)
    if read is None: return False
    write=await request(provider,'write',job,ctx,read.receipt,read.value*3+7)
    return write is not None
