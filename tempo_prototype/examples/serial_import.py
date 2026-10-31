"""Authored importer: a shared SDK lock unnecessarily serializes full requests."""
import asyncio


def configure(provider):
    return {'lock': asyncio.Lock(), 'next': 0.0}


async def integrate(provider, job, context):
    # Quota safety was implemented by serializing the entire network operation.
    async with context['lock']:
        loop = asyncio.get_running_loop()
        timeout = max(2, provider.s.slow_service*1.1)
        for attempt in range(24):
            await asyncio.sleep(max(0, context['next']-loop.time()))
            context['next'] = loop.time()+provider.s.window*provider.s.scale/provider.s.limit
            try:
                response = await asyncio.wait_for(provider.post(job, f'job-{job}'), timeout*provider.s.scale)
                if response.status == 200:
                    return True
                await asyncio.sleep((response.retry_after+.01)*provider.s.scale)
            except asyncio.TimeoutError:
                timeout *= 2
        return False
