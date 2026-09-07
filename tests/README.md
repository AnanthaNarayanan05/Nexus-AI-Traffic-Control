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
| `integration/test_api.py` | REST + WS surface through `TestClient` (lifespan on). Deferred endpoints (training / experiments / models / replay) asserted **absent**, not stubbed (spec §98). |

Every `tests/` subdirectory has an `__init__.py` so `from tests.factories import ...`
works under pytest's prepend import mode.

## Frontend

```bash
cd frontend && npm run test      # vitest run
```

`src/lib/format.test.ts`, `src/store/index.test.ts` (socket wiring via a stubbed
`socket`), `src/render/scene.test.ts` (world-frame direction vectors + geometry
constants vs the backend).
