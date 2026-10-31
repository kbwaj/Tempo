"""Authored integration with independent retry loops and short timeouts."""
import asyncio


def configure(provider):
    return None


async def integrate(provider, job, context):
    for outer in range(3):
        for inner in range(3):
            try:
                response = await asyncio.wait_for(provider.post(job), .25*provider.s.scale)
                if response.status == 200:
                    return True
            except asyncio.TimeoutError:
                pass
            await asyncio.sleep((2**inner)*.1*provider.s.scale)
        await asyncio.sleep((2**outer)*.1*provider.s.scale)
    return False
