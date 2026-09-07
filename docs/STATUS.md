# Feature status

Honest state of the build (spec §98 — nothing unimplemented is dressed up as done). Updated per slice.

Legend: ✅ working end-to-end · 🟡 partial / scaffolded · ⬜ not started

## Slice 1 — Foundation + simulation + full three-agent vertical slice  *(complete, inference-only)*

Verified end-to-end 2026-09-07: built-in sim → FastAPI → WebSocket → PixiJS render →
A2C/DQN/PPO decision loop → coordination → safety → applied phase → measured metrics,
all in the browser. `pytest tests/` (139, incl. Slice 2) + `vitest` (29) green;
`npm run build` + `eslint` + `tsc -b` clean.

| Area | State | Notes |
|---|---|---|
| Monorepo structure, configs, docs | ✅ | |
| §120 design docs | ✅ | architecture, system-flow, simulation schema, a2c/dqn/ppo, coordination, safety, metrics, experiments, assumptions, limitations |
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
| Tests (reward, state builders, agents, coordination, safety, sim determinism, API) | ✅ | `pytest tests/` → 139 pass (agents 64, coordination 14, safety 17, simulation 10, integration/API+WS 22, training 12); `vitest` → 29 pass (format, store wiring, scene geometry) |

## Slice 2 — training loops  *(in progress)*

Headless single-agent RL: real episodes → real reward → real gradient steps → checkpoints
→ observable episode-return curve. Docs: [`training.md`](training.md).

| Area | State | Notes |
|---|---|---|
| `make_reward_context()` shared by live loop + trainer | ✅ | one reward code path (§84); `SimulationManager` refactored onto it |
| `TrainingEnv` — headless single-agent episode driver | ✅ | same pipeline as the live loop for one agent; safety authoritative (§113); terminal transition realised with `done=True` |
| `TrainingManager` — N-episode run, checkpoints, run metrics | ✅ | `models/<agent>/` checkpoints + `latest.pt` + `<run_id>.json` (returns/losses/override counts/episode metrics + reproducibility blob) |
| `scripts/training/train.py` CLI (`make train`) | ✅ | `--agent --episodes --scenario --seed --checkpoint-every --episode-seconds`; per-episode progress line |
| A2C training | ✅ | n-step updates from episode 1 |
| DQN training | ✅ | replay fills (~2 episodes) then target-net updates every `train_freq` |
| PPO training | 🟡 | GAE/clip update runs, but ~1/episode at the 600-decision cadence — rollout length wants tuning |
| SQLite model registry + versioning | ⬜ | next sub-slice; `latest.pt` on disk is the record of truth for now |
| `GET /api/v1/training` + WS progress stream | ⬜ | still 404 (§98); `test_deferred_endpoints_are_absent_not_stubbed` still valid |
| Training Lab UI (`/training`) + trained-vs-fixed comparison | ⬜ | next sub-slice |
| Trained checkpoint wired into live `SimulationManager` | ⬜ | live app still inference-only (honest `UNTRAINED` badges) |

## Later slices — not started

Experiment Lab + comparison UI · Experience-replay inspector · full inspectors (vehicle / emergency /
signal / coordination "brain") · Scenario Lab UI · Replay engine + UI · presentation mode ·
notifications · keyboard shortcuts · CSV/JSON/HTML export · low-power quality modes · responsive
breakpoints · accessibility pass · performance audit · Docker images.
