import asyncio
import random
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tempo import VirtualLoop
from pipeline.model import PipelineScenario,PipelineProvider,SimulationQuota,ServerQuota
from pipeline.runtime import run
from pipeline.runner import generate
from workbench.worker import load_source


class QuotaTests(unittest.TestCase):
    def test_weighted_independent_quota_engines(self):
        for mode in ['fixed','token']:
            for capacity in [3,7,11]:
                a,b=SimulationQuota(capacity,1.7,mode),ServerQuota(capacity,1.7,mode)
                rng=random.Random(73)
                now=0
                for _ in range(100):
                    now+=rng.uniform(.001,.4)
                    cost=rng.randint(1,3)
                    x,y=a.wait(now,cost),b.wait(now,cost)
                    self.assertAlmostEqual(x,y,places=7)
                    if x<1e-8:
                        a.consume(now,cost);b.consume(now,cost)

    def test_cancelled_request_does_not_free_server_slot(self):
        async def case():
            s=PipelineScenario(jobs=2,concurrency=1,slow_every=1,slow_service=.3,transient_every=0,scale=.1)
            p=PipelineProvider(s)
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(p.request('read',0),.01*s.scale)
            self.assertEqual(len(p.inflight),1)
            response=await p.request('read',1)
            self.assertEqual(response.status,429)
            self.assertEqual(response.scope,'concurrency')
            await asyncio.sleep(.31*s.scale)
            self.assertEqual(len(p.inflight),0)
        loop=VirtualLoop()
        try: loop.run_until_complete(case())
        finally: loop.close()

    def test_receipt_transform_and_key_collisions_are_checked(self):
        async def case():
            s=PipelineScenario(jobs=2,account_limit=100,read_limit=100,write_limit=100,concurrency=10,transient_every=0,scale=.1)
            p=PipelineProvider(s)
            invalid=await p.request('write',0,key='x',receipt='fabricated',value=3)
            self.assertEqual(invalid.status,422)
            a=await p.request('read',0)
            response=await p.request('write',0,key='x',receipt=a.receipt,value=a.value*3+7)
            self.assertEqual(response.status,200)
            again=await p.request('write',0,key='x',receipt=a.receipt,value=a.value*3+7)
            self.assertEqual(again.status,200)
            self.assertEqual(p.effects[0],1)
            b=await p.request('read',1)
            collision=await p.request('write',1,key='x',receipt=b.receipt,value=b.value*3+7)
            self.assertEqual(collision.status,409)
            self.assertNotIn(1,p.effects)
        loop=VirtualLoop()
        try: loop.run_until_complete(case())
        finally: loop.close()


class IntegrationTests(unittest.TestCase):
    def test_reference_on_generated_cases(self):
        source=load_source((ROOT/'pipeline/reference.py').read_text())
        for s in generate(73119,12,'test'):
            with self.subTest(s.name):
                result=run(s,source)
                self.assertTrue(result['correct'],{k:v for k,v in result.items() if k!='events'})
                self.assertLessEqual(result['peak_inflight'],s.concurrency)

    def test_wrong_transform_and_fake_success_fail(self):
        source=(ROOT/'pipeline/reference.py').read_text().replace('read.value*3+7','read.value*3+8')
        result=run(PipelineScenario(jobs=3,transient_every=0),load_source(source))
        self.assertFalse(result['correct'])
        self.assertGreater(result['invalid_writes'],0)
        liar='def configure(p): return None\nasync def integrate(p,j,c): return True\n'
        result=run(PipelineScenario(jobs=3),load_source(liar))
        self.assertFalse(result['correct'])

    def ambiguous_source(self, safe):
        key="f'{stage}-{job}'" if safe else 'None'
        return """import asyncio

def configure(provider): return None
async def integrate(provider,job,ctx):
    async def send(stage,receipt='',value=None):
        timeout=.05
        for attempt in range(6):
            try:
                r=await asyncio.wait_for(provider.request(stage,job,key=KEY,receipt=receipt,value=value),timeout*provider.s.scale)
                if r.status==200:return r
                await asyncio.sleep(r.retry_after*provider.s.scale)
            except asyncio.TimeoutError:timeout*=2
        return None
    read=await send('read')
    if read is None:return False
    return await send('write',read.receipt,read.value*3+7) is not None
""".replace('KEY',key)

    def test_ambiguous_write_retries_preserve_one_effect(self):
        s=PipelineScenario(jobs=2,account_limit=100,read_limit=100,write_limit=100,
            concurrency=100,slow_every=1,slow_service=.3,transient_every=0,scale=.1)
        source=load_source(self.ambiguous_source(True))
        virtual,actual=run(s,source),run(s,source,'http')
        for result in [virtual,actual]:
            self.assertTrue(result['correct'])
            self.assertGreater(result['requests'],s.jobs*2)
            self.assertEqual(result['duplicate_side_effects'],0)

    def test_ambiguous_write_without_key_is_caught(self):
        s=PipelineScenario(jobs=2,account_limit=100,read_limit=100,write_limit=100,
            concurrency=100,slow_every=1,slow_service=.3,transient_every=0,scale=.1)
        result=run(s,load_source(self.ambiguous_source(False)))
        self.assertFalse(result['correct'])
        self.assertGreater(result['duplicate_side_effects'],0)

    def test_http_uses_separate_quota_engine(self):
        s=PipelineScenario(jobs=5,account_limit=6,account_window=.6,read_limit=4,read_window=.4,
            write_limit=2,write_window=.5,write_mode='token',concurrency=3,slow_service=.12,
            transient_every=0,scale=.3)
        source=load_source((ROOT/'pipeline/reference.py').read_text())
        virtual,actual=run(s,source),run(s,source,'http')
        self.assertTrue(actual['correct'],actual)
        for field in ['acknowledged','unique_side_effects','duplicate_side_effects','invalid_writes','requests']:
            self.assertEqual(virtual[field],actual[field],field)
        self.assertLess(abs(virtual['completion_seconds']-actual['completion_seconds']),.12)


if __name__=='__main__': unittest.main()
