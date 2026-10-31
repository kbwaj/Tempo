# Tempo — source-level API work optimization

The presentation demo is a successful multi-tenant catalog sync optimization.
A live AI-generated patch cuts **192 requests to 108**, with **identical output**,
zero duplicate writes, and **3.38 → 1.84 seconds** median local HTTP completion.
It reaches the **108-request minimum** under the declared API contract.

```sh
python3 tempo_prototype/tempo_demo.py
```

Open http://127.0.0.1:8877.

[Demo narrative, results and commands](CATALOG_DEMO.md).

The page includes the source diff, operation counts, output hash, repeated HTTP
measurements, lower-bound derivation, a replay button, and a live AI-run button.
The configured baseline already has robust retries, rate and concurrency limits.
The AI changes semantic dataflow by sharing and batching snapshot-safe lookups.

The manual semantic reference reaches the same request minimum. These are
controlled synthetic measurements; no named competitor superiority or production
performance is claimed. Earlier experiments and their limitations remain in
[the engineering archive](ARCHIVE_README.md), [workbench guide](WORKBENCH.md),
and [contract-lab research](PIVOT_RESULTS.md).
