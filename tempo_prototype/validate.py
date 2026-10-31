"""Second experiment: changed policy after first experiment's failures.

The old holdout is now regression data. New cases vary quota mechanism, quota,
window, workload size, response delay and slow-response job IDs.
"""
import json
import time
from pathlib import Path
from tempo import Scenario, run, baseline
from candidates import Policy, configured, tuned


def compact(r):
    return {k:v for k,v in r.items() if k!='events'}


def correct(r):
    return r['acknowledged']==r['jobs'] and r['unique_side_effects']==r['jobs'] and r['duplicate_side_effects']==0 and not r['deadline_exceeded']


def main():
    first=json.loads(Path('first_experiment.json').read_text())
    policy=Policy(**first['best']['policy'])
    policy.timeout_growth=2.0
    regressions=[]
    for old in first['held_out']:
        r=run(Scenario(**old['scenario']),tuned,configured(policy))
        regressions.append(compact(r))
    cases=[]
    start=time.perf_counter()
    for mode in ['fixed','token']:
        for limit in [3,7,13]:
            for window in [7.,13.]:
                for jobs in [20,73]:
                    for slow in [0.1,5.8]:
                        s=Scenario(name=f'{mode}_l{limit}_w{window}_n{jobs}_s{slow}',jobs=jobs,limit=limit,window=window,service=0.07,slow_service=slow,seed=11,slow_every=5,deadline=600,quota_mode=mode)
                        before=run(s)
                        after=run(s,tuned,configured(policy))
                        cases.append({'scenario':vars(s),'baseline':compact(before),'candidate':compact(after),'pass':correct(after)})
    wall=time.perf_counter()-start
    fidelity=[]
    # Real waits are short enough to run here, but include a committed write
    # whose ACK exceeds the initial timeout, triggering a safe retry.
    s=Scenario(name='timeout_idempotency_crosscheck',jobs=4,limit=20,window=10,service=0.02,slow_service=0.3,slow_every=2,deadline=10)
    fp=Policy(rate=20,timeout=0.12,timeout_growth=2.)
    for i in range(3):
        v=run(s,tuned,configured(fp))
        r=run(s,tuned,configured(fp),virtual=False)
        fields=['acknowledged','unique_side_effects','duplicate_side_effects','requests','rate_limit_responses']
        match=all(v[k]==r[k] for k in fields)
        fidelity.append({'virtual':compact(v),'real':compact(r),'counts_match':match})
        assert match and correct(v) and correct(r),fidelity[-1]
    # Ablation: the same retry architecture without idempotency must be caught.
    bad=Policy(rate=20,timeout=0.12,timeout_growth=2.,idempotency=False)
    ablation=run(s,tuned,configured(bad))
    assert ablation['duplicate_side_effects']>0 and not correct(ablation)
    repeated=run(s,tuned,configured(fp))
    assert repeated['events']==v['events']
    report={'policy':vars(policy),'regression_passed':sum(correct(r) for r in regressions),'regression_total':len(regressions),'fresh_passed':sum(c['pass'] for c in cases),'fresh_total':len(cases),'fresh_matrix_wall_seconds':round(wall,6),'fresh_matrix_simulated_seconds':round(sum(c['candidate']['virtual_seconds']+c['baseline']['virtual_seconds'] for c in cases),6),'cases':cases,'regressions':regressions,'fidelity':fidelity,'idempotency_ablation':compact(ablation),'repeatable_events':True}
    Path('validation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ['cases','regressions','fidelity']},indent=2))
    print('Real clock:',json.dumps(fidelity[0],indent=2))


if __name__=='__main__':
    main()
