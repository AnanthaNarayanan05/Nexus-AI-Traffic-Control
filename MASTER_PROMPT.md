# NEXUS AI TRAFFIC CONTROL — Master Build Specification (working copy)

> This is the condensed, section-numbered working copy of the original master
> build brief. Section numbers match the original. Binding constraints
> (algorithm assignments, reward forms, safety authority, academic honesty) are
> reproduced verbatim. The academic source of truth is
> [`reference/Smart_Traffic_Signal_Multi_Algorithm.pptx`](reference/Smart_Traffic_Signal_Multi_Algorithm.pptx).

> **⚠️ SUPERSEDED IN PART BY R9 (2026-09-08).** The governing directive is now the
> *MASTER IMPLEMENTATION PROMPT — R9*. Where R9 and this document disagree, **R9 wins**.
> Deltas that matter for reading this file:
> - **Active algorithm scope is A2C + DQN only.** PPO is deprecated / legacy — its code,
>   checkpoints and unit tests are *preserved* (R9 destructive-change rule) but it is out
>   of the live loop, coordination, training workflow and primary UI. Every "A2C / DQN / PPO"
>   phrasing below should be read as "A2C / DQN" for current work.
> - **DQN objective** is stated by R9 as *efficiency / fuel / emissions / safety*.
> - Remaining build priorities (R9 §35): ~~P1 evaluation + comparison UI~~ ✅ · ~~P2 scenario
>   system (8 presets + custom builder)~~ ✅ · ~~P3 replay (engine + Replay Lab) + inspectors
>   (`#/inspect`: coordination brain / signal / emergency / vehicle / DQN experience replay)~~ ✅ ·
>   P4 ~~export (`GET /api/v1/export/{experiments|replays}/{id}?format=csv|json`)~~ ✅ + presentation mode ·
>   P5 polish · P6 perf/a11y/responsive · P7 docs/QA/demo.
> - Current honest state: [`docs/STATUS.md`](docs/STATUS.md) (see its "R9 scope revision" section).

## 1–2. Project & core idea
**NEXUS AI TRAFFIC CONTROL** — *Three Intelligent Agents. One Coordinated Traffic Control System.*
Real-time intelligent traffic-control simulator around a 2D urban four-way intersection with **three
objective-specific RL agents** that are **not merged into a single generic model**:

| Agent | Objective |
|---|---|
| **A2C** | Emergency Vehicle Prioritization |
| **DQN** | Fuel Consumption + Emission Reduction + Traffic Safety / Violation Monitoring |
| **PPO** | Adaptive Traffic Congestion Reduction |

Pipeline: `A2C / DQN / PPO → COORDINATION ENGINE → SAFETY CONSTRAINT LAYER → FINAL SIGNAL ACTION → TRAFFIC SIMULATION`.

## 3. Source of truth
Read `reference/Smart_Traffic_Signal_Multi_Algorithm.pptx`. Do **not** silently change the algorithm
assignments, replace an algorithm, collapse the three into one policy, or add claims not supported by the
source or by real experiments. When details are missing, choose a reasonable engineering approach and
**document the assumption** (see [`docs/assumptions.md`](docs/assumptions.md)).

## 4–5. Product objective & UX
Feels like a professional **AI Traffic Operations Command Center**: Simulation + real A2C/DQN/PPO agents +
live explainability + interactive control + scientific AI-vs-fixed-time evaluation + an elegant
demonstration mode. Session flow: open → live intersection → select scenario → traffic evolves → AI
observes → agents analyze → recommendations → coordination → safety → final action → traffic response →
metrics update → inspect decision → run comparison → run experiment → results stored. **Everything must be connected.**

## 6–7. Architecture & repo
Modular: presentation / API / simulation / RL / coordination / safety / metrics / experiments / persistence,
strictly separated. Professional monorepo — see [`docs/architecture.md`](docs/architecture.md).

## 8. Stack
Frontend: React + TypeScript + PixiJS + modern CSS + animation lib.
Backend: Python + FastAPI + Pydantic + WebSockets.
Simulation: SUMO / libsumo / TraCI *(where practical — see §122 assumption)*.
RL: PyTorch, Stable-Baselines3 where practical, custom wrappers where necessary.
Data: NumPy, Pandas, SQLite. Testing: pytest + a React test framework. Pin compatible versions.

