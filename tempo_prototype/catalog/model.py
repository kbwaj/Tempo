import asyncio
import collections
import hashlib
import json
import math
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Scenario:
    name: str = 'Catalog sync · 48 products'
    jobs: int = 48
    tenants: int = 3
    snapshots: int = 2
    categories: int = 2
    currencies: int = 2
    limit: int = 10
    window: float = 1.0
    quota_mode: str = 'token'
    concurrency: int = 6
    batch_size: int = 8
    service: float = .045
    slow_service: float = .16
    slow_every: int = 11
    transient_every: int = 29
    scale: float = .18
    deadline: float = 100
    seed: int = 731


@dataclass(frozen=True)
class Item:
    id: int
    tenant: int
    snapshot: str
    category: str
    currency: str
    price_cents: int


def items_for(s):
    items=[]
    for j in range(s.jobs):
        group=j//(s.tenants*s.snapshots)
        items.append(Item(j,j%s.tenants,f'v{(j//s.tenants)%s.snapshots}',
                          f'category-{group%s.categories}',f'currency-{(group//s.categories)%s.currencies}',
                          1000+(j*317+s.seed)%9000))
    return tuple(items)


@dataclass(frozen=True)
class Contract:
    limit: int
    window: float
    quota_mode: str
    concurrency: int
    batch_size: int
    service: float
    slow_service: float
    scale: float
    deadline: float
    immutable_snapshot_lookups: bool = True
    inventory_cacheable: bool = False


@dataclass(frozen=True)
class Reply:
    status: int
    retry_after: float = 0
    data: object = None


class Quota:
    def __init__(self,s):
        self.s=s;self.tokens=float(s.limit);self.updated=0.;self.index=-1;self.used=0
    def acquire(self,now):
        if self.s.quota_mode=='token':
            self.tokens=min(self.s.limit,self.tokens+(now-self.updated)*self.s.limit/self.s.window);self.updated=now
            if self.tokens<1-1e-8:return (1-self.tokens)*self.s.window/self.s.limit
            self.tokens-=1;return 0
        index=math.floor((now+1e-9)/self.s.window)
        if index!=self.index:self.index,self.used=index,0
        if self.used>=self.s.limit:return (index+1)*self.s.window-now
        self.used+=1;return 0


class ServerQuota:
    """Independent debt/expiry algorithm; business fixture remains shared."""
    def __init__(self,s):
        self.s=s;self.debt=0.;self.expires=s.window;self.remaining=s.limit
    def acquire(self,now):
        if self.s.quota_mode=='token':
            interval=self.s.window/self.s.limit
            earliest=self.debt-(self.s.limit-1)*interval
            if now<earliest-1e-8:return earliest-now
            self.debt=max(now,self.debt)+interval;return 0
        if now>=self.expires:self.expires=(math.floor(now/self.s.window)+1)*self.s.window;self.remaining=self.s.limit
        if not self.remaining:return self.expires-now
        self.remaining-=1;return 0


