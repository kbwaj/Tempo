# Measured end-to-end demo results

Two live Codex optimization runs completed on 31 October 2026. Each used two
model proposals, selection on two training cases, and confirmation on two
validation cases with three real HTTP repetitions per implementation. These
are controlled local synthetic workloads, not production benchmarks.

## Serialized importer: performance improvement

| Validation quota | Original median HTTP time | Agent patch median HTTP time | Reduction | Requests before / after |
|---|---:|---:|---:|---:|
| Fixed window, 11 jobs | 2.237 s | 1.864 s | 16.7% | 11 / 11 |
| Token bucket, 13 jobs | 2.275 s | 1.180 s | 48.1% | 13 / 13 |

Every patch run completed all jobs with zero duplicate effects. All 24
simulation/HTTP count-and-timing comparisons passed. The agent removed
serialization across network waits and used the documented burst allowance.

The patch also improved completion over the smooth quota-aware reference by
9.4% and 33.3%. It essentially **matched the stronger burst-aware reference**:
about 1.865 s and 1.180 s. The result supports agent-driven application of
ordinary best practices, not a newly superior rate-limiting algorithm.

[Report and source diffs](../runs/workbench/20261031T174150189056Z/index.html)
· [Raw evidence](../runs/workbench/20261031T174150189056Z/report.json)

## Retry-heavy integration: correctness repair

| Validation quota | Original acknowledgments | Original requests | Patched acknowledgments | Patched requests |
|---|---:|---:|---:|---:|
| Fixed window | 4 / 11 | 81 | 11 / 11 | 11 |
| Token bucket | 4 / 13 | 93 | 13 / 13 | 13 |

The token-bucket original produced five duplicate effects in the first
repetition. The patch produced zero duplicates in every repetition. Its
median completion was 1.871 s / 1.193 s, close to the strong burst reference.
The original's incomplete runs do not support a successful-run latency
comparison. All six candidate fidelity checks passed; 21/24 checks passed
across all implementations, preserving original-policy timing differences.

[Report and source diffs](../runs/workbench/20261031T174608636990Z/index.html)
· [Raw evidence](../runs/workbench/20261031T174608636990Z/report.json)

## Already-optimized integration: no verified improvement

Replaying the saved source proposal against the already-configured reference
produced an apparent training improvement, but HTTP confirmation failed to show
an improvement. Tempo retained the experiment and reported **no verified
improvement**. This control used one HTTP repetition per implementation and is a
smoke check; current verification also requires at least three repetitions.

[Rejected optimization](../runs/workbench/20261031T174837150677Z/index.html)

The earlier sandbox-denied live attempt is retained too. Neither failed model
access nor unavailable HTTP sockets are reported as successful execution.

## What can be demonstrated now

A real model reads source and traces, returns actual replacement Python, gets
training feedback, and produces a selected diff. That source runs unchanged
through a calibrated simulator and a real async HTTP client. An independent
local server records effects. The report keeps references, failed proposals,
validation, repeated measurements, timing ranges, and provenance.

Validation is withheld from the model prompt until selection. These particular
cases have now been inspected and are regression data. Generate another matrix
for further testing, and retain all results. Small repetition counts and
synthetic provider assumptions limit any generalization.

## Generated matrix after source freeze: mixed performance

A separate matrix was generated with seed 735193 after the live patch had been
selected. The unchanged saved patch was replayed; this run made no new model
calls and did not filter cases based on outcomes. Both validation cases happened
to use token buckets.

| Generated case | Original median HTTP time | Frozen patch median HTTP time | Reduction |
|---|---:|---:|---:|
| 12 jobs, quota 2 | 2.717 s | 2.686 s | 1.1% |
| 8 jobs, quota 4 | 1.225 s | 0.786 s | 35.9% |

All jobs completed with unchanged request counts and zero duplicates. All 24
count-and-timing fidelity checks passed. The first reduction is small and should
not be treated as strong evidence from three repeats. The patch was **9.1% and
11.1% slower than the burst-aware reference**. Its report passes the configured
improvement threshold against the original, not a superiority test against the
strongest reference. This limits any claim that the chosen patch generalizes as
the best policy.

[Generated-matrix report](../runs/workbench/20261031T175959223084Z/index.html)
· [Scenario matrix](../runs/generated-matrix-735193.json)

The launcher was also tested end to end with no model calls and the already-
optimized integration: 24 HTTP runs, correct outcomes, and **no verified
improvement**. This confirms the launcher does not label a no-op as a win.

[Launcher smoke run](../runs/workbench/20261031T175557737496Z/index.html)

The 12 workbench tests pass. Dashboard HTTP endpoints, report serving, launch
requests, and JavaScript syntax were checked. Browser visual inspection was
unavailable because Computer Use permissions were not granted.
