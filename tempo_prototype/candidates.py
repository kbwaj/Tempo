"""Agent-authored candidates, evaluated after examining baseline.json.

These policies are NOT discovered automatically by the runner. The assistant
authored them in this session. Quota parameters come from an explicit contract;
they are not inferred from telemetry in this prototype.
"""
import asyncio
import random
from dataclasses import dataclass


async def retry_after_only(provider, job):
    # A plausible local fix: honor 429s, but preserve short timeout and lack of
    # idempotency. Test whether the apparently sensible patch is sufficient.
    for attempt in range(12):
        try:
            response = await asyncio.wait_for(provider.post(job), 0.8*provider.s.scale)
            if response.status == 200:
                return True
            delay = response.retry_after + 0.001
        except asyncio.TimeoutError:
            delay = 1
        await asyncio.sleep(delay*provider.s.scale)
    return False


@dataclass
class Policy:
    # This budget is for this application's share of provider quota, not an
    # assertion that the application is the provider's only customer.
    rate: float = 0.8
    timeout: float = 2.0
    attempts: int = 12
    idempotency: bool = True
    timeout_growth: float = 1.0


class Gate:
    def __init__(self, policy, scale):
        self.policy, self.scale = policy, scale
        self.next_slot = 0.0
        self.cooldown = 0.0
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            loop = asyncio.get_running_loop()
            await asyncio.sleep(max(0, max(self.next_slot, self.cooldown)-loop.time()))
            self.next_slot = loop.time() + (1/self.policy.rate + 1e-5)*self.scale

    def defer(self, delay):
        self.cooldown = max(self.cooldown, asyncio.get_running_loop().time() + (delay+0.001)*self.scale)


async def tuned(provider, job, gate):
    timeout = gate.policy.timeout
    for attempt in range(gate.policy.attempts):
        await gate.acquire()
        try:
            response = await asyncio.wait_for(
                provider.post(job, idempotency_key=f'job-{job}' if gate.policy.idempotency else None),
                timeout*provider.s.scale,
            )
            if response.status == 200:
                return True
            gate.defer(response.retry_after)
        except asyncio.TimeoutError:
            # Retry with the SAME idempotency key. The server may have committed.
            timeout = min(16.0, timeout * gate.policy.timeout_growth)
    return False


def configured(policy):
    return lambda provider: Gate(policy, provider.s.scale)


async def sensible_baseline(provider, job):
    """Single retry layer, Retry-After + jitter, stable key, growing timeout.

    This is a stronger baseline than the deliberately flawed nested fixture.
    It lacks cross-request admission coordination, but includes ordinary best
    practices. Authored code, not a claim to benchmark any vendor library.
    """
    rng = random.Random(1729+job)
    timeout = 2.0
    for attempt in range(24):
        try:
            response = await asyncio.wait_for(provider.post(job, f'job-{job}'),timeout*provider.s.scale)
            if response.status == 200:
                return True
            delay = response.retry_after + .001 + rng.random()*.5
        except asyncio.TimeoutError:
            timeout = min(16.,timeout*2)
            delay = rng.random()*min(8.,2**min(attempt,3))
        await asyncio.sleep(delay*provider.s.scale)
    return False
