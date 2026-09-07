# PPO — Adaptive Traffic Congestion Reduction

Owner in the source deck: **Delna Liz Denny**. PPT slides 14–18, 19–20.

> *Why PPO (PPT):* "Continuously shifting demand needs stable, incremental policy updates — PPO's
> clipped objective avoids destructive large updates."

## 1. State (`PPOStateBuilder` → `float32[33]`)

| Group | Dims | Contents |
|---|---|---|
| Queue per approach | 4 | `queue_length / lane_capacity` |
| Vehicle count per approach | 4 | `count / count_ref` |
| Mean waiting per approach | 4 | `mean_wait_s / 120` |
| Arrival rate per approach | 4 | `arrival_rate_vph / arrival_ref` |
| Mean speed per approach | 4 | `mean_speed_mps / free_flow_mps` |
| Density per approach | 4 | `density_veh_per_km / jam_density` |
| Current phase | 8 | one-hot `NS, EW, N, E, S, W, YELLOW, ALL_RED` |
| Phase duration | 1 | `phase_elapsed_s / max_green_s` |

Source mapping (PPT slide 16): queue length per lane, number of vehicles, average waiting time, vehicle
arrival rate, current signal phase, duration of current phase, average vehicle speed, traffic density →
all present.

## 2. Actions (`PPOAction`, discrete, 4 — PPT slide 16)

| # | Name | Effect |
|---|---|---|
| 0 | `KEEP_PHASE` | hold the current phase |
| 1 | `EXTEND_GREEN` | `+extend_step_s`, bounded by max-green |
| 2 | `REDUCE_GREEN` | permit an earlier change once min-green is met |
| 3 | `SWITCH_PHASE` | move to the other ring phase via the mandated transition |

## 3. Reward — `R = -α·Q - β·W + γ·T` (PPT slides 16, 20)

`PPOReward.decompose(prev, action, curr)` over the decision interval:

| Term | Symbol | Definition | Weight |
|---|---|---|---|
| Queue | `Q` | mean queue length across approaches, normalised | `α = 0.25` |
| Waiting | `W` | mean waiting time across approaches, normalised | `β = 0.4` |
| Throughput | `T` | vehicles cleared this interval, normalised | `γ = 0.5` |
| *Switch penalty* | — | `-switch_penalty` on `SWITCH_PHASE` — **[ASSUMPTION]** (spec allows documented penalties) | `0.15` |

## 4. Network & learning (`backend/app/agents/ppo/`)

- **`PolicyValueNet`** — shared trunk `33 → 128 → 128`, policy head `→ 4`, value head `→ 1`.
- **Rollout buffer** — `rollout_steps = 512`, GAE(`γ = 0.99`, `λ = 0.95`).
- **Clipped objective** — `L^CLIP = E[min(ρₜ·Aₜ, clip(ρₜ, 1−ε, 1+ε)·Aₜ)]`, `ε = 0.2`,
  `epochs = 4`, `minibatch = 64`, value + entropy coefficients `0.5 / 0.01`, `max_grad_norm = 0.5`.
- **Tracked**: policy loss, value loss, entropy, KL estimate, clip fraction, reward, mean advantage,
  episode return.

## 5. Queue-pressure readout (PPT slide 17, UI §19)

`PPOAgent.pressure()` exposes a normalised per-approach queue-pressure vector plus the recommendation
(`"EXTEND NORTH GREEN"` etc.) for the dashboard PPO strip — derived from the same state the policy sees.

## 6. Working scenario (PPT slide 17 → `scenarios/uneven_demand.yaml`)

N–S carries a large queue, E–W a small one. PPO detects the imbalance in the state, selects
`EXTEND_GREEN` on the N–S ring, the N–S queue drains, the advantage estimate confirms the gain vs. the
prior policy, positive reward is returned, and the policy updates via the clipped objective — green time
follows demand, not the clock.
