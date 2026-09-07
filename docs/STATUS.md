# Feature status

Honest state of the build (spec §98 — nothing unimplemented is dressed up as done). Updated per slice.

Legend: ✅ working end-to-end · 🟡 partial / scaffolded · ⬜ not started · ⚠️ deprecated / legacy (kept, not extended)

## R9 scope revision (2026-09-08)

The governing directive is now **MASTER IMPLEMENTATION PROMPT — R9**. Key change to the
algorithm roster:

- **Active scope = A2C + DQN only.** A2C → emergency-vehicle prioritization (owner
  Anantha Narayanan A). DQN → efficiency / fuel / emissions / safety (owner Shaun Joseph Sabu).
- **PPO is ⚠️ deprecated / legacy.** Per the R9 destructive-change rule it was *not*
  deleted: `AgentName.PPO`, `app/agents/ppo/*`, PPO checkpoints + registry rows, PPO unit
  tests and the `AGENT_LABEL/OBJECTIVE/OWNER.ppo` maps all remain so pre-R9 artefacts stay
  loadable and inspectable. What changed: the live decision loop, the coordination
  pipeline, the training workflow (`ACTIVE_AGENTS` gate) and the primary frontend now only
  touch A2C + DQN. New PPO training runs are rejected; `GET /api/v1/agents/ppo` → 404;
  `POST /simulation/model {agent:"ppo"}` → rejected; `PPOStrip.tsx` is unmounted.
- R9 priority order for remaining work: ~~**P1** evaluation correctness + comparison UI~~ ✅ →
  **P2** preset/custom scenario system → **P3** replay + inspectors → **P4** export +
  presentation mode → **P5** UI polish → **P6** performance / a11y / responsive →
  **P7** docs / QA / reproducibility / demo readiness.
- **P1 done (2026-09-08):** `ExperimentService` + `GET/POST /api/v1/experiments` +
  `experiments` persistence table + Experiment Lab (`#/experiments`) with the honest
  Fixed-Time vs AI comparison table. See the Slice 2 table below and
  [`experiments.md`](experiments.md).

## Slice 1 — Foundation + simulation + full agent vertical slice  *(complete, inference-only)*

