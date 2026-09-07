# Replay

Spec §18–19, §54–56, §90. A replay is a **captured run of the live decision loop** —
the ordered list of the real `DecisionRecord`s the backend already produced, replayed
frame by frame. Nothing is reconstructed or synthesised (§84).

Status: **implemented (R9 P3, 2026-09-08)** — capture on the running `SimulationManager`
+ `replays` persistence table + REST + Replay Lab UI (`#/replay`). The §19 inspectors
(Vehicle / Emergency / Signal / AI-Coordination + DQN experience replay) are the other
half of P3 and are also done — see [`inspectors.md`](inspectors.md).

## 1. What a replay frame is

One frame **is** a `DecisionRecord` (`app/schemas/events.py`) — the same object the live
dashboard renders once per AI decision:

| field | what it holds |
|---|---|
| `t` / `step` | sim time and physics step of the decision |
| `state_summary` | compact traffic state (phase, per-approach queues, vehicles, emergency, throughput, violations) |
| `recommendations` | `{a2c, dqn}` → the agent's `AgentRecommendation` (target phase, action, score, confidence, priority, value estimate, reason) |
| `coordination` | the `CoordinationDecision` — candidate phase, winner, basis, priority-ladder trace, per-phase score breakdown |
| `safety` | the `SafetyResult` — approved flag, `action_taken`, violated rules, reason, the command actually applied |
| `rewards` / `reward_breakdowns` | per-agent scalar reward and its component decomposition (realised one interval later — on-policy order, [`assumptions.md` A18](assumptions.md)) |
| `metrics` | the `MetricSnapshot` at that decision (traffic / environmental-ESTIMATED / emergency / safety) |
| `applied_phase` | the phase the signal controller ran after the safety layer |

**The cadence is the decision interval (~6 s of sim), not the physics tick.** A replay is
not a recording of vehicle positions — there is no car-level scrubbing. The Replay Lab
says this in the player (`"Vehicle-level playback is not captured."`). Vehicle-level
inspection is a live-only feature; the §19 inspectors will cover paused live state.

## 2. When a replay is captured

`SimulationManager` keeps the decision timeline of the **current run** in memory
(`_timeline`, `_timeline_events`) and persists it as a `ReplayRecord` on:

| trigger | `episode_complete` | reason tag |
|---|---|---|
| episode reaches `scenario.duration_s` (`_finish_episode`) | `True` | `episode_complete` |
| run torn down — `reset` / load scenario (`_reset_locked`, first thing) | run's done flag | `teardown` |
| explicit `POST /api/v1/replay/capture` | run's done flag | `manual` |
| process shutdown (`shutdown`) | run's done flag | `shutdown` |

A run with fewer than **`_MIN_REPLAY_DECISIONS` (3)** decisions is not worth persisting —
`_build_replay_record` returns `None` and the trigger is a no-op (so the first
`_reset_locked` at startup writes nothing, and `capture` returns `409`).

The in-memory timeline is hard-capped at `_MAX_REPLAY_FRAMES` (5000) /
`_MAX_REPLAY_EVENTS` (8000) so a pathologically long session can't grow without bound.

### Reset the run identity

`_reset_locked` mints a fresh `_run_id` (`replay-<UTC compact stamp>-<6 hex>`),
`_run_started_iso` and `_run_seed` for every new run, so the persisted `id`, `label` and
`seed` describe the run that was actually played (not `ScenarioConfig.seed`, which is just
the config default).

## 3. Persistence — `replays` table (`app/persistence/models.py`)

```
replays(
  id                TEXT  PK   -- "replay-<stamp>-<hex>"
  label             TEXT       -- "<scenario> · seed <n> · <mode> · <episode|partial>"
  created_at        TEXT  idx  -- ISO-8601 UTC
  scenario_id / scenario_name
  seed / mode / model_modes (JSON)
  config_digest     TEXT       -- config.yaml digest at capture time
  sim_duration_s / decision_count / episode_complete
  timeline          JSON       -- list[DecisionRecord] (model_dump mode="json")
  events            JSON       -- list[EventMessage] over the run
  episode_metrics   JSON|null  -- the flat episode metric bag, only when episode_complete
)
```

`ReplayStore` (`app/persistence/replays.py`) is the facade, same shape as
`ScenarioStore` / `ExperimentStore` — stateless, `init_db()` in `__init__`,
`session_scope()` per call:

