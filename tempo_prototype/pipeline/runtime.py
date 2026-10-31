import asyncio
import json
import math
import statistics
import time
from dataclasses import asdict

from tempo import VirtualLoop
from pipeline.model import PipelineProvider, PipelineScenario, Reply, Port, SimulationQuota, ServerQuota


class Server:
    def __init__(self, scenario):
        self.provider = PipelineProvider(scenario, ServerQuota)
        self.tasks = set()
        self.errors = []

    async def __aenter__(self):
        self.server = await asyncio.start_server(self.handle, '127.0.0.1', 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *args):
        self.server.close()
        await self.server.wait_closed()
        tasks = list(self.tasks | self.provider.pending)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        try:
            lines = (await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 2)).decode('ascii').split('\r\n')
            method, path, version = lines[0].split()
            if method != 'POST' or path not in {'/read','/write'} or version != 'HTTP/1.1':
                raise ValueError('Unsupported request')
            headers = dict(line.lower().split(': ', 1) for line in lines[1:] if line)
            size = int(headers['content-length'])
            if not 0 < size < 2048:
                raise ValueError('Body too large')
            data = json.loads(await reader.readexactly(size))
            reply = await self.provider.request(path[1:], data['job'], headers.get('idempotency-key'), data.get('receipt',''), data.get('value'))
            body = json.dumps(asdict(reply)).encode()
            header = (f'HTTP/1.1 {reply.status} Result\r\nContent-Length: {len(body)}\r\n'
                      f'Retry-After: {round(reply.retry_after*self.provider.s.scale)}\r\nConnection: close\r\n\r\n')
            writer.write(header.encode()+body)
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        except Exception as exc:
            self.errors.append(repr(exc))
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
            self.tasks.discard(task)


class HTTPPort:
    def __init__(self, server):
        self.s = server.provider.s
        self.server = server

    async def request(self, stage, job, key=None, receipt='', value=None):
        writer = None
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', self.server.port)
            body = json.dumps({'job': job, 'receipt': receipt, 'value': value}).encode()
            header = f'POST /{stage} HTTP/1.1\r\nHost: localhost\r\nContent-Length: {len(body)}\r\n'
            if key is not None:
                header += f'Idempotency-Key: {key}\r\n'
            writer.write(header.encode()+b'Connection: close\r\n\r\n'+body)
            await writer.drain()
            lines = (await reader.readuntil(b'\r\n\r\n')).decode().split('\r\n')
            headers = dict(line.lower().split(': ',1) for line in lines[1:] if line)
            data = json.loads(await reader.readexactly(int(headers['content-length'])))
            data['status'] = int(lines[0].split()[1])
            data['retry_after'] = int(headers['retry-after'])/self.s.scale
            return Reply(**data)
        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except ConnectionError:
                    pass


async def execute(scenario, module, provider, request_provider):
    ctx = module.configure(Port(request_provider))
    completions = {}
    async def job(index):
        outcome = await module.integrate(Port(request_provider,index),index,ctx)
        if outcome:
            completions[index] = provider.now()*scenario.scale
        return bool(outcome)
    tasks = [asyncio.create_task(job(j)) for j in range(scenario.jobs)]
    deadline = False
    try:
        outcomes = await asyncio.wait_for(asyncio.gather(*tasks), scenario.deadline*scenario.scale)
    except asyncio.TimeoutError:
        deadline = True
        outcomes = [t.result() if t.done() and not t.cancelled() and t.exception() is None else False for t in tasks]
    elapsed = provider.now()*scenario.scale
    duplicates = sum(max(0,n-1) for n in provider.effects.values())
    payloads_valid = all(provider.values.get(j)==provider.value(j)*3+7 for j in range(scenario.jobs))
    correct = (sum(outcomes)==scenario.jobs and len(provider.effects)==scenario.jobs and not duplicates and
               not provider.invalid_writes and payloads_valid and not deadline)
    return {'correct': correct, 'acknowledged': sum(outcomes), 'jobs': scenario.jobs,
            'unique_side_effects': len(provider.effects), 'duplicate_side_effects': duplicates,
            'invalid_writes': provider.invalid_writes, 'payloads_valid': payloads_valid,
            'requests': sum(provider.calls.values()), 'requests_by_stage': dict(provider.calls),
            'statuses': dict(provider.statuses), 'peak_inflight': provider.peak_inflight,
            'completion_seconds': elapsed, 'deadline_exceeded': deadline,
            'job_completion_seconds': completions,
            'tenant_completion_seconds': {str(t): max([v for j,v in completions.items() if j % scenario.tenants==t],default=0) for t in range(scenario.tenants)},
            'events': provider.events}


async def evaluate(scenario, module, transport):
    start = time.perf_counter()
    if transport == 'http':
        async with Server(scenario) as server:
            result = await execute(scenario, module, server.provider, HTTPPort(server))
            result['server_errors'] = server.errors.copy()
            result['correct'] &= not result['server_errors']
    else:
        provider = PipelineProvider(scenario, SimulationQuota)
        result = await execute(scenario, module, provider, provider)
        result['server_errors'] = []
    result['clock'] = transport
    result['wall_seconds'] = time.perf_counter()-start
    return result


def run(scenario, module, transport='virtual'):
    loop = VirtualLoop() if transport=='virtual' else asyncio.new_event_loop()
    try:
        return loop.run_until_complete(evaluate(scenario, module, transport))
    finally:
        tasks = list(asyncio.all_tasks(loop))
        for task in tasks:
            task.cancel()
        if tasks:
            loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        loop.close()
