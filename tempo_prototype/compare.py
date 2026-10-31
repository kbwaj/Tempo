import json
import statistics
import time
from pathlib import Path
from tempo import Scenario, run
from candidates import Policy, configured, tuned, sensible_baseline
from validate import compact, correct


def main():
    robust=json.loads(Path('robust_results.json').read_text())
    policy=Policy(**robust['policy'])
    s=Scenario()
    reference=run(s,sensible_baseline)
    candidate=run(s,tuned,configured(policy))
    rows=[]
    for c in robust['fresh']:
        before=run(Scenario(**c['scenario']),sensible_baseline)
        after=c['result']
        rows.append({'scenario':c['scenario']['name'],'reference':compact(before),'candidate':after,'request_ratio':after['requests']/before['requests'],'completion_ratio':after['virtual_seconds']/before['virtual_seconds']})
    result={'reference_description':'Single retry layer + Retry-After jitter + stable idempotency key + growing timeouts; no shared admission gate. Authored baseline.', 'demo':{'reference':compact(reference),'candidate':compact(candidate)},'reference_successes':sum(correct(x['reference']) for x in rows),'candidate_successes':sum(correct(x['candidate']) for x in rows),'cases':len(rows),'median_request_ratio':statistics.median(x['request_ratio'] for x in rows),'median_completion_ratio':statistics.median(x['completion_ratio'] for x in rows),'candidate_faster_cases':sum(x['completion_ratio']<1 for x in rows),'rows':rows}
    paired=[x for x in rows if correct(x['reference']) and correct(x['candidate'])]
    result['both_complete_cases']=len(paired)
    result['paired_median_request_ratio']=statistics.median(x['request_ratio'] for x in paired)
    result['paired_median_completion_ratio']=statistics.median(x['completion_ratio'] for x in paired)
    Path('comparison.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))


if __name__=='__main__':
    main()
