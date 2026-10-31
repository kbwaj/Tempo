import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from catalog.model import Scenario
from catalog.runtime import run
from workbench.worker import load_source

if __name__=='__main__':
    try:
        request=json.load(sys.stdin)
        result=run(Scenario(**request['scenario']),load_source(Path(request['source']).read_text()),request['transport'])
        print(json.dumps({'result':result}))
    except Exception as exc:
        print(json.dumps({'error':f'{type(exc).__name__}: {exc}'}));sys.exit(1)
