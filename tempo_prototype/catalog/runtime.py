import asyncio
import hashlib
import json
import time
from dataclasses import asdict
from tempo import VirtualLoop
from catalog.model import Provider,Port,Reply,ServerQuota,items_for


class Server:
    def __init__(self,s):
        self.provider=Provider(s,ServerQuota);self.tasks=set();self.errors=[]
    async def __aenter__(self):
        self.server=await asyncio.start_server(self.handle,'127.0.0.1',0)
        self.port=self.server.sockets[0].getsockname()[1];return self
    async def __aexit__(self,*args):
        self.server.close();await self.server.wait_closed()
        tasks=list(self.tasks|self.provider.pending)
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
    async def handle(self,reader,writer):
        task=asyncio.current_task();self.tasks.add(task)
        try:
            lines=(await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),2)).decode().split('\r\n')
            method,path,version=lines[0].split()
            if method!='POST' or path not in ('/category','/fx','/inventory','/write') or version!='HTTP/1.1':raise ValueError('Unsupported request')
            headers=dict(line.lower().split(': ',1) for line in lines[1:] if line)
            size=int(headers['content-length'])
            if not 0<size<32768:raise ValueError('Invalid body length')
            data=json.loads(await reader.readexactly(size))
            reply=await self.provider.call(path[1:],data,headers.get('idempotency-key'))
            body=json.dumps(asdict(reply)).encode()
            header=f'HTTP/1.1 {reply.status} Result\r\nContent-Length: {len(body)}\r\nRetry-After: {round(reply.retry_after*self.provider.s.scale)}\r\nConnection: close\r\n\r\n'
            writer.write(header.encode()+body);await writer.drain()
        except (ConnectionError,asyncio.IncompleteReadError):pass
        except Exception as exc:self.errors.append(repr(exc))
        finally:
            writer.close()
            try:await writer.wait_closed()
            except ConnectionError:pass
            self.tasks.discard(task)


class HTTPProvider:
    def __init__(self,server):
        self.server=server;self.s=server.provider.s;self.items=server.provider.items
    async def call(self,operation,body,key=None):
        writer=None
        try:
            reader,writer=await asyncio.open_connection('127.0.0.1',self.server.port)
            data=json.dumps(body).encode();header=f'POST /{operation} HTTP/1.1\r\nHost: localhost\r\nContent-Length: {len(data)}\r\n'
            if key is not None:header+=f'Idempotency-Key: {key}\r\n'
            writer.write(header.encode()+b'Connection: close\r\n\r\n'+data);await writer.drain()
            lines=(await reader.readuntil(b'\r\n\r\n')).decode().split('\r\n');headers=dict(line.lower().split(': ',1) for line in lines[1:] if line)
            response=json.loads(await reader.readexactly(int(headers['content-length'])))
            response['status']=int(lines[0].split()[1]);response['retry_after']=int(headers['retry-after'])/self.s.scale
            return Reply(**response)
        finally:
            if writer:
                writer.close()
                try:await writer.wait_closed()
                except ConnectionError:pass


def digest(outputs):
    return hashlib.sha256(json.dumps(outputs,sort_keys=True,separators=(',',':')).encode()).hexdigest()


async def execute(s,module,provider,transport_provider):
    ctx=module.configure(Port(transport_provider));tasks=[];completion={}
    async def worker(j):
        result=await module.integrate(Port(transport_provider,j),j,ctx)
        if result:completion[j]=provider.now()*s.scale
        return bool(result)
    tasks=[asyncio.create_task(worker(j)) for j in range(s.jobs)]
    deadline=False
    try:outcomes=await asyncio.wait_for(asyncio.gather(*tasks),s.deadline*s.scale)
    except asyncio.TimeoutError:
        deadline=True;outcomes=[t.result() if t.done() and not t.cancelled() and t.exception() is None else False for t in tasks]
    outputs=[provider.outputs.get(j) for j in range(s.jobs)];expected=[provider.expected(item) for item in provider.items]
    duplicates=sum(max(0,n-1) for n in provider.effects.values())
    result={'correct':sum(outcomes)==s.jobs and outputs==expected and not duplicates and not provider.invalid and not deadline,
        'jobs':s.jobs,'acknowledged':sum(outcomes),'requests':sum(provider.calls.values()),'requests_by_operation':dict(provider.calls),
        'duplicate_side_effects':duplicates,'invalid_outputs':provider.invalid,'outputs_match':outputs==expected,
        'output_sha256':digest(outputs),'expected_sha256':digest(expected),'completion_seconds':provider.now()*s.scale,
        'rate_limit_responses':provider.throttled,'transient_responses':provider.transient,'peak_inflight':provider.peak_inflight,
        'deadline_exceeded':deadline,'events':provider.events,'outputs':outputs,'job_completion_seconds':completion}
    return result


async def evaluate(s,module,transport):
    start=time.perf_counter()
    if transport=='http':
        async with Server(s) as server:
            result=await execute(s,module,server.provider,HTTPProvider(server));result['server_errors']=server.errors.copy()
    else:
        provider=Provider(s);result=await execute(s,module,provider,provider);result['server_errors']=[]
    result['correct'] &= not result['server_errors'];result['clock']=transport;result['wall_seconds']=time.perf_counter()-start
    return result


def run(s,module,transport='virtual'):
    loop=VirtualLoop() if transport=='virtual' else asyncio.new_event_loop()
    try:return loop.run_until_complete(evaluate(s,module,transport))
    finally:
        pending=list(asyncio.all_tasks(loop))
        for t in pending:t.cancel()
        if pending:loop.run_until_complete(asyncio.gather(*pending,return_exceptions=True))
        loop.close()
