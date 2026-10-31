"""Authored connector with a sensible but overly broad retry coordinator.

Stable keys, growing timeouts, Retry-After, and bounded concurrency are present.
The entire read-transform-write job holds its worker slot through quota waits.
Any endpoint throttle pauses the whole connector, including unrelated reads.
"""
import asyncio


def configure(provider):
    return {'workers':asyncio.Semaphore(provider.s.concurrency), 'cooldown':0.0}


async def call(provider,stage,job,ctx,receipt='',value=None):
    timeout=max(2.0,provider.s.slow_service*1.2)
    for attempt in range(32):
        await asyncio.sleep(max(0,ctx['cooldown']-asyncio.get_running_loop().time()))
        try:
            response=await asyncio.wait_for(provider.request(stage,job,key=f'{stage}-{job}',receipt=receipt,value=value),timeout*provider.s.scale)
        except asyncio.TimeoutError:
            timeout=min(32,timeout*2)
            continue
        if response.status==200: return response
        if response.status not in (429,503): return None
        ctx['cooldown']=max(ctx['cooldown'],asyncio.get_running_loop().time()+(response.retry_after+.02)*provider.s.scale)
    return None


async def integrate(provider,job,ctx):
    async with ctx['workers']:
        read=await call(provider,'read',job,ctx)
        if read is None: return False
        write=await call(provider,'write',job,ctx,read.receipt,read.value*3+7)
        return write is not None
