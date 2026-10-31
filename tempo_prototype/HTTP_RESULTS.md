# HTTP experiment results

Synthetic eight-job fixtures; three repeats per policy and quota mode. Times below are actual wall seconds (median), not production estimates.

| Quota | Policy | Requests | Duplicate effects | Wall seconds |
|---|---|---:|---:|---:|
| fixed | retry_reference | 15 | 0 | 2.274 |
| fixed | quota_baseline | 8 | 0 | 1.187 |
| fixed | candidate | 9 | 0 | 1.837 |
| fixed | unsafe_no_idempotency | 20 | 6 | 4.307 |
| token | retry_reference | 15 | 0 | 2.273 |
| token | quota_baseline | 8 | 0 | 1.187 |
| token | candidate | 8 | 0 | 0.896 |
| token | unsafe_no_idempotency | 20 | 6 | 4.307 |

Acceptance failures: 0. Exact virtual/HTTP count matches: 12/24. All safe policies acknowledged eight jobs without duplicate effects; unsafe controls produced six duplicates each.

The tuned candidate loses to ordinary quota configuration on the fixed-window fixture, but finishes faster on the token-bucket fixture. This is evidence for provider-dependent tradeoffs, not a universal optimization win. Integer Retry-After serialization prevents a claim of timing fidelity to the original fractional-delay model.

Full traces: [report.json](../runs/http/20261031T165902090991Z/report.json). The earlier permission-denied bind attempt is retained alongside this run.

The original five experiment scripts were rerun successfully; the original 53/168 request counts, 54.401/51.418 simulated seconds, and 60/60 candidate successes reproduced. No autonomous agent, model extraction, or customer adaptation has been added.
