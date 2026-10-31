"""Execution boundary, calibrated simulated transport, and independent HTTP oracle."""
import asyncio
import collections
import math
import time
from dataclasses import dataclass

from tempo import Scenario, Provider, Response, VirtualLoop, execute
from http_experiment import LocalServer, HTTPProvider


@dataclass(frozen=True)
class Contract:
    jobs: int
    limit: int
    window: float
    scale: float
    deadline: float
    quota_mode: str
    service: float
    slow_service: float


class ClientPort:
    """Only the contract and a request operation are part of the adapter API."""
    __slots__ = ('s', '_provider', '_job')

    def __init__(self, provider, job=None):
        self.s = Contract(**{k: getattr(provider.s, k) for k in Contract.__annotations__})
        self._provider, self._job = provider, job

    async def post(self, job, idempotency_key=None):
        if self._job is None or type(job) is not int or job != self._job:
            raise ValueError('An integration may submit only its assigned job')
        if idempotency_key is not None and (not isinstance(idempotency_key, str) or
                len(idempotency_key) > 100 or any(ord(c) < 32 or ord(c) > 126 for c in idempotency_key)):
            raise ValueError('Invalid idempotency key')
        return await self._provider.post(job, idempotency_key)


class WireModel(Provider):
    async def post(self, job, idempotency_key=None):
        response = await super().post(job, idempotency_key)
        return Response(response.status, math.ceil(response.retry_after * self.s.scale)/self.s.scale)


class ServerOracle:
    """Separate quota implementation: server does not inherit the simulation model.

    Fixed windows are tracked by an expiry; token quotas by virtual token debt.
    The controlled contract starts with a full quota and a known local epoch.
    """
    def __init__(self, scenario):
        self.s = scenario
        self.loop = asyncio.get_running_loop()
        self.origin = self.loop.time()
        self.end = scenario.window
        self.remaining = scenario.limit
        self.debt_until = 0.0
        self.effects = collections.Counter()
        self.keys = set()
        self.calls = self.rejected = 0
        self.events = []

    def now(self):
        return (self.loop.time()-self.origin)/self.s.scale

    async def post(self, job, idempotency_key=None):
        now = self.now()
        self.calls += 1
        if self.s.quota_mode == 'fixed':
            if now >= self.end:
                self.end = (math.floor(now/self.s.window)+1)*self.s.window
                self.remaining = self.s.limit
            allowed = self.remaining > 0
            delay = self.end-now
            if allowed:
                self.remaining -= 1
        else:
            interval = self.s.window/self.s.limit
            earliest = self.debt_until-(self.s.limit-1)*interval
            allowed = now >= earliest-1e-8
            delay = max(0, earliest-now)
            if allowed:
                self.debt_until = max(now, self.debt_until)+interval
        if not allowed:
            self.rejected += 1
            self.events.append({'t': round(now, 6), 'job': job, 'status': 429,
                                'retry_after': round(delay, 6)})
            return Response(429, delay)
        duplicate = idempotency_key is not None and idempotency_key in self.keys
        if not duplicate:
            self.effects[job] += 1
            if idempotency_key is not None:
                self.keys.add(idempotency_key)
        self.events.append({'t': round(now, 6), 'job': job, 'status': 200, 'deduplicated': duplicate})
        slow = (job+self.s.seed) % self.s.slow_every == 0
        await asyncio.sleep((self.s.slow_service if slow else self.s.service)*self.s.scale)
        return Response(200)


async def evaluate(scenario, module, transport):
    async def client(provider, job, context):
        return await module.integrate(ClientPort(provider, job), job, context)

    def configure(provider):
        return module.configure(ClientPort(provider))

    start = time.perf_counter()
    if transport == 'http':
        async with LocalServer(scenario, provider_factory=ServerOracle) as server:
            result = await execute(scenario, client, configure, HTTPProvider(server))
            result['server_errors'] = server.errors.copy()
    else:
        result = await execute(scenario, client, configure, WireModel(scenario))
        result['server_errors'] = []
    result['clock'] = transport
    result['wall_seconds'] = time.perf_counter()-start
    result['completion_seconds'] = result['virtual_seconds']*scenario.scale
    return result


def run_module(scenario, module, transport):
    loop = VirtualLoop() if transport == 'virtual' else asyncio.new_event_loop()
    try:
        return loop.run_until_complete(evaluate(scenario, module, transport))
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
