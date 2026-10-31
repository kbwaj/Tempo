"""Small real-asyncio experiment runner. No external services or dependencies.

The virtual loop is ONLY for fully simulated I/O. It does not accelerate real
network calls, CPU work, threads, wall-clock reads, or arbitrary Python programs.
"""
import asyncio
import collections
import hashlib
import json
import math
import time
from dataclasses import dataclass, asdict
from pathlib import Path


class VirtualSelector:
    def __init__(self, selector, loop):
        self.inner, self.loop = selector, loop

    def select(self, timeout=None):
        if timeout is None:
            raise RuntimeError('Simulation has no next event; possible deadlock')
        if len(self.inner.get_map()) > 1:
            raise RuntimeError('Real socket I/O is not supported in virtual mode')
        self.loop.now += max(0.0, timeout)
        return self.inner.select(0)

    def __getattr__(self, name):
        return getattr(self.inner, name)


class VirtualLoop(asyncio.SelectorEventLoop):
    def __init__(self):
        self.now = 0.0
        super().__init__()
        self._selector = VirtualSelector(self._selector, self)

    def time(self):
        return self.now


@dataclass
class Scenario:
    name: str = 'quota_and_slow_responses'
    jobs: int = 48
    limit: int = 8
    window: float = 10.0
    service: float = 0.4
    slow_service: float = 1.4
    slow_every: int = 7
    deadline: float = 240.0
    seed: int = 0
    scale: float = 1.0
    quota_mode: str = 'fixed'


@dataclass
class Response:
    status: int
    retry_after: float = 0.0


class Provider:
    """Explicit synthetic fixed-window quota + delayed ACKs + idempotency.

    A side effect commits before the delayed response. Client cancellation cannot
    undo the effect. Quota is consumed by accepted submissions, not 429s.
    This is a model, NOT a claim about any named provider's production behavior.
    """
    def __init__(self, scenario):
        self.s = scenario
        self.loop = asyncio.get_running_loop()
        self.origin = self.loop.time()
        self.window_id = -1
        self.used = 0
        self.keys = set()
        self.effects = collections.Counter()
        self.calls = 0
        self.rejected = 0
        self.events = []
        self.tokens = float(scenario.limit)
        self.last_refill = 0.0

    def now(self):
        return (self.loop.time() - self.origin) / self.s.scale

    async def post(self, job, idempotency_key=None):
        now = self.now()
        self.calls += 1
        window_id = math.floor((now + 1e-8) / self.s.window)
        if window_id != self.window_id:
            self.window_id, self.used = window_id, 0
        if self.s.quota_mode == 'token':
            self.tokens = min(self.s.limit, self.tokens + (now-self.last_refill)*self.s.limit/self.s.window)
            self.last_refill = now
            allowed = self.tokens >= 1-1e-8
            delay = max(0, (1-self.tokens)*self.s.window/self.s.limit)
        else:
            allowed = self.used < self.s.limit
            delay = max(0, (window_id+1)*self.s.window-now)
        if not allowed:
            self.rejected += 1
            self.events.append({'t': round(now, 6), 'job': job, 'status': 429, 'retry_after': round(delay, 6)})
            return Response(429, delay)
        self.used += 1
        if self.s.quota_mode == 'token':
            self.tokens -= 1
        duplicate_key = idempotency_key is not None and idempotency_key in self.keys
        if not duplicate_key:
            self.effects[job] += 1
            if idempotency_key is not None:
                self.keys.add(idempotency_key)
        self.events.append({'t': round(now, 6), 'job': job, 'status': 200, 'deduplicated': duplicate_key})
        slow = (job + self.s.seed) % self.s.slow_every == 0
        await asyncio.sleep((self.s.slow_service if slow else self.s.service) * self.s.scale)
        return Response(200)


async def baseline(provider, job):
    """Representative layered retry code: SDK retries inside application retries.

    This is an authored fixture, not a real vendor SDK or an imported production bug.
    """
    s = provider.s
    for outer in range(3):
        for inner in range(3):
            try:
                response = await asyncio.wait_for(provider.post(job), timeout=0.8*s.scale)
                if response.status == 200:
                    return True
            except asyncio.TimeoutError:
                pass
            await asyncio.sleep((2 ** inner) * s.scale)
        await asyncio.sleep((2 ** outer) * s.scale)
    return False


async def execute(scenario, client, configure=None, provider=None):
    provider = Provider(scenario) if provider is None else provider
    ctx = configure(provider) if configure else None
    async def worker(job):
        if configure:
            return await client(provider, job, ctx)
        return await client(provider, job)
    tasks = [asyncio.create_task(worker(j)) for j in range(scenario.jobs)]
    timed_out = False
    try:
        outcomes = await asyncio.wait_for(asyncio.gather(*tasks), scenario.deadline*scenario.scale)
    except asyncio.TimeoutError:
        timed_out = True
        outcomes = [t.result() if t.done() and not t.cancelled() and t.exception() is None else False for t in tasks]
    result = {
        'scenario': scenario.name,
        'jobs': scenario.jobs,
        'acknowledged': sum(bool(x) for x in outcomes),
        'unique_side_effects': len(provider.effects),
        'duplicate_side_effects': sum(max(0, n-1) for n in provider.effects.values()),
        'requests': provider.calls,
        'rate_limit_responses': provider.rejected,
        'virtual_seconds': round(provider.now(), 6),
        'deadline_exceeded': timed_out,
        'events': provider.events,
    }
    return result


def run(scenario, client=baseline, configure=None, virtual=True):
    loop = VirtualLoop() if virtual else asyncio.new_event_loop()
    start = time.perf_counter()
    try:
        result = loop.run_until_complete(execute(scenario, client, configure))
        result['wall_seconds'] = round(time.perf_counter()-start, 6)
        result['clock'] = 'virtual' if virtual else 'real'
        return result
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()


if __name__ == '__main__':
    result = run(Scenario())
    Path('baseline.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='events'}, indent=2))
    print('First 12 events:', json.dumps(result['events'][:12]))
