"""One source/case evaluation per subprocess, bounded by the parent process.

This is fault isolation, NOT a security sandbox. Run only trusted local adapters
and review model output before using it with credentials or customer code.
"""
import ast
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tempo import Scenario
from workbench.runtime import run_module


def validate_source(source):
    if len(source) > 30000:
        raise ValueError('Source exceeds 30KB limit')
    tree = ast.parse(source)
    banned = {'open', 'exec', 'eval', 'compile', '__import__', 'globals', 'locals', 'vars',
              'getattr', 'setattr', 'delattr', 'input', 'breakpoint', 'help', 'type', 'object', 'super'}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [n.name for n in node.names] if isinstance(node, ast.Import) else [node.module]
            if any(m not in {'asyncio', 'math', 'random', 'collections'} for m in modules):
                raise ValueError('Only asyncio/math/random/collections imports are supported')
        if isinstance(node, ast.Attribute) and node.attr.startswith('_'):
            raise ValueError('Private or reflective attributes are unsupported')
        if isinstance(node, ast.Name) and (node.id in banned or node.id.startswith('__')):
            raise ValueError(f'Unsupported identifier: {node.id}')
    names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if not {'configure', 'integrate'} <= names:
        raise ValueError('Adapter needs configure(provider) and async integrate(provider, job, context)')
    return tree


def load_source(source):
    tree = validate_source(source)
    module = types.ModuleType('tempo_integration')
    exec(compile(tree, '<tempo integration>', 'exec'), module.__dict__)
    return module


if __name__ == '__main__':
    try:
        request = json.load(sys.stdin)
        module = load_source(Path(request['source']).read_text())
        result = run_module(Scenario(**request['scenario']), module, request['transport'])
        print(json.dumps({'result': result}))
    except Exception as exc:
        print(json.dumps({'error': f'{type(exc).__name__}: {exc}'}))
        sys.exit(1)