```python
ReplayStore().save(record)          # upsert by id -> summary dict
ReplayStore().get(id)   -> dict | None      # full: timeline + events + episode_metrics
ReplayStore().list(limit=50) -> list[dict]  # summary only, newest first
ReplayStore().delete(id)            # ReplayStoreError if unknown
ReplayStore().prune(keep=N) -> int  # storage management (§90) - drop all but newest N
ReplayStore().count() -> int
```

`_persist_replay` calls `prune(keep=_REPLAY_KEEP)` (**40**) after every save, so the table
self-trims. `data/nexus.db` is a runtime artifact (`.gitignore: *.db`).

## 4. REST surface

| endpoint | |
|---|---|
| `GET /api/v1/replay?limit=N` | `{replays: [summary…]}` — newest first, no timeline (`limit` 1–200, default 50) |
| `POST /api/v1/replay/capture` | freeze the current live run now → `201` + summary. `409` when the run has &lt; 3 decisions |
| `GET /api/v1/replay/{id}` | full replay (timeline + events + episode metrics) or `404` |
| `GET /api/v1/replay/{id}/at?t=<sec>` | `{replay_id, index, total, t, prev_t, next_t, frame}` — the last decision frame at-or-before `t` (clamped to frame 0 before the first decision). `404` unknown id / empty timeline |
| `DELETE /api/v1/replay/{id}` | `{deleted: id}` or `404` |

Capture and delete route through `SimulationManager` (`capture_replay`, `delete_replay`)
so they run on the loop thread; list / detail / seek read `ReplayStore` directly.

There is **no** `replay_update` WS frame — a replay is immutable once captured and
playback is entirely client-side.

## 5. Replay Lab UI — `#/replay` (`frontend/src/replay/`)

`ReplayLab.tsx` is a client-side player over the REST surface. No simulation runs; it
only reads.

- **Captured-replays list** — scenario name, `FULL EPISODE` / `PARTIAL` badge,
  `seed · mode · N decisions · duration`, capture time, per-row **Delete**.
  **Refresh** and **Capture current run** (surfaces the `409` as
  *"run the simulation on the dashboard for a few decisions first"*). The newest replay
  auto-opens.
- **Metadata panel** — scenario + id, seed, control mode, per-agent model mode,
  config digest, capture time.
- **Transport** — ⏮ first · ◀ prev · ▶/⏸ play/pause · ▶ next · ⏭ last · speed
  (0.5/1/2/4×, `BASE_STEP_MS` 850 ms at 1×) · a range scrubber · a readout
  (`decision N / total · t mm:ss of mm:ss`). Play auto-stops on the last frame.
- **Per-frame panels**, all from the frame's `DecisionRecord`:
  1. **pipeline row** — `COORDINATOR` (candidate phase + winner + basis) → `SAFETY ·
     AUTHORITATIVE` (applied phase + `action_taken` + reason). Where they differ the
     safety layer won — stated in the legend and the row (§113).
  2. **AGENT RECOMMENDATIONS** — a2c / dqn: target phase, action, score / confidence /
     priority / value, reason; `— no recommendation` when absent.
  3. **COORDINATION LADDER** — the `ladder_trace` rungs + per-phase score components.
  4. **REWARD DECOMPOSITION** — per-agent total + each component's contribution
     (green / red); `breakdown not recorded for this step` when a step has none.
  5. **METRICS AT THIS DECISION** — traffic / environmental (ESTIMATED) / emergency /
     safety stat grid.
  6. **TRAFFIC STATE** — phase, per-approach queues, vehicles / queued, emergency,
     run-total violations.
  7. **EVENTS UP TO THIS POINT** — the run's events with `t ≤` the current frame.

## 6. Honesty / safety notes

- Every frame is a stored backend record; the UI never interpolates or invents a value
  (§84). A metric or reward that wasn't recorded shows as unavailable, not zero.
- The safety layer is authoritative in a replay exactly as it was live — the pipeline row
  shows the coordinated choice *and* what safety applied, and there is no control that
  can present an agent recommendation as the final action (§113).
- `episode_metrics` is populated only for a `FULL EPISODE` replay; a `PARTIAL` capture
  carries `null` there rather than a truncated aggregate.

## 7. Not yet built

- **Synchronized replay of an experiment's compared runs** on one timeline (§18) — needs
  the experiment runner to keep per-decision data, which today it does not (it records
  episode aggregates only). Deferred.
- **Export** of a replay (CSV / JSON) — R9 P4 (§23).
