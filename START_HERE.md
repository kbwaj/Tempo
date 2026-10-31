# Tempo — ready-to-present catalog optimization demo

```sh
python3 tempo_prototype/tempo_demo.py
```

Open http://127.0.0.1:8877.

**Live AI result:** 48 products, **192 → 108 HTTP requests**, **3.38 → 1.84 seconds**,
identical output, zero duplicate writes. The patch reaches the declared API's
**108-request lower bound**. The original already has robust retry and rate-limit
configuration; the AI removes redundant business-level API work.

[90-second presentation script and results](tempo_prototype/CATALOG_DEMO.md).

The main screen leads with the successful catalog demo. Use **Re-run HTTP
benchmark** for fresh execution of the saved model patch (no model call), or
**Generate a new AI patch** to invoke your signed-in Codex CLI.

Replay requires Python with SelectorEventLoop support and loopback networking.
Live mode also requires an installed, signed-in Codex CLI. All earlier research
and experiment evidence is retained under `runs/` and in the engineering lab.

These are synthetic local measurements under an explicit bulk/snapshot API
contract. New customer integrations require adaptation and provider calibration.
