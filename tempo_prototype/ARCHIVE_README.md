# Extended hackathon direction: Tempo Contract Lab

The prototype now also tests read → transform → write integrations with weighted
account quotas, endpoint quotas, concurrency, transient failures and ambiguous
acknowledgments. It compares direct and feedback-guided AI proposals and searches
for counterexamples to explicit performance contracts.

[Direction and commands](PIVOT.md) · [Extended measured results](PIVOT_RESULTS.md).

The experiments preserve substantial improvements **and** failed fidelity gates,
rejected near-no-ops, and a confirmed HTTP performance counterexample. This is
not a claim of universally superior optimization or an untouched market.

---

# Current end-to-end workbench

**The next milestone is implemented.** Tempo now has a live Codex patch driver,
a reusable integration adapter, calibrated virtual HTTP behavior, an independent
local-server quota implementation, strong references, validation, repeated real
HTTP confirmation, and a local demo launcher.

Start here: [Workbench guide](WORKBENCH.md) · [Measured demo results](DEMO_RESULTS.md).

```sh
python3 tempo_prototype/tempo_demo.py
```

The remainder of this file is the historical README for the original research
scripts and the first HTTP milestone. Its statements about a missing agent refer
to those earlier versions; the current workbench is documented above. Automatic
model extraction and customer-repository adaptation remain unimplemented.

---

# Tempo: a virtual-time optimization workbench for async API integrations

## Status

Executed research prototype, 31 October 2026. Python standard library only.
This is a prototype of a possible product, not a production-tested integration,
novel retry algorithm, or an autonomous agent application.

The assistant acted as the optimization agent: read the first trace, authored
candidate source, inspected failures, revised the policy, then ran bounded
parameter search. The artifact reproduces execution and evaluation; it does
not call an LLM. Model extraction from documentation/traffic and automatic
repository adaptation are not implemented.

## The proposed product

An AI agent adapts a team's outbound API integration to a local virtual-time
workbench, proposes source patches, and tests them against several plausible
provider behaviors. It returns a patch with an executable scenario and a
tradeoff report. First customer: backend teams owning quota-constrained batch
imports, exports, enrichment jobs, and external-API connectors.

The useful transfer is applying fast discrete-event experimentation to the
*real coroutine implementation* and using its traces to improve code. The
prototype executes Python tasks, sleep, wait_for, locks and cancellation; it
does not merely plot an equation for a hypothetical retry policy.

## Run

From this directory, on CPython with SelectorEventLoop support (tested Linux):

```sh
python3 tempo.py
python3 experiment.py
python3 validate.py
python3 robust_search.py
python3 compare.py
```

`first_experiment.json` is a frozen record of the first experiment. The other
JSON reports can be regenerated. All provider activity is simulated, no API
credentials, packages, traffic or payments are involved. Several short fidelity
checks use actual wall-clock sleeps and normally take a few seconds combined.

## Actual measured findings

- The initial fixture confirmed 21/48 jobs with 363 requests.
- A local Retry-After fix confirmed 41/48 and caused 23 duplicate side effects.
- The revised coordinated policy confirmed 48/48 with 53 requests and no
  duplicate effects on that fixture.
- A stronger reference policy (one retry layer, Retry-After plus jitter,
  idempotency and adaptive timeouts) completed 48/48 using 168 requests.
- Candidate versus strong reference: 53 versus 168 requests, 54.40 versus
  51.42 simulated seconds. The candidate was 5.8% slower on this fixture while
  reducing requests 68.5%. This is not an unconditional latency improvement.
- Final candidate completed 60/60 fresh seeded scenarios; strong reference
  completed 41/60 under the same 24-attempt budget. Failures of the reference
  generally concern retry exhaustion, not duplicate effects.
- On the 41 cases where both completed, the median per-case request ratio was
  0.2457 and completion-time ratio was 0.9950. Do not interpret this as a
  production speedup or compare failed fast runs as successful low latency.
- Ten policy candidates across four training scenarios traversed 11,023
  simulated seconds in about 0.10 measured seconds (one local run). This
  excludes agent reasoning, real provider work and model calibration.
- An earlier candidate passed only 9/18 holdouts. Its timeout revision passed
  47/48 fresh cases. Those failures are retained; after revising the attempt
  budget, the 48 cases became regression data, and a NEW 60-case seeded set
  was used. This is not 60 independent production workloads.
- Virtual and real clock counts matched in two simple cases and three runs
  of a timeout/idempotency case. This checks clock implementation on those
  fixtures, not fidelity of the provider model to a real provider.
- Removing idempotency in the ablation produced four duplicates. An impossible
  deadline correctly remained a failure. Both controls are in the reports.

## Exactly what a two-minute demo can show

1. Display the short integration function and its nested retry loops.
2. Run the virtual clock; show 21/48 acknowledgments and the event log.
3. Show the plausible Retry-After-only patch producing duplicate side effects.
4. Show the coordinated candidate and strong reference side by side: fewer
   attempts, all jobs completed, explicit small latency tradeoff.
