# Architecture

## 1. Layers (strict separation — spec §6)

```
┌──────────────────────────────────────────────────────────────────────┐
│  PRESENTATION   frontend/src  · React + TypeScript + PixiJS           │
│    app/ dashboard/ simulation/ ai/ inspectors/ scenarios/ experiments/│
│    training/ replay/ history/ · services/ hooks/ state/ types/        │
└───────────────┬──────────────────────────────────────────────────────┘
                │  REST (control, config, queries)  +  WebSocket (live stream)
┌───────────────▼──────────────────────────────────────────────────────┐
│  API            backend/app/api  · FastAPI routers + WS hub           │
└───────────────┬──────────────────────────────────────────────────────┘
        ┌───────┼─────────────────────────┬───────────────────┐
        ▼       ▼                         ▼                   ▼
  SimulationManager           ExperimentManager        TrainingManager
  (one live sim + loop)       (headless batch runs)    (agent training runs)
        │
        ▼
┌──────────────────────────────────────────────────────────────────────┐
│  SIMULATION     backend/app/simulation                                │
│    SimulationAdapter (Protocol)                                       │
│      ├── BuiltinAdapter   pure-python microsimulation  (default)      │
│      └── SumoAdapter      libsumo / traci              (optional)     │
│    → SimulationState  (typed, adapter-independent)                    │
└───────────────┬──────────────────────────────────────────────────────┘
                ▼   state builders (per agent)
        ┌───────┼───────┐
        ▼       ▼       ▼
      A2C     DQN     PPO          backend/app/agents/*
   (actor/  (Q-net/  (policy/
    critic)  target)  value)
        │       │       │  → AgentRecommendation ×3
        └───────┼───────┘
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  COORDINATION   backend/app/coordination · deterministic priority     │
│                 ladder → CoordinationDecision (candidate action)      │
└───────────────┬──────────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  SAFETY         backend/app/safety · authoritative validator (§113)   │
│                 → SafetyResult (approved action or safe fallback)     │
└───────────────┬──────────────────────────────────────────────────────┘
                ▼
        SignalController → SimulationAdapter.apply_phase()
                │
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  METRICS        backend/app/metrics · rolling + episode aggregates    │
│  PERSISTENCE    backend/app/persistence · SQLite (experiments, models)│
│  REPLAY         backend/app/replay · decision records + snapshots     │
│  LOGGING        backend/app/logging · structured events               │
└──────────────────────────────────────────────────────────────────────┘
```

**Dependency rule:** arrows point downward only. `agents/`, `coordination/`, `safety/`, `metrics/`
depend on `schemas/` and `core/`, never on `api/` or on a concrete adapter. The simulation loop is the
only place that wires them together.

## 2. The decision loop (`SimulationManager`)

Two decoupled cadences (spec §72):

| Loop | Cadence | Work |
|---|---|---|
| **Physics** | every `step_length_s` (0.5 s sim) | advance the adapter one tick |
| **Decision** | every `decision_interval_s` (6 s sim, PPT) | build states → 3 agents infer → coordinate → safety → apply phase → record `DecisionRecord` |
| **Stream** | `stream_hz` (20 / real s) | push `simulation_state` + `metric_update` frames over WS |

The physics + decision loop runs in a background thread (CPU-bound numpy / torch). The WS hub reads the
latest immutable snapshot; it never blocks on the sim.

## 3. Control modes

`AI` (coordinator + safety) · `FIXED_TIME` (baseline schedule + safety) · `MANUAL` (user actions + safety).
Safety runs in **all** modes.

## 4. Frontend component hierarchy

```
<App>
 ├─ <CommandBar>            live/paused · FPS · mode toggle · sim clock · scenario
 ├─ <Route: /dashboard>
 │   ├─ <A2CPanel>          emergency state · actor bars · critic value · reward decomp
 │   ├─ <SimulationStage>   PixiJS canvas: roads, vehicles, signals, emergency routes
 │   ├─ <DQNPanel>          efficiency/safety readout · Q-value bars · epsilon · replay size
 │   ├─ <PPOStrip>          per-approach queue pressure · recommendation
 │   ├─ <CoordinationBar>   3 recommendations → winner + reason + safety verdict
 │   ├─ <MetricsRow>        wait · queue · throughput · fuel · CO₂ · emergency · violations · FPS
 │   └─ <EventTimeline>     filterable TRAFFIC/AI/EMERGENCY/SAFETY/VIOLATION/SYSTEM
 ├─ <Route: /inspect/a2c|dqn|ppo>   full-screen inspectors (pause + step)
 ├─ <Route: /coordination>          "brain" view
 ├─ <Route: /scenarios>             Scenario Lab
 ├─ <Route: /experiments>           Experiment Lab + comparison
 ├─ <Route: /replay>                Replay engine
 ├─ <Route: /training>              Training Lab
 ├─ <Route: /history>               past decisions / experiments
 └─ <Route: /present>               Presentation mode
```

State: `zustand` stores split by concern (`simStore`, `aiStore`, `uiStore`, `scenarioStore`,
`experimentStore`, `replayStore`). The WS service is the single writer of `simStore` / `aiStore`.

## 5. Technology choices & rationale

| Area | Choice | Why |
|---|---|---|
| Sim engine | Built-in microsimulation behind `SimulationAdapter` | SUMO/libsumo not reliably installable here; adapter keeps the SUMO door open (spec §9, §122) |
| RL | Custom PyTorch A2C/DQN/PPO | Inspectors need per-step actor probs / Q-values / critic / advantage / reward components that SB3 hides |
| Transport | REST for control, WebSocket for the 20 Hz stream | Matches spec §71; avoids polling |
| Charts | `uPlot` + tiny canvas sparklines | 60 FPS streaming without React re-render churn |
| Rendering | PixiJS (WebGL) for vehicles/signals; React/DOM for panels | spec §73 — no massive DOM tree for moving traffic |
| Persistence | SQLite via SQLAlchemy Core | spec §90; abstracted for later replacement |

See [`system-flow.md`](system-flow.md) for the message-level sequence and [`simulation.md`](simulation.md)
for the state schema.