## 9–12. Simulation
SUMO/libsumo where practical, behind a clean `SimulationAdapter` — the rest of the app must not depend on
raw TraCI. Represent: four-way intersection, approaches, lanes, lights, arrivals/departures, queues,
waiting, speeds, stops, turning, emergency vehicles, violations, demand changes. Typed internal models for
`SimulationState`, vehicles, and signals. Signal phases explicit; **no arbitrary unsafe phase switching** —
always go through yellow / all-red transitions. UI visualizes GREEN / YELLOW / RED / TRANSITION.

## 13–14. A2C — Emergency Vehicle Prioritization
**State:** emergency detected, direction, distance, speed; queue lengths; waiting time; current signal
phase; traffic density; normal traffic flow.
**Actions (discrete):** maintain current signal · extend current green · switch to emergency direction ·
reduce current green · restore normal operation.
**Reward:** `R = -α·Wₑ - β·Q + γ·Pₑ + δ·T` (Wₑ = emergency waiting time, Q = normal queue,
Pₑ = emergency passage/priority, T = throughput). Weights configurable; document any extra engineering penalties.
**Implement genuine A2C:** Actor, Critic, policy output, value function, advantage, actor loss, critic
loss, entropy, optimizer, training loop. Track episode reward, actor/critic loss, value estimate,
advantage, action probabilities, action frequency, emergency delay. UI shows real actor probabilities,
critic value, selected action, reward decomposition, live graphs — **no faked outputs**.

## 15–17. DQN — Fuel + Emissions + Efficiency + Safety
**State:** vehicle count, queue length, average waiting, average speed, stops, current phase, estimated
emissions, violations.
**Actions:** keep green · extend green · switch phase · reduce green · appropriate transition.
**Reward:** positive for smooth movement, decreasing waits, fewer stops, lower estimated emissions;
negative for prolonged stationary vehicles, growing queues, unnecessary stops, emissions, unsafe/violation
events. Violation indicators enter the **state**; violation events enter the **reward** as penalties.
**Implement genuine DQN:** Q-network, target network, replay buffer, Bellman target, optimizer, loss,
epsilon-greedy, target-update strategy. Track Q-values, Q-loss, reward, epsilon, replay size, action
frequency, convergence. Provide an **Experience Replay inspector** (human-readable transition:
state → action → reward → next state → done).

## 18–19. PPO — Adaptive Traffic Congestion Reduction
**State:** lane queue lengths, vehicle counts, waiting, arrival rates, phase, phase duration, average
speed, density.
**Actions:** keep phase · extend green · reduce green · switch phase.
**Reward:** `R = -α·Q - β·W + γ·T` (Q = queue length, W = waiting time, T = throughput).
**Implement genuine PPO:** policy net, value net, rollout buffer, GAE, clipped objective, policy updates,
value loss, entropy. Track policy loss, value loss, entropy, reward, advantage, episode return.

## 20–21. Coordination engine
A2C/DQN/PPO **do not independently control a signal** — each returns an `AgentRecommendation`
(agent, action, score, confidence, reason, relevant_state, priority). Coordinator is **deterministic given
identical inputs**. Explainable priority ladder: **1 Safety · 2 Emergency priority · 3 Current valid
phase · 4 Congestion · 5 Efficiency · 6 Throughput · 7 avoid unnecessary switching.** Not averaging, not
meaningless voting — a transparent scoring/priority mechanism, documented, with the UI showing **why** a
decision won.

## 22. Safety filter
Dedicated module. Before any signal action: validate phase compatibility, minimum green, maximum green,
yellow transition, all-red, conflicting phases, emergency timeout, recovery behaviour. Invalid → reject
and pick the safest valid alternative. **Log every override.**

## 23–26. Emergency vehicles · violations · fuel · emissions
Emergency types: ambulance, fire truck, police — visual distinction, lights, priority state, path,
distance, speed, direction, detection state. A2C activates on detection, releases priority once cleared.
Violations: red-light, unsafe crossing, lane/signal — record vehicle ID, timestamp, location, type, signal
state, severity; feed DQN state + reward + safety metrics + timeline. Fuel: transparent estimate from
speed/accel/idle/stops/type, configurable, clearly labelled **ESTIMATED**. Emissions: estimated CO₂ from
fuel/speed/accel/idle/type, labelled **ESTIMATED**, assumptions documented.

