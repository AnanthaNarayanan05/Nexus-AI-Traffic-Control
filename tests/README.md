# Backend test suite

Run from `backend/` so `pyproject.toml [tool.pytest.ini_options]` is picked up
(`testpaths = ["../tests"]`, `asyncio_mode = "auto"`):

```bash
cd backend && ../.venv/Scripts/python -m pytest -q
```

Running from the repo root also works but misses that config (a harmless
pytest-asyncio deprecation warning appears).

## Layout

| Path | Covers |
|---|---|
| `factories.py` | `make_state(...)` synthetic `SimulationState` builder, `active_emergency(...)`, `advance(eng, seconds)`. Imported by `conftest.py` for its side effect of putting `backend/` on `sys.path`, so `app.*` resolves whatever the working directory is. |
| `conftest.py` | `state` and `adapter` fixtures. |
| `agents/` | reward *form* (components / signs / `contribution == raw*weight`), state-builder observation contract (dims, float32, `[0,1]` normalisation, labels), agent inference contract (valid recommendation, honest `is_trained=False`, inspector shape, objective ownership kept separate). |
| `coordination/test_coordination.py` | priority ladder: timing short-circuits, emergency override threshold, valid-phase filter, weighted scoring, consensus, purity. |
| `coordination/test_safety.py` | one test per safety rule in `RULES` order + the `APPLIED` pass-through + validator bookkeeping. |
| `simulation/` | same-seed reproducibility, different-seed divergence, `reset()` rewind, geometry vs `config.yaml`. |
| `integration/test_api.py` | REST + WS surface through `TestClient` (lifespan on). Training + models endpoints live (status, start-validation, unknown-id 404, `training_update` over WS); `POST /simulation/model` (defaults untrained, rejects a trained request with no checkpoint, bad input); agents restricted to `{a2c, dqn}` with `GET /agents/ppo` → 404 (R9); `experiments` / `replay` still asserted **absent**, not stubbed (spec §98). |
| `training/test_training.py` | headless single-agent training: safety consulted on every decision (§113), episodes advance + `trained_episodes` increments, A2C runs real gradient steps, PPO does several on-policy updates per full episode (tuning guard — PPO now legacy but its `learn()` path stays covered), same-seed reproducibility, `TrainingManager` checkpoints round-trip. Short (~4 min sim) episodes. |
| `training/test_live_model_swap.py` | STEP 8: `SimulationManager.set_model` loads a real trained checkpoint into the live loop, flips `is_trained` honestly, reverts on `untrained`, raises for a missing checkpoint (no fake badge), and rejects deprecated `ppo` (R9). |
| `training/test_evaluation.py` | headless evaluation: fixed-time deterministic + 0 overrides, agent eval deterministic, aggregates carry every metric key, a trained checkpoint changes behaviour, `improvement_pct` sign follows metric direction, `compare` / `write_report` shapes. |
| `training/test_service.py` | `TrainingService`: idle snapshot, a real 2-episode job publishes progress then completes + registers, second concurrent run rejected (`TrainingBusy`), bad input rejected, finished run appears in `history()` / `run_detail()`. |
| `persistence/test_registry.py` | model registry: register/get round-trip + upsert, evaluation attach → `evaluated`, `promote` exclusive per agent (demotes previous), `list`/`latest`/`active` filters, `TrainingManager` auto-registers its final checkpoint (`register=False` opts out). Per-test temp SQLite. |

Every `tests/` subdirectory has an `__init__.py` so `from tests.factories import ...`
works under pytest's prepend import mode.

## Frontend

```bash
cd frontend && npm run test      # vitest run
```

`src/lib/format.test.ts` (display helpers + `ACTIVE_AGENTS` R9 scope lock),
`src/store/index.test.ts` (socket wiring via a stubbed `socket`, incl. the
`training_update` frame), `src/render/scene.test.ts` (world-frame direction vectors +
geometry constants vs the backend), `src/training/TrainingLab.test.tsx` (the `#/training`
view: TRAINING/EVALUATION/LIVE-INFERENCE framing, idle live-run state, registry rows —
API client stubbed), `src/components/ModelModeBar.test.tsx` (per-agent UNTRAINED/TRAINED
toggle reflects status + emits the `set_model` command).
