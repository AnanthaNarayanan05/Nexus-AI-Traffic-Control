# Safety Constraint Layer

Spec §22, §82, §113 — **authoritative**. No RL recommendation, however advantageous, may bypass it.

## 1. Position in the pipeline

```
CoordinationDecision.candidate_phase  ──▶  SafetyValidator.validate(candidate, state)  ──▶  SafetyResult
                                                                                             │
                          approved ────────────────────────────────────────────────────────┤
                          rejected ──▶ choose safest admissible alternative ────────────────┘
```

`SignalController` only ever executes a `SafetyResult.command`. It has no path that takes a raw agent or
coordinator action.

## 2. Rules enforced (`backend/app/safety/rules.py`)

| Rule | Check |
|---|---|
| **Phase compatibility** | `candidate` is a defined phase; its movements do not conflict with a phase already being served without a transition between them |
| **Minimum green** | a served green must last ≥ `min_green_s` before any change (emergency included — the source states emergency actions "remain constrained by min green / yellow / max green") |
| **Maximum green** | a served green ≥ `max_green_s` is *forced* to change even if every agent said hold |
| **Yellow transition** | any served → served change is rewritten to `served → YELLOW(yellow_s) → ALL_RED(all_red_s) → candidate` |
| **All-red clearance** | enforced between antagonistic phases |
| **No mid-transition switching** | while in `YELLOW` / `ALL_RED`, the only admissible command is "continue the transition" |
| **Conflicting phases** | `NS`/`EW` and single-approach phases that would green-light crossing streams are rejected |
| **Emergency timeout** | a single-approach emergency phase may not be held beyond `emergency_max_priority_s`; on timeout, safety forces `RESTORE_NORMAL` |
| **Post-emergency recovery** | after an emergency phase ends, the next served phase is the demand-matched ring phase, then normal control resumes |

## 3. `SafetyResult`

```
SafetyResult
  approved:      bool
  command:       PhaseCommand  (what SignalController will execute this tick)
  original:      the candidate phase the coordinator asked for
  action_taken:  "APPLIED" | "REWRITTEN_TRANSITION" | "BLOCKED_HOLD" | "FORCED_CHANGE" | "EMERGENCY_TIMEOUT"
  violated_rules: list[str]     (rule ids the candidate broke)
  reason:        human string ("Minimum current-green duration not reached (4.0 s < 8.0 s)")
```

## 4. Override logging (spec §22)

Every result where `action_taken ≠ "APPLIED"` is written to the structured log (`component = "SAFETY"`),
emitted as a `SAFETY` timeline event, and stored on the `DecisionRecord`. The Safety inspector and
`GET /api/v1/safety/overrides` expose the recent history. Example timeline entry:

```
13:42:09  SAFETY   RL action SWITCH_TO_N blocked — min green not reached (4.0 s < 8.0 s). Held NS.
```

## 5. Tests (`tests/coordination/test_safety.py`, spec §82)

Explicit cases: min-green block · max-green forced change · yellow inserted on ring change · conflicting
phase rejected · no switching mid-transition · emergency still bounded by min-green · emergency timeout
forces restore · post-emergency recovery path. Each asserts both the `command` and the `action_taken` /
`reason`.
