# Limitations

Preserved honestly from the source (PPT slide 22) and spec §97. This project is a **simulation-based
research demonstrator**, not a deployable traffic controller.

## From the academic source (PPT "Challenges & Limitations")
| Limitation | How it shows up here |
|---|---|
| **Reward design** — weighting objectives per algorithm | Weights in `config.yaml`; results are sensitive to them. We report the weights used with every experiment. |
| **Coordinating three independently trained agents** | The coordinator is a transparent priority ladder, not a learned meta-policy. Conflicts are resolved by rule, not by a jointly optimal criterion. |
| **Training time** — many episodes across three algorithms | Shipped checkpoints are lightly trained on CPU. Deeper training needs a GPU and hours. |
| **Exploration risk during training** | ε-greedy (DQN) and entropy bonuses (A2C/PPO) can produce poor intermediate policies; training is done headless, never on the live demo. |
| **Generalization across intersections** | Single intersection only. No claim of transfer. |
| **Safety constraints** (min green / yellow) | Enforced by the safety layer, which can and does override "better" RL actions. |
| **Simulation-to-real gap** | The microsimulation is uncalibrated. Absolute numbers are not real-world predictions. |

## Additional engineering limitations
- **Fuel & CO₂ are estimates** from a parametric model (see [`assumptions.md`](assumptions.md) A12–A13),
  labelled ESTIMATED throughout. No emissions species beyond CO₂.
- **No computer vision.** Violation and emergency-vehicle "detection" is simulated, not sensed.
- **Built-in engine ≠ SUMO.** Vehicle dynamics are simplified; a `SumoAdapter` is scaffolded but not
  wired.
- **Determinism is not bit-exact** across different BLAS / CPU for the torch forward pass; the metric
  series is stable, the last few significant digits of logits are not (see [`experiments.md`](experiments.md) §4).
- **Coordination assumes** the three agents' `priority` signals are comparable on a `[0, 1]` scale; they
  are constructed to be, but this is a modelling choice.
- **Live sessions are not reproducible** frame-for-frame (wall-clock paced); use the experiment runner
  for reproducible results.

## Future extensions (PPT slide 22)
Coordinate agents further with shared or communicated state — one agent per objective, per intersection,
across a network.
