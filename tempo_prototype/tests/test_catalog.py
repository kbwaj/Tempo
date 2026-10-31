import asyncio
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tempo import VirtualLoop
from catalog.model import Scenario,Provider,Quota,ServerQuota
from catalog.runtime import run
from catalog.optimality import lower_bound
from catalog.runner import corpus,protected_helpers
from workbench.worker import load_source


class CatalogTests(unittest.TestCase):
    def test_manual_optimization_hits_bound_and_preserves_every_output(self):
        s=Scenario(transient_every=0)
        before=run(s,load_source((ROOT/'catalog/baseline.py').read_text()))
        after=run(s,load_source((ROOT/'catalog/manual_reference.py').read_text()))
        self.assertTrue(before['correct']);self.assertTrue(after['correct'])
        self.assertEqual(before['output_sha256'],after['output_sha256'])
        self.assertEqual(before['requests'],192)
        self.assertEqual(after['requests'],lower_bound(s)['minimum_total_requests'])
        self.assertEqual(after['requests'],108)
        self.assertEqual(after['requests_by_operation']['inventory'],s.jobs)
        self.assertEqual(after['requests_by_operation']['write'],s.jobs)

    def test_verified_ai_source_hits_bound(self):
        s=Scenario(transient_every=0)
        result=run(s,load_source((ROOT/'catalog/optimized.py').read_text()))
        self.assertTrue(result['correct'])
        self.assertEqual(result['requests'],lower_bound(s)['minimum_total_requests'])
        self.assertEqual(result['output_sha256'],result['expected_sha256'])

    def test_no_sharing_contract_preserves_correctness_without_promising_gain(self):
        s=Scenario(jobs=12,tenants=12,snapshots=1,categories=12,currencies=12,transient_every=0)
        result=run(s,load_source((ROOT/'catalog/manual_reference.py').read_text()))
        self.assertTrue(result['correct'])
        self.assertEqual(lower_bound(s)['minimum_total_requests'],4*s.jobs)
        self.assertEqual(result['requests'],4*s.jobs)

    def test_cross_tenant_receipts_and_skipped_inventory_are_rejected(self):
        async def case():
            s=Scenario(jobs=2,tenants=2,snapshots=1,limit=100,concurrency=100,transient_every=0)
            p=Provider(s);item=p.items[1]
            wrong=(await p.call('category',{'tenant':0,'snapshot':item.snapshot,'keys':[item.category]})).data[item.category]
            fx=(await p.call('fx',{'tenant':item.tenant,'snapshot':item.snapshot,'keys':[item.currency]})).data[item.currency]
            stock=(await p.call('inventory',{'item':1})).data
            response=await p.call('write',{'item':1,'payload':p.expected(item),'receipts':[wrong['receipt'],fx['receipt'],stock['receipt']]},'write-1')
            self.assertEqual(response.status,422)
            category=(await p.call('category',{'tenant':item.tenant,'snapshot':item.snapshot,'keys':[item.category]})).data[item.category]
            response=await p.call('write',{'item':1,'payload':p.expected(item),'receipts':[category['receipt'],fx['receipt'],'invented-stock']},'write-1')
            self.assertEqual(response.status,422)
            self.assertEqual(len(p.effects),0)
        loop=VirtualLoop()
        try:loop.run_until_complete(case())
        finally:loop.close()

    def test_independent_quota_algorithms(self):
        for mode in ('token','fixed'):
            s=Scenario(limit=4,window=.7,quota_mode=mode)
            a,b=Quota(s),ServerQuota(s)
            for i in range(200):
                t=i*.031
                self.assertAlmostEqual(a.acquire(t),b.acquire(t),places=7)

    def test_manual_reference_on_seeded_contracts(self):
        source=load_source((ROOT/'catalog/manual_reference.py').read_text())
        for s in corpus(93017,8):
            with self.subTest(s.name):self.assertTrue(run(s,source)['correct'])

    def test_transport_helpers_identical(self):
        self.assertEqual(protected_helpers((ROOT/'catalog/baseline.py').read_text()),protected_helpers((ROOT/'catalog/manual_reference.py').read_text()))

    def test_real_http_output_equality(self):
        s=Scenario(jobs=12,tenants=2,snapshots=1,categories=1,currencies=1,transient_every=0,scale=.1)
        source=load_source((ROOT/'catalog/manual_reference.py').read_text())
        virtual,actual=run(s,source),run(s,source,'http')
        self.assertTrue(actual['correct'])
        self.assertEqual(actual['output_sha256'],virtual['output_sha256'])
        self.assertEqual(actual['requests'],virtual['requests'])
        self.assertEqual(actual['duplicate_side_effects'],0)


if __name__=='__main__':unittest.main()
