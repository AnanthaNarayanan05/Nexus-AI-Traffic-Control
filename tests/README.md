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
| `agents/` | reward *form* (components / signs / `contribution == raw*weight`), state-builder observation contract (dims, float32, `[0,1]` normalisation, labels), agent inference contract (valid recommendation, honest `is_trained=False`, inspector shape, objective ownership kept separate); DQN raw Q-values in the inspector, and `observe()` fills the replay buffer in inference mode while `learn()` stays a no-op (R9 P3 §17). |
| `api/test_exporters.py` | R9 P4 export serialisers (`app/api/exporters.py`): experiment CSV is one tidy row per `(metric, controller)` with the full stats + honest improvement %, baseline row has no improvement; replay CSV is one row per decision (coordinator candidate → authoritative applied phase, safety verdict, per-agent reward, flat metrics), a missing metric is blank not zero (§84); `safe_filename` strips path separators / dodgy chars. Pure functions, no DB. |
| `coordination/test_coordination.py` | priority ladder: timing short-circuits, emergency override threshold, valid-phase filter, weighted scoring, consensus, purity. |
| `coordination/test_safety.py` | one test per safety rule in `RULES` order + the `APPLIED` pass-through + validator bookkeeping. |
| `simulation/` | same-seed reproducibility, different-seed divergence, `reset()` rewind, geometry vs `config.yaml`. |
| `integration/test_api.py` | REST + WS surface through `TestClient` (lifespan on). Training + models endpoints live (status, start-validation, unknown-id 404, `training_update` over WS); `POST /simulation/model` (defaults untrained, rejects a trained request with no checkpoint, bad input); agents restricted to `{a2c, dqn}` with `GET /agents/ppo` → 404 (R9); `experiments` endpoints live (R9 P1 — status/detail shapes, `POST` validation: ppo controller → 422, unknown scenario → 404, empty seeds → 422, missing checkpoint → 422); scenarios (R9 P2 — all 8 §8A presets present with metadata, `POST` create validates + persists + 409 on preset id + 422 on out-of-range / unknown field, `duplicate`, `DELETE` refuses presets / 404 unknown); replay (R9 P3 — `capture` 409 below the minimum then 201, list is summary-only, `GET /{id}` frame shape, `/at?t=` lands on the right decision, `DELETE` then 404, and a run reset with decisions leaves a `partial` replay behind); export (R9 P4 — unknown id → 404, bad `format` → 422, an experiment written straight to the store then exported as CSV + JSON with the `attachment` header, a real captured replay exported as a per-decision CSV). |
| `training/test_training.py` | headless single-agent training: safety consulted on every decision (§113), episodes advance + `trained_episodes` increments, A2C runs real gradient steps, PPO does several on-policy updates per full episode (tuning guard — PPO now legacy but its `learn()` path stays covered), same-seed reproducibility, `TrainingManager` checkpoints round-trip. Short (~4 min sim) episodes. |
| `training/test_live_model_swap.py` | STEP 8: `SimulationManager.set_model` loads a real trained checkpoint into the live loop, flips `is_trained` honestly, reverts on `untrained`, raises for a missing checkpoint (no fake badge), and rejects deprecated `ppo` (R9). |
| `training/test_evaluation.py` | headless evaluation: fixed-time deterministic + 0 overrides, agent eval deterministic, aggregates carry every metric key, a trained checkpoint changes behaviour, `improvement_pct` sign follows metric direction, `compare` / `write_report` shapes. |
| `training/test_service.py` | `TrainingService`: idle snapshot, a real 2-episode job publishes progress then completes + registers, second concurrent run rejected (`TrainingBusy`), bad input rejected, finished run appears in `history()` / `run_detail()`. |
| `experiments/test_experiment_store.py` | `ExperimentStore` (R9 P1): `create` is `running` + carries the reproducibility blob, duplicate id rejected, `complete` writes comparison/results in place, `fail` records the error, `list` is newest-first summary-only, `complete` on an unknown id raises. Per-test temp SQLite. |
| `experiments/test_experiment_service.py` | `ExperimentService` (R9 P1): idle snapshot, a real `fixed_time` + `a2c` 2-seed run publishes progress then completes (comparison-blob honesty: baseline row has `None` improvement, `model_mode == "untrained"`), completed run persisted + in `history()`, second concurrent run rejected (`ExperimentBusy`), bad input rejected, a trained checkpoint is used when selected by registry id. |
| `scenarios/test_presets.py` | R9 §8A: `REQUIRED_PRESET_IDS` is exactly the eight; every preset (incl. `surge_midway`) builds with a non-empty objective / ai_focus / valid difficulty; `list_scenarios()` marks presets and surfaces the metadata; `get_scenario()` returns a fresh copy; `safety_violation` / `mixed_crisis` carry their stress knobs; unknown id → `KeyError`. |
| `scenarios/test_scenario_store.py` | R9 §8B: `ScenarioConfig` validation (out-of-range → `ValidationError`, unknown field forbidden, bad slug / weather, bad or full-closure `blocked_lanes`, scheduled change past episode end, zero demand); `ScenarioStore` CRUD round-trip (upsert, delete, missing-id raises); `register_scenario` persists + survives a cache/engine reset, rejects preset ids; `delete_scenario` refuses presets / unknown; a saved custom scenario actually runs a headless episode. Per-test temp SQLite + `_reset_custom_for_tests()`. |
| `persistence/test_registry.py` | model registry: register/get round-trip + upsert, evaluation attach → `evaluated`, `promote` exclusive per agent (demotes previous), `list`/`latest`/`active` filters, `TrainingManager` auto-registers its final checkpoint (`register=False` opts out). Per-test temp SQLite. |
| `persistence/test_replay_store.py` | `ReplayStore` (R9 P3): save → get round-trips the full timeline, unknown id → `None`, save is an upsert, `list` is summary-only (no timeline) and newest-first, `delete` removes + missing raises `ReplayStoreError`, `prune(keep=N)` keeps the newest N. Per-test temp SQLite. |

