"""Conventional per-request retry + semaphore, without predictive quotas.

Uses stable keys, timeout growth and server Retry-After. A useful ordinary
configuration comparator; the hierarchical reference is the stronger one.
"""
import asyncio
import random


def configure(provider):
    return asyncio.Semaphore(provider.s.concurrency)


async def call(provider,stage,job,ctx,receipt='',value=None):
    timeout=max(2.0,provider.s.slow_service*1.2)
    rng=random.Random(job+173)
    for attempt in range(32):
        async with ctx:
            try:
                response=await asyncio.wait_for(provider.request(stage,job,key=f'{stage}-{job}',receipt=receipt,value=value),timeout*provider.s.scale)
            except asyncio.TimeoutError:
                timeout=min(32,timeout*2)
                continue
        if response.status==200: return response
        if response.status not in (429,503): return None
        await asyncio.sleep((response.retry_after+.02+rng.random()*.05)*provider.s.scale)
    return None


async def integrate(provider,job,ctx):
    read=await call(provider,'read',job,ctx)
    if read is None: return False
    return await call(provider,'write',job,ctx,read.receipt,read.value*3+7) is not None
