"""Actual real-time HTTP comparison with a recordable terminal dashboard.

Counters read live controlled-server state. No prerecorded events drive this UI.
"""
import argparse,asyncio,json,sys,time
from dataclasses import asdict
from pathlib import Path
from catalog.model import Scenario
from catalog.runtime import Server,HTTPProvider,execute
from workbench.worker import load_source

WIDTH=104
class Recording:
    def __init__(self,path):
        self.path=path;self.start=time.monotonic();self.frames=[]
    def screen(self,lines):
        lines=[line[:WIDTH] for line in lines]
        frame={'t':time.monotonic()-self.start,'lines':lines};self.frames.append(frame)
        print('\033[H\033[2J'+'\n'.join(lines),end='',flush=True)
    def save(self):
        self.path.write_text(json.dumps({'format':'tempo-terminal-capture-v1','width':WIDTH,'frames':self.frames,'duration':time.monotonic()-self.start},indent=2))

def bar(value,total,n=42):return '['+'#'*round(n*value/total)+' '*(n-round(n*value/total))+']'
def panel(stage,s,provider=None,elapsed=0,results=None):
    results=results or []
    lines=['TEMPO  /  LIVE HTTP COMPARISON','='*WIDTH,
      'SCENARIO: 48-product catalog sync | 3 tenants | 2 immutable snapshots',
      'Category + currency + item-specific inventory + product write',
      f'Same inputs, quotas, concurrency, retries and write keys. Clock scale: {s.scale}.',
      'Real TCP HTTP to a controlled local server. Recorded AI patch; no model call.', '',stage,'-'*WIDTH]
    if provider:
        calls=dict(provider.calls);done=len(provider.outputs)
        lines += [f'Wall elapsed: {elapsed:5.1f}s    Products committed: {done:2}/{s.jobs}  {bar(done,s.jobs,28)}',
          f"HTTP requests observed by server: {sum(calls.values()):3}", '',
          'OPERATION        REQUESTS     WHY THIS WORK IS REQUIRED']
        for op,why in [('category','shared only within tenant + snapshot'),('fx','shared only within tenant + snapshot'),('inventory','one real inventory receipt per product'),('write','one exact transformed payload per product')]:
            lines.append(f'{op:<17}{calls.get(op,0):>4}         {why}')
        lines += ['',f'Server rate-limit responses: {provider.throttled}    Invalid writes: {provider.invalid}']
    elif not results:lines += ['Ready: cold server state for each implementation.','','Run the configured original, then the AI source patch.']
    if results:
        lines+=['','COMPLETED RUNS', '-'*WIDTH]
        for name,r in results:lines.append(f"{name:<13} {r['requests']:3} requests | {r['completion_seconds']:5.2f}s | {r['acknowledged']}/48 outputs | correct={r['correct']}")
    return lines

async def main(args):
    root=Path(__file__).resolve().parent;s=Scenario(scale=args.scale,transient_every=0)
    rec=Recording(args.capture);results=[];rec.screen(panel('READY: same authored workload, two implementations',s));await asyncio.sleep(2)
    for name,file in [('ORIGINAL','baseline.py'),('AI PATCH','optimized.py')]:
        module=load_source((root/'catalog'/file).read_text())
        async with Server(s) as server:
            start=time.monotonic();task=asyncio.create_task(execute(s,module,server.provider,HTTPProvider(server)))
            while not task.done():
                rec.screen(panel(f'RUNNING {name}  /  real-time HTTP execution',s,server.provider,time.monotonic()-start,results))
                await asyncio.sleep(.1)
            r=await task;r['correct'] &= not server.errors
            assert r['correct'],r
            results.append((name,r))
            rec.screen(panel(f'{name} FINISHED',s,server.provider,time.monotonic()-start,results))
            await asyncio.sleep(1.5)
    a,b=[r for _,r in results];assert a['outputs']==b['outputs'];assert a['output_sha256']==b['output_sha256']
    lines=panel('VERIFIED: IDENTICAL OUTPUTS, LESS API WORK',s,results=results)
    lines+=['',f"Requests: {a['requests']} -> {b['requests']}   ({100*(1-b['requests']/a['requests']):.1f}% fewer)",
      f"Completion: {a['completion_seconds']:.2f}s -> {b['completion_seconds']:.2f}s",'',
      'Full output SHA-256 matches across both implementations:',a['output_sha256'],
      '48/48 products correct | zero duplicate effects | zero invalid outputs',
      'Controlled synthetic provider; these are local HTTP measurements.']
    rec.screen(lines);await asyncio.sleep(4);rec.save()
    args.results.write_text(json.dumps({'scenario':asdict(s),'runs':dict(results),'hashes_equal':True,'outputs_equal':True},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scale',type=float,default=.65)
    p.add_argument('--capture',type=Path,default=Path('live-terminal.json'));p.add_argument('--results',type=Path,default=Path('live-results.json'))
    args=p.parse_args();assert .1<=args.scale<=1;asyncio.run(main(args))