5. Run the fresh scenario matrix and replay a deterministic counterexample.
6. Show the source diff and the exported JSON, not invented animation metrics.

The CLI and reports work now. A polished UI, agent API driver, real HTTP client
adapter, model extraction and real-project validation remain work for tomorrow.
Do not promise that all of those can be finished in one day.

## Model assumptions and limits

- Synthetic fixed-window and token-bucket quotas; explicit parameter families.
- A write commits before its response, which may arrive after client timeout.
- The provider honors stable idempotency keys; this MUST be an actual contract
  before applying that policy to real APIs. No key expiry/eviction is modeled.
- Latencies are exogenous; queueing, CPU, network bandwidth, distributed quota
  contention, 5xx/outages and billing semantics are not modeled.
- A single process coordinates requests. A distributed deployment would need
  different admission coordination.
- Input is authored fixture code, not a customer repository or real SDK.
- Virtual clock rejects real sockets. It does not accelerate blocking I/O,
  threads, time.time(), CPU work, or arbitrary Python programs. It uses asyncio
  private event-loop details, so portability is not promised.
- Large speed ratios reflect skipping simulated waiting. They do not predict
  how much faster a production job would run.

## Competition found before recommendation

No claim of zero competitors or newly invented virtual time:

- aiotools VirtualClock: existing fast asyncio timers.
  https://aiotools.readthedocs.io/en/latest/aiotools.timer.html
- Antithesis: much broader deterministic simulation, fault injection, agents
  and time acceleration. Not claimed inferior to this prototype.
  https://antithesis.com/docs/best_practices/optimizing/
- Microsoft AOAI API Simulator: existing provider simulation and rate limits.
  https://github.com/microsoft/aoai-api-simulator
- Speedscale: service virtualization and captured-traffic replay.
  https://docs.speedscale.com/guides/mocking/llm-simulation/
- RetryProof: particularly close; AI analysis and repair of consequential n8n
  workflows with deterministic retry faults. A generic retry-repair pitch would
  overlap strongly. Our proposed emphasis is source-level performance-policy
  optimization across provider-model uncertainty, not n8n duplicate repair.
  https://github.com/MarMarLabs/RetryProof
- Retry calculators, teaching simulators and shared-budget designs exist:
  https://www.integronauts.com/tools/retry-simulator
  https://github.com/sibasispadhi/acm-tech-talk

The proposed differentiation is a narrow workflow and integration, not a novel
algorithm. The next investment test is adapting one real async client and
comparing source patches with a well-configured standard rate limiter. If
ordinary configuration solves it just as easily, the startup case is weak.

## Files

- tempo.py: virtual-time runner, explicit provider model, authored buggy client.
- candidates.py: agent-authored candidates and strong reference policy.
- experiment.py: first candidate sweep and basic clock-fidelity checks.
- validate.py: failed-candidate regression, fresh matrix, real-time checks.
- robust_search.py: bounded search over model family; new 60-case evaluation.
- compare.py: comparison with stronger baseline, including paired-success stats.
- *.json: complete measured results, events, failures and negative controls.

No content from external repositories was copied into the implementation.

## Local HTTP milestone

Run from the workspace root:

```sh
python3 tempo_prototype/http_experiment.py --repeats 3
```

This uses a real async HTTP/1.1 client built on `asyncio` streams and a local
controlled server bound to an ephemeral loopback port. No packages or credentials
are required. It exercises actual TCP, HTTP framing, request cancellation,
server-side commit before delayed acknowledgment, and stable idempotency keys.
The client is intentionally limited to this server's Content-Length responses;
it is not a replacement for a general HTTP client library.

Four policies run against fixed-window and token-bucket quotas, each repeated
three times: the existing retry reference, a new quota-aware standard-library
pacing baseline, the previously selected candidate, and an unsafe no-idempotency
control. The pacing baseline uses the declared quota, the same retry code,
stable keys, and growing timeouts. This is a fairer test of whether source
optimization adds value over ordinary configuration. Fixtures use eight jobs
and scaled real waits; they do not extend the 48-job claim to real providers.

Reports are timestamped under `runs/http/`. Every completed experiment includes
both traces, server-observed effects, correctness, count differences, and a
completion-time difference. Failed runs retain a failure record. Original
archive reports remain untouched; rerun outputs are in `runs/original-rerun/`.

Fidelity is measured, not assumed: this server rounds Retry-After up to integer
wall seconds, whereas the original model returns fractional simulated seconds.
At the fixture's time scale that can materially increase waits. Exact counts
are reported separately from correctness; a passing acceptance check does not
mean timing fidelity passed. The server also shares the Provider implementation
with simulation, so these runs do not independently validate quota semantics.
There is no socket acceleration: virtual runs and HTTP runs are separate.

The autonomous patch agent remains unimplemented. Transport calibration and a
strong configuration baseline now provide a concrete evaluation boundary for
that future driver. Model extraction and customer-repository adaptation also
remain unimplemented.
