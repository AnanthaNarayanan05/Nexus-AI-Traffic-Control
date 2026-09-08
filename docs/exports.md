# Exports

Spec §23, §64–79 ("CSV / JSON exports + optional report"). Turn a stored **experiment**
(a Fixed-Time vs AI comparison) or a captured **replay** (a decision timeline) into a
file you can drop into a spreadsheet, a notebook or a report.

Status: **implemented (R9 P4, 2026-09-08)** — CSV + JSON for both record types. HTML
report is not built (the comparison table in the Experiment Lab is the on-screen report).

## 1. What you can export

| Source | From the UI | CSV shape | JSON shape |
|---|---|---|---|
| Experiment | Experiment Lab (`#/experiments`) → open a completed run → **Export CSV / JSON** | one row per `(metric, controller)`: `n / mean / median / std / min / max / ci_half_width` + honest `improvement_pct_vs_baseline` | the whole `experiments` row — reproducibility blob, comparison blob, and every per-seed episode aggregate |
| Replay | Replay Lab (`#/replay`) → select a replay → **Export CSV / JSON** | one row per decision: coordinator `candidate_phase` → authoritative `applied_phase`, `safety_action`, `violated_rules`, each agent's total reward, the flat metric snapshot | the whole `replays` row — full `DecisionRecord` timeline, events, episode metrics |

## 2. REST surface

```
GET /api/v1/export/experiments/{experiment_id}?format=csv|json
GET /api/v1/export/replays/{replay_id}?format=csv|json
```

- `format` defaults to `csv`; an unknown value is a **422** (the route declares a
  `Literal["csv","json"]`).
- Unknown id → **404**. An experiment with no completed comparison, or a CSV request for
  a replay with no timeline → **409** (an empty file is never emitted — spec §98).
- The response carries `Content-Disposition: attachment; filename="…"`, so the browser
  downloads it. The frontend links to these URLs directly (`lib/api.ts` → `exportUrls`);
  it does not `fetch` + blob them.
- The download filename stem is sanitised to `[A-Za-z0-9_-]` (spec §88) — nothing in a
  path segment can walk a directory or spoof an extension.

GET (not the `POST /api/v1/export` originally sketched in system-flow.md) so a plain
link works and the URL can be shared / curled.

## 3. Honesty (spec §84)

The exporters in `app/api/exporters.py` are **pure functions over the stored record**.
They never run a simulation, never recompute a metric, and never fill a gap with a
zero: a metric absent from a record is absent from the CSV (an empty cell), and a
baseline row's `improvement_pct_vs_baseline` is blank, not `0`. Everything in an export
traces back to a real measured episode or a real captured decision.

## 4. Not built

- **HTML / PDF report.** The spec calls it "optional". The Experiment Lab comparison
  table is the rendered report; JSON export covers programmatic use.
- **Bulk export** (all experiments / all replays in one archive). One record at a time.
- **Training-run export.** Training curves are already on disk as `models/<agent>/<run>.json`;
  no REST export was added for them.
