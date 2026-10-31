# Tempo Contract Lab

**Pitch:** Before accepting an AI-generated integration patch, find the provider
conditions under which its performance promise stops holding.

The hackathon direction is a focused application of AI to integration engineering:
source proposals plus a reproducible contract stress lab. The useful artifact is
a source diff, measured operating envelope, and replayable counterexample—not
an unsupported claim that an agent found a universally faster retry algorithm.

## What is different from the first prototype

The new workload is a real read → transform → write pipeline. The write must carry
the receipt from its read and the correctly transformed value. Independent
server-side checks reject fabricated acknowledgments, wrong values, missing
reads, and cross-job idempotency-key collisions.

Each request competes for:

- A shared account quota with weighted read/write costs.
- A separate endpoint quota, independently fixed-window or token-bucket.
- A shared request-concurrency cap.

The provider injects seeded transient 503s after charging quota and before
commit. Writes commit before a delayed acknowledgment. Client cancellation does
not cancel server work or free its slot. Different slow/fault IDs, mixed quota
mechanisms, weights, load and capacities form the scenario family. Tenant labels
are measured, but this version does not implement separate per-tenant quotas.

These are authored synthetic semantics inspired by common API constraints;
this is not a simulator of any named provider. For example, Stripe documents
[global/endpoint rate and concurrency limits](https://docs.stripe.com/rate-limits).
The weighted-cost component is an additional synthetic assumption.

Two integration examples are supplied:

- `pipeline/examples/shared_cooldown.py`: endpoint errors pause the whole
  connector; worker slots span the whole job and its retry waits.
- `pipeline/examples/endpoint_islands.py`: separately paced SDK endpoints fail
  to coordinate their shared account budget and concurrency.

The references include ordinary per-request retry+semaphore and a conventional
hierarchical limiter that coordinates weighted account quota, endpoint quota,
and request slots. It does not hold request slots across quota waits. These are
explicit comparisons with ordinary engineering configuration, not inventions.

## Run the extended lab

From the workspace root:

```sh
python3 tempo_prototype/tempo_demo.py
```

Open http://127.0.0.1:8877 and select **Contract stress lab**. Existing reports,
including the original workbench, remain available. The lab can run live or
replay saved model proposals. New launcher runs record a generated seed.

CLI:

```sh
python3 tempo_prototype/tempo_pipeline.py \
  --seed 610731 --validation-cases 24 \
  --http-cases 3 --http-repeats 3 --rounds 2
```

The live experiment uses four model calls: two independent direct proposals and
two feedback-guided proposals. Each arm is selected on the same three training
scenarios using the same correctness-first score. The direct arm sees source
and contracts; the feedback arm additionally sees measured training outcomes
and prior attempts. Selection freezes before validation. The same 24 validation
cases and the fixed first three HTTP cases are used for every implementation;
there is no successful-case filtering.

This is equal **proposal count**, not equal token consumption. Model randomness,
arm order, different prompt lengths and the small sample limit causal claims.
The result may show no incremental feedback benefit. That is retained.

Inspect model usage and paired-case comparisons:

```sh
python3 tempo_prototype/pipeline/analysis.py runs/pipeline/RUN_ID
```

The report stores all generated cases, source attempts, model events, transforms,
side effects, failures, controls, validation and HTTP traces. Fidelity separates
outcome agreement, exact attempt counts, and timing within max(120ms, 20%).
All three must pass for the feedback candidate to receive verified status.
The acceptance test additionally requires all virtual validation cases correct,
all confirmed HTTP cases correct, zero invalid writes/duplicates, caught
controls, three HTTP repetitions, and at least 5% plus 20ms latency improvement
in every correct original HTTP case with no more than 10% request regression.
Matching an expert reference is never labeled superiority to that reference.

## Falsify a patch's performance promise

After source selection, run a separate seeded search without revising the patch:

```sh
python3 tempo_prototype/tempo_falsify.py \
  --source runs/pipeline/RUN_ID/feedback-selected.py \
  --seed 910231 --cases 60 --max-latency-ratio 1.1 --http-repeats 3
```

This tests the explicit claim that the frozen patch is correct and takes no more
than 1.1× the hierarchical reference's time, with a 20ms minimum difference.
Every generated case is retained. If a violation is found, the first violating
case is reduced by exhaustive job-count search with all other fields fixed, then
replayed over real HTTP. It may produce a counterexample, a simulation-only
counterexample, or no counterexample found. None means exhaustive proof.

You can change the reference with `--reference`, for example to test an explicit
promise relative to a source integration. The bound is a declared evaluation
criterion, not a model-discovered law. Deliberate fault mutants in the main lab
are clearly labeled as oracle controls rather than discovered customer bugs.

## Where the potential lies

A useful demo question is: “This patch passed my tests and got faster on one
fixture. Which combinations of rate limits, costs, concurrency and timeouts make
that claim fail?” The workbench searches for an answer and hands the engineer a
small executable example. This supports reviewing AI-generated patches and
provider/SDK configuration changes.

This is a narrower product hypothesis, **not an untouched technical area**:

- [Speedscale's Agent Factory](https://speedscale.com/blog/traffic-context-confirmed-fix-3-minutes/)
  already describes AI diagnosis, a source concurrency fix, and local HTTP
  validation for a real Gmail integration. That strongly overlaps the original
  pitch.
- [Codeflash](https://www.codeflash.ai/) already markets AI source optimization
  with correctness checks and benchmarks.
- [RetryProof](https://github.com/MarMarLabs/RetryProof) already combines AI repair
  with deterministic workflow invariants and replay evidence.
- [Bottleneck](https://github.com/SGrondin/bottleneck) already supports chaining
  limiters and grouped scheduling. Hierarchical quota coordination is established.

The proposed focus is a lightweight source-patch stress workflow across
interacting API-contract families, with counterexample reduction and HTTP
confirmation. This combination may be useful, but we have not established
exclusive features, customer demand, or superiority to those products.

## Limits

No production API traffic, customer repository, automatic provider-model
extraction, real SDK adaptation, distributed coordinator, idempotency expiry,
or arbitrary workflow graph is implemented. The model and HTTP server have
independent quota algorithms but share their business fixture. Subprocesses
provide fault/time isolation, not a hostile-code security sandbox. Run trusted
source only. Inspected validation cases become regression data. No finite
scenario set certifies production safety.

For an already observed HTTP failure, reproduce it explicitly as a regression
and optionally attempt a reduction:

```sh
python3 tempo_prototype/tempo_replay_failure.py \
  --run runs/pipeline/RUN_ID --case 1 \
  --max-latency-ratio 1.1 --http-repeats 3 --minimize
```

A one-shot reduction must pass repeated confirmation before replacing a larger
confirmed case. Failed reductions remain recorded. See
[extended measured results](PIVOT_RESULTS.md) for the live comparison, rejected
second-example optimization, simulation-only finding and confirmed HTTP replay.
The proposal loop currently uses training traces; the exported HTTP counterexample
is not automatically sent into another model repair cycle.
