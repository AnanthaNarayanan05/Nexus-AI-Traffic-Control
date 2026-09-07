<h1 align="center">NEXUS AI TRAFFIC CONTROL</h1>
<p align="center"><b>Three Intelligent Agents. One Coordinated Traffic Control System.</b><br/>
<i>Adaptive traffic control through objective-matched reinforcement learning.</i></p>

---

A real-time 2D digital twin of an intelligent urban intersection driven by **three objective-specific
reinforcement-learning agents**, coordinated through an explicit decision-and-safety layer:

| Agent | Objective | Reward |
|---|---|---|
| **A2C** | Emergency vehicle prioritization | `R = -α·Wₑ - β·Q + γ·Pₑ + δ·T` |
| **DQN** | Fuel · emission · violation / safety | smoothness reward − violation penalty |
| **PPO** | Adaptive congestion reduction | `R = -α·Q - β·W + γ·T` |

`A2C / DQN / PPO → Coordination Engine → Safety Constraint Layer → Final Signal Action → Traffic Simulation`

The agents are **objective-specific specialists, not one merged policy** — this framing comes straight from
the academic source, [`reference/Smart_Traffic_Signal_Multi_Algorithm.pptx`](reference/Smart_Traffic_Signal_Multi_Algorithm.pptx),
and is preserved deliberately.

## Status

This repository is built in **vertical slices** (spec §100). See
[`docs/STATUS.md`](docs/STATUS.md) for the live feature matrix — what is genuinely working end-to-end vs.
scaffolded vs. not yet started. Per spec §98, nothing unimplemented is dressed up as complete.

## Repository layout

```
nexus-ai-traffic/
├── configs/config.yaml     every tunable number (spec §92)
├── reference/              the academic source of truth (PPT)
├── docs/                   architecture, per-agent, coordination, safety, ...
├── backend/app/            FastAPI · simulation · agents · coordination · safety · metrics
├── frontend/src/           React + TypeScript + PixiJS command centre
├── simulation/             network / route / scenario / signal-config assets
├── models/                 trained agent checkpoints (+ metadata)
├── data/                   experiments · replays · exports (SQLite db)
├── tests/                  unit · integration · simulation · agents · coordination
└── scripts/                setup · training · experiments · validation
```

## Prerequisites

- **Python 3.11** (3.12 also supported)
- **Node.js ≥ 20** and npm
- **SUMO is optional.** The default simulation engine is a self-contained, deterministic
  pure-Python microsimulation (`NEXUS_SIM_ADAPTER=builtin`). A `libsumo` adapter can be swapped in later
  (`NEXUS_SIM_ADAPTER=sumo`) — see [`docs/simulation.md`](docs/simulation.md).

## Quick start

### 1. Install

```bash
# from the repo root
python -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip          # Windows
# source .venv/bin/activate                                # macOS / Linux
.venv/Scripts/python -m pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
```

Or, with GNU make (Git Bash / WSL / macOS / Linux):

```bash
make install
```

Windows PowerShell without `make`:

```powershell
./scripts/setup/install.ps1
```

### 2. Run the backend

```bash
.venv/Scripts/uvicorn app.main:app --app-dir backend --reload --port 8000
# or: make backend
```

Backend is now at <http://127.0.0.1:8000> (OpenAPI docs at `/docs`, WebSocket at `/ws`).

### 3. Run the frontend

```bash
cd frontend && npm run dev
# or: make frontend
```

Open <http://127.0.0.1:5173>.

### 4. Run both at once

```bash
make dev
# or, PowerShell:
./scripts/setup/dev.ps1
```

## Common tasks

| Task | Command |
|---|---|
| Run all tests | `make test` &nbsp;·&nbsp; `.venv/Scripts/python -m pytest -q` &nbsp;·&nbsp; `cd frontend && npm test` |
| Train an agent | `.venv/Scripts/python -m scripts.training.train --agent a2c --episodes 200` |
| Evaluate a model | `.venv/Scripts/python -m scripts.training.evaluate --agent a2c --model models/a2c-v1.0.pt` |
| Run an experiment batch | `.venv/Scripts/python -m scripts.experiments.run --config configs/experiments/mixed_crisis.yaml` |
| Repository validation | `.venv/Scripts/python -m scripts.validation.check_all` |
| Presentation mode | Start backend + frontend, then press **P** in the UI (or open `/#/present`) |
| Export results | Experiment Lab → **EXPORT**, or `scripts/experiments/export.py` |

## SUMO setup (optional)

1. Install SUMO ≥ 1.20 from <https://eclipse.dev/sumo/> and set `SUMO_HOME`.
2. `pip install -r backend/requirements.txt` then `pip install ".[sumo]"` (from `backend/`).
3. Set `NEXUS_SIM_ADAPTER=sumo` in `.env`.
4. Details, network files, and the fallback contract: [`docs/simulation.md`](docs/simulation.md).

## Documentation

[architecture](docs/architecture.md) ·
[system-flow](docs/system-flow.md) ·
[a2c](docs/a2c.md) · [dqn](docs/dqn.md) · [ppo](docs/ppo.md) ·
[coordination](docs/coordination.md) · [safety](docs/safety.md) ·
[simulation](docs/simulation.md) · [metrics](docs/metrics.md) ·
[experiments](docs/experiments.md) · [assumptions](docs/assumptions.md) ·
[limitations](docs/limitations.md) · [demo-guide](docs/demo-guide.md) ·
[troubleshooting](docs/troubleshooting.md)

## Academic honesty

Every value the UI presents as an AI decision, score, Q-value, actor probability, critic value, reward, or
experiment result originates from a real system calculation (spec §84, §114). Estimated quantities (fuel,
emissions) are labelled **ESTIMATED** and their models are documented in
[`docs/assumptions.md`](docs/assumptions.md).
