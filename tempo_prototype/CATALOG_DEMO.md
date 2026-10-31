# Tempo: source-level API work optimization

**Pitch:** Tempo uses AI to remove unnecessary API work from integrations, then
verifies the source patch against exact output checks and real HTTP measurements.

This demo is a multi-tenant catalog sync: category enrichment, exchange-rate
conversion, per-item inventory, and one product write. The original already has
burst-aware rate limiting, bounded retries/timeouts, concurrency control and
stable write keys. The AI changes business dataflow while its scheduling and
retry helpers stay identical.

## Measured live-model experiment

A real Codex driver proposed two source revisions. The selected source passed
35 validation scenarios and three HTTP repetitions on each of three declared
catalog workloads, alongside the configured original and a manual semantic
reference. No warm cache carries between runs.

| Workload | Requests original → AI | Median HTTP original → AI | Request reduction | Completion reduction |
|---|---:|---:|---:|---:|
| 48 products | 192 → 108 | 3.379 → 1.836 s | 43.8% | 45.7% |
| 72 products | 288 → 156 | 5.161 → 2.717 s | 45.8% | 47.3% |
| 64 products | 256 → 144 | 4.532 → 2.540 s | 43.8% | 44.0% |

Every output is identical to the configured baseline, with zero duplicate write
effects and zero invalid outputs. The full output SHA-256 matches, not just a
record count. All acceptance gates passed, including simulation/HTTP request,
output and timing fidelity. Timing tolerance is max(100ms, 15%). These are local
controlled synthetic measurements, not production benchmarks.

Main output SHA-256:

```
1f7c2a342ea504c865411d04ca600286020d263228e4b612ecfa69efeeac065d
```

[Live-model report](../runs/catalog/20261031T190132409388Z/index.html)
· [Raw measurements](../runs/catalog/20261031T190132409388Z/report.json)
· [Lower-bound derivation](../runs/catalog/20261031T190132409388Z/optimality.json)

## Why the request count is provable within this contract

The server requires one item-bound inventory receipt and one write for each
product. That requires **48 + 48 = 96 requests**. Category and FX receipts are
scoped by kind, tenant, snapshot and key. A bulk lookup covers at most eight keys
in exactly one scope. The required scope/key sets need at least six category
batches and six FX batches: **12 more requests**.

Therefore the cold-start lower bound is **96 + 12 = 108 requests**. The AI patch
uses exactly 108 on the quota-only demo. It attains the request-count minimum
under the declared API. This is not a claim of latency optimality or of beating
an expert implementation: the manual semantic reference also reaches 108.

The model proposed shared tasks for each scoped batch. Products await those
shared results, then each performs its own inventory read and write. The diff
changes the source's dataflow, rather than improving results by weakening the
rate limiter or removing verification.

## Present it in 90 seconds

**0–15 seconds — problem**

“Every product performs the same four-step API workflow. The client already has
correct retries and rate limiting, but repeated category and currency lookups
still consume quota.”

**15–35 seconds — AI change**

“Tempo reads the integration and measured traces, then proposes a source patch.
It shares immutable lookups only within their tenant and snapshot, and batches
compatible keys. Inventory stays per product. Here is the actual model diff.”

Click **Inspect the AI patch**, then open the source diff.

**35–60 seconds — result**

“For 48 products, actual HTTP requests fall from 192 to 108, and median completion
falls from 3.38 to 1.84 seconds. Every output is identical. We compare the entire
output SHA-256 and check receipts, prices and write effects on the server.”

Point to the operation breakdown: category 48 → 6, FX 48 → 6, inventory 48 → 48,
writes 48 → 48.

**60–80 seconds — proof**

“The API requires 96 item-specific operations plus 12 minimum lookup batches.
The patch reaches that 108-request lower bound. We also verified different
sizes, tenants, snapshots, quotas and batch limits.”

**80–90 seconds — product value**

“Tempo turns an integration optimization suggestion into a reviewable source
patch with executable evidence. Its focus is reducing API work while preserving
application semantics.”

The main screen leads with this successful experiment. Earlier research runs
remain accessible in the engineering lab; they are not the presentation's main
flow. Do not describe replay as a new AI run.

## Run it

From the workspace root:

```sh
python3 tempo_prototype/tempo_demo.py
```

Open http://127.0.0.1:8877. The home page opens the latest catalog report.
**Re-run HTTP benchmark** launches fresh measurements of the saved model patch,
with no model call. **Generate a new AI patch** runs the live installed/signed-in
Codex CLI, then validation and HTTP confirmation. This uses configured Codex
usage. The page always labels live and replay provenance.

CLI replay:

```sh
python3 tempo_prototype/tempo_catalog.py \
  --agent replay --proposal tempo_prototype/catalog/saved-proposal.json \
  --rounds 1 --validation-cases 32 --http-repeats 3
```

Live:

```sh
python3 tempo_prototype/tempo_catalog.py \
  --agent codex --rounds 2 --validation-cases 32 --http-repeats 3
```

A checked-in copy of the verified model source is `catalog/optimized.py`.
Original source is `catalog/baseline.py`. No customer source is auto-modified.
The request lower bound is calculated independently by `catalog/optimality.py`.
Every run retains source, prompts, model event logs, diffs, traces, scenario
corpus, output hashes and rejected attempts under `runs/catalog/`.

## Contract and comparison scope

The demonstration assumes category and FX responses are immutable within an
explicit tenant/snapshot, and that a supported bulk lookup costs one request
quota unit. Both assumptions are declared before execution. Inventory receipts
remain item-bound and every product still needs a real inventory call and write.
The synthetic inventory values are stable within the authored workload; this is
not a test of arbitrary production freshness or idempotency expiry semantics.

Validation varies workload size, tenants, snapshots, key reuse, token/fixed
quotas, batch limits, service delays and transient errors. A low-sharing boundary
checks correctness without requiring a speedup. Tests also verify an explicit
zero-sharing case. A provider with different caching/billing contracts needs an
adapter and a different model.

The model and server have independent quota algorithms, while sharing the
business fixture. Subprocesses provide fault/time isolation rather than a
hostile-code sandbox. Run trusted adapters only. No real customer repository,
external production API, automatic provider extraction, named competitor
benchmark, or market-exclusive algorithm is claimed.

The focused application is **semantics-preserving API work elimination**: a
source-aware optimization beyond adjusting retry and concurrency settings.
General AI optimization products may perform similar rewrites. Present the
concrete request-optimal result and executable verification, not an unmeasured
claim to outperform those products.

## Rehearsal completed

The replay button was exercised through the application API. Its fresh run
again passed all 35 validation scenarios and all 27 HTTP comparisons, including
the request lower bound. The main 48-product replay again used 108 versus 192
requests and approximately 46% less completion time. This replay makes no new
model call and is labeled accordingly.

All **28 tests pass**, including a regression test of the checked-in AI source,
full output equivalence over HTTP, the request lower bound, tenant-scoped
receipts and the explicit zero-sharing boundary. The home route, model-response
artifact, replay launch, source/evidence routes and JavaScript syntax were
checked. Automated browser visual inspection remains unverified; the measured
results come from Python execution and HTTP, not browser animation.

[Rehearsed application replay](../runs/catalog/20261031T190844164773Z/index.html)
