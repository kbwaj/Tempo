"""Reproduce and reduce an HTTP-observed performance counterexample.

This is a post-hoc regression diagnosis, explicitly not a fresh blind search.
"""
import argparse
import hashlib
import html
import json
import statistics
from dataclasses import asdict,replace
from datetime import datetime,timezone
from pathlib import Path
from pipeline.model import PipelineScenario
from pipeline.runner import evaluate
from workbench.runner import save


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--case',type=int,required=True)
    p.add_argument('--policy',default='feedback')
    p.add_argument('--reference',default='hierarchical_reference')
    p.add_argument('--max-latency-ratio',type=float,default=1.1)
    p.add_argument('--http-repeats',type=int,default=3)
    p.add_argument('--minimize',action='store_true')
    args=p.parse_args()
    if not 0<=args.case or not 1<=args.http_repeats<=5 or not 1<=args.max_latency_ratio<=5:p.error('Invalid bounds')
    origin=json.loads((args.run/'report.json').read_text())
    scenario=PipelineScenario(**origin['validation'][args.case]['scenario'])
    source=args.run/(args.policy+'-selected.py' if args.policy in {'direct','feedback'} else args.policy+'.py')
    baseline=args.run/(args.reference+'-selected.py' if args.reference in {'direct','feedback'} else args.reference+'.py')
    directory=(Path('runs/falsify')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')).resolve();directory.mkdir(parents=True)
    patch=directory/'patch.py';patch.write_text(source.read_text())
    reference=directory/'reference.py';reference.write_text(baseline.read_text())
    report={'name':'HTTP-derived integration counterexample','status':'running','agent':'diagnostic',
            'origin_run':str(args.run),'origin_case':args.case,'search_provenance':'Post-hoc replay of previously observed HTTP failure; not blind search.',
            'bound':args.max_latency_ratio,'source_sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),
            'http':[],'reductions':[],'scenario':asdict(scenario)}
    save(directory/'report.json',report)
    def confirm(s,repeats,label):
        measured={}
        for i in range(repeats):
            for name,path in [('patch',patch),('reference',reference)][::1 if i%2==0 else -1]:
                print(label,'repeat',i+1,name,'jobs',s.jobs,flush=True)
                r=evaluate(path,s,'http',directory,f'{label}-{i}-{name}')
                report['http'].append({'label':label,'repeat':i,'policy':name,'scenario':asdict(s),'result':r})
                measured.setdefault(name,[]).append(r)
        correct={name:all(r.get('correct') for r in rows) for name,rows in measured.items()}
        result={'all_correct':correct,'jobs':s.jobs}
        if all(correct.values()):
            times={name:statistics.median(r['completion_seconds'] for r in rows) for name,rows in measured.items()}
            result.update(medians=times,ratio=times['patch']/times['reference'],violation=times['patch']>times['reference']*args.max_latency_ratio and times['patch']-times['reference']>.02)
        else: result['violation']=not correct['patch']
        save(directory/'report.json',report)
        return result
    initial=confirm(scenario,args.http_repeats,'initial')
    report['initial_confirmation']=initial
    final_s=scenario
    final=initial
    if initial['violation'] and args.minimize:
        for jobs in range(2,scenario.jobs):
            s=replace(scenario,jobs=jobs,name=scenario.name+f'_jobs{jobs}')
            smoke=confirm(s,1,f'reduce-{jobs}')
            record={'smoke':smoke}
            report['reductions'].append(record)
            if smoke['violation']:
                # A noisy one-shot reduction cannot replace an already
                # confirmed larger counterexample. Validate it before accepting.
                repeated=confirm(s,args.http_repeats,f'confirm-reduction-{jobs}')
                record['confirmation']=repeated
                if repeated['violation']:
                    final_s,final=s,repeated
                    break
        if final_s==scenario:
            final=confirm(scenario,args.http_repeats,'final-original')
    report['final_confirmation']=final
    report['counterexample']=asdict(final_s)
    save(directory/'counterexample.json',asdict(final_s))
    report['status']='http_confirmed_counterexample' if final['violation'] else 'not_reproduced'
    save(directory/'report.json',report)
    esc=lambda x:html.escape(str(x))
    body=f'''<h1>Tempo · HTTP-derived counterexample</h1><p><b>{esc(report['status'])}</b></p><p>This is a post-hoc regression replay of case {args.case} from an earlier experiment, not a fresh blind search. No model was called and no source was changed.</p><h2>Declared contract</h2><p>The patch must remain correct and complete within {args.max_latency_ratio:g}× the hierarchical reference, with at least a 20ms difference to flag a performance violation.</p><h2>Repeated confirmation</h2><pre>{esc(json.dumps(final,indent=2))}</pre><h2>Retained counterexample scenario</h2><pre>{esc(json.dumps(asdict(final_s),indent=2))}</pre><p>Reduction screens use one repetition per job count; a screen hit must pass {args.http_repeats} repetitions before replacing the confirmed larger case. This is a heuristic reduction, not a proof of global minimality. Socket timing and scheduling remain sources of variation.</p><p><a href="report.json">Every HTTP run and reduction</a> · <a href="counterexample.json">Executable scenario parameters</a> · <a href="patch.py">Frozen patch</a> · <a href="reference.py">Reference</a></p>'''
    (directory/'index.html').write_text('<!doctype html><html><head><meta charset="utf-8"><title>Tempo HTTP counterexample</title><style>body{background:#0b1420;color:#edf4ff;font:16px/1.7 system-ui;max-width:1000px;margin:50px auto;padding:20px}p{color:#b6c9df}pre{background:#142339;padding:24px;border-radius:12px}a{color:#8bf5cc}</style></head><body>'+body+'</body></html>')
    print('HTTP regression result:',report['status'],directory/'index.html',flush=True)


if __name__=='__main__':main()