Every `tests/` subdirectory has an `__init__.py` so `from tests.factories import ...`
works under pytest's prepend import mode.

## Frontend

```bash
cd frontend && npm run test      # vitest run
```

`src/lib/format.test.ts` (display helpers + `ACTIVE_AGENTS` R9 scope lock),
`src/store/index.test.ts` (socket wiring via a stubbed `socket`, incl. the
`training_update` and `experiment_update` frames), `src/render/scene.test.ts` (world-frame
direction vectors + geometry constants vs the backend), `src/training/TrainingLab.test.tsx`
(the `#/training` view: TRAINING/EVALUATION/LIVE-INFERENCE framing, idle live-run state,
registry rows — API client stubbed), `src/components/ModelModeBar.test.tsx` (per-agent
UNTRAINED/TRAINED toggle reflects status + emits the `set_model` command),
`src/experiments/ComparisonTable.test.tsx` (the R9 §16 honesty rules: baseline column
always shown, directional-improvement colouring, "within noise" for sub-CI deltas, no fake
ratio when the baseline is ~0, direction indicators), `src/experiments/ExperimentLab.test.tsx`
(the `#/experiments` view: honest-comparison framing, controller picker, past-experiment
rows, a completed row opens from the keyboard (Enter, R9 P6), CSV / JSON export links on a
completed run's detail point at `/export/experiments/{id}` (R9 P4) — API client stubbed),
`src/scenarios/ScenarioLab.test.tsx` (the `#/scenarios` view:
presets list with difficulty, presets are read-only with only "Duplicate to edit", a custom
scenario opens editable with Save/Delete, "+ New" slugifies the name into the id and Save
posts the draft, the preview describes the draft in plain English — API client stubbed),
`src/replay/ReplayLab.test.tsx` (the `#/replay` view: list with PARTIAL / FULL-EPISODE
badge, newest replay auto-opens and shows the coordinator → authoritative-safety pipeline,
the transport steps through decisions, "Capture current run" hits the endpoint and shows
the result with a friendly message on 409, "vehicle-level playback is not captured" stated,
a replay row is selectable from the keyboard (Enter, R9 P6),
CSV / JSON export links point at `/export/replays/{id}` (R9 P4) — API client stubbed),
`src/present/PresentationMode.test.tsx` (the `#/present` view, R9 P4 §60–63: the three
flagship demos are listed; launching one fires the real command sequence — `set_mode` AI →
`load_scenario` at the pinned seed 42 → `start`; the "what to watch" brief appears; the
number keys launch and `Esc` exits; the launchers are disabled while the backend is offline
— socket + child panels stubbed), `src/inspectors/InspectorLab.test.tsx` (the `#/inspect` view, R9 P3
§19: the Coordination brain shows the coordinator → authoritative-safety pipeline + priority
ladder + phase scores + per-agent recommendations + safety verdict, warns when safety
rewrote the choice, empty state outside AI mode; the Signal tab renders the phase SM +
per-approach authoritative aspect; the Emergency tab shows the active EV + A2C priority
override, empty otherwise; the Vehicle tab polls `GET /simulation/state`, lists + filters
vehicles (a `role="listbox"` of `role="option"` rows) and opens a per-vehicle detail on
click or from the keyboard (Space, R9 P6); the DQN tab renders sampled `state → action →
reward → next state → done` transitions and an empty-buffer state; the inspector-view
buttons carry `aria-pressed` for the active view and every panel title is a real heading
(R9 P6) — API client + stores stubbed), `src/components/MetricsRow.test.tsx` (the live metrics panel, R9 P5: the figures
are read straight from the `MetricSnapshot`, an awaiting-first-snapshot badge shows before
any frame, the trend strip accumulates a polyline across distinct `sim_time` frames, and a
frame re-published at the same `sim_time` adds no sample — so a single reading stays a
dashed placeholder, never a faked flat line (§84) — socket stubbed),
`src/components/EventTimeline.test.tsx` (the event timeline, R9 P5: events render in
store order newest-first, a category filter chip hides that category and updates the
visible/total count, Clear empties the list, a server-side command rejection is shown
verbatim and dismissed on click, and the empty state distinguishes "nothing yet" from
"everything filtered out" — socket stubbed).
