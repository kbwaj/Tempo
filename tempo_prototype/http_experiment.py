"""Real HTTP/1.1 boundary using asyncio streams; no third-party dependencies.

Deliberately narrow client: loopback HTTP, Content-Length, one POST per connection.
Not a general HTTP library. The controlled server shares Provider semantics with
simulation: this validates transport/timing fidelity, not an independent model.
"""
import asyncio
import json
import time
from dataclasses import asdict
from pathlib import Path
from datetime import datetime, timezone

from tempo import Scenario, Provider, Response, execute, run
from candidates import Policy, configured, tuned, sensible_baseline
from validate import correct


class LocalServer:
    def __init__(self, scenario, provider_factory=Provider):
        self.provider = provider_factory(scenario)
        self.tasks = set()
        self.errors = []

    async def __aenter__(self):
        self.server = await asyncio.start_server(self.handle, '127.0.0.1', 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *args):
        self.server.close()
        await self.server.wait_closed()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        try:
            header = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 2)
            lines = header.decode('ascii').split('\r\n')
            if lines[0] != 'POST /jobs HTTP/1.1':
                raise ValueError('unexpected request')
            headers = dict(line.lower().split(': ', 1) for line in lines[1:] if line)
            length = int(headers['content-length'])
            if not 0 < length <= 1024:
                raise ValueError('invalid body size')
            body = json.loads(await reader.readexactly(length))
            response = await self.provider.post(body['job'], headers.get('idempotency-key'))
            # Retry-After is an integer delta in real wall seconds. Rounding up
            # is conservative and is intentionally visible in fidelity results.
            import math
            retry = math.ceil(response.retry_after * self.provider.s.scale)
            wire = (f'HTTP/1.1 {response.status} Result\r\nContent-Length: 2\r\n'
                    f'Retry-After: {retry}\r\nConnection: close\r\n\r\n{{}}')
            writer.write(wire.encode('ascii'))
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass  # A timed-out client may already have disconnected after commit.
        except Exception as exc:
            self.errors.append(repr(exc))
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
            self.tasks.discard(task)


class HTTPProvider:
    def __init__(self, server):
        self.server = server
        self.s = server.provider.s

    def __getattr__(self, name):
        # Measurement comes from server-side effects, never client assumptions.
        return getattr(self.server.provider, name)

    async def post(self, job, idempotency_key=None):
        writer = None
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', self.server.port)
            body = json.dumps({'job': job}).encode('ascii')
            headers = (f'POST /jobs HTTP/1.1\r\nHost: localhost\r\n'
                       f'Content-Length: {len(body)}\r\nConnection: close\r\n')
            if idempotency_key is not None:
                headers += f'Idempotency-Key: {idempotency_key}\r\n'
            writer.write(headers.encode('ascii') + b'\r\n' + body)
            await writer.drain()
            lines = (await reader.readuntil(b'\r\n\r\n')).decode('ascii').split('\r\n')
            status = int(lines[0].split()[1])
            headers = dict(line.lower().split(': ', 1) for line in lines[1:] if line)
            await reader.readexactly(int(headers['content-length']))
            return Response(status, float(headers['retry-after']) / self.s.scale)
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except ConnectionError:
                    pass


def quota_baseline(provider):
    """Ordinary shared pacing at documented quota; same retry/idempotency code.

    This isolates the value of tuning from simply configuring a rate limiter.
    No assertion of superiority to production HTTP SDKs or limiters.
    """
    return configured(Policy(rate=provider.s.limit/provider.s.window,
                             timeout=2, timeout_growth=2, attempts=24))(provider)


async def http_run(scenario, client, configure):
    async with LocalServer(scenario) as server:
        result = await execute(scenario, client, configure, HTTPProvider(server))
        result['clock'] = 'real_http'
        result['server_errors'] = server.errors.copy()
        return result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('runs/http'))
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    directory = args.output / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True)
    policies = [('retry_reference', sensible_baseline, None),
                ('quota_baseline', tuned, quota_baseline),
                ('candidate', tuned, configured(Policy(rate=2, timeout=2, timeout_growth=2, attempts=24))),
                ('unsafe_no_idempotency', tuned, configured(Policy(rate=20, timeout=.12, timeout_growth=2, idempotency=False)))]
    scenarios = [Scenario(name=f'http_{mode}', jobs=8, limit=3, window=2,
                          service=.04, slow_service=.30, slow_every=3,
                          scale=.25, deadline=40, quota_mode=mode) for mode in ['fixed', 'token']]
    rows = []
    try:
        for scenario in scenarios:
            for name, client, cfg in policies:
                virtual = run(scenario, client, cfg)
                for repeat in range(args.repeats):
                    actual = asyncio.run(http_run(scenario, client, cfg))
                    fields = ['acknowledged', 'unique_side_effects', 'duplicate_side_effects', 'requests', 'rate_limit_responses']
                    row = {'scenario': asdict(scenario), 'policy': name, 'repeat': repeat,
                           'virtual': virtual, 'http': actual,
                           'count_deltas': {k: actual[k]-virtual[k] for k in fields},
                           'completion_delta_seconds': actual['virtual_seconds']-virtual['virtual_seconds'],
                           'virtual_correct': correct(virtual), 'http_correct': correct(actual)}
                    rows.append(row)
                    (directory / f'{scenario.quota_mode}-{name}-{repeat}.json').write_text(json.dumps(row, indent=2))
                    print(scenario.quota_mode, name, repeat, 'HTTP', actual['acknowledged'], actual['requests'], actual['duplicate_side_effects'], actual['virtual_seconds'], flush=True)
        failures = [r for r in rows if r['http']['server_errors'] or
                    (r['policy'] != 'unsafe_no_idempotency' and not r['http_correct']) or
                    (r['policy'] == 'unsafe_no_idempotency' and r['http']['duplicate_side_effects'] == 0)]
        report = {'scope': 'Synthetic local HTTP only; shared model; integer Retry-After causes intentional timing differences. No autonomous agent.',
                  'rows': rows, 'acceptance_failures': len(failures),
                  'exact_count_matches': sum(all(v == 0 for v in r['count_deltas'].values()) for r in rows)}
        (directory / 'report.json').write_text(json.dumps(report, indent=2))
        print('Report:', directory / 'report.json')
        if failures:
            raise SystemExit(f'{len(failures)} acceptance failures (retained)')
    except BaseException as exc:
        (directory / 'failure.json').write_text(json.dumps({'error': repr(exc), 'completed_rows': len(rows)}, indent=2))
        raise


if __name__ == '__main__':
    main()
