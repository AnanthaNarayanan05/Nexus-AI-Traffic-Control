# Experiments

Spec §16, §48–56. Experiments run **real headless simulations** — no synthetic numbers
(§84). One Fixed-Time vs AI comparison at a time.

Status: **implemented (R9 P1, 2026-09-08)** — service + REST/WS + persistence + Experiment
Lab UI. CSV/JSON export added in P4 (see [`exports.md`](exports.md)); synchronized replay
is deferred (see [`replay.md`](replay.md) §8).

## 1. What an experiment is

A comparison of one or more **controllers** on a single **scenario** over a fixed set of
**seeds** (one headless episode per controller per seed). Controllers:

| id | what runs |
|---|---|
| `fixed_time` | the fixed-cycle baseline (`FixedTimeController`) |
| `a2c` | the A2C agent — emergency-vehicle prioritization |
| `dqn` | the DQN agent — efficiency / fuel / emissions / safety |
| `ppo` | the PPO agent — adaptive congestion reduction |

Any other controller id is rejected (`422`).

Per agent controller a **model selector** picks the weights:

| selector | resolves to |
|---|---|
| `untrained` (default) | fresh randomly-initialised weights — labelled `"<agent> untrained"` |
| `active` | the agent's `active` registry checkpoint (`ModelRegistry.active`) |
| `latest` | the newest registry checkpoint (`ModelRegistry.latest`) |
| `<registry model id>` | that specific row |

The checkpoint path is resolved **up front** in `start()` — before the DB row is created —
so a missing/promoted-away checkpoint fails fast with `422` and nothing half-writes.

## 2. Runner — `app/training/experiment_service.py`

`ExperimentService` mirrors `TrainingService`: the heavy work runs on its own daemon
thread and only ever *publishes* an immutable snapshot; REST/WS read `snapshot()`.

`start(name, scenario, controllers, seeds, models, episode_seconds)`:
1. validate controllers / seeds (≤ 16) / `episode_seconds` (60–7200); resolve the scenario
   (`404` if unknown); resolve every agent checkpoint (`422` if absent).
2. freeze a `reproducibility` blob: `created_at`, scenario id + name, seeds, controllers,
   baseline, `episode_seconds`, per-agent `models` plan, `config_digest`, `git_commit`,
   `decision_interval_s`, `step_length_s`, per-agent `reward_weights`, `safety` config,
   `torch_version`.
3. `ExperimentBusy` (`409`) if a run is active; else create the `_JobState` + thread.
   `experiment_id = f"exp-{YYYYMMDDThhmmssSSSZ}"` (millisecond stamp).
4. worker: `ExperimentStore.create(...)` → for each controller run
   `training.evaluation.evaluate(controller, scenario_id, seeds, checkpoint=…, episode_seconds=…,
   on_episode=…)` (deterministic policy, safety authoritative §113); bump `episodes_done`
   per episode → `compare(results, baseline_label=…)` → `ExperimentStore.complete(...)`.
   On any exception: `ExperimentStore.fail(experiment_id, error=…)` and the job phase → `failed`.

Baseline = `fixed_time` if selected, else the first controller.

## 3. Comparison blob — `training.evaluation.compare()`

```
{ scenario, baseline, seeds, n_episodes,
  metrics: { "<family>.<metric>": {
      lower_is_better: bool,
      values: { "<label>": { mean, ci_half_width, improvement_pct_vs_baseline } } } } }
```

18 metric keys across `traffic` / `environmental` / `emergency` / `safety`
(`METRIC_DIRECTION` is the single source of truth for which direction is better).
`improvement_pct_vs_baseline` is **signed so that positive always means better** for that
metric's direction, and is `None` when the baseline mean is ~0 (no meaningful ratio) or for
the baseline's own row. `ci_half_width` is the 95% CI half-width (`0` when n < 2).

## 4. REST + WebSocket

| endpoint | |
|---|---|
| `GET /api/v1/experiments?history=N` | `{seq, running, job, history:[summary…]}` |
| `POST /api/v1/experiments` | body `{name?, scenario, controllers[], seeds[], models{}, episode_seconds?}` → `202` + snapshot. `409` busy · `404` unknown scenario · `422` bad controller/seed/missing checkpoint |
| `GET /api/v1/experiments/{id}` | full detail (reproducibility + comparison + per-controller results) or `404` |

`experiment_update` WS frame carries the same snapshot whenever `seq` changes and a job exists.

## 5. Persistence — `experiments` table (`app/persistence/models.py`)

```
experiments(
  id, name, created_at, finished_at, wall_time_s,
  scenario, controllers (JSON), seeds (JSON), episode_seconds, baseline,
  reproducibility (JSON), comparison (JSON), results (JSON),
  status ∈ {running, completed, failed}, error)
```

`ExperimentStore` (`app/persistence/experiments.py`): `create` (status `running`),
`complete` (writes comparison + results + wall time in place), `fail`, `get` (full),
`list` (summary-only, newest first). Written by the worker thread; the live `_JobState`
snapshot is the fresher source while a run is in progress.

## 6. Experiment Lab UI — `#/experiments` (`frontend/src/experiments/`)

- **`ExperimentLab.tsx`** — scenario `<select>` (from the scenario store), controller
  checkboxes with a per-agent model `<select>`, seed comma-list (default `1, 2, 3`),
  optional episode-seconds → `POST /experiments`. Live progress panel (phase badge,
  `episodes_done / episodes_total`, current controller). Past-experiments table; clicking a
  completed row loads its detail + reproducibility.
- **`ComparisonTable.tsx`** — the honest table (§16):
  - the **baseline column is always rendered** — a % is never shown without the absolute
    values behind it;
  - each metric row shows its **direction** (↓ lower better / ↑ higher better);
  - each AI cell: `mean ± CI`, then the **absolute Δ** and the **direction-aware %** —
    green only when the metric moved the *better* way, red when worse;
  - **"within noise"** when `|Δ| ≤ baseline CI + candidate CI` (tone forced neutral);
  - **Winner** = the best-mean controller, but only named when it clears the runner-up by
    more than their combined CI — otherwise "≈ tie" (so an all-equal row crowns nobody).

## 7. Reproducibility (spec §54, §83)

The stored `reproducibility` blob records everything needed to re-run:
`(scenario, seeds, controllers, model plan, config digest, git commit, reward weights,
decision/step cadence, torch version)`. Headless evaluation is deterministic per
`(scenario, seed, controller, checkpoint)`; not bit-reproducible across different
CPU/BLAS for the torch forward pass or different Python/numpy minor versions.

## 8. Export

`GET /api/v1/export/experiments/{id}?format=csv|json` — CSV is one row per
`(metric, controller)` with the full `summarise_series` stats + honest
`improvement_pct_vs_baseline`; JSON is the whole stored row. The Experiment Lab links to
both from a completed run's detail panel (R9 P4). See [`exports.md`](exports.md).

## 9. Not yet built

- **Synchronized replay** of the compared runs on one timeline — R9 P3 (§18). Needs the
  experiment runner to keep per-decision data; today it records episode aggregates only.
  Deferred (see [`replay.md`](replay.md) §8).
