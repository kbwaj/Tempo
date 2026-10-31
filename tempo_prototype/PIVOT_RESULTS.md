# Tempo Contract Lab: what the extended experiment established

The useful hackathon pivot is **AI patch contract auditing**: test whether a
source patch stays correct and worthwhile as interacting provider constraints
change, and produce a replayable counterexample when an explicit performance
contract fails. This is a narrow workflow hypothesis, not an untouched market
or a new scheduling algorithm.

## Expanded experiment

The new integration must read each job, transform its value, and write the
correct value with the read's receipt. It faces weighted account quotas,
independent endpoint quotas, concurrency caps, seeded transient 503s, delayed
acknowledgments, and server work that survives client cancellation.

- Two authored connector examples with different coordination mistakes.
- One live experiment with **4 model calls**: 2 direct proposals and 2 proposals
  receiving experimental feedback. Same configured model and call count, with
  different token consumption and fixed arm order.
- 3 training scenarios and 24 generated validation scenarios in that experiment.
- A second 24-case matrix reusing the frozen proposals against another original
  connector; explicitly a replay, not a second autonomous optimization run.
- A separate 60-case seeded falsification search after source freeze.
- **108/108 generated scenarios passed the frozen patch's correctness checks.**
  These are parameter variants of one synthetic workflow contract, not 108
  independent integrations or customer workloads.
- **75 planned HTTP comparison runs**, plus **34 diagnostic HTTP replays and
  reduction checks**, for **109 new HTTP evaluations**. Repetitions are not
  statistically independent workloads.
- **20 tests pass**, including real HTTP ambiguous-write retries, duplicate
  controls, weighted independent quota algorithms, payload/receipt validation,
  cancellation occupancy, and the original workbench tests.

## Initial complex connector: useful gains, incomplete fidelity

Three validation cases were selected by fixed position before results were
observed. Each implementation ran three times; values below are medians of
actual local wall seconds.

| Case | Jobs | Original | AI feedback patch | Hierarchical reference | Patch reduction vs original |
|---|---:|---:|---:|---:|---:|
| 0 | 11 | 6.143 s | 2.525 s | 2.680 s | 58.9% |
| 1 | 16 | 8.156 s | 3.523 s | 2.635 s | 56.8% |
| 2 | 9 | 5.152 s | 2.241 s | 2.435 s | 56.5% |

All HTTP jobs completed with correct transformed values, zero duplicate effects,
and no invalid writes. The patch used 26, 40 and 20 requests, versus the original's
29, 45 and 27. It sometimes beat the conventional hierarchical reference and
sometimes lost to it. No universal superiority was established.

Crucially, **the complete verification status was `no_verified_improvement`**:
HTTP outcomes agreed with simulation, but exact attempt counts and completion
predictions disagreed in some cases. The gate remained closed despite large
observed gains. The traces contain account-scope 429s over HTTP that were absent
in virtual execution. Real request-arrival timing and tight quota accounting
appear to be responsible; transport fidelity is not fully calibrated.

[Live experiment report](../runs/pipeline/20261031T182358087545Z/index.html)
· [All evidence](../runs/pipeline/20261031T182358087545Z/report.json)
· [Direct-vs-feedback analysis](../runs/pipeline/20261031T182358087545Z/analysis.json)

## Does experimental feedback beat direct model proposals?

Not overall in this small experiment. Across 24 paired virtual validation
successes, the median feedback/direct completion ratio was **1.000**. Feedback
was at least 5% faster on six cases and at least 5% slower on three. Both source
variants passed all 24 correctness checks.

Direct proposals consumed 36,340 input / 5,657 output tokens; feedback proposals
consumed 39,026 input / 4,730 output tokens. There were two completed model calls
per arm. This is exploratory evidence with different prompts, no counterbalanced
arm order, and no repeated model runs. Do not claim proven incremental AI value
from the feedback loop. The useful demonstrated value is executable evaluation,
strong comparisons, and detecting when a patch's claimed operating envelope
fails.

## Second connector: reject a negligible improvement

This example uses separately paced endpoint SDK clients that share an account.
The same recorded patches were tested on another 24-case matrix, with three
HTTP repetitions on the fixed first two validation cases.

| Case | Original | Frozen feedback patch | Requests original / patch |
|---|---:|---:|---:|
| 0 | 2.400 s | 2.383 s | 30 / 28 |
| 1 | 2.264 s | 2.268 s | 28 / 26 |

All correctness and candidate fidelity checks passed, but the performance gate
failed. The original was already near the patch's latency. Result:
**`no_verified_improvement`**. Retaining this outcome is part of the product.

[Second connector report](../runs/pipeline/20261031T184020726975Z/index.html)

## Counterexample search: distinguish simulation from confirmation

The separate 60-case search tested an engineer-declared contract: the patch must
be correct and finish within **1.1×** the hierarchical reference's time, with a
20ms minimum difference. This was a test criterion, not a promise made by the
model. Eight virtual cases violated it. The first violation was reduced by job
count, but its HTTP median ratio was approximately **1.005**, so it was labeled
**simulation-only**, not a confirmed performance failure.

[Blind search and non-confirming replay](../runs/falsify/20261031T183219417361Z/index.html)

A separate **post-hoc regression replay** used HTTP case 1 from the live experiment.
This was explicitly derived from a previously observed failure, not presented
as a fresh blind discovery. The full 16-job case repeatedly violated the same
1.1× reference contract:

- Earlier diagnostic replay: patch **3.519 s**, reference **2.638 s**.
- Later clean replay: patch **6.283 s**, reference **2.638 s**.
- Every source variant remained correct. The large timing variation is itself
  evidence that the patch's performance is sensitive to execution timing.

A six-job reduction appeared to violate the contract in a one-shot screen but
failed repeated confirmation. That failed reduction is retained. Reduction logic
now requires repeat confirmation before replacing a confirmed larger case.
The confirmed example remains 16 jobs; no globally minimal claim is made.

[Confirmed full HTTP counterexample](../runs/falsify/20261031T183824872617Z/index.html)
· [Exact scenario](../runs/falsify/20261031T183824872617Z/counterexample.json)
· [Failed smaller reduction](../runs/falsify/20261031T183527173952Z/index.html)

## What to present

“Tempo stress-tests AI-generated integration patches against interacting API
contracts. It reports measured benefits, shows where those benefits disappear,
and returns replayable evidence instead of a universal green badge.”

Demo: show the multi-stage connector and AI diff; show its initial HTTP gain;
open the 24-case operating envelope; show the token-accounting fidelity failure;
replay the explicit performance-contract counterexample. End with the second
connector's rejected near-no-op.

The proposal loop consumes training traces. HTTP-derived counterexamples are
currently exported for review; they are not automatically fed into a subsequent
repair cycle. Customer adaptation and provider extraction also remain future
work. Existing Speedscale, Codeflash, RetryProof and Antithesis capabilities
have substantial overlap. The distinction is a focused source-patch stress
workflow across provider-contract families, not demonstrated market exclusivity.

The updated dashboard endpoints, mixed experiment history, pipeline/falsification
artifact routes and JavaScript syntax were checked. Automated visual browser QA
was blocked by the browser tool's security policy; no alternative browser
mechanism was used to bypass it.
