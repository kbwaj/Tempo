# Tempo: run the complete optimization loop

Tempo now takes an adapted async integration, asks a real model to propose source
changes, evaluates those changes in virtual time, freezes a selection, and
confirms it over real TCP/HTTP against an independently implemented local server.
It generates a shareable HTML report with source diffs, traces, controls, and
failed experiments. Everything runs with Python's standard library.

## Start the demo

From the workspace root:

```sh
python3 tempo_prototype/tempo_demo.py
```

Open http://127.0.0.1:8877. Choose an example, then choose a driver:

- **Live Codex:** invokes the installed, signed-in `codex exec`. The model reads
  the original source and training traces, returns replacement source, and gets
  feedback for the next proposal. This consumes your configured Codex usage.
- **Replay:** re-evaluates a saved, genuinely model-generated proposal. No model
  is called, and the report says replay. Useful for a predictable presentation.
- **Evaluate original:** runs the original and references without proposing code.

The launcher allows one active run. A typical run includes 2 proposals, 2 virtual
training cases, 2 validation cases, and 24 HTTP evaluations (4 implementations ×
2 cases × 3 repeats). Runtime depends on model response and real waiting. The
launcher stays bound to loopback. Run this in a trusted local workspace.

CLI equivalent:

```sh
python3 tempo_prototype/tempo_workbench.py \
  --example tempo_prototype/examples/serial_import.json \
  --agent codex --rounds 2 --http-repeats 3
```

For a repeatable demo without another model call:

```sh
python3 tempo_prototype/tempo_workbench.py \
  --example tempo_prototype/examples/serial_import.json \
  --agent replay \
  --proposal tempo_prototype/examples/proposals/serial_import.json \
  --rounds 1 --http-repeats 3
```

Use `--model NAME` only if you want to override your configured Codex model.
`--output PATH` selects the evidence directory. Runs never overwrite earlier
runs. CLI success means the experiment completed, not that an improvement was
verified: inspect `status` and `gates` in its report. One-repeat runs are smoke
checks and cannot receive verified status. Driver failure is retained and never
silently replaced with a scripted proposal.

## Try your own example

Copy an example manifest to a new file and point `source` at your integration's
Python file. Paths are relative to the manifest. You can put the manifest
anywhere and use `--example /absolute/path/example.json`; place it under
`tempo_prototype/examples/` to make it appear in the launcher. Put an optional
saved proposal at `examples/proposals/NAME.json` to enable replay for that example.

The adapter has two entrypoints:

```python
import asyncio

def configure(provider):
    return {'lock': asyncio.Lock()}

async def integrate(provider, job, context):
    response = await provider.post(job, idempotency_key=f'job-{job}')
    return response.status == 200
```

The runner calls `integrate` concurrently for each integer job ID. Use the port's
`post` method for outbound requests; the same source then runs against simulated
I/O and the local async HTTP client. The adapter API exposes only `post` and an
immutable `s` contract: jobs, limit, window, scale, deadline, quota_mode, service,
and slow_service. It does not expose server effects, counters, or validation
seeds. Each job can submit only its own ID. Return success only after a 200.

Time in the contract is logical seconds. Multiply sleep and timeout durations by
`s.scale`; event-loop time is in elapsed wall/virtual seconds. Response
`retry_after` is expressed in logical seconds after HTTP serialization, so also
multiply by scale. HTTP uses integer seconds on the wire. The simulator models
that rounding explicitly.

Supported source imports are `asyncio`, `math`, `random`, and `collections`.
Arbitrary existing Python repositories, SDK imports, real endpoints, automatic
provider extraction, and automatic call-site adaptation are not supported. This
is **arbitrary adapted examples within an explicit contract**, not a claim to
optimize arbitrary programs. More complex clients need another adapter/transport.