## 27–30. Demand · Scenario Lab · event injection · manual mode
Dynamic demand: constant / periodic / rush-hour / stochastic / lane-imbalance, changeable mid-run.
Scenario Lab with presets (Normal, Rush Hour, Emergency Response, Uneven Demand, High Stop-Go, Road
Blockage, Violation Event, Mixed Crisis) and custom params (per-approach demand, spawn rate, emergency /
violation / accident probability, blocked lane, weather, time of day, duration, seed). Manual event
injection buttons create **real simulation events**, never just UI text. Modes: AI / Fixed-Time / Manual.

## 31–40. UI, design system, visualization, metrics, graphs, timeline
Premium command-center layout: A2C left · live 2D simulation centre (visually dominant) · DQN right · PPO
strip · AI coordination · metrics row · event timeline. Dark, restrained accents, glass panels, high
typography, purposeful animation. 2D traffic: lane-following, rotation, red-light slowing, queueing,
smooth turns; emergency sprites flash. Animated data-flow: state → agents → recommendations →
coordination → safety → signal. Live metrics + high-quality live charts + filterable event timeline.

## 41–47. Inspectors
Full-screen A2C / DQN / PPO inspectors (state, feature vector, outputs, selected action, value/advantage,
reward decomposition, history, training metrics); pause-and-inspect. Vehicle inspector, emergency-vehicle
inspector, signal inspector, and an AI-coordination "brain" page with explicit reasoning.

## 48–56. Baseline, comparison, experiments, replay
Deterministic seeded scenario generator (random + reproducible modes). Real fixed-time controller
baseline. AI-vs-Fixed-Time comparison (side-by-side or synchronized replay) using **actual measured
results**. Experiment Lab (controller, scenario, seed, episodes, duration; RUN/PAUSE/STOP/EXPORT) running
**real simulations**. Metrics across Traffic / Environmental / Emergency / Safety / RL families. Statistics:
mean, median, std, min, max, CIs where justified, improvement % — **do not overstate significance**. Store
full reproducibility metadata in SQLite. Replay engine: play/pause/step/rewind/ff/speed/jump, showing
agent states + recommendations + coordinator + safety + metrics at any time.

## 57–59. Training Lab · model management · versioning
Separate training view with per-agent live curves and TRAIN/PAUSE/STOP/SAVE/LOAD/EVALUATE. Model metadata
(algorithm, version, timestamp, env version, config, reward weights, episodes, seed, performance summary);
warn on incompatible loads; bump version on change; associate experiment results with model version.

## 60–63. Presentation mode & flagship demos
Dedicated presentation mode (minimal nav, large panels, deterministic seed). Flagship demos:
**1 — Emergency Response Challenge (A2C)**, **2 — Efficiency Challenge (DQN)**, **3 — Mixed Crisis (full AI)**.

## 64–79. Controls, shortcuts, notifications, errors, logging, state, types, protocol, performance, exports
Keyboard shortcuts (Space/R/E/M/A/F/1/2/3/C/S) that don't fire while typing. Non-intrusive notifications.
Graceful error handling (SUMO/backend/model/WebSocket/config). Structured logs. Centralized, separated
frontend state. Strong types everywhere (TS interfaces + Pydantic). Explicit WebSocket message types
(`simulation_state`, `agent_update`, `coordination_update`, `signal_update`, `metric_update`, `event`,
`experiment_update`, `training_update`, `error`). ~60 FPS target with separated loops; measured, not
promised. CSV / JSON exports + optional report.

## 80–83. Testing & reproducibility
Unit (reward fns, state builders, action maps, fuel/emission models, metrics, safety rules, coordination),
integration (sim → state → agent → coordination → safety → signal), scenario tests, UI tests, RL
validation tests, safety validation tests. All experiments seedable; record the seed; document determinism limits.

## 84. Academic honesty rules *(verbatim)*
> Never fabricate: model performance, Q-values, actor outputs, critic values, rewards, experiment
> outcomes, training curves, percentage improvements. The UI must not contain fake values in
> production/demo mode. Development mocks may exist only behind an unmistakable developer/mock mode.

## 85–87. Explainability
Every reward decomposable and displayed by component. Every decision shows: what the agent saw, its
options, its selection, why, the resulting reward, the coordinator action, whether safety was involved.
Full decision record persisted for timeline / replay / history / inspectors / experiment analysis.

