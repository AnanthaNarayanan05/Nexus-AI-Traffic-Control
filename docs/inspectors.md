# Inspectors

Spec §19, §41–47. Five **read-only, pause-and-inspect** views over the live decision
loop. Every value comes straight from a backend record — the coordinator's trace, the
signal state machine, per-vehicle physics, the DQN replay buffer. Nothing is
reconstructed or synthesised (§84).

Status: **implemented (R9 P3, 2026-09-08)** — `#/inspect` route, `InspectorLab.tsx`, no
new backend endpoints except reuse of `GET /api/v1/simulation/state`. Completes P3
alongside the replay engine ([`replay.md`](replay.md)).

## 1. Where the data comes from

| Inspector | Source | Cadence |
|---|---|---|
| Coordination brain | `useAgentStore().coordination` — the `coordination_update` WS frame (`CoordinationUpdate`) | per AI decision (~6 s) |
| Signal | `useSimStore().state.signal` — the `signal_update` / `simulation_state` WS frame (`SignalState`) | 20 Hz stream |
| Emergency vehicle | `useSimStore().state.emergency` + `.signal` + `useAgentStore().coordination` + `.agents.a2c.recommendation` | 20 Hz / per decision |
| Vehicle | `GET /api/v1/simulation/state` (`FullSimulationState`, full `VehicleSnapshot[]`) polled on demand | 2 s while the tab is open |
| DQN experience replay | `useAgentInspector('dqn')` → `GET /api/v1/agents/dqn` → `extra.replay_sample` | 2 s poll |

The 20 Hz stream's `compact_vehicles` drops `accel` / `stops` / `fuel` / `co2` /
`movement`, so the Vehicle inspector fetches the full dump (`GET /simulation/state`,
which already returns the complete `SimulationState.model_dump()`) rather than reading
the stream. No new endpoint was added for it.

## 2. The five inspectors

### Coordination brain (`#/inspect`, default tab)

The "why did this decision win" page (§19, §44). From one `CoordinationUpdate`:

- **pipeline row** — `COORDINATOR` (candidate phase, winner badge, `basis`) →
  `SAFETY · AUTHORITATIVE` (applied phase, `action_taken`, reason). A warn banner when
  `action_taken !== 'APPLIED'` spelling out the coordinated → applied change.
- **PRIORITY LADDER** — every `ladder_trace` rung (`safety` / `emergency` /
  `valid_phase` / `weighted_score` / `stability`) with its outcome, detail, and a
  one-line gloss of what that rung does.
- **PHASE SCORES** — the `scores` table (congestion / efficiency / throughput /
  stability / consensus / total), the candidate phase's row highlighted.
- **AGENT RECOMMENDATIONS** — full card per active agent: action name, target phase,
  score / confidence / priority / value estimate, reason, and the `relevant_state` the
  agent keyed on. `— no recommendation` when one didn't reach the coordinator.
- **SAFETY VERDICT** — approved flag, `action_taken`, candidate vs applied phase, the
  `PhaseCommand` actually issued, `violated_rules`, reason, and a note that the safety
  layer runs on every decision and no agent can bypass it (§113).

Empty state when there is no decision yet, or the control mode is not `AI`.

### Signal

The phase state machine (§19). From `SignalState`:

- current / served phase, phase elapsed;
- **MIN GREEN** — `phase_remaining_min_s <= 0` → "satisfied — a phase change is allowed";
  otherwise a progress bar and the seconds remaining;
- **MAX GREEN** — progress bar toward the forced change;
- **TRANSITION IN PROGRESS** — kind, from → to, elapsed / total bar (only while
  `signal.transition` is set);
- `allowed_next` chips, `last_action`;
- **PER-APPROACH ASPECT** — N / E / S / W → the authoritative `approach_colors` value,
  with a note that the renderer shows exactly this, not a phase-derived colour (§114).

### Emergency vehicle

A2C's job (§19, §45). If `emergency.active` is false: an empty state plus the
`cleared_this_episode` count. If active:

- vehicle id, type, approach, distance, speed, ETA to the stop line,
  `cleared_this_episode`;
- **A2C PRIORITY RESPONSE** — whether the coordinator's `emergency` ladder rung is
  currently `override` (ACTIVE / not overriding), plus A2C's action / target phase /
  reason;
- **SIGNAL RESPONSE** — whether the current phase serves the emergency approach
  (`NS` serves N/S, `EW` serves E/W), and a note that min-green and safe transitions
  are still enforced under priority (§113).

### Vehicle

Per-vehicle state (§19, §46). Polls `GET /simulation/state` every 2 s while mounted:

- filters — approach (all / N / E / S / W), emergency-only, violator-only;
- a scrollable list (id, type, approach·lane, speed, wait, state; 🚨 / ⚠ flags),
  capped at 120 rows with a "narrow the filter" hint past that;
- click a row → a detail block: type, approach, lane, movement, speed, accel, waiting,
  stops, fuel used (ESTIMATED), CO₂ (ESTIMATED), position, heading. "Vehicle _id_ has
  left the network" once it departs.
- header note: snapshot polled every 2 s — pause the simulation to inspect a frozen
  frame.

### DQN experience replay (§17)

From the DQN inspector payload's `extra`:

- buffer size (`replay_size`), epsilon (`0` in inference — acts greedily);
- **SAMPLED TRANSITIONS** — one card per stored transition:
  `state_summary` (queue / wait / speed means, emission rate, violations) →
  action badge + reward (green / red) + done badge → `next_state_summary`. Sampled
  uniformly from the buffer, **not** in time order.
- Empty state when the buffer has not filled — "start the simulation in AI mode and let
  a few decisions run".

**The DQN records transitions whether or not it is training.** `DQNAgent.observe()`
always appends to the fixed-capacity ring buffer; `learn()` stays gated on
`self.training`, so in the live (inference) loop this is a pure observability change with
no effect on the policy. Without it the §17 inspector would have nothing real to show,
and a faked transition table is not allowed (§84).

## 3. Honesty / safety notes

- Nothing here writes to the simulation — every inspector is a `useState` /
  `useMemo` / poll over data the backend already produced.
- The Coordination brain always shows the agents' recommendations **and then** what the
  safety layer applied. Where they differ, the safety layer won. There is no control on
  any inspector that can present an agent recommendation as the final signal action
  (§113).
- A value the backend has not produced renders as `—` (`NO_DATA`), never a zero. Fuel
  and CO₂ carry the `ESTIMATED` tag (see [`assumptions.md`](assumptions.md) A12–A13).

## 4. Not yet built

- **Full-screen A2C / DQN / PPO forward-pass inspectors** (§41–43) with the network
  internals laid out — the dashboard `A2CPanel` / `DQNPanel` already carry the actor /
  critic / Q bars; a dedicated full-page view is P5 polish.
- **Synchronised pause of the render + inspector** — today "pause" is the normal
  simulation pause; a dedicated inspector freeze that snapshots the frame independent of
  the loop is deferred.
