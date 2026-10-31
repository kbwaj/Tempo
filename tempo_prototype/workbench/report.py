"""Dependency-free, shareable experiment report; no invented live metrics."""
import html
import json
from pathlib import Path


def render(report, path):
    esc = lambda x: html.escape(str(x))
    experiments = report.get('experiments', [])
    cards = []
    for case in report.get('comparisons', []):
        rows = []
        for name, values in case['policies'].items():
            latency = f"{values['completion_seconds']:.3f}s" if values.get('all_correct') else 'incomplete'
            requests = values.get('requests', values.get('observed_requests', '—'))
            spread = values.get('completion_range')
            spread_text = f'{spread[0]:.3f}–{spread[1]:.3f}s' if spread else '—'
            rows.append(f'<tr><td>{esc(name)}</td><td>{"PASS" if values.get("all_correct") else "FAIL"}</td><td>{requests}</td><td>{latency}</td><td>{spread_text}</td></tr>')
        candidate = case['candidate_vs'].get('original', {})
        claim = 'Original incomplete: correctness repair; no latency speedup claimed'
        if 'completion_ratio' in candidate:
            claim = f"{(1-candidate['completion_ratio'])*100:.1f}% completion-time reduction · {(1-candidate['request_ratio'])*100:.1f}% request reduction vs original"
        scenario = report['validation'][case['case']]['scenario']
        cards.append(f'<section class="card"><div class="eyebrow">SEALED CASE {case["case"]+1} · {esc(scenario["quota_mode"])} QUOTA</div><h2>{esc(scenario["name"])}</h2><p>{esc(claim)}</p><div class="scroll"><table><thead><tr><th>Integration</th><th>Correctness</th><th>Requests¹</th><th>HTTP completion¹</th><th>Observed range</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>')
    patches = []
    for exp in experiments:
        i = exp['iteration']
        diff = path.parent/f'patch-{i}.diff'
        text = diff.read_text() if diff.exists() else exp.get('error', 'No patch produced')
        patches.append(f'<details><summary>Proposal {i+1} · {"selected in training" if exp.get("selected_on_training") else "retained"}</summary><p>{esc(exp.get("rationale", exp.get("error", "")))}</p><pre>{esc(text)}</pre></details>')
    gates = ''.join(f'<div class="gate {"pass" if value else "fail"}"><span>{"✓" if value else "×"}</span> {esc(key.replace("_", " "))}</div>' for key, value in report.get('gates', {}).items())
    fidelity = report.get('http', [])
    matches = sum(r.get('counts_match', False) and r.get('timing_matches', False) for r in fidelity)
    outcome = report.get('outcome', 'performance_improvement' if all(x['results']['original'].get('correct') for x in report.get('validation', [])) else 'correctness_repair')
    source = path.parent/report.get('selected_source', 'original.py')
    source_text = source.read_text() if source.exists() else ''
    doc = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Tempo · Verified experiments</title><style>
