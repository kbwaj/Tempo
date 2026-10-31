"""Two SDK clients each pace their endpoint, sharing one provider account.

Each endpoint limiter is individually reasonable. They do not coordinate the
weighted account budget, and each SDK independently permits full concurrency.
"""
import asyncio


def configure(provider):
    return {stage:{'lock':asyncio.Lock(),'next':0.0,'sem':asyncio.Semaphore(provider.s.concurrency)} for stage in ['read','write']}


async def call(provider,stage,job,ctx,receipt='',value=None):
    s=provider.s
    interval=(s.read_window/s.read_limit if stage=='read' else s.write_window/s.write_limit)*s.scale
    timeout=max(2.0,s.slow_service*1.2)
    for attempt in range(32):
        state=ctx[stage]
        async with state['lock']:
            await asyncio.sleep(max(0,state['next']-asyncio.get_running_loop().time()))
            state['next']=asyncio.get_running_loop().time()+interval+.01*s.scale
        async with state['sem']:
            try:
                response=await asyncio.wait_for(provider.request(stage,job,key=f'{stage}-{job}',receipt=receipt,value=value),timeout*s.scale)
            except asyncio.TimeoutError:
                timeout=min(32,timeout*2)
                continue
        if response.status==200:return response
        if response.status not in (429,503):return None
        await asyncio.sleep((response.retry_after+.02)*s.scale)
    return None


async def integrate(provider,job,ctx):
    read=await call(provider,'read',job,ctx)
    if read is None:return False
    return await call(provider,'write',job,ctx,read.receipt,read.value*3+7) is not None