class Provider:
    def __init__(self,s,quota_cls=Quota):
        self.s=s;self.items=items_for(s);self.loop=asyncio.get_running_loop();self.origin=self.loop.time();self.quota=quota_cls(s)
        self.calls=collections.Counter();self.events=[];self.effects=collections.Counter();self.outputs={};self.keys={}
        self.reads={};self.inventory_reads=collections.Counter();self.attempts=collections.Counter();self.pending=set();self.inflight=0;self.peak_inflight=0
        self.invalid=0;self.throttled=0;self.transient=0
    def now(self):return (self.loop.time()-self.origin)/self.s.scale
    def proof(self,kind,tenant,snapshot,key,value):
        text=f'{self.s.seed}:{kind}:{tenant}:{snapshot}:{key}:{value}'
        return hashlib.sha256(text.encode()).hexdigest()[:24]
    def lookup_value(self,kind,tenant,snapshot,key):
        n=sum(ord(c) for c in key+snapshot)
        return f'{tenant}:{snapshot}:{key}:{(self.s.seed+n)%97}' if kind=='category' else 7000+(self.s.seed*31+tenant*173+n*53)%9000
    def expected(self,item,inventory=None):
        label=self.lookup_value('category',item.tenant,item.snapshot,item.category)
        rate=self.lookup_value('fx',item.tenant,item.snapshot,item.currency)
        stock=(self.s.seed+item.id*7)%101 if inventory is None else inventory
        return {'id':item.id,'tenant':item.tenant,'snapshot':item.snapshot,'category_label':label,
                'converted_cents':(item.price_cents*rate+5000)//10000,'stock':stock}
    def response(self,status,data=None,delay=0):return Reply(status,math.ceil(max(0,delay)*self.s.scale)/self.s.scale,data)
    async def call(self,operation,body,key=None):
        now=self.now();self.calls[operation]+=1
        event={'t':round(now,6),'operation':operation,'status':None};self.events.append(event)
        event['item']=body.get('item');event['tenant']=body.get('tenant');event['snapshot']=body.get('snapshot');event['keys']=body.get('keys')
        def reply(status,data=None,delay=0):
            event['status']=status;return self.response(status,data,delay)
        if self.inflight>=self.s.concurrency:
            self.throttled+=1;return reply(429,delay=self.s.service)
        delay=self.quota.acquire(now)
        if delay>1e-8:
            self.throttled+=1;return reply(429,delay=delay)
        signature=json.dumps([operation,body],sort_keys=True)
        self.attempts[signature]+=1
        # At most one transient per request identity, before effects but after quota debit.
        marker=int(hashlib.sha256((str(self.s.seed)+signature).encode()).hexdigest()[:8],16)
        if self.s.transient_every and marker%self.s.transient_every==0 and self.attempts[signature]==1:
            self.transient+=1;return reply(503,delay=.05)
        if operation in ('category','fx'):
            tenant,snapshot,keys=body['tenant'],body['snapshot'],body['keys']
            if type(tenant) is not int or not 0<=tenant<self.s.tenants or not isinstance(snapshot,str) or not 1<=len(keys)<=self.s.batch_size:
                self.invalid+=1;return reply(422)
            data={}
            for k in keys:
                value=self.lookup_value(operation,tenant,snapshot,k)
                receipt=self.proof(operation,tenant,snapshot,k,value)
                data[k]={'value':value,'receipt':receipt};self.reads[receipt]=(operation,tenant,snapshot,k,value)
        elif operation=='inventory':
            j=body['item'];item=self.items[j]
            self.inventory_reads[j]+=1
            # This endpoint is explicitly NOT snapshot-cacheable. It belongs to
            # the assigned item, and the proof cannot be shared between products.
            value=(self.s.seed+j*7)%101
            receipt=self.proof('inventory',item.tenant,item.snapshot,str(j),value)
            self.reads[receipt]=('inventory',item.tenant,item.snapshot,str(j),value)
            data={'value':value,'receipt':receipt}
        elif operation=='write':
            j=body['item'];item=self.items[j];payload=body['payload'];receipts=body['receipts']
            expected_receipts=[self.proof('category',item.tenant,item.snapshot,item.category,self.lookup_value('category',item.tenant,item.snapshot,item.category)),
                self.proof('fx',item.tenant,item.snapshot,item.currency,self.lookup_value('fx',item.tenant,item.snapshot,item.currency)),
                self.proof('inventory',item.tenant,item.snapshot,str(j),(self.s.seed+j*7)%101)]
            if payload!=self.expected(item) or receipts!=expected_receipts or any(r not in self.reads for r in receipts):
                self.invalid+=1;return reply(422)
            if key is not None and key in self.keys and self.keys[key]!=j:
                self.invalid+=1;return reply(409)
            duplicate=key is not None and key in self.keys
            if not duplicate:
                self.effects[j]+=1;self.outputs[j]=payload
                if key is not None:self.keys[key]=j
            event['deduplicated']=duplicate;data={'saved':j}
        else:
            self.invalid+=1;return reply(400)
        self.inflight+=1;self.peak_inflight=max(self.peak_inflight,self.inflight)
        service=self.s.slow_service if marker%self.s.slow_every==0 else self.s.service
        async def finish():
            try:
                await asyncio.sleep(service*self.s.scale)
                return reply(200,data)
            finally:self.inflight-=1
        task=asyncio.create_task(finish());self.pending.add(task);task.add_done_callback(self.pending.discard)
        return await asyncio.shield(task)


class Port:
    __slots__=('s','items','_provider','_job')
    def __init__(self,provider,job=None):
        s=provider.s
        self.s=Contract(**{name:getattr(s,name) for name in Contract.__annotations__ if name not in ('immutable_snapshot_lookups','inventory_cacheable')})
        self.items=provider.items;self._provider=provider;self._job=job
    async def lookup(self,kind,tenant,snapshot,keys):
        if kind not in ('category','fx') or not isinstance(keys,(list,tuple)) or any(not isinstance(k,str) for k in keys):raise ValueError('Invalid lookup')
        return await self._provider.call(kind,{'tenant':tenant,'snapshot':snapshot,'keys':list(keys)})
    async def inventory(self,item):
        if self._job is None or item!=self._job:raise ValueError('Inventory must belong to assigned item')
        return await self._provider.call('inventory',{'item':item})
    async def write(self,item,payload,receipts,key):
        if self._job is None or item!=self._job:raise ValueError('Write must belong to assigned item')
        if not isinstance(key,str) or len(key)>100 or any(ord(c)<32 or ord(c)>126 for c in key):raise ValueError('Invalid key')
        return await self._provider.call('write',{'item':item,'payload':payload,'receipts':receipts},key)
