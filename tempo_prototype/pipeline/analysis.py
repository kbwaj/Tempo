"""Post-run comparisons; no selection or outcome filtering occurs here."""
import json
import math
import statistics
from pathlib import Path


def analyze(report,directory):
    result={'scope':'Exploratory two-arm comparison; same model and proposal counts, not equal token budgets or a causal estimate.',
            'arms':{},'feedback_vs_direct':{},'feedback_vs_hierarchical':{},'feedback_vs_original':{},'case_envelope':[]}
    for name in ['direct','feedback']:
        usage={'input_tokens':0,'output_tokens':0,'reasoning_output_tokens':0,'completed_model_calls':0}
        indices=range(0,report['rounds']) if name=='direct' else range(report['rounds'],report['rounds']*2)
        for i in indices:
            path=directory/f'agent-{i}.json'
            if not path.exists():continue
            record=json.loads(path.read_text())
            for line in record.get('stdout','').splitlines():
                try:event=json.loads(line)
                except ValueError:continue
                if event.get('type')=='turn.completed' and event.get('usage'):
                    usage['completed_model_calls']+=1
                    for key in ['input_tokens','output_tokens','reasoning_output_tokens']:
                        usage[key]+=event['usage'].get(key,0)
        result['arms'][name]=usage
    for base in ['direct','hierarchical_reference','original']:
        rows=[]
        for case in report.get('validation',[]):
            candidate,baseline=case['results']['feedback'],case['results'][base]
            if candidate.get('correct') and baseline.get('correct'):
                rows.append({'completion_ratio':candidate['completion_seconds']/max(baseline['completion_seconds'],1e-9),
                             'request_ratio':candidate['requests']/max(baseline['requests'],1)})
        key={'direct':'feedback_vs_direct','hierarchical_reference':'feedback_vs_hierarchical','original':'feedback_vs_original'}[base]
        result[key]={'paired_success_cases':len(rows),'faster_by_at_least_5pct':sum(r['completion_ratio']<=.95 for r in rows),
                     'slower_by_at_least_5pct':sum(r['completion_ratio']>=1.05 for r in rows),
                     'median_completion_ratio':statistics.median(r['completion_ratio'] for r in rows) if rows else None,
                     'median_request_ratio':statistics.median(r['request_ratio'] for r in rows) if rows else None}
    for i,case in enumerate(report.get('validation',[])):
        s=case['scenario'];row={'case':i,'name':s['name'],'jobs':s['jobs'],'concurrency':s['concurrency'],
            'account':f"{s['account_mode']} {s['account_limit']}/{s['account_window']} cost {s['write_cost']}",
            'read':f"{s['read_mode']} {s['read_limit']}/{s['read_window']}",
            'write':f"{s['write_mode']} {s['write_limit']}/{s['write_window']}",'policies':{}}
        for name,r in case['results'].items():
            row['policies'][name]={'correct':r.get('correct',False),'requests':r.get('requests'),
                                   'completion_seconds':r.get('completion_seconds'),'error':r.get('error')}
        result['case_envelope'].append(row)
    return result


def write_analysis(directory):
    report=json.loads((directory/'report.json').read_text())
    result=analyze(report,directory)
    (directory/'analysis.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    result=write_analysis(args.directory)
    print(json.dumps({k:v for k,v in result.items() if k!='case_envelope'},indent=2))
