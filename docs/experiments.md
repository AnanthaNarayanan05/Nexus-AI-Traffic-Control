# Experiments

Spec §48–56. Experiments run **real headless simulations** — no synthetic numbers.

## 1. Configuration

```yaml
# configs/experiments/<name>.yaml
name: mixed_crisis_ai_vs_fixed
controllers: [ai, fixed_time]        # run each
scenario: mixed_crisis               # preset id or inline ScenarioConfig
seeds: [1, 2, 3, 4, 5]               # one episode per seed per controller
episode_length_s: 3600
model_versions: {a2c: latest, dqn: latest, ppo: latest}
```

## 2. Runner

`ExperimentManager.run(config)`:
1. resolve config → freeze a `reproducibility` blob (seed list, scenario, model versions, reward weights,
   safety config, config digest, code version)
2. for each `(controller, seed)` → headless `SimulationManager` at fixed step count, no wall-clock pacing
3. collect the episode `MetricSnapshot`
4. aggregate per controller (§2 of [`metrics.md`](metrics.md)) and compute AI-vs-baseline deltas
5. persist to SQLite (`experiments`, `experiment_metrics`, `experiment_configs`)
6. stream `experiment_update` progress to any connected UI

CLI: `python -m scripts.experiments.run --config configs/experiments/mixed_crisis.yaml`

## 3. Comparison mode (spec §50)

`GET /api/v1/experiments/{id}` returns both controllers' aggregates side by side; the UI renders the
fixed-time vs. NEXUS AI table (queue, waiting, throughput, stops, fuel, CO₂, emergency delay, violations)
with per-metric improvement % and CI. Synchronized replay: both runs recorded, scrubbed on one timeline.

## 4. Determinism & reproducibility (spec §54, §83)

Reproducible: `(scenario, seed, controller, model versions, config digest)` → identical metric series in
headless mode. **Not** bit-reproducible across: different CPU/BLAS for the torch forward pass (argmax ties
are stable, but logits differ in the last ~1e-6), different Python/numpy minor versions. The stored
`reproducibility` blob records everything needed to re-run; `scripts/validation/reproduce.py <exp_id>`
re-runs and diffs.

## 5. Persistence schema (spec §55, §90)

```
experiments(id, name, created_at, scenario, controllers, seeds, status, code_version)
experiment_configs(experiment_id, key, value_json)          # frozen reproducibility blob
experiment_metrics(experiment_id, controller, seed, family, metric, value)
models(id, agent, version, created_at, episodes, seed, env_version, config_json, perf_json)
simulation_runs(id, experiment_id, controller, seed, started_at, ended_at, episode_metrics_json)
events(id, run_id, t, category, severity, description, meta_json)
replays(id, run_id, path, size_bytes, created_at)
```

## 6. Export (spec §78–79)

`POST /api/v1/export {experiment_id, format}` → CSV (one row per `controller,seed,metric`) or JSON (full
aggregates + reproducibility blob). Optional HTML report via `scripts/experiments/report.py`.
