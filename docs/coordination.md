# Coordination Engine

Spec §20–21. PPT slide 19: *"coordinated at the traffic-signal level, not merged into one shared
network."* Each agent stays algorithmically distinct; the coordinator arbitrates between their
**recommendations**.

## 1. `AgentRecommendation`

Every agent's `act()` returns:

```
AgentRecommendation
  agent:        "a2c" | "dqn" | "ppo"
  action:       the agent's own action enum value
  target_phase: the concrete phase the action resolves to given current state ("NS","EW","N",...)
  score:        float in [0, 1]  — agent's confidence-weighted preference for its own best action
  confidence:   float in [0, 1]  — softmax margin (policy) or normalised Q-gap (value)
  priority:     float in [0, 1]  — objective-urgency signal (A2C: emergency pressure; DQN: violation +
                                   emission pressure; PPO: max queue pressure)
  reason:       short human string ("Ambulance 43 m on N, closing 12 m/s")
  relevant_state: the few state fields that drove the choice (for the UI "what did it see")
```

## 2. Deterministic priority ladder (spec §21)

`Coordinator.resolve(recs, state)` is a pure function — identical inputs always yield the identical
`CoordinationDecision`. It walks the ladder from `config.yaml → coordination.priority_order`:

| Rung | Rule |
|---|---|
| **1. Safety** | If the current phase cannot legally change yet (min-green unmet, mid-transition), the only admissible candidate is "hold" — the ladder short-circuits to `target_phase = served_phase`, `winner = "constraint"`. |
| **2. Emergency** | If `state.emergency.active` **and** `rec_a2c.priority ≥ emergency_override_threshold` (0.55): `rec_a2c` wins outright. `winner = "a2c"`, `basis = "emergency_override"`. A2C's `target_phase` is the candidate. |
| **3. Valid phase** | Candidates whose `target_phase` is not in `state.signal.allowed_next` (plus "hold") are dropped before scoring. |
| **4–7. Weighted score** | For each *remaining* candidate phase `p`, sum contributions: `congestion` = PPO score if PPO's target = `p`; `efficiency` = DQN score if DQN's target = `p`; `throughput` = small bonus for the phase serving the most vehicles; `stability` = `-switch_bias` if `p ≠ served_phase`. Add `consensus_bonus` (0.1) per additional agent that also targets `p`. Highest total wins. |

Ties break toward `served_phase` (stability), then by fixed phase order — never randomly.

## 3. `CoordinationDecision`

```
CoordinationDecision
  candidate_phase:   the phase handed to the safety layer
  winner:            "a2c" | "dqn" | "ppo" | "consensus" | "constraint"
  basis:             "emergency_override" | "weighted_score" | "min_green_hold" | "transition_lock"
  ladder_trace:      ordered list of {rung, outcome, detail}  — drives the UI "why this won"
  scores:            per-candidate-phase score breakdown
  recommendations:   the three AgentRecommendations, passed through for display
```

## 4. Examples (spec §21)

**Consensus** — all three target `N` green: rung 2 not triggered (no emergency), rung 4 scores `N`
highest with a +0.2 consensus bonus. `winner = "consensus"`, basis `weighted_score`.

**Conflict** — A2C→`N` (emergency), DQN→`EW`, PPO→`N`: rung 2 fires because
`emergency.active ∧ a2c.priority ≥ 0.55`. `winner = "a2c"`, basis `emergency_override`, trace records
"efficiency preference (DQN→EW) overridden by emergency priority".

**Constraint** — served `NS` for only 4 s (min-green 8 s): rung 1 short-circuits,
`candidate_phase = NS`, `winner = "constraint"`, basis `min_green_hold` — no agent could have changed it.

## 5. Guarantees

- Pure / deterministic (tested in `tests/coordination/`).
- Never averages actions, never votes without weights (spec §21).
- Emits a full trace for every decision — nothing about the outcome is opaque.
- Output is a *candidate*: the safety layer still has the final word (spec §113).
