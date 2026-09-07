# DQN — Fuel · Emission · Efficiency · Safety

Owner in the source deck: **Shaun Joseph Sabu**. PPT slides 9–13, 19–20.

> *Why DQN (PPT):* "A discrete-action, value-based problem with a large replay history to learn from —
> DQN's Q-value approximation fits directly." And: "Violation indicators enter the state, and violation
> events enter the reward as a penalty — safety is optimised alongside efficiency, not bolted on."

## 1. State (`DQNStateBuilder` → `float32[33]`)

| Group | Dims | Contents |
|---|---|---|
| Vehicle count per approach | 4 | `count / count_ref` |
| Queue per approach | 4 | `queue_length / lane_capacity` |
| Mean waiting per approach | 4 | `mean_wait_s / 120` |
| Mean speed per approach | 4 | `mean_speed_mps / free_flow_mps` |
| Stops per approach (window) | 4 | `stops_last_window / stops_ref` |
| Current phase | 8 | one-hot `NS, EW, N, E, S, W, YELLOW, ALL_RED` |
| Phase timing | 2 | `phase_elapsed / max_green` · min-green satisfied flag |
| Estimated emission rate | 1 | interval CO₂ estimate / reference |
| Violation indicator | 1 | `violations_last_window / violation_ref` (clamped) |
| Total load | 1 | total vehicles / `max_vehicles` |

Source mapping (PPT slide 11): vehicle count, queue length, average waiting time, average speed, number
of stops, current signal phase, estimated emission level, violation indicators → all present.

## 2. Actions (`DQNAction`, discrete, 5 — PPT slide 11)

| # | Name | Effect |
|---|---|---|
| 0 | `KEEP_GREEN` | hold the served phase |
| 1 | `EXTEND_GREEN` | `+extend_step_s`, bounded by max-green |
| 2 | `SWITCH_PHASE` | move to the other ring phase (`NS ↔ EW`) via the mandated transition |
| 3 | `REDUCE_GREEN` | permit an earlier change once min-green is met |
| 4 | `TRANSITION` | begin the `YELLOW → ALL_RED` clearance now (explicit safe transition) |

## 3. Reward — smoothness reward − violation penalty (PPT slides 11, 20)

`DQNReward.decompose(prev, action, curr)`:

| Component | Sign | Definition | Weight |
|---|---|---|---|
| Smooth flow | + | mean speed / free-flow, averaged over approaches | `0.4` |
| Waiting drop | + | `max(0, mean_wait_prev − mean_wait_curr)` normalised | `0.5` |
| Stop penalty | − | new stop events this interval, normalised | `0.25` |
| Idle penalty | − | vehicle-seconds spent stationary this interval, normalised | `0.15` |
| Emission penalty | − | interval CO₂ estimate, normalised | `0.6` |
| Queue penalty | − | mean queue length, normalised | `0.1` |
| **Violation penalty** | − | violation events this interval × weight | `3.0` |
| Switch penalty | − | applied on `SWITCH_PHASE` / `TRANSITION` to discourage churn | `0.1` |

## 4. Network & learning (`backend/app/agents/dqn/`)

- **`QNetwork`** — MLP `33 → 128 → 128 → 5`; **target network** copied every `target_update_interval`
  (1000 steps).
- **Replay buffer** — uniform, capacity `100_000`, `learning_starts = 1000`, `train_freq = 4`.
- **Bellman target** — `y = r + γ·(1−done)·maxₐ' Q_target(s', a')` ; Huber loss.
- **Exploration** — ε-greedy, linear decay `1.0 → 0.05` over `40_000` steps.
- **Tracked**: Q-values (per action), Q-loss, reward, ε, replay size, action frequency, TD-error
  moving average (convergence proxy).

## 5. Violation monitoring (PPT slide 12)

Separate `ViolationMonitor` component attached to the environment (not a CV model — the source explicitly
leaves the detector unspecified). Pipeline: `traffic environment → behaviour monitoring → violation
indicator → reward penalty + safety metric + timeline event`. Types: red-light run, illegal crossing
during red, lane violation, unsafe signal-related behaviour.

## 6. Experience-replay inspector (spec §17)

`GET /api/v1/agents/dqn?replay_sample=8` returns 8 sampled transitions rendered human-readably:
labelled `state` → `action` name → `reward` (with decomposition) → labelled `next_state` → `done`.
Large tensors are summarised, not dumped, unless `?raw=1`.

## 7. Working scenario (PPT slide 13 → `scenarios/efficiency_challenge.yaml`)

Stop-and-go arrivals produce high queue / stops / idle. DQN observes the state, its Q-values shift toward
`SWITCH_PHASE` / `EXTEND_GREEN` where vehicles actually wait, flow smooths, the estimated fuel and CO₂
curves fall, reward rises. In parallel a scripted violation is detected → penalty in reward + monitoring
record + timeline event.
