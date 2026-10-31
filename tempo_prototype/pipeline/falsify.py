"""Search for a counterexample to a declared patch performance contract.

Evaluates every seeded case, retains all outcomes, then minimizes job count of
first violating case. No model call and no patch revision occurs here.
"""
import argparse
import hashlib
import html
import json
import statistics
from dataclasses import asdict,replace
from datetime import datetime,timezone
from pathlib import Path

from pipeline.runner import generate,evaluate,compact
from workbench.runner import save
from workbench.worker import validate_source

ROOT=Path(__file__).resolve().parents[1]


def violation(candidate,reference,bound):
    if not candidate.get('correct'):return 'correctness'
    if not reference.get('correct'):return None
    if candidate['completion_seconds']>reference['completion_seconds']*bound and candidate['completion_seconds']-reference['completion_seconds']>.02:
        return 'performance_bound'
    return None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--reference',type=Path,default=ROOT/'pipeline/reference.py')
    parser.add_argument('--seed',type=int,default=910231)
    parser.add_argument('--cases',type=int,default=60)
    parser.add_argument('--max-latency-ratio',type=float,default=1.1)
    parser.add_argument('--http-repeats',type=int,default=3)
    parser.add_argument('--output',type=Path,default=Path('runs/falsify'))
    args=parser.parse_args()
    if not 1<=args.cases<=200 or not 1<=args.http_repeats<=5 or not 1<=args.max_latency_ratio<=5:parser.error('Invalid bounded search arguments')
    validate_source(args.source.read_text());validate_source(args.reference.read_text())
    directory=(args.output/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')).resolve();directory.mkdir(parents=True)
    source=directory/'patch.py';source.write_text(args.source.read_text())
    reference=directory/'reference.py';reference.write_text(args.reference.read_text())
    report={'name':'Patch contract falsification','status':'running','seed':args.seed,'bound':args.max_latency_ratio,
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'cases':[],'http':[]}
    save(directory/'report.json',report)
    for i,s in enumerate(generate(args.seed,args.cases,'falsification')):
        candidate=evaluate(source,s,'virtual',directory,f'case-{i}-patch')
        baseline=evaluate(reference,s,'virtual',directory,f'case-{i}-reference')
        report['cases'].append({'scenario':asdict(s),'patch':candidate,'reference':baseline,'violation':violation(candidate,baseline,args.max_latency_ratio)})
    failures=[r for r in report['cases'] if r['violation']]
    report['violating_cases']=len(failures)
    if failures:
        first=failures[0]
        scenario=generate(args.seed,args.cases,'falsification')[report['cases'].index(first)]
        minimized=first
        # Exhaustive over job count only; all other parameters remain fixed.
        for jobs in range(2,scenario.jobs):
            s=replace(scenario,jobs=jobs,name=scenario.name+f'_jobs{jobs}')
            candidate=evaluate(source,s,'virtual',directory,f'shrink-{jobs}-patch')
            baseline=evaluate(reference,s,'virtual',directory,f'shrink-{jobs}-reference')
            reason=violation(candidate,baseline,args.max_latency_ratio)
            if reason==first['violation']:
                scenario=s;minimized={'scenario':asdict(s),'patch':candidate,'reference':baseline,'violation':reason};break
        report['counterexample']=minimized
        save(directory/'counterexample.json',asdict(scenario))
        for repeat in range(args.http_repeats):
            for name,path in [('patch',source),('reference',reference)][::1 if repeat%2==0 else -1]:
                print('Counterexample HTTP',repeat+1,name,flush=True)
                r=evaluate(path,scenario,'http',directory,f'http-{repeat}-{name}')
                report['http'].append({'repeat':repeat,'policy':name,'result':r})
        patch=[r['result'] for r in report['http'] if r['policy']=='patch']
        ref=[r['result'] for r in report['http'] if r['policy']=='reference']
        if all(r.get('correct') for r in patch+ref):
            p=statistics.median(r['completion_seconds'] for r in patch)
            b=statistics.median(r['completion_seconds'] for r in ref)
            report['http_ratio']=p/b
            report['http_confirms_violation']=p>b*args.max_latency_ratio and p-b>.02
        else:report['http_confirms_violation']=any(not r.get('correct') for r in patch)
        report['status']='http_confirmed_counterexample' if report['http_confirms_violation'] else 'simulation_only_counterexample'
    else:report['status']='no_counterexample_found'
    save(directory/'report.json',report)
    esc=lambda v:html.escape(str(v))
    detail=report.get('counterexample')
    text=f'<h1>Tempo · Patch contract falsification</h1><p>Status: <b>{esc(report["status"])}</b></p><p>{len(failures)}/{args.cases} seeded cases violated the declared correctness or latency contract. Every generated case was evaluated; no cases were filtered by success.</p><p>Contract: patch must be correct and take no more than {args.max_latency_ratio:g}× the reference completion time (with a 20ms minimum difference).</p>'
    if detail:
        text+=f'<h2>First counterexample, reduced by job count</h2><p>{esc(detail["violation"])}. HTTP median ratio: {esc(report.get("http_ratio","not comparable"))}.</p><pre>{esc(json.dumps(detail["scenario"],indent=2))}</pre><p>The reduction varies only job count. It is not a globally minimal counterexample.</p>'
    text+='<p><a href="report.json">All results, failures and HTTP traces</a> · <a href="patch.py">Frozen patch</a> · <a href="reference.py">Reference</a></p><p>Controlled synthetic model; no claim of production safety or exhaustive search. This run diagnoses a frozen patch and never revises it.</p>'
    (directory/'index.html').write_text('<!doctype html><html><head><meta charset="utf-8"><title>Tempo falsification</title><style>body{background:#0c1420;color:#edf4ff;font:16px/1.7 system-ui;max-width:1000px;margin:50px auto;padding:20px}p{color:#b5c7dd}pre{background:#142339;padding:24px;border-radius:12px}a{color:#8cf7cc}</style></head><body>'+text+'</body></html>')
    print('Falsification result:',report['status'],directory/'index.html',flush=True)


if __name__=='__main__':main()
