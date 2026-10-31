import asyncio
import json
import math
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tempo import Scenario, VirtualLoop
from workbench.runtime import WireModel, ServerOracle, run_module, ClientPort
from workbench.worker import load_source, validate_source
from workbench.runner import evaluate, objective_score, load_manifest, make_prompt, bounded_process, propose
from tempo_scenarios import cases


class QuotaOracleTests(unittest.TestCase):
    def scripted(self, factory, mode):
        async def script():
            s = Scenario(jobs=8, limit=3, window=1.7, scale=.3,
                         service=.01, slow_service=.05, slow_every=4, quota_mode=mode)
            provider = factory(s)
            observed = []
            # Burst, retry, window transition and duplicate key all exercised.
            for index, gap in enumerate([0, 0, 0, .1, .6, .5, .7, .1, .5, .8]):
                await asyncio.sleep(gap*s.scale)
                response = await provider.post(index % 4, f'job-{index % 4}')
                observed.append((response.status, math.ceil(response.retry_after*s.scale)))
            return observed, dict(provider.effects), provider.calls, provider.rejected
        loop = VirtualLoop()
        try:
            return loop.run_until_complete(script())
        finally:
            loop.close()

    def test_independent_quota_implementations_agree(self):
        for mode in ['fixed', 'token']:
            self.assertEqual(self.scripted(WireModel, mode), self.scripted(ServerOracle, mode))

    def test_negative_duplicate_control(self):
        source = '''import asyncio

def configure(provider): return None
async def integrate(provider, job, context):
    timeout = .05
    for attempt in range(6):
        try:
            response = await asyncio.wait_for(provider.post(job), timeout*provider.s.scale)
            if response.status == 200: return True
        except asyncio.TimeoutError: timeout *= 2
    return False
'''
        result = run_module(Scenario(jobs=4, limit=100, slow_every=1, service=.01,
                                    slow_service=.3, scale=.1), load_source(source), 'virtual')
        self.assertEqual(result['acknowledged'], 4)
        self.assertGreater(result['duplicate_side_effects'], 0)

    def test_safe_timeout_retry_has_one_effect_per_job(self):
        source = '''import asyncio

def configure(provider): return None
async def integrate(provider, job, context):
    timeout = .05
    for attempt in range(6):
        try:
            response = await asyncio.wait_for(provider.post(job, f'job-{job}'), timeout*provider.s.scale)
            if response.status == 200: return True
        except asyncio.TimeoutError: timeout *= 2
    return False
'''
        result = run_module(Scenario(jobs=4, limit=100, slow_every=1, service=.01,
                                    slow_service=.3, scale=.1), load_source(source), 'virtual')
        self.assertEqual(result['acknowledged'], 4)
        self.assertEqual(result['unique_side_effects'], 4)
        self.assertEqual(result['duplicate_side_effects'], 0)
        self.assertGreater(result['requests'], 4)

    def test_deadline_is_a_failure(self):
        source = (ROOT/'workbench/reference.py').read_text()
        result = run_module(Scenario(jobs=10, limit=1, window=100, deadline=.1,
                                    service=.01, slow_service=.01), load_source(source), 'virtual')
        self.assertTrue(result['deadline_exceeded'])
        self.assertLess(result['acknowledged'], 10)


class EvaluationTests(unittest.TestCase):
    def test_acknowledgements_cannot_replace_actual_effects(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            path = directory/'liar.py'
            path.write_text('def configure(provider): return None\nasync def integrate(provider, job, ctx): return True\n')
            result = evaluate(path, vars(Scenario(jobs=3)), 'virtual', directory, 'liar')
            self.assertEqual(result['acknowledged'], 3)
            self.assertFalse(result['correct'])

    def test_subprocess_error_and_timeout_are_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            path = directory/'broken.py'
            path.write_text('def configure(provider): return None\nasync def integrate(provider, job, ctx): raise ValueError("bad patch")\n')
            result = evaluate(path, vars(Scenario(jobs=3)), 'virtual', directory, 'broken')
            self.assertFalse(result['correct'])
            self.assertIn('bad patch', result['error'])
            self.assertTrue((directory/'broken.json').exists())
            record = bounded_process([sys.executable, '-c', 'while True: pass'], input_text='', cwd=directory, timeout=.1)
            self.assertEqual(record['error'], 'wall timeout')

    def test_correctness_precedes_performance(self):
        good = {'correct': True, 'completion_seconds': 2, 'requests': 10}
        bad = {'correct': False, 'completion_seconds': .1, 'requests': 1}
        self.assertEqual(objective_score([bad], [good], 'latency', .1), math.inf)
        costly = {'correct': True, 'completion_seconds': 1, 'requests': 12}
        self.assertEqual(objective_score([costly], [good], 'latency', .1), math.inf)

    def test_validation_not_in_model_prompt(self):
        manifest, source = load_manifest(ROOT/'examples/serial_import.json')
        prompt = make_prompt(source.read_text(), manifest, [{} for _ in manifest['training']], [])
        self.assertNotIn('validation_fixed', prompt)
        self.assertNotIn('validation_token', prompt)
        self.assertNotIn('"seed": 17', prompt)
        self.assertIn('train_fixed', prompt)

    def test_model_tool_use_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory/'proposal-0.json').write_text(json.dumps({'source': 'example', 'rationale': 'example'}))
            args = SimpleNamespace(agent='codex', model=None, agent_timeout=1)
            record = {'returncode': 0, 'stdout': json.dumps({'item': {'type': 'command_execution'}}), 'stderr': ''}
            with patch('workbench.runner.bounded_process', return_value=record):
                with self.assertRaisesRegex(RuntimeError, 'used tools'):
                    propose(args, directory, 'training context', 0)
            self.assertTrue((directory/'agent-0.json').exists())

    def test_seeded_cases_are_reproducible_and_separate(self):
        self.assertEqual(cases(73, 4, 'training'), cases(73, 4, 'training'))
        self.assertNotEqual(cases(73, 4, 'training'), cases(74, 4, 'validation'))
        for seed in range(20):
            for item in cases(seed, 12, 'generated'):
                self.assertLessEqual(item['deadline']*item['scale'], 25)
                self.assertGreater(item['deadline'], item['window']*item['jobs']/item['limit'])

    def test_examples_and_import_boundary(self):
        for path in (ROOT/'examples').glob('*.json'):
            load_manifest(path)
        with self.assertRaises(ValueError):
            validate_source('import os\ndef configure(p): pass\nasync def integrate(p,j,c): pass')
        with self.assertRaises(ValueError):
            validate_source('def configure(p): return p._provider\nasync def integrate(p,j,c): pass')


class RealHTTPTests(unittest.TestCase):
    def test_http_against_independent_oracle(self):
        source = load_source((ROOT/'workbench/reference.py').read_text())
        s = Scenario(name='small_http', jobs=5, limit=2, window=.4,
                     service=.02, slow_service=.08, slow_every=2, scale=.5, deadline=5)
        virtual = run_module(s, source, 'virtual')
        actual = run_module(s, source, 'http')
        for field in ['acknowledged', 'unique_side_effects', 'duplicate_side_effects', 'requests', 'rate_limit_responses']:
            self.assertEqual(virtual[field], actual[field], field)
        self.assertFalse(actual['server_errors'])
        self.assertLess(abs(actual['completion_seconds']-virtual['completion_seconds']), .08)


if __name__ == '__main__':
    unittest.main()