A manifest specifies `name`, `source`, `objective` (`latency` or `requests`),
`max_other_metric_regression` (default 0.1), `training`, and `validation`. Scenario
fields are those of `tempo.Scenario`; see the checked-in JSON examples. Vary
quota mode, jobs, limit, window, response delays and slow-job seed. Keep validation
scenarios separate from training. Once inspected or reused, call them regression
cases rather than fresh holdouts. The CLI caps workload size and real deadlines
so accidental large examples do not run indefinitely.

## What the experiment verifies

1. Measure original source, a shared smooth quota limiter, and a provider-aware
   burst limiter. Both references use stable keys and robust timeout/retry logic.
2. Send only source, training scenarios/results, and previous training feedback
   to the proposer. Save prompts, CLI JSON events, raw responses, source, diffs,
   and every rejected attempt. Reject a proposal if the driver used tools rather
   than relying on supplied context.
3. Select by correctness, then objective, while bounding the other metric.
   Freeze the selected source before evaluating validation. There is no model
   feedback from validation or HTTP confirmation.
4. Re-run original, both references, and selected source over local HTTP. Rotate
   order between repeats. Measure effects on the server, not from client claims.
5. Compare simulated/HTTP counts exactly and completion within a disclosed
   tolerance: max(80ms, 15% of simulated completion). Preserve mismatches.
6. Require validation correctness, real HTTP correctness, candidate fidelity,
   improvement in validation and every HTTP case, tradeoff bounds, and at least
   three HTTP repeats before issuing verified status. A failed original supports
   a correctness repair, not a successful-run latency speedup.

The server has its own quota implementation rather than inheriting the simulated
Provider. Both implement the same authored contract: fixed windows or a token
bucket, initially full quota, no external consumers, stable idempotency without
expiry, and a write that commits before a delayed response. The fixed-window
local epoch is known approximately at configure time. This is a controlled
contract, not an assumption about an unknown real API. No outages, arbitrary
5xx patterns, connection pools, distributed quota coordination, or expiry are
modeled. Independent implementations reduce shared-code blind spots but do not
prove fidelity to any production provider.

Python subprocesses isolate crashes and enforce wall timeouts; they are **not a
security sandbox**. The source validator restricts supported syntax/imports and
worker environments omit credentials, but run only trusted adapters/model
outputs. Do not feed hostile code or attach production secrets. The model driver
uses Codex's read-only mode and requests no tool use. Validation is withheld from
its prompt; this is an evaluation protocol, not cryptographic data isolation.

## Evidence and presentation

`runs/workbench/TIMESTAMP/` contains `index.html`, `report.json`, original and
selected source, source hashes, training/validation/HTTP traces, model prompts,
model event logs, and patch diffs. Current runs also hash the evaluation engine.
No candidate is auto-applied to your source file. The HTML report labels live
runs and replay, shows timing ranges and every standard comparator, and never
turns a failed fast run into a latency win.

Start with the serialized importer, show the source diff, then the repeated HTTP
results. Show the burst-aware reference beside it: the patch matches ordinary
well-configured scheduling. Then show the retry example as a correctness repair,
and the already-optimized control as a rejected optimization. That demonstrates
an optimization workflow and its limits rather than claiming a new algorithm.

Tests (one test opens a loopback server):

```sh
python3 -m unittest discover -s tempo_prototype/tests -v
```

## Generate a new scenario matrix

For a new adapted source, generate scenarios without selecting for good results:

```sh
python3 tempo_prototype/tempo_scenarios.py \
  --source /path/to/integration.py \
  --output /path/to/custom-example.json \
  --seed 731901 --cases-per-split 4

python3 tempo_prototype/tempo_workbench.py \
  --example /path/to/custom-example.json --agent codex
```

The generator varies quota mechanism, load, burst capacity, response delays and
slow-job IDs. It uses separate deterministic seeds for training and validation,
refuses to overwrite an existing matrix, and never filters cases by outcome.
This is a reproducible stress family, not automatic production-model extraction.
Use a different seed for another run; keep failures as part of the evidence.

The model driver follows the documented [Codex non-interactive structured-output
interface](https://learn.chatgpt.com/docs/non-interactive-mode). Authentication
uses your installed CLI; no API key is copied into the workbench.
