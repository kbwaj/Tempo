"""Standard-library contract-aware limiter: an explicit strong comparator.

MODE='paced' gives the simpler smooth limiter; MODE='burst' uses the provider's
published burst allowance and fixed-window epoch. No LLM generated this file.
"""
import asyncio
import math

MODE = 'burst'


def configure(provider):
    return {'lock': asyncio.Lock(), 'origin': asyncio.get_running_loop().time(),
            'next': 0.0, 'window': -1, 'used': 0, 'tokens': float(provider.s.limit),
            'updated': asyncio.get_running_loop().time(), 'cooldown': 0.0}


async def admit(provider, ctx):
    s = provider.s
    loop = asyncio.get_running_loop()
    async with ctx['lock']:
        while True:
            now = loop.time()
            if now < ctx['cooldown']:
                await asyncio.sleep(ctx['cooldown']-now)
                continue
            interval = s.window*s.scale/s.limit
            if MODE == 'paced':
                await asyncio.sleep(max(0, ctx['next']-now))
                ctx['next'] = loop.time()+interval+0.001*s.scale
                return
            if s.quota_mode == 'fixed':
                # Epoch is part of this controlled local contract. This assumes
                # no unobserved consumers; not portable to arbitrary providers.
                elapsed = (now-ctx['origin'])/s.scale
                window = math.floor(elapsed/s.window)
                if window != ctx['window']:
                    ctx['window'], ctx['used'] = window, 0
                if ctx['used'] < s.limit:
                    ctx['used'] += 1
                    return
                await asyncio.sleep(max(0, ctx['origin']+(window+1)*s.window*s.scale-now)+.002*s.scale)
            else:
                ctx['tokens'] = min(s.limit, ctx['tokens']+(now-ctx['updated'])/interval)
                ctx['updated'] = now
                if ctx['tokens'] >= 1:
                    ctx['tokens'] -= 1
                    return
                await asyncio.sleep((1-ctx['tokens'])*interval+.002*s.scale)


async def integrate(provider, job, ctx):
    timeout = max(2.0, provider.s.slow_service*1.1)
    for attempt in range(24):
        await admit(provider, ctx)
        try:
            response = await asyncio.wait_for(provider.post(job, f'job-{job}'), timeout*provider.s.scale)
            if response.status == 200:
                return True
            if response.status != 429:
                return False
            ctx['cooldown'] = max(ctx['cooldown'], asyncio.get_running_loop().time() +
                                  response.retry_after*provider.s.scale+.002*provider.s.scale)
        except asyncio.TimeoutError:
            timeout = min(32, timeout*2)
    return False
