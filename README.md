# Tempo — do less API work, ship the same result

Tempo is an AI optimization workbench for async API integrations. It proposes source changes, checks exact application outputs, and measures performance against a controlled local HTTP server.

[Watch the narrated demo](https://drive.google.com/file/d/1EITOMmRWj1Kh9E5W81FyC0pfDxwW1rlW/view) — 2 minutes 32 seconds, including real-time execution. Drive sharing permissions must allow viewers access.

## Run the UI

Requirements: Python 3.11+ on macOS or Linux, with permission to bind localhost sockets. The application uses the Python standard library. From the repository root:

```sh
python3 tempo_prototype/tempo_demo.py
```

Open **[Tempo UI](http://127.0.0.1:8877/)** after starting the server. This is a local application address, not a public hosted deployment. The UI opens the latest catalog report.

## Reproduce the benchmark

```sh
python3 tempo_prototype/tempo_catalog.py --agent replay --proposal tempo_prototype/catalog/saved-proposal.json --rounds 1 --validation-cases 32 --http-repeats 3
```

This evaluates the saved AI-generated patch without a model call. Source, diffs, scenarios, outputs and HTTP measurements are saved under `runs/catalog/`. Refresh the UI to inspect the latest run.

For a new AI proposal, install and sign into the Codex CLI, then run:

```sh
python3 tempo_prototype/tempo_catalog.py --agent codex --rounds 2 --validation-cases 32 --http-repeats 3
```

Live proposals use your configured Codex account usage. Adapters must be trusted; subprocess isolation is not a hostile-code sandbox.

## Live before-and-after demonstration

```sh
python3 tempo_prototype/tempo_live_demo.py
```

The original and AI-patched integrations execute consecutively against fresh local servers with identical inputs and limits. Live counters read server state. Longer server waits make the demonstration readable; the displayed clock scale differs from the report timing.

## Measured result

For an authored 48-product catalog workload, requests fall from **192 to 108**, with **identical outputs** and **zero duplicate effects**. Median local HTTP completion falls from approximately **3.38s to 1.84s**, over three repetitions. The patch passed 35 validation scenarios, with HTTP confirmation across three workloads.

The original already handles retries, rate limits, concurrency, timeouts and stable write keys. The patch shares immutable category and currency lookups within a tenant and snapshot, and batches compatible keys. Each product retains its own inventory read and write. Retry and transport helper ASTs stay identical.

Under the declared API contract, 48 inventory calls + 48 writes + at least 12 lookup batches require **108 requests**. The AI patch reaches that minimum, matching a manually authored semantic reference. These are controlled synthetic measurements, not production benchmarks or a named competitor comparison.

## Verify and inspect

```sh
python3 -m unittest discover -s tempo_prototype/tests -v
```

All 28 tests passed before publication.

- [Results and demo guide](tempo_prototype/CATALOG_DEMO.md)
- [Original integration](tempo_prototype/catalog/baseline.py)
- [AI-generated integration](tempo_prototype/catalog/optimized.py)
- [Request-count lower bound](tempo_prototype/catalog/optimality.py)
- [Experiment runner](tempo_prototype/catalog/runner.py)
- [Real HTTP server and client](tempo_prototype/catalog/runtime.py)

New customer integrations require an adapter and a validated provider contract. Automatic model extraction and arbitrary repository optimization are not implemented.