## 88–96. API, security, DB, storage, config, setup, one-command dev, production, docs
Versioned, documented REST + WebSocket API. Validate all input; sanitize filenames; restrict file paths;
no arbitrary code execution. SQLite schema (experiments, experiment_metrics, experiment_configs, models,
simulation_runs, events, replays); summaries/snapshots not infinite raw data; storage-management controls.
Central config file (no scattered magic numbers). `.env.example` + sensible defaults. `make dev` (or
equivalent) one-command start. Production build (optimized frontend, backend startup, model loading,
persistent data path); Docker optional but preferred. Full docs set (§117).

## 97. Project limitations *(preserve honestly)*
Simulation-to-real gap; fuel/emission estimation assumptions; no computer vision unless implemented;
limited intersection scale; training complexity; reward sensitivity; coordination assumptions. The source
itself lists reward design, coordinating independently trained agents, training time, exploration risk,
generalization, safety constraints, sim-to-real. See [`docs/limitations.md`](docs/limitations.md).

## 98. No fake completeness *(verbatim intent)*
If a feature is not implemented: do **not** wrap a fake UI card / fake status / fake graph / false claim
around it. Instead mark it unavailable, log it, document it, and continue with implemented functionality.

## 99. No unnecessary scope
No 3D, blockchain, IoT hardware, real traffic-light control, unnecessary microservices, computer vision
(unless required), cloud infra, or multi-city simulation. Focus: RL, simulation, coordination, safety,
explainability, premium 2D visualization, experiments, performance.

## 100–101. Strategy & phases
Work in **vertical slices** (UI + backend + simulation + AI + result working together). Phases 0–20:
Discovery → Foundation → Traffic Simulation → 2D Frontend → Simulation Connection → A2C → DQN → PPO →
Coordination → Safety → Events → Metrics → Baseline → Experiments → Replay → Training Lab → Premium UI →
Performance → Testing → Presentation Mode → Final Audit.

## 102. Definition of done
A feature is done only when **input → real processing → real decision → real simulation effect → real
metric → observable result** exists — not because a button/card/chart/label exists.

## 103–108. Final validation, performance audit, demo reliability, UX audit, viva audit, demo script
Full checklists for every agent, coordination, safety, simulation, metrics, experiments, UI. Measure and
report real FPS / frame time / AI latency / sim latency / WS latency / memory. Presentation mode
deterministic under a fixed seed; flagship demos run repeatedly with no crash / stuck vehicle / stuck
signal / disconnected UI / fake output.

## 109–116. Design & engineering philosophy *(binding)*
Visual hierarchy: traffic situation → AI decision → final action → outcome → metrics → internals. The
simulation is the story. Always prefer correctness over visual fake complexity; real state over mock
state; real model outputs over fake visualizations; measured results over promotional claims; modular
architecture over one giant file; explainability over black-box; measurement over assumption.
**§113 Safety is authoritative** — no RL recommendation may bypass the safety controller, even a
theoretically advantageous one. **§114** every production/demo value shown as an AI decision / score /
Q-value / actor probability / critic / reward / metric / experiment result must originate from real
system calculations — no hard-coded fake outputs.

## 117–118. Documentation & runbook
`README.md` + `docs/{architecture, system-flow, a2c, dqn, ppo, coordination, safety, simulation, metrics,
experiments, assumptions, limitations, demo-guide, troubleshooting}.md`. README provides exact commands
for install / backend / frontend / SUMO / model loading / training / evaluation / experiments /
presentation mode / exports / troubleshooting.

## 119. Final delivery checklist
Repository builds; frontend & backend launch; simulation runs; traffic moves; signals work; A2C/DQN/PPO
work; coordination & safety work; emergency & violation work; metrics work; fixed-time baseline &
comparison work; experiments, replay, training, model loading, presentation mode, exports work; tests
pass; docs exist; performance measured; **no production fake AI outputs**.

## 120–124. First action & product standard
Discovery before implementation: read spec + PPT + repo, produce architecture map, directory tree,
simulation state schema, A2C/DQN/PPO specs, coordination design, safety design, frontend component
hierarchy, API/WebSocket model, implementation sequence, technical risks — **then build for real, test,
measure, document. Do not fake it.**
