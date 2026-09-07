# Feature status

Honest state of the build (spec §98 — nothing unimplemented is dressed up as done). Updated per slice.

Legend: ✅ working end-to-end · 🟡 partial / scaffolded · ⬜ not started

## Slice 1 — Foundation + simulation + full three-agent vertical slice  *(complete, inference-only)*

Verified end-to-end 2026-09-07: built-in sim → FastAPI → WebSocket → PixiJS render →
A2C/DQN/PPO decision loop → coordination → safety → applied phase → measured metrics,
all in the browser. `pytest tests/` (176, incl. Slice 2) + `vitest` (35) green;
`npm run build` + `eslint` + `tsc -b` clean.

| Area | State | Notes |
|---|---|---|
| Monorepo structure, configs, docs | ✅ | |
| §120 design docs | ✅ | architecture, system-flow, simulation schema, a2c/dqn/ppo, coordination, safety, metrics, experiments, persistence, training, assumptions, limitations |
| `SimulationAdapter` + `BuiltinAdapter` | ✅ | 4-way intersection, Poisson arrivals, IDM-lite car-following, signal SM, fuel/emission accrual; deterministic per seed |
| `SumoAdapter` | ⬜ | interface stub + install guide only |
| Typed schemas (`SimulationState`, recommendations, decisions, safety, metrics, events) | ✅ | |
| Signal controller + phase state machine | ✅ | served→YELLOW→ALL_RED→served; authoritative `approach_colors` on the wire |
| Safety constraint layer | ✅ | 8 rules, authoritative; `action_taken` ∈ APPLIED/REWRITTEN_TRANSITION/BLOCKED_HOLD/FORCED_CHANGE/EMERGENCY_TIMEOUT |
| Coordination engine | ✅ | deterministic priority ladder, weighted phase scoring, consensus detection |
| A2C agent (net, state builder, reward, inference) | ✅ | inference-only in the live loop; `is_trained=false` reported honestly |
| DQN agent | ✅ | inference-only in the live loop; raw Q-values exposed |
| PPO agent | ✅ | inference-only in the live loop; GAE/clip `learn()` exercised by training (Slice 2) |
| Fixed-time baseline controller | ✅ | 60 s cycle; measurably different from AI mode |
| Manual control | ✅ | HOLD/SWITCH/EXTEND/REDUCE/SET_* via REST + WS |
| Metrics aggregator | ✅ | rolling + episode windows; fuel/CO₂ flagged ESTIMATED |
| FastAPI app + REST + WebSocket hub | ✅ | `command_result` channel separate from `status` |
| `SimulationManager` decision loop | ✅ | own thread; reward for decision N realised at N+1 (on-policy order) |
| Frontend shell + command bar | ✅ | start/pause/step/reset, mode, scenario, speed, inject; live/paused, sim clock, seed, cfg digest |
| PixiJS `SimulationStage` | ✅ | config-driven geometry, roads, vehicles (eased), signal lamps, queue counts, view-radius zoom |
| A2C / DQN / PPO dashboard panels | ✅ | actor bars, critic V(s), Q(s,a), queue pressure, reward decomposition, UNTRAINED badge |
| Coordination bar | ✅ | 3 recs → winner + basis → safety verdict + ladder trace + score breakdown |
| Metrics row + event timeline | ✅ | filterable TRAFFIC/AI/EMERGENCY/SAFETY/VIOLATION/SYSTEM; server errors surfaced verbatim |
| Agent inspector REST polling | ✅ | `GET /agents/{name}` on a 2 s poll; not streamed (cost) |
| Tests (reward, state builders, agents, coordination, safety, sim determinism, API, training, evaluation) | ✅ | `pytest tests/` → 176 pass (agents 64, coordination 14, safety 17, simulation 10, integration/API+WS 30, training 16, evaluation 8, training-service 5, persistence 12); `vitest` → 35 pass (format, store wiring incl. `training_update`, scene geometry, Training Lab, model-mode bar) |

## Slice 2 — training loops  *(in progress)*

Headless single-agent RL: real episodes → real reward → real gradient steps → checkpoints
→ observable episode-return curve. Docs: [`training.md`](training.md).

