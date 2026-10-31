import json
import statistics
import time
from pathlib import Path
from tempo import Scenario, run, baseline
from candidates import Policy, configured, tuned, retry_after_only


def compact(r):
    return {k:v for k,v in r.items() if k != 'events'}


def score(r):
    # Correctness first, latency and request count only among correct policies.
    return (r['jobs']-r['acknowledged'], r['duplicate_side_effects'], r['virtual_seconds'], r['requests'])


def main():
    base_s = Scenario()
    baseline_r = run(base_s)
    local_r = run(base_s, retry_after_only)
    # Deterministic parameter search over agent-authored policy architecture.
    # This is a sweep, not an autonomous LLM or learned optimizer.
    candidates = []
    start = time.perf_counter()
    for rate in [0.4, 0.6, 0.8, 1.2, 2.0]:
        for timeout in [0.8, 2.0, 4.0]:
            policy = Policy(rate=rate, timeout=timeout)
            r = run(base_s, tuned, configured(policy))
            candidates.append({'policy':vars(policy), 'result':compact(r)})
    best = min(candidates, key=lambda c:score(c['result']))
    policy = Policy(**best['policy'])
    search_wall = time.perf_counter()-start
    final_r = run(base_s, tuned, configured(policy))
    # Held-out conditions: not used to choose the policy.
    held = []
    for jobs in [12, 48, 96]:
        for limit in [4, 8, 16]:
            for slow in [1.4, 3.5]:
                s = Scenario(name=f'n{jobs}_limit{limit}_slow{slow}', jobs=jobs, limit=limit, slow_service=slow, deadline=600, seed=3)
                old = run(s)
                new = run(s, tuned, configured(policy))
                held.append({'scenario':vars(s), 'baseline':compact(old), 'candidate':compact(new)})
    # Differential REAL clock comparison on a short test; same application,
    # same model, only event loop clock differs. Compare outcomes, not exact
    # timestamps, since the real scheduler introduces jitter.
    fidelity = []
    fs = Scenario(name='real_clock_crosscheck', jobs=6, limit=3, window=0.6, service=0.02, slow_service=0.03, deadline=10)
    for name, client, cfg in [('baseline',baseline,None), ('candidate',tuned,configured(Policy(rate=5.0,timeout=2.0)))]:
        v = run(fs,client,cfg,virtual=True)
        real = run(fs,client,cfg,virtual=False)
        fields = ['acknowledged','unique_side_effects','duplicate_side_effects','requests','rate_limit_responses']
        matches = all(v[k] == real[k] for k in fields)
        fidelity.append({'policy':name,'virtual':compact(v),'real':compact(real),'counts_match':matches})
        assert matches, fidelity[-1]
    # Repeatability: event sequences must be identical on the same seed.
    repeat = run(base_s,tuned,configured(policy))
    assert final_r['events'] == repeat['events']
    assert final_r['acknowledged']==base_s.jobs and final_r['duplicate_side_effects']==0
    report = {
        'scope':'Synthetic provider; authored workload; real Python coroutine execution; no live API traffic.',
        'agent_provenance':'Assistant inspected baseline, authored policy candidates, then ran bounded deterministic sweep. No autonomous LLM API inside this artifact.',
        'baseline':compact(baseline_r), 'local_fix':compact(local_r),
        'best':best, 'search_wall_seconds':round(search_wall,6),
        'search_simulated_seconds':round(sum(c['result']['virtual_seconds'] for c in candidates),6),
        'candidate_count':len(candidates), 'candidates':candidates,
        'held_out':held, 'fidelity':fidelity, 'deterministic_replay':True,
        'held_out_complete_without_duplicates':sum(x['candidate']['acknowledged']==x['candidate']['jobs'] and x['candidate']['duplicate_side_effects']==0 for x in held),
    }
    Path('results.json').write_text(json.dumps(report,indent=2))
    Path('demo_events.json').write_text(json.dumps({'baseline':baseline_r['events'],'local_fix':local_r['events'],'candidate':final_r['events']},indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ['candidates','held_out','fidelity']},indent=2))
    print('Real-clock crosscheck:',json.dumps(fidelity,indent=2))


if __name__=='__main__':
    main()
