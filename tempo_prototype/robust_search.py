"""Choose a policy over a family of possible providers, not one happy path.

The corpus used here has already been inspected by the assistant: it is a
regression corpus. The final independent cases are generated below.
"""
import json
import time
import random
import statistics
from pathlib import Path
from tempo import Scenario, run
from candidates import Policy, configured, tuned
from validate import correct, compact


def main():
    previous=json.loads(Path('validation.json').read_text())
    # Small representative search set, chosen after inspecting first failures.
    train=[Scenario(name=f'train_{m}_{n}',quota_mode=m,jobs=n,limit=3,window=13,service=.07,slow_service=5.8,seed=11,slow_every=5,deadline=600) for m in ['token','fixed'] for n in [20,73]]
    records=[]
    started=time.perf_counter()
    for rate in [.3,.5,.8,1.2,2.0]:
        for attempts in [12,24]:
            p=Policy(rate=rate,timeout=2,timeout_growth=2,attempts=attempts)
            rr=[run(s,tuned,configured(p)) for s in train]
            records.append({'policy':vars(p),'failures':sum(not correct(r) for r in rr),'worst_completion':max(r['virtual_seconds'] for r in rr),'total_requests':sum(r['requests'] for r in rr),'results':[compact(r) for r in rr]})
    best=min(records,key=lambda x:(x['failures'],x['worst_completion'],x['total_requests']))
    p=Policy(**best['policy'])
    search_wall=time.perf_counter()-started
    regression=[run(Scenario(**c['scenario']),tuned,configured(p)) for c in previous['cases']]
    rng=random.Random(90173)
    fresh=[]
    start=time.perf_counter()
    for i in range(60):
        s=Scenario(name=f'fresh_{i}',jobs=rng.randint(9,85),limit=rng.randint(3,17),window=rng.uniform(5,15),service=rng.uniform(.03,.3),slow_service=rng.uniform(.5,7),slow_every=rng.randint(4,11),seed=rng.randint(0,99),quota_mode=rng.choice(['fixed','token']),deadline=600)
        r=run(s,tuned,configured(p))
        fresh.append({'scenario':vars(s),'result':compact(r),'pass':correct(r)})
    fresh_wall=time.perf_counter()-start
    # An infeasible scenario remains a visible counterexample, not a passing run.
    impossible=Scenario(name='infeasible_deadline',jobs=100,limit=1,window=60,deadline=10)
    negative=run(impossible,tuned,configured(p))
    assert not correct(negative) and negative['deadline_exceeded']
    demo=run(Scenario(),tuned,configured(p))
    report={'policy':vars(p),'search_candidates':len(records),'search_wall_seconds':round(search_wall,6),'search_total_virtual_seconds':sum(r['virtual_seconds'] for x in records for r in x['results']),'training':records,'regression_passed':sum(correct(r) for r in regression),'regression_total':len(regression),'fresh_passed':sum(c['pass'] for c in fresh),'fresh_total':len(fresh),'fresh_wall_seconds':round(fresh_wall,6),'fresh_total_virtual_seconds':round(sum(c['result']['virtual_seconds'] for c in fresh),6),'fresh':fresh,'negative_control':compact(negative),'demo':compact(demo)}
    Path('robust_results.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ['training','fresh']},indent=2))


if __name__=='__main__':
    main()