| Area | State | Notes |
|---|---|---|
| `make_reward_context()` shared by live loop + trainer | ✅ | one reward code path (§84); `SimulationManager` refactored onto it |
| `TrainingEnv` — headless single-agent episode driver | ✅ | same pipeline as the live loop for one agent; safety authoritative (§113); terminal transition realised with `done=True` |
| `TrainingManager` — N-episode run, checkpoints, run metrics | ✅ | `models/<agent>/` checkpoints + `latest.pt` + `<run_id>.json` (returns/losses/override counts/episode metrics + reproducibility blob) |
| `scripts/training/train.py` CLI (`make train`) | ✅ | `--agent --episodes --scenario --seed --checkpoint-every --episode-seconds`; per-episode progress line |
| Evaluation harness (`evaluation.py`, `scripts/training/evaluate.py`) | ✅ | deterministic policy, safety authoritative; fixed-time vs untrained vs trained over held-out seeds; mean ± 95% CI + improvement %; JSON report |
| A2C training | ✅ | n-step updates from episode 1. **Run `a2c-20260907T155926Z`, `emergency_heavy`, 200 episodes, 509 s.** Return +422 (ep 1–25) → +475 (ep 151–175); entropy 1.61 → 0.31. `models/a2c/latest.pt` = `a2c-v1.4-dev`. |
| A2C evaluated (8 held-out seeds) | ✅ | vs fixed-time: emergency delay **+28.8%**, emergency wait **+52.2%**, avg waiting **+61.1%**, speed +33.9%; throughput −7.7% (noisy). Trained ≫ untrained (untrained is catastrophic). Caveat: 147 safety overrides/ep — policy leans on the safety layer. Full table in [`training.md`](training.md). |
| DQN training | ✅ | replay fills (~2 episodes) then target-net updates every `train_freq` (~151/episode). **Run `dqn-20260907T165632Z`, `high_stop_go`, 200 episodes, 773 s.** Return −492 (first 5) → −475 (last 5); ε floors at 0.05 by ~ep 67; mean Q drifts −18 → −45 (not fully converged). `models/dqn/latest.pt` = `dqn-v1.4-dev`. |
| DQN evaluated (8 held-out seeds) | ✅ | vs fixed-time: avg waiting **+62.9%**, avg queue **+50.8%**, idle time **+52.3%**, speed +43.6%, stops/veh +12.4%, fuel/CO₂ per veh **+2.6% / +2.4%** (its objective), emergency wait +32.3%. **Cost: red-light violations −35.7% (7.0 → 9.5/ep), other violations −70%, 27 safety overrides/ep.** Trained ≫ untrained (catastrophic). Full table in [`training.md`](training.md). |
| PPO training | ✅ | tuned: `rollout_steps` 512 → 200 + episode-end flush → **3 real updates/episode** (was ~1); seeded minibatch shuffle → reproducible. **Run `ppo-20260907T171054Z`, `rush_hour`, 200 episodes, 910 s.** Return +183 → +220 over first ~60 ep then flat; entropy 1.38 → ~0.9. `models/ppo/latest.pt` = `ppo-v1.4-dev`. |
| PPO evaluated (8 held-out seeds) | ✅ | vs fixed-time: avg waiting **+30.7%**, avg queue +42.2%, speed **+65.7%**, stops/veh +30.4%, travel time +8.4%, fuel/CO₂ per veh +6.4% / +6.0%. **Cost: throughput −12.6%**; 47 safety overrides/ep. Untrained PPO is *not* catastrophic here (unlike A2C/DQN) so the trained-vs-random gap is smaller. Full table in [`training.md`](training.md). |
| SQLite model registry + versioning | ✅ | `app/persistence` (SQLAlchemy 2 + SQLite at `data/nexus.db`). `models` table: agent, version, checkpoint path, run id, scenario, seed, episodes, training + reward config, config digest, git sha, torch version, timestamps, eval metrics, status (`trained`→`evaluated`→`active`, one `active`/agent). `TrainingManager` auto-registers its final checkpoint; `evaluate --register` attaches the comparison blob; `scripts.training.backfill_registry` imports pre-registry runs. 12 tests. Doc: [`persistence.md`](persistence.md). |
| `TrainingService` (background job + live progress) | ✅ | one run at a time on its own thread; publishes an immutable snapshot polled by REST/WS; `history()` from on-disk run records. 6 tests. |
| Training REST API | ✅ | `GET /api/v1/training` (status + job + history), `POST /api/v1/training/runs` (start, 409 if busy), `GET /api/v1/training/runs[/{id}]`, `GET /api/v1/models[/{id}]`. `experiments` + `replay` still 404 (§98). |
| Training WebSocket progress | ✅ | `training_update` frame (`{seq, running, job:{phase, episode, progress, returns, last_episode:{return, losses, metrics}, ...}}`) pushed on every published change; real episode measurements only (§84). |
| Training Lab UI (`#/training`) | ✅ | hash route (no react-router). Legend spells out **TRAINING vs EVALUATION vs LIVE INFERENCE**. Start-a-run form (agent/episodes/scenario/seed/checkpoint-every → `POST /training/runs`), live-run panel (progress bar, episode-return sparkline, last-episode losses/metrics — fed by the `training_update` WS frame, REST-polled fallback), finished-runs + model-registry tables with status badges. All values are real backend measurements (§84). 4 vitest specs. |
| Trained-vs-fixed comparison UI | ⬜ | eval JSON reports exist; surfacing them in the lab is a later sub-slice |
| Trained checkpoint wired into live `SimulationManager` | ✅ | `POST /api/v1/simulation/model {agent, mode, version?}` + `set_model` WS command. `mode:"trained"` loads the agent's `active` (else latest) registry checkpoint, validates the file exists **and** that `trained_episodes > 0` post-load — otherwise 400 and the agent is left untouched (no fake `is_trained`, §84/§114). `mode:"untrained"` always restores fresh weights. Status carries `model_modes` + `model_sources`; agent `is_trained` flips honestly. Safety stays authoritative in both modes (§113). Front end: `ModelModeBar` on the dashboard (per-agent UNTRAINED/TRAINED toggle + honest badge). Tests: +6 pytest (integration + live-swap with a real checkpoint), +2 vitest. |

## Later slices — not started

Experiment Lab + comparison UI · Experience-replay inspector · full inspectors (vehicle / emergency /
signal / coordination "brain") · Scenario Lab UI · Replay engine + UI · presentation mode ·
notifications · keyboard shortcuts · CSV/JSON/HTML export · low-power quality modes · responsive
breakpoints · accessibility pass · performance audit · Docker images.
