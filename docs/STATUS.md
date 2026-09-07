# Feature status

Honest state of the build (spec §98 — nothing unimplemented is dressed up as done). Updated per slice.

Legend: ✅ working end-to-end · 🟡 partial / scaffolded · ⬜ not started

## Slice 1 — Foundation + simulation + full three-agent vertical slice  *(complete, inference-only)*

Verified end-to-end 2026-09-07: built-in sim → FastAPI → WebSocket → PixiJS render →
A2C/DQN/PPO decision loop → coordination → safety → applied phase → measured metrics,
all in the browser. `pytest tests/` (127) + `vitest` (29) green; `npm run build` +
`eslint` + `tsc -b` clean.

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
| A2C agent (net, state builder, reward, inference) | ✅ | inference-only; `is_trained=false` reported honestly |
| A2C training loop | ⬜ | later slice |
| DQN agent | ✅ | inference-only; raw Q-values exposed; training ⬜ |
| PPO agent | ✅ | inference-only; GAE/clip `learn()` written but not run in the live loop; training ⬜ |
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
| Tests (reward, state builders, agents, coordination, safety, sim determinism, API) | ✅ | `pytest tests/` → 127 pass (agents 64, coordination 14, safety 17, simulation 10, integration/API+WS 22); `vitest` → 29 pass (format, store wiring, scene geometry) |

## Later slices — not started

DQN/PPO training + inspectors · Experience-replay inspector · full inspectors (vehicle / emergency /
signal / coordination "brain") · Scenario Lab UI · Experiment Lab + comparison UI · Replay engine +
UI · Training Lab UI · model management/versioning · presentation mode · notifications · keyboard
shortcuts · CSV/JSON/HTML export · low-power quality modes · responsive breakpoints · accessibility
pass · performance audit · Docker images.
