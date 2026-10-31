"""Authored multi-stage contract; model and server use different quota engines.

Business semantics are shared, so quota implementation independence does not
constitute independent validation of the entire provider model.
"""
import asyncio
import collections
import hashlib
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineScenario:
    name: str = 'pipeline'
    jobs: int = 16
    tenants: int = 3
    account_limit: int = 8
    account_window: float = 1.2
    account_mode: str = 'token'
    read_limit: int = 5
    read_window: float = 1.0
    read_mode: str = 'token'
    write_limit: int = 3
    write_window: float = 1.4
    write_mode: str = 'fixed'
    read_cost: int = 1
    write_cost: int = 2
    concurrency: int = 4
    read_service: float = .04
    write_service: float = .12
    slow_service: float = .5
    slow_every: int = 5
    transient_every: int = 7
    seed: int = 0
    deadline: float = 70
    scale: float = .2


@dataclass(frozen=True)
class Contract:
    jobs: int
    tenants: int
    account_limit: int
    account_window: float
    account_mode: str
    read_limit: int
    read_window: float
    read_mode: str
    write_limit: int
    write_window: float
    write_mode: str
    read_cost: int
    write_cost: int
    concurrency: int
    read_service: float
    write_service: float
    slow_service: float
    deadline: float
    scale: float


@dataclass(frozen=True)
class Reply:
    status: int
    retry_after: float = 0
    scope: str = ''
    receipt: str = ''
    value: int = 0


class SimulationQuota:
    def __init__(self, limit, window, mode):
        self.limit, self.window, self.mode = limit, window, mode
        self.tokens, self.updated, self.window_id, self.used = float(limit), 0.0, -1, 0

    def wait(self, now, cost):
        if self.mode == 'token':
            self.tokens = min(self.limit, self.tokens+(now-self.updated)*self.limit/self.window)
            self.updated = now
            return max(0.0, (cost-self.tokens)*self.window/self.limit)
        index = math.floor((now+1e-9)/self.window)
        if index != self.window_id:
            self.window_id, self.used = index, 0
        return 0.0 if self.used+cost <= self.limit else (index+1)*self.window-now

    def consume(self, now, cost):
        if self.mode == 'token':
            self.tokens -= cost
        else:
            self.used += cost


class ServerQuota:
    """Independent debt/expiry implementation of the same quota contract."""
    def __init__(self, limit, window, mode):
        self.capacity, self.period, self.kind = limit, window, mode
        self.available, self.expires, self.debt = limit, window, 0.0

    def wait(self, now, cost):
        if self.kind == 'token':
            interval = self.period/self.capacity
            return max(0.0, self.debt-(self.capacity-cost)*interval-now)
        if now >= self.expires:
            self.expires = (math.floor(now/self.period)+1)*self.period
            self.available = self.capacity
        return 0.0 if self.available >= cost else self.expires-now

    def consume(self, now, cost):
        if self.kind == 'token':
            self.debt = max(now, self.debt)+cost*self.period/self.capacity
        else:
            self.available -= cost


