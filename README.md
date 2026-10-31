# Tempo — do less API work, ship the same result

Public hackathon repository: https://github.com/kbwaj/Tempo

Tempo is an AI optimization workbench for async API integrations. It proposes
source changes, checks exact application outputs, and measures performance
against a controlled local HTTP server.

**[Watch the narrated demo](https://drive.google.com/file/d/1EITOMmRWj1Kh9E5W81FyC0pfDxwW1rlW/view)**
— approximately 2 minutes 32 seconds, including a continuous real-time execution.
Drive viewing permissions must be set before sharing this link with judges.

[Browse the recorded experiment](runs/catalog/20261031T191522732159Z/index.html)
· [Raw results](runs/catalog/20261031T191522732159Z/report.json)

## Run the UI

Clone this public repository first:

```sh
git clone https://github.com/kbwaj/Tempo.git
cd Tempo
```

Requirements: Python 3.11 or later with SelectorEventLoop support (macOS or Linux),
and permission to bind localhost sockets. The benchmark and UI use the Python
standard library. Run these commands from the repository root:

```sh
python3 tempo_prototype/tempo_demo.py
```

Then open **[Tempo UI](http://127.0.0.1:8877/)**.
This address runs on your own computer after starting the server; it is not a
public hosted deployment. The server opens the latest catalog experiment when
available. To generate a report first, use the replay command below.

## Reproduce the benchmark

```sh
python3 tempo_prototype/tempo_catalog.py \
  --agent replay \
  --proposal tempo_prototype/catalog/saved-proposal.json \
  --rounds 1 --validation-cases 32 --http-repeats 3
```

This evaluates the saved AI-generated source patch without a model call. It
stores the source, diffs, scenarios, complete outputs and HTTP measurements in
`runs/catalog/`. Restart or refresh the UI to inspect the latest report.

For a fresh AI proposal, install and sign into the Codex CLI, then run:

```sh
python3 tempo_prototype/tempo_catalog.py \
  --agent codex --rounds 2 --validation-cases 32 --http-repeats 3
```

Live proposals use your configured Codex account usage. The source validator and
subprocess execution are intended for trusted adapters, not hostile-code isolation.

## Run the live terminal demonstration

```sh
python3 tempo_prototype/tempo_live_demo.py
```

The original and AI-patched integrations execute consecutively against fresh
local servers with identical inputs and limits. Counters read server state
during execution. Longer real server waits make the demonstration readable;
its clock scale is displayed and differs from the report's shorter waits.

## Measured result

In the authored 48-product catalog workload, the configured original issued
**192 requests** and the AI patch issued **108**, with **identical outputs** and
**zero duplicate effects**. Median local HTTP completion was approximately
**3.38 seconds versus 1.84 seconds**, over three repetitions. The selected patch
passed 35 validation scenarios, with HTTP confirmation across three workloads.

The original already handles retries, rate limits, concurrency, timeouts and
stable write keys. The patch batches and shares immutable category and currency
lookups within a tenant and snapshot. Every product retains its own inventory
read and write. Transport and retry helper ASTs remain identical.

The declared API requires 48 inventory calls, 48 writes and at least 12 lookup
batches: **108 requests**. The patch reaches this request-count lower bound,
matching a manually authored semantic reference. These are controlled synthetic
measurements, not production benchmarks or a named competitor comparison.

## Verify and inspect

```sh
python3 -m unittest discover -s tempo_prototype/tests -v
```

- [Detailed results and demo guide](tempo_prototype/CATALOG_DEMO.md)
- [Original integration](tempo_prototype/catalog/baseline.py)
- [AI-generated integration](tempo_prototype/catalog/optimized.py)
- [Independent request-bound calculation](tempo_prototype/catalog/optimality.py)
- [Experiment runner](tempo_prototype/catalog/runner.py)
- [HTTP server and client](tempo_prototype/catalog/runtime.py)

New customer integrations require an adapter and a validated provider contract.
Automatic provider-model extraction and arbitrary repository optimization are
not implemented.
