"""Local demo launcher. Run only in a trusted workspace; binds loopback only."""
import argparse
import json
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
RUNS = WORKSPACE/'runs/workbench'
EXAMPLES = ROOT/'examples'
RUN_ROOTS = {'workbench': RUNS, 'pipeline': WORKSPACE/'runs/pipeline', 'falsify': WORKSPACE/'runs/falsify', 'catalog': WORKSPACE/'runs/catalog'}


class DemoState:
    def __init__(self):
        self.lock = threading.Lock()
        self.process = None
        self.log_path = None

    def snapshot(self):
        return {'running': self.process is not None and self.process.poll() is None,
                'returncode': self.process.poll() if self.process else None,
                'log': self.log_path.read_text()[-24000:] if self.log_path and self.log_path.exists() else ''}


class Handler(BaseHTTPRequestHandler):
    state = DemoState()

    def log_message(self, *args):
        pass

    def send(self, status, body, content_type='application/json', location=None):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode() if content_type == 'application/json' else body.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        if location:self.send_header('Location',location)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; frame-ancestors 'self'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            reports=sorted(RUN_ROOTS['catalog'].glob('*/index.html'),reverse=True)
            if reports:
                report=reports[0]
                return self.send(302,b'',location='/artifacts/catalog-'+report.parent.name+'/index.html')
            return self.send(200,(ROOT/'workbench/dashboard.html').read_text(),'text/html; charset=utf-8')
        if path == '/lab':
            return self.send(200,(ROOT/'workbench/dashboard.html').read_text(),'text/html; charset=utf-8')
        if path == '/api/examples':
            items = [{'id':'catalog_showcase','name':'Catalog sync · semantic API optimization','objective':'requests'},{'id':'pipeline_lab','name':'Contract stress lab · multi-stage integration','objective':'latency'}]
            for file in sorted(EXAMPLES.glob('*.json')):
                data = json.loads(file.read_text())
                items.append({'id': file.stem, 'name': data['name'], 'objective': data.get('objective', 'latency')})
            return self.send(200, items)
        if path == '/api/runs':
            rows = []
            for family, root in RUN_ROOTS.items():
                for file in root.glob('*/report.json'):
                    try:
                        data = json.loads(file.read_text())
                        rows.append({'id': file.parent.name if family=='workbench' else family+'-'+file.parent.name,
                                     'family':family,'timestamp':file.parent.name,'name':data['name'],'status':data['status'],
                                     'agent':data.get('agent','diagnostic'),'gates':data.get('gates',{}),
                                     'experiments':len(data.get('experiments',data.get('trials',[]))),
                                     'http_runs':len(data.get('http',[])),'comparisons':data.get('comparisons',[])})
                    except (ValueError, KeyError):
                        continue
            rows.sort(key=lambda row:row['timestamp'],reverse=True)
            return self.send(200, rows)
        if path == '/api/status':
            with self.state.lock:
                return self.send(200, self.state.snapshot())
        if path.startswith('/artifacts/'):
            relative = unquote(path[len('/artifacts/'):])
            head, separator, tail = relative.partition('/')
            family = next((name for name in RUN_ROOTS if name!='workbench' and head.startswith(name+'-')),'workbench')
            run_root = RUN_ROOTS[family]
            if family!='workbench':
                relative = head[len(family)+1:] + (separator+tail if separator else '')
            file = (run_root/relative).resolve()
            if not file.is_relative_to(run_root.resolve()) or not file.is_file():
                return self.send(404, {'error': 'No artifact'})
            if file.suffix not in {'.html', '.json', '.py', '.diff', '.txt'}:
                return self.send(404, {'error': 'Unsupported artifact'})
            content_type = {'.html': 'text/html; charset=utf-8', '.json': 'application/json'}.get(file.suffix, 'text/plain; charset=utf-8')
            return self.send(200, file.read_bytes(), content_type)
        self.send(404, {'error': 'Not found'})

    def do_POST(self):
        host = self.headers.get('Host', '')
        expected_hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        origin = self.headers.get('Origin')
        if host not in expected_hosts or (origin and origin != f'http://{host}') or self.headers.get('Content-Type') != 'application/json':
            return self.send(403, {'error': 'Local same-origin JSON requests only'})
        if self.path != '/api/run':
            return self.send(404, {'error': 'Not found'})
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 4096:
                raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(length))
            example = data['example']
            if not re.fullmatch(r'[a-zA-Z0-9_-]+', example) or (example not in ('pipeline_lab','catalog_showcase') and not (EXAMPLES/f'{example}.json').is_file()):
                raise ValueError('Unknown example')
            driver = data.get('driver', 'codex')
            if driver not in {'codex', 'replay', 'none'}:
                raise ValueError('Unknown driver')
            with self.state.lock:
                if self.state.snapshot()['running']:
                    return self.send(409, {'error': 'A run is already active'})
                if example=='catalog_showcase':
                    command=[sys.executable,str(ROOT/'tempo_catalog.py'),'--agent',driver,'--rounds','2' if driver=='codex' else '1',
                             '--validation-cases','32','--http-repeats','3','--seed',str(time.time_ns()%1000000),'--output',str(RUN_ROOTS['catalog'])]
                    proposal=ROOT/'catalog/saved-proposal.json'
                elif example=='pipeline_lab':
                    command = [sys.executable,str(ROOT/'tempo_pipeline.py'),'--agent',driver,
                               '--rounds','2' if driver=='codex' else '1','--http-repeats','3',
                               '--validation-cases','24','--http-cases','3','--seed',str(time.time_ns()%1000000),
                               '--output',str(RUN_ROOTS['pipeline'])]
                    proposal = ROOT/'pipeline/examples/saved-proposals.json'
                else:
                    command = [sys.executable, str(ROOT/'tempo_workbench.py'), '--example', str(EXAMPLES/f'{example}.json'),
                               '--agent', driver, '--rounds', '2' if driver == 'codex' else '1', '--http-repeats', '3',
                               '--output', str(RUNS)]
                    proposal = EXAMPLES/'proposals'/f'{example}.json'
                if driver == 'replay':
                    if not proposal.exists():
                        raise ValueError('No saved proposal for this example; use live Codex')
                    command += ['--proposal', str(proposal)]
                logs = WORKSPACE/'runs/launcher'
                logs.mkdir(parents=True, exist_ok=True)
                self.state.log_path = logs/f'{time.time_ns()}.log'
                with self.state.log_path.open('w') as stream:
                    self.state.process = subprocess.Popen(command, cwd=WORKSPACE, stdout=stream, stderr=subprocess.STDOUT)
                return self.send(202, self.state.snapshot())
        except (ValueError, KeyError, OSError) as exc:
            self.send(400, {'error': str(exc)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8877)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Tempo demo: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
