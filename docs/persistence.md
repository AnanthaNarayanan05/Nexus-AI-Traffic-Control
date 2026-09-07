# Persistence

Spec §55, §90. SQLite via SQLAlchemy 2 (`SQLAlchemy==2.0.36`, already a backend
dependency). Store at `data/nexus.db` (override with `NEXUS_DB_URL`). Tests get a fresh
temp database per test (autouse `_isolated_db` fixture in `tests/conftest.py`).

Four tables so far: the model registry (`models`, Slice 2), experiments (`experiments`,
R9 P1), user-saved scenarios (`scenarios`, R9 P2) and captured replays (`replays`, R9 P3).
`app/persistence` follows one facade-per-table shape so the rest slot in next to
`ModelRecord`.

## `app/persistence`

| Module | Responsibility |
|---|---|
| `db.py` | one lazy process-wide `Engine` + `sessionmaker` from `settings.db_url`; `init_db()` (create tables), `session_scope()` (commit/rollback/close), `reset_engine_for_tests()` |
| `models.py` | ORM tables: `ModelRecord` (`models`), `ExperimentRecord` (`experiments`), `ScenarioRecord` (`scenarios`), `ReplayRecord` (`replays`) |
| `registry.py` | `ModelRegistry` — the write/read API over `models` |
| `experiments.py` | `ExperimentStore` — create / complete / fail / get / list over `experiments` ([`experiments.md` §5](experiments.md)) |
| `scenarios.py` | `ScenarioStore` — save (upsert) / get / list / delete over `scenarios` ([`scenarios.md`](scenarios.md)) |
| `replays.py` | `ReplayStore` — save (upsert) / get / list / delete / `prune(keep=N)` / count over `replays` ([`replay.md` §3](replay.md)) |

SQLite pragmas on connect: `foreign_keys=ON`, `journal_mode=WAL`.

## `models` table

One row per trained checkpoint that the pipeline keeps (the final checkpoint of a run;
more if a caller registers them).

| Column | Source |
|---|---|
| `id` | `<run_id>-ep<NNN>` |
| `agent` / `version` | agent name / `agent.model_version` at save time |
| `checkpoint_path` | absolute `.pt` path |
| `run_id` / `scenario` / `seed` / `episodes` | the `TrainingRun` |
| `training_config` | `reproducibility.rl_hyperparams` (JSON) |
| `reward_config` | `reproducibility.reward_weights` (JSON) |
| `env_version` | `config.digest` (sha256[:16] of `config.yaml`) |
| `code_version` / `torch_version` | git short sha / `torch.__version__` |
| `created_at` / `evaluated_at` | ISO-8601 UTC |
| `eval_scenario` / `eval_metrics` | attached after an evaluation (JSON `compare()` blob) |
| `status` | lifecycle, below |
| `notes` | free text |

### Status lifecycle

```
trained ──(attach_evaluation)──▶ evaluated ──(promote)──▶ active
   │                                  │                     │
   └──────────────(promote)───────────┴─────────────────────┘
                                                    archived (set_status)
```

- **`trained`** — checkpoint registered, not yet evaluated.
- **`evaluated`** — an evaluation blob is attached.
- **`active`** — this is the checkpoint live inference loads for that agent.
  `promote()` is exclusive: promoting one `active` model demotes the previous one
  (back to `evaluated` if it had an eval, else `trained`). At most one `active` per agent.
- **`archived`** — retired; kept for provenance.

## How rows get written

| Path | When |
|---|---|
| `TrainingManager.run()` → `_register()` | end of every training run (unless `register=False`). Registry failure logs a warning and never fails the run — the `<run_id>.json` on disk is still the full record. |
| `python -m scripts.training.evaluate --agent <a> --scenario <s> --register` | attaches the `compare()` blob to the checkpoint's row (matched by the checkpoint's `run_id`, or `--model-id`). |
| `python -m scripts.training.backfill_registry [--agent <a>]` | imports runs that finished before the registry existed, from their `models/<agent>/<run_id>.json` records, and attaches the newest matching `eval-*.json`. Idempotent. |

## `ModelRegistry` API

```python
reg = ModelRegistry()
reg.register(model_id=..., agent=..., version=..., checkpoint_path=..., run_id=...,
             scenario=..., seed=..., episodes=..., training_config={}, reward_config={},
             env_version=..., code_version=..., torch_version=..., status="trained")
reg.register_training_run(run, checkpoint=None, model_id=None)   # from a TrainingRun
reg.attach_evaluation(model_id, scenario=..., metrics={...})     # -> status "evaluated"
reg.promote(model_id)                                            # -> status "active" (exclusive)
reg.set_status(model_id, "archived")
reg.get(model_id) -> dict | None
reg.list(agent=None, status=None) -> list[dict]                  # newest first
reg.active(agent) -> dict | None                                 # the live-serving row
reg.latest(agent) -> dict | None                                 # newest row, any status
```

`data/nexus.db` is a runtime artifact (`.gitignore`: `*.db`). Rebuild it any time with
`backfill_registry`; the durable records are the `models/**/*.json` files.
