# A2C — Emergency Vehicle Prioritization

Owner in the source deck: **Anantha Narayanan A**. PPT slides 4–8, 19–20.

> *Why A2C (PPT):* "A continuous trade-off between two competing values (emergency delay vs.
> normal-traffic delay) — Actor picks the action, Critic scores how good the trade-off is."

## 1. State (`A2CStateBuilder` → `float32[31]`)

| Group | Dims | Contents (all normalised to ~[0, 1] or [-1, 1]) |
|---|---|---|
| Emergency presence | 1 | `1.0` if an emergency vehicle is detected on any approach |
| Emergency direction | 4 | one-hot `N, E, S, W` (all zero if none) |
| Emergency kinematics | 3 | distance / approach length · speed / free-flow · ETA clamped to 30 s |
| Queue per approach | 4 | `queue_length / lane_capacity` for `N, E, S, W` |
| Waiting per approach | 4 | `mean_wait_s / 120` |
| Density per approach | 4 | `density_veh_per_km / jam_density` |
| Current phase | 8 | one-hot `NS, EW, N, E, S, W, YELLOW, ALL_RED` |
| Phase timing | 2 | `phase_elapsed_s / max_green_s` · `1.0` if min-green satisfied |
| Normal throughput | 1 | vehicles cleared per second / reference rate |

Source mapping: emergency detected/location/distance/speed, queue length per lane, waiting time, current
signal phase, traffic density, normal traffic flow (PPT slide 6) → all present.

## 2. Actions (`A2CAction`, discrete, 5 — PPT slide 6)

| # | Name | Effect (resolved against current state by `resolve_a2c_action`) |
|---|---|---|
| 0 | `MAINTAIN` | keep the current served phase, no timer change |
| 1 | `EXTEND` | request `+extend_step_s` of green on the current served phase (bounded by max-green) |
| 2 | `SWITCH_EMERGENCY` | request the single-approach phase for the emergency direction; no-op (→ `MAINTAIN`) if no emergency |
| 3 | `REDUCE` | shorten current green — allow a phase change as soon as min-green is met |
| 4 | `RESTORE_NORMAL` | leave any emergency phase, return to the `NS`/`EW` ring phase that best matches current demand |

The action is a **request**. Coordination may or may not carry it forward; safety may veto it. What the
agent *chose* is always recorded and shown, distinct from what was *applied*.

## 3. Reward — `R = -α·Wₑ - β·Q + γ·Pₑ + δ·T` (PPT slides 6, 20)

Computed by `A2CReward.decompose(prev, action, curr)` over the decision interval:

| Term | Symbol | Definition | Default weight |
|---|---|---|---|
| Emergency wait | `Wₑ` | Σ waiting seconds accrued by active emergency vehicles this interval, normalised | `α = 1.0` |
| Normal queue | `Q` | mean non-emergency queue length across approaches, normalised | `β = 0.15` |
| Emergency passage | `Pₑ` | `+1` per emergency vehicle that clears the intersection this interval; partial credit for distance closed | `γ = 2.0` |
| Throughput | `T` | non-emergency vehicles cleared this interval, normalised | `δ = 0.3` |
| *Switching penalty* | — | `-switch_penalty` if the served phase changed and no emergency is active — **[ASSUMPTION]**, curbs flapping (spec §13 allows documented engineering penalties) | `0.2` |

`decompose()` returns every term separately so the UI reward panel and the inspector show component
contributions (spec §85).

## 4. Network & learning (`backend/app/agents/a2c/`)

- **`ActorCritic`** — shared MLP trunk `31 → 128 → 128`, then a policy head `→ 5` (logits) and a value
  head `→ 1`. `tanh` activations.
- **Advantage** — n-step returns (`n_steps = 20`) with bootstrap: `Aₜ = Σγⁱrₜ₊ᵢ + γⁿV(sₜ₊ₙ) − V(sₜ)`.
- **Losses** — `L_actor = -(logπ(a|s)·A) - entropy_coef·H(π)` ; `L_critic = value_coef·MSE(V, return)` ;
  `max_grad_norm = 0.5`.
- **Optimizer** — Adam, `lr = 3e-4`, `γ = 0.99`.
- **Tracked** (→ `training_update`, inspector): episode reward, actor loss, critic loss, mean value
  estimate, mean advantage, action probabilities, action frequency, mean emergency delay.

## 5. Inspector payload (`GET /api/v1/agents/a2c`)

`features` (labelled vector) · `actor_probs` (5) · `selected_action` · `critic_value` · `advantage`
(last) · `reward` (component breakdown + total) · `reward_history` · `emergency` block ·
`decision_history` (last N) · `model` (version, episodes trained, checkpoint) · `training` (latest curve).

## 6. Working scenario (PPT slide 7 → `scenarios/emergency_response.yaml`)

Ambulance from the North while E–W flows: state flags the emergency → actor weighs priority vs. E–W cost
→ actor selects `SWITCH_EMERGENCY` → coordinator gives emergency the top non-safety rung → safety
validates the `EW → YELLOW → ALL_RED → N` transition → ambulance clears → `RESTORE_NORMAL` → adaptive
control resumes before E–W queues build. Bounded by `emergency_max_priority_s`.