Verified end-to-end 2026-09-07: built-in sim → FastAPI → WebSocket → PixiJS render →
agent decision loop → coordination → safety → applied phase → measured metrics,
all in the browser. `pytest tests/` (191, incl. Slice 2 + R9 deprecation + P1 experiments) +
`vitest` (46) green; `npm run build` + `eslint` + `tsc -b` clean.

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
| A2C agent (net, state builder, reward, inference) | ✅ | live loop; emergency-vehicle prioritization; `is_trained` reported honestly |
| DQN agent | ✅ | live loop; efficiency / fuel / emissions / safety; raw Q-values exposed |
| PPO agent | ⚠️ | **legacy** — code + checkpoints retained and loadable, but removed from the live loop, coordination and training workflow (R9). `GET /agents/ppo` → 404. |
| Fixed-time baseline controller | ✅ | 60 s cycle; measurably different from AI mode |
| Manual control | ✅ | HOLD/SWITCH/EXTEND/REDUCE/SET_* via REST + WS |
| Metrics aggregator | ✅ | rolling + episode windows; fuel/CO₂ flagged ESTIMATED |
| FastAPI app + REST + WebSocket hub | ✅ | `command_result` channel separate from `status` |
| `SimulationManager` decision loop | ✅ | own thread; reward for decision N realised at N+1 (on-policy order) |
| Frontend shell + command bar | ✅ | start/pause/step/reset, mode, scenario, speed, inject; live/paused, sim clock, seed, cfg digest |
| PixiJS `SimulationStage` | ✅ | config-driven geometry, roads, vehicles (eased), signal lamps, queue counts, view-radius zoom |
| A2C / DQN dashboard panels | ✅ | actor bars, critic V(s), Q(s,a), queue pressure, reward decomposition, honest trained/UNTRAINED badge. `PPOStrip.tsx` retained but ⚠️ unmounted (R9). |
| Coordination bar | ✅ | A2C + DQN recs → winner + basis → safety verdict + ladder trace + score breakdown (engine still accepts N recs; PPO no longer feeds it) |
| Metrics row + event timeline | ✅ | filterable TRAFFIC/AI/EMERGENCY/SAFETY/VIOLATION/SYSTEM; server errors surfaced verbatim |
| Agent inspector REST polling | ✅ | `GET /agents/{name}` on a 2 s poll; not streamed (cost) |
| Tests (reward, state builders, agents, coordination, safety, sim determinism, API, training, evaluation, experiments) | ✅ | `pytest tests/` → **191 pass** (incl. R9: PPO rejected from live inference + agent inspector; P1: experiment store + service + API); `vitest` → **46 pass** (incl. `ACTIVE_AGENTS` scope lock, `ComparisonTable` honesty rules, `ExperimentLab`). PPO unit tests (agent contract, reward, state builder) retained and green — legacy code stays covered. |

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
| PPO training | ⚠️ | **legacy — frozen at R9, not extended.** Historical run `ppo-20260907T171054Z` (`rush_hour`, 200 episodes, 910 s) and `models/ppo/latest.pt` (`ppo-v1.4-dev`) are kept and loadable. `TrainingService.start` now rejects `agent="ppo"`. |
| PPO evaluated (8 held-out seeds) | ⚠️ | legacy result kept for the record (vs fixed-time: avg waiting +30.7%, speed +65.7%, throughput −12.6%, 47 safety overrides/ep). PPO is out of the R9 comparison workflow. Full table in [`training.md`](training.md). |
| SQLite model registry + versioning | ✅ | `app/persistence` (SQLAlchemy 2 + SQLite at `data/nexus.db`). `models` table: agent, version, checkpoint path, run id, scenario, seed, episodes, training + reward config, config digest, git sha, torch version, timestamps, eval metrics, status (`trained`→`evaluated`→`active`, one `active`/agent). `TrainingManager` auto-registers its final checkpoint; `evaluate --register` attaches the comparison blob; `scripts.training.backfill_registry` imports pre-registry runs. 12 tests. Doc: [`persistence.md`](persistence.md). |
| `TrainingService` (background job + live progress) | ✅ | one run at a time on its own thread; publishes an immutable snapshot polled by REST/WS; `history()` from on-disk run records. 6 tests. |
| Training REST API | ✅ | `GET /api/v1/training` (status + job + history), `POST /api/v1/training/runs` (start, 409 if busy), `GET /api/v1/training/runs[/{id}]`, `GET /api/v1/models[/{id}]`. `replay` still 404 (§98). |
| Training WebSocket progress | ✅ | `training_update` frame (`{seq, running, job:{phase, episode, progress, returns, last_episode:{return, losses, metrics}, ...}}`) pushed on every published change; real episode measurements only (§84). |
| Training Lab UI (`#/training`) | ✅ | hash route (no react-router). Legend spells out **TRAINING vs EVALUATION vs LIVE INFERENCE**. Start-a-run form (agent/episodes/scenario/seed/checkpoint-every → `POST /training/runs`), live-run panel (progress bar, episode-return sparkline, last-episode losses/metrics — fed by the `training_update` WS frame, REST-polled fallback), finished-runs + model-registry tables with status badges. All values are real backend measurements (§84). 4 vitest specs. |
| `ExperimentService` (background comparison job + live progress) | ✅ | **R9 P1.** Mirrors `TrainingService`: one experiment at a time on its own thread, publishes an immutable snapshot polled by REST/WS. Controllers `fixed_time \| a2c \| dqn`; per-agent model selector `untrained \| active \| latest \| <registry id>` resolved to a checkpoint **up front** (fail-fast, never a fake path). Reproducibility blob frozen at start (config digest, git sha, seeds, reward weights, decision/step cadence, torch version). 6 tests. |
| Experiments REST + WS + persistence | ✅ | `GET /api/v1/experiments?history=` (snapshot + past runs), `POST /api/v1/experiments` (202; 409 busy, 404 unknown scenario, 422 bad controllers/seeds/missing checkpoint), `GET /api/v1/experiments/{id}` (full detail). New `experiments` SQLite table (scenario, controllers, seeds, baseline, reproducibility, comparison blob, per-controller results, status). `experiment_update` WS frame. +8 tests (store + integration). |
| Trained-vs-fixed comparison UI | ✅ | **R9 P1** — Experiment Lab (`#/experiments`): scenario select, controller checkboxes (Fixed-Time / A2C / DQN) with per-agent model selector, seed list, optional episode length → `POST /experiments`; live progress panel; past-experiments table; **honest `ComparisonTable`** — baseline column always shown (never % without absolute values, §16), per-metric direction (↓/↑), absolute Δ + direction-aware % (green only when it moved the *better* way), "within noise" when \|Δ\| ≤ combined 95% CI, winner = best controller only when it clears the runner-up by more than their combined CI. Fed by `experiment_update` WS frame + REST poll. +9 vitest. |
| Trained checkpoint wired into live `SimulationManager` | ✅ | `POST /api/v1/simulation/model {agent, mode, version?}` + `set_model` WS command. `mode:"trained"` loads the agent's `active` (else latest) registry checkpoint, validates the file exists **and** that `trained_episodes > 0` post-load — otherwise 400 and the agent is left untouched (no fake `is_trained`, §84/§114). `mode:"untrained"` always restores fresh weights. Status carries `model_modes` + `model_sources`; agent `is_trained` flips honestly. Safety stays authoritative in both modes (§113). Front end: `ModelModeBar` on the dashboard (per-agent UNTRAINED/TRAINED toggle + honest badge). Tests: +6 pytest (integration + live-swap with a real checkpoint), +2 vitest. |

## R9 remaining work (priority order)

| P | Item | Notes |
|---|---|---|
| P1 | Evaluation correctness + comparison UI | ✅ **done 2026-09-08** — `ExperimentService` + `experiments` REST/WS/persistence + Experiment Lab with the honest `ComparisonTable` (see Slice 2 table). Multi-seed mean ± 95% CI, reproducibility blob, direction-aware improvement %, never % without baseline values. |
| P2 | Preset + custom scenario system | expand presets to the 8 required (§8A: NORMAL, RUSH HOUR, EMERGENCY RESPONSE, UNEQUAL DEMAND, STOP-GO EFFICIENCY, ROAD BLOCKAGE, SAFETY/VIOLATION, MIXED CRISIS) with name/description/objective/AI-focus/difficulty; custom builder (§8B) with all user-safe params, validation, human-readable preview, SAVE/LOAD/DUPLICATE/DELETE (persisted); safety layer never user-disableable |
| P3 | Replay + inspectors | lightweight replay (§18: play/pause/seek/step/speed/events), `GET /api/v1/replay`; Vehicle / Emergency / Signal / AI-Coordination inspectors (§19) |
| P4 | Export + presentation mode | CSV + JSON export (§23, HTML desirable); presentation/demo mode (§24) — reduced controls, clean narrative |
| P5 | Premium UI polish | |
| P6 | Performance (60 FPS) · accessibility · responsive | |
| P7 | Final docs · QA · reproducibility · demo readiness | §39 quality-bar checklist |
