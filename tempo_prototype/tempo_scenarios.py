"""Create a reproducible scenario manifest for any trusted adapted integration.

Generation is blind to performance: no outcome filtering. Keep the validation
seed/cases uninspected until selection; after use, they are regression data.
"""
import argparse
import json
import os
import random
from pathlib import Path


def cases(seed, count, label):
    rng = random.Random(seed)
    rows = []
    for index in range(count):
        jobs = rng.randint(7, 20)
        limit = rng.randint(2, 7)
        window = rng.uniform(1.2, 3.8)
        slow = rng.uniform(.2, 1.8)
        rows.append({'name': f'{label}_{seed}_{index}', 'jobs': jobs, 'limit': limit,
                     'window': round(window, 4), 'service': round(rng.uniform(.02, .15), 4),
                     'slow_service': round(slow, 4), 'slow_every': rng.randint(2, 6),
                     'seed': rng.randint(0, 1000000), 'scale': .2,
                     'deadline': round(max(20, (jobs/limit+4)*window+jobs*slow), 4),
                     'quota_mode': rng.choice(['fixed', 'token'])})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--name', default='Custom integration')
    parser.add_argument('--seed', type=int, default=20261031)
    parser.add_argument('--cases-per-split', type=int, default=4)
    parser.add_argument('--objective', choices=['latency', 'requests'], default='latency')
    args = parser.parse_args()
    if not 1 <= args.cases_per_split <= 12:
        parser.error('--cases-per-split must be between 1 and 12')
    if not args.source.is_file():
        parser.error('--source must exist')
    if args.output.exists():
        parser.error('Output already exists; use a new filename to retain previous cases')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {'name': args.name, 'source': os.path.relpath(args.source.resolve(), args.output.parent.resolve()),
                'objective': args.objective, 'max_other_metric_regression': .1,
                'training': cases(args.seed, args.cases_per_split, 'training'),
                'validation': cases(args.seed+1, args.cases_per_split, 'validation')}
    args.output.write_text(json.dumps(manifest, indent=2)+'\n')
    print(args.output)


if __name__ == '__main__':
    main()