:root{color-scheme:dark;--bg:#0b111b;--panel:#111c2c;--line:#24354b;--muted:#9ab0c7;--accent:#7cf3c6}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#e9f0f9;font:15px/1.6 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif}main{max-width:1160px;margin:auto;padding:48px 28px}nav{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:22px}.brand{font-size:28px;font-weight:800;letter-spacing:-1px}.brand b{color:var(--accent)}.eyebrow{color:var(--accent);font-size:11px;letter-spacing:2px;font-weight:700}h1{font-size:clamp(32px,5vw,56px);line-height:1.1;letter-spacing:-2px;max-width:850px;margin:28px 0 20px}h2{font-size:23px;letter-spacing:-.5px}p{color:var(--muted);max-width:850px}.status{border:1px solid var(--line);border-radius:30px;padding:7px 15px;color:var(--accent)}.card{background:var(--panel);border:1px solid var(--line);padding:26px;border-radius:16px;margin:24px 0}.gates{display:flex;flex-wrap:wrap;gap:10px;margin:25px 0}.gate{border:1px solid var(--line);padding:8px 13px;border-radius:8px}.pass span{color:var(--accent)}.fail span{color:#ffbb88}table{width:100%;border-collapse:collapse;text-align:left}th{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:1px}td,th{padding:13px 12px;border-bottom:1px solid var(--line)}td:first-child{font-family:monospace;color:#c9d9ee}tr:last-child td{border:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#080e17;border:1px solid var(--line);padding:22px;border-radius:10px;font-size:12px;color:#c3d8ee}summary{cursor:pointer;padding:17px 0;font-weight:600}a{color:var(--accent)}small{color:var(--muted)}.scroll{overflow:auto}.steps{display:flex;gap:12px;flex-wrap:wrap;margin:32px 0}.steps span{padding:10px 16px;border:1px solid var(--line);border-radius:8px;color:var(--muted)}footer{margin-top:40px;border-top:1px solid var(--line);padding-top:20px;color:var(--muted);font-size:12px}</style></head><body><main>'''
    doc += f'<nav><div class="brand">tempo<b>.</b></div><div class="status">{esc(report["status"].replace("_", " "))}</div></nav><div class="eyebrow" style="margin-top:44px">SOURCE OPTIMIZATION WORKBENCH</div><h1>{esc(report["name"])}</h1><p>Propose a source patch. Test real coroutines in virtual time. Confirm the selected patch over local HTTP.</p><div class="steps"><span>01 Baseline</span><span>02 Agent proposals</span><span>03 Sealed validation</span><span>04 HTTP confirmation</span></div><div class="gates">{gates}</div>'
    doc += f'<p>Driver: <strong>{esc(report["agent"])}</strong> · {len(experiments)} preserved proposal attempts · {len(fidelity)} HTTP runs · {matches}/{len(fidelity)} count-and-timing fidelity checks passed. Timing tolerance: max(80ms, 15% of simulated completion).</p>'
    if report.get('error'):
        doc += f'<section class="card"><h2>Run failed</h2><pre>{esc(report["error"])}</pre></section>'
    if outcome == 'correctness_repair':
        doc += '<section class="card"><h2>Correctness repair</h2><p>The original did not complete all validation cases correctly. This run establishes a correctness repair; it does not support a successful-run speedup against the original. Performance comparisons use the successful standard references.</p></section>'
    doc += ''.join(cards)
    doc += '<small>¹ Median across repetitions. Completion is actual wall seconds. Failed runs are excluded from performance comparisons and shown as incomplete. All effects are measured on the server. These are authored synthetic workloads, not production benchmarks.</small>'
    doc += '<section class="card"><h2>What the result supports</h2><p>A gain over the original integration demonstrates a measured patch benefit on these cases. Matching the burst-aware reference means the patch recovered ordinary configuration performance; it does not establish a new algorithm or an advantage over the strongest baseline. Validation scenarios were evaluated only after source selection; they remain authored fixtures, not independent customer workloads.</p><p>Fidelity compares independently implemented server quotas with calibrated simulation. It does not validate a real provider model. New examples require the adapter contract; automatic repository adaptation and model extraction are outside this prototype.</p></section>'
    doc += f'<section class="card"><h2>Source changes & failed attempts</h2>{"".join(patches) or "<p>No proposals requested.</p>"}</section><details><summary>Selected integration source</summary><pre>{esc(source_text)}</pre></details>'
    doc += '<section class="card"><h2>Evidence</h2><p><a href="report.json">Full report and traces</a> · <a href="manifest.json">Scenario manifest</a> · <a href="selected.py">Selected source</a></p><p>Every attempt retains its model output, prompt, source diff, execution result, and failure. Source selection uses training only; real HTTP confirmation may reject it.</p></section>'
    doc += f'<footer>{esc(report["scope"])}<br>Original source SHA-256: {esc(report["original_sha256"])}<br>Selected source SHA-256: {esc(report.get("selected_sha256", "pending"))}</footer></main></body></html>'
    path.write_text(doc)
