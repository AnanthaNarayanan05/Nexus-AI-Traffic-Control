# Scenarios

Spec §28, R9 §8A (presets) + §8B (custom builder). A scenario is the full definition of
one traffic situation — demand, events, closures, conditions — that the live dashboard,
the Training Lab and the Experiment Lab all run against.

Status: **implemented (R9 P2, 2026-09-08)** — 8 preset scenarios with metadata,
`ScenarioConfig` validation, a `scenarios` persistence table, CRUD REST endpoints and the
Scenario Lab UI (`#/scenarios`).

## 1. `ScenarioConfig`

`backend/app/schemas/scenario.py`. Every field is bounded; `model_config` forbids unknown
fields.

| field | meaning | bounds |
|---|---|---|
| `id` | slug, primary key | `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$` |
| `name` / `description` | display | 1–120 / 0–1000 chars |
| `objective` | what a viewer should watch for (§8A) | display only, ≤ 500 chars |
| `ai_focus` | which agent / metric family this exercises (§8A) | display only, ≤ 500 chars |
| `difficulty` | `easy` \| `moderate` \| `hard` \| `extreme` (§8A) | display only |
| `demand.weights` | per-approach relative weights (N/E/S/W) | each ≥ 0, total > 0 |
| `demand.arrivals_vph` | total arrivals per hour | `(0, 12000]` |
| `demand.turn_split` | left / through / right fractions | each ≥ 0, total > 0 |
| `scheduled_changes` | `[{at_s, profile}]` mid-episode demand swaps | every `at_s` < `duration_s` |
| `emergency_probability_per_min` | emergency-vehicle spawn rate | `[0, 60]` |
| `violation_probability_scale` | multiplier on base red-run probability | `[0, 20]` |
| `accident_probability_per_min` | accident rate | `[0, 60]` |
| `blocked_lanes` | `[{approach, lane}]` closed lanes | approach ∈ N/E/S/W, lane ∈ 0–2, never **all** lanes of one approach |
| `weather` | `clear` \| `rain` \| `fog` \| `snow` \| `storm` | display / atmosphere only |
| `time_of_day` | `day` \| `night` \| `dawn` \| `dusk` | display / atmosphere only |
| `duration_s` | episode length | `[60, 14400]` |
| `seed` | RNG seed | `≥ 0` |

The metadata fields (`objective`, `ai_focus`, `difficulty`) are **display only** — nothing
in the microsimulation reads them.

**Safety:** there is no scenario-level switch for the authoritative safety layer (§113),
and `extra="forbid"` means a request cannot introduce one. An out-of-range value is a
`422`, never a silent clamp — what the user asked for is exactly what runs.

## 2. Preset scenarios (§8A)

Built lazily in `backend/app/scenarios/presets.py` from `configs/config.yaml ->
demand.profiles`. `REQUIRED_PRESET_IDS` is the eight R9 §8A scenarios, in presentation
order:

| id | name | difficulty | AI focus | profile |
|---|---|---|---|---|
| `normal` | Normal traffic | easy | both — the control case | `normal` |
| `rush_hour` | Rush hour | hard | DQN throughput / waiting under saturation | `rush_hour` |
| `emergency_heavy` | Emergency response | hard | A2C emergency prioritization | `normal` + 3.0 emergency/min |
| `uneven` | Unequal demand | moderate | adaptive phase splitting | `uneven` |
| `high_stop_go` | Stop-go efficiency | moderate | DQN fuel / CO₂ / stops-per-vehicle | `high_stop_go` |
| `incident` | Road blockage | hard | coordination / DQN queue balancing | `normal` + E lane 1 closed |
| `safety_violation` | Safety / violation | hard | safety layer (authoritative) + DQN violation penalty | `safety_stress` + ×2.5 violation, accidents |
| `mixed_crisis` | Mixed crisis | extreme | all three at once | `mixed_crisis` + emergencies + blockage + mid-episode surge |

`surge_midway` ("Mid-episode surge", moderate) is kept as a **ninth, non-required**
preset — it is the simplest scenario that exercises `scheduled_changes`, and pre-R9 runs
or registry rows may still reference it. Per the R9 destructive-change rule it was not
deleted when the required set was fixed at eight.

New demand profiles added for the required set: `safety_stress` (balanced + heavy,
maximises red-running temptation) and `mixed_crisis` (asymmetric + very heavy).

`get_scenario(pid)` returns a fresh deep copy every call. `list_scenarios()` returns
summaries (`_summary()`) carrying the metadata plus normalised weights and a
`scheduled_changes` count.

## 3. Custom scenarios (§8B)

User-created scenarios are persisted; presets never are.

- **Table** `scenarios` (`backend/app/persistence/models.py::ScenarioRecord`): `id` PK,
  `name`, `config` (full JSON blob), `created_at`, `updated_at`.
- **Store** `ScenarioStore` (`backend/app/persistence/scenarios.py`): `save` (upsert),
  `get`, `list` (newest first), `delete`. Mirrors the `ExperimentStore` facade.
- **In-process** `app.scenarios.presets._CUSTOM` is populated lazily on first access
  (`_load_custom()` — avoids a DB hit at import and keeps the tests' per-test SQLite
  isolation intact). `register_scenario(sc, persist=True)` writes through to the store;
  `delete_scenario(pid)` rejects preset ids and removes from both.

### REST

| method + path | behaviour |
|---|---|
| `GET /api/v1/scenarios` | presets + custom, summary + §8A metadata |
| `GET /api/v1/scenarios/{id}` | full `ScenarioConfig` blob (preset or custom) |
| `POST /api/v1/scenarios` | create / update a custom scenario — `422` on a bounds violation or unknown field, `409` if the id is a preset |
| `POST /api/v1/scenarios/{id}/duplicate` | `{new_id, name?}` — copy any scenario (preset or custom) to a new custom id; `409` if `new_id` is a preset |
| `DELETE /api/v1/scenarios/{id}` | delete a custom scenario — `409` for a preset, `404` if unknown |
| `POST /api/v1/scenarios/load` | reset the live simulation onto `{id}` or an inline `{config}` |

## 4. Scenario Lab UI (`#/scenarios`)

`frontend/src/scenarios/ScenarioLab.tsx`. Hash route (no react-router), same two-column
`lab-columns` layout as the Training / Experiment labs.

- **Left** — preset list (R9 §8A) then custom list, each row showing the difficulty badge,
  the objective and the AI focus. "+ New" starts a blank draft from the standard defaults.
- **Right** — a preset opens **read-only** with a single **Duplicate to edit** action; a
  custom scenario (or a new draft) opens a full editable form: name / id-slug, description,
  objective, AI focus, difficulty, demand (4 weights + arrivals + turn split), emergency /
  violation / accident rates, an add/remove list of closed lanes, an add/remove list of
  mid-episode demand changes, weather / time-of-day, duration and seed.
- **Preview** — a plain-English paragraph regenerated live from the current draft
  (`describe()`), e.g. *"~2,600 veh/h, heaviest from N (50%), lightest from W (10%).
  Emergency vehicles about 0.40/min. Episode 1:00:00 long, seed 42."*
- **Actions** — Save / Duplicate / Delete / **Load into simulation**. Backend `422` / `409`
  messages are shown verbatim; nothing is clamped client-side.

The API client (`frontend/src/lib/api.ts`) sends `cache: 'no-store'` so a backend restart
can never leave the browser showing a stale scenario list.

## 5. Not yet built

- Inline scenario editing from the Experiment Lab / command bar (they select by id only).
- Import / export of a scenario file (covered by the P4 export work).