class PipelineProvider:
    def __init__(self, scenario, quota_type=SimulationQuota):
        self.s = scenario
        self.loop = asyncio.get_running_loop()
        self.origin = self.loop.time()
        self.quotas = {scope: quota_type(getattr(scenario, scope+'_limit'), getattr(scenario, scope+'_window'), getattr(scenario, scope+'_mode')) for scope in ['account','read','write']}
        self.calls = collections.Counter()
        self.statuses = collections.Counter()
        self.effects = collections.Counter()
        self.values = {}
        self.keys = {}
        self.reads = set()
        self.attempts = collections.Counter()
        self.inflight = set()
        self.pending = set()
        self.events = []
        self.invalid_writes = 0
        self.peak_inflight = 0

    def now(self):
        return (self.loop.time()-self.origin)/self.s.scale

    def receipt(self, job):
        return hashlib.sha256(f'{self.s.seed}:{job}:read'.encode()).hexdigest()[:24]

    def value(self, job):
        return (job*17+self.s.seed*13) % 997

    def response(self, status, scope='', delay=0, receipt='', value=0):
        # Exact same integer-wall-second wire representation in both modes.
        return Reply(status, math.ceil(max(0, delay)*self.s.scale)/self.s.scale, scope, receipt, value)

    async def request(self, stage, job, key=None, receipt='', value=None):
        now = self.now()
        self.calls[stage] += 1
        event = {'t': round(now, 6), 'job': job, 'tenant': job % self.s.tenants, 'stage': stage}
        self.events.append(event)
        def respond(status, scope='', delay=0, **kwargs):
            event.update(status=status, scope=scope)
            self.statuses[status] += 1
            response = self.response(status, scope, delay, **kwargs)
            event['retry_after'] = response.retry_after
            return response
        if stage == 'write' and (job not in self.reads or receipt != self.receipt(job) or value != self.value(job)*3+7):
            self.invalid_writes += 1
            return respond(422, 'payload')
        cost = getattr(self.s, stage+'_cost')
        delays = [('account', self.quotas['account'].wait(now, cost)), (stage, self.quotas[stage].wait(now, 1))]
        blocked = [(scope, delay) for scope, delay in delays if delay > 1e-8]
        if blocked:
            scope, delay = max(blocked, key=lambda row: row[1])
            return respond(429, scope, delay)
        if len(self.inflight) >= self.s.concurrency:
            return respond(429, 'concurrency', min(self.inflight)-now)
        self.quotas['account'].consume(now, cost)
        self.quotas[stage].consume(now, 1)
        self.attempts[(stage, job)] += 1
        # Transient errors before commit, after quota debit. Contract does not
        # reveal which IDs fault. The agent knows retryable 503 semantics only.
        if self.s.transient_every and (job+self.s.seed) % self.s.transient_every == 0 and self.attempts[(stage, job)] == 1:
            return respond(503, 'transient', .1)
        if stage == 'read':
            self.reads.add(job)
        else:
            identity = (stage, key) if key is not None else None
            if identity is not None and identity in self.keys and self.keys[identity] != job:
                self.invalid_writes += 1
                return respond(409, 'key_collision')
            duplicate = identity is not None and identity in self.keys
            event['deduplicated'] = duplicate
            if not duplicate:
                self.effects[job] += 1
                self.values[job] = value
                if identity is not None:
                    self.keys[identity] = job
        slow = (job+self.s.seed) % self.s.slow_every == 0
        delay = self.s.slow_service if slow else getattr(self.s, stage+'_service')
        # Keep server work alive after a client timeout in BOTH transports.
        finish = now+delay
        while finish in self.inflight:
            finish += 1e-12
        self.inflight.add(finish)
        self.peak_inflight = max(self.peak_inflight, len(self.inflight))
        async def finish_work():
            try:
                await asyncio.sleep(delay*self.s.scale)
                return respond(200, receipt=self.receipt(job) if stage=='read' else '', value=self.value(job) if stage=='read' else value)
            finally:
                self.inflight.discard(finish)
        task = asyncio.create_task(finish_work())
        self.pending.add(task)
        task.add_done_callback(self.pending.discard)
        return await asyncio.shield(task)


class Port:
    __slots__ = ('s', '_provider', '_job')
    def __init__(self, provider, job=None):
        self.s = Contract(**{key: getattr(provider.s, key) for key in Contract.__annotations__})
        self._provider, self._job = provider, job

    async def request(self, stage, job, key=None, receipt='', value=None):
        if self._job is None or job != self._job or stage not in {'read','write'}:
            raise ValueError('Use read/write for assigned job only')
        if key is not None and (not isinstance(key,str) or len(key)>100 or any(ord(c)<32 or ord(c)>126 for c in key)):
            raise ValueError('Invalid key')
        return await self._provider.request(stage, job, key, receipt, value)
