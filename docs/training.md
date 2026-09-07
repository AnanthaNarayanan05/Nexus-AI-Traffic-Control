# Training — headless single-agent RL

Spec §100 (vertical slices), §111 (agent contract), §113 (safety authoritative),
§84 (no fabricated numbers). Code: `backend/app/training/`, CLI
`scripts/training/train.py`.

Slice 2, first cut. Each of the three policies is trained **on its own**, against its
own reward, against a fresh built-in simulation. The coordination engine plays no part
in training — it is an inference-time concern (PPT slide 20: *"three reward functions,
one behind each algorithm — rather than one shared equation"*).

## Pipeline (identical to the live loop, minus coordination)

```
agent.act(state)            # stochastic — the agent's `training` flag is True
   → agent.resolve_phase()  # action index → concrete Phase
   → action_to_command()    # → PhaseCommand
   → SafetyValidator.validate()   ← AUTHORITATIVE (spec §113)
   → adapter.apply_phase(result.command)
```

The policy only ever observes the effect of `result.command` — the command the safety
layer actually allowed. An action the safety layer would rewrite or block is never
"tried" in the environment. Safety overrides are counted per episode and recorded in
the run metrics; their individual `WARNING` log lines are muted for the duration of a
run (`TrainingManager(quiet_safety_logs=True)`, the default) so the progress output
stays readable.

## Reward

Both the live `SimulationManager` and `TrainingEnv` build the `RewardContext` through
the same function — `app.agents.common.rewards.make_reward_context(prev, curr, …)` — so
a policy learns against exactly the reward signal it is later evaluated on. The reward
for decision *N* is realised at decision *N+1* (on-policy order), and the final decision
of an episode is realised with `done=True` so terminal bootstrapping is correct.

## Cadence

From `configs/config.yaml → simulation` (§92): physics tick `step_length_s` (0.5 s),
decision every `decision_interval_s` (6 s), episode `episode_length_s` (3600 s) →
600 decisions per episode. Override the episode length for quick iterations with
`--episode-seconds`.

## Scenarios

Each agent trains on its own stress preset by default (see
`app/scenarios/presets.py`):

| Agent | Objective | Default scenario |
|---|---|---|
| A2C | emergency-vehicle prioritisation | `emergency_heavy` |
| DQN | fuel / emission / violation | `high_stop_go` |
| PPO | congestion reduction | `rush_hour` |

Override with `--scenario <preset id>`.

## Seeds

`--seed S` is the **base** seed. Episode *N* runs with seed `S + (N − 1)` — the whole
run is reproducible from `S`, while episodes still vary so the policy sees a spread of
traffic. Default `S` is `simulation.seed` (42).

## CLI

```bash
python -m scripts.training.train --agent a2c --episodes 200
python -m scripts.training.train --agent ppo --episodes 300 --scenario rush_hour --seed 7
python -m scripts.training.train --agent dqn --episodes 50 --episode-seconds 900   # quick
```

Also `make train AGENT=a2c EPISODES=200`.

Per-episode line: return, mean reward, decision count, gradient-update count, safety
overrides, wall time, and whatever `agent.learn()` reported (losses / entropy / …).

## Artifacts

Under `models/<agent>/` (git-ignored):

| File | Contents |
|---|---|
| `<run_id>-ep<NNN>.pt` | torch checkpoint at the `--checkpoint-every` cadence + the final episode |
| `latest.pt` | copy of the final checkpoint — what the app loads |
| `<run_id>.json` | full run record: per-episode returns / losses / safety-override counts / episode `MetricSnapshot` + a reproducibility blob (scenario, seeds, config digest, git commit, torch/python/platform, reward weights, RL hyper-params) |

Checkpoint payload (per agent `save()`): `state_dict`, `trained_episodes`,
`model_version`, `meta` (`run_id`, `scenario`, `seed`, `episode`, `config_digest`,
`trained_at`); DQN also stores `env_steps`.

## What runs, per algorithm

- **A2C** — n-step returns every `rl.a2c.n_steps` (20) decisions; updates from episode 1.
- **DQN** — fills the replay buffer to `rl.dqn.learning_starts` (1000 transitions ≈ first
  ~2 episodes) before the first gradient step; then trains every `train_freq` steps with
  a target network.
- **PPO** — GAE + clipped-surrogate update once the rollout reaches
  `rl.ppo.rollout_steps` (200), i.e. ~3 updates per 600-decision episode. Each update
  runs `rl.ppo.epochs` (6) passes over the rollout in `minibatch_size` (64) chunks,
  shuffled by a seeded RNG (reproducible). At episode end, `update_at_episode_end`
  forces one more update on the leftover rollout (if it holds at least
  `PPOAgent._MIN_UPDATE_STEPS` = 16 steps) and then clears it, so a rollout never
  spans two episodes or two seeds. `learn(force=True)` is the episode-end path;
  off-policy DQN ignores `force`.

## Evaluation

`app/training/evaluation.py` + `python -m scripts.training.evaluate`. Runs three
controllers over the **same held-out seeds** — fixed-time, the agent's untrained
(random-init) network, and a trained checkpoint — with the policy deterministic
(`training=False` ⇒ argmax for A2C/PPO, greedy for DQN). Safety stays authoritative.
Aggregates every episode `MetricSnapshot` with mean / median / std / min / max / 95 % CI
half-width (`summarise_series`, Student-t for n < 30) and reports signed improvement %
vs fixed-time (sign follows whether lower or higher is better for each metric). Writes
`models/<agent>/eval-<ts>.json`.

```bash
python -m scripts.training.evaluate --agent a2c --scenario emergency_heavy \
    --seeds 1,2,3,4,5,6,7,8 --checkpoint models/a2c/latest.pt [--register]
```

`--register` attaches the comparison blob to the checkpoint's row in the model
registry (`docs/persistence.md`), matched by the checkpoint's `run_id`.

### A2C — `a2c-v1.4-dev`, `emergency_heavy`, seeds 1–8 (held out from training seeds 42–241)

| Metric | fixed-time | untrained A2C | **trained A2C** | trained vs fixed |
|---|--:|--:|--:|--:|
| emergency delay (s) | 18.19 | 44.40 | **12.95** | **+28.8 %** |
| emergency wait (s) | 7.82 | 29.85 | **3.73** | **+52.2 %** |
| emergency travel time (s) | 46.61 | 72.82 | **41.38** | +11.2 % |
| emergencies cleared | 175.8 | 174.1 | 175.9 | +0.1 % |
| avg vehicle waiting (s) | 4.68 | 37.84 | **1.82** | **+61.1 %** |
| avg queue (veh) | 1.13 | 5.69 | **0.72** | +36.1 % |
| avg speed (m/s) | 7.46 | 4.79 | **9.99** | +33.9 % |
| stops / veh | 0.45 | 0.60 | 0.39 | +13.6 % |
| fuel / veh (est.) | 0.103 | 0.119 | 0.100 | +2.6 % |
| CO₂ / veh (est.) | 0.257 | 0.295 | 0.251 | +2.4 % |
| throughput (vph) | 1957 | 1860 | 1807 | −7.7 % |
| safety overrides / episode | 0.0 | 70.4 | **147.2** | — |

n = 8; CIs are wide (e.g. avg-waiting ±0.8–1.5 s) — **indicative, not a significance
claim**. Full per-metric CIs in the JSON report.

**Reading it honestly:**
- Training worked. The untrained random-init network is *catastrophic* (emergency wait
  30 s, avg waiting 38 s); the trained policy beats **both** it and fixed-time on its own
  objective and on most secondary metrics.
- The one real cost is **throughput −7.7 %** (CIs overlap, so weak) and a small rise in
  `other_violations` (0.5 → 1.0 events/episode, tiny absolute).
- **The trained policy leans on the safety layer:** 147 overrides/episode vs fixed-time's
  0. It proposes aggressive switches to emergency phases and the safety rules (min/max
  green, emergency timeout) bound them every interval. This is spec-compliant (§113 —
  safety is authoritative and doing its job) but it means "learned A2C behaviour" is
  partly "propose aggressively, get bounded". Worth watching in the coordinated-AI
  comparison and a candidate for a future shaping-penalty review.

### DQN — `dqn-v1.4-dev`, `high_stop_go`, seeds 1–8 (held out from training seeds 42–241)

Run `dqn-20260907T165632Z`: 200 episodes, 773 s. ε reaches its 0.05 floor by ~episode 67;
~151 gradient steps/episode. Episode return is roughly flat (−492 first-5 → −475 last-5);
mean Q keeps drifting negative through training (−18 → −45) — the value function has **not
fully converged** at 200 episodes, though the resulting greedy policy is already useful.

| Metric | fixed-time | untrained DQN | **trained DQN** | trained vs fixed |
|---|--:|--:|--:|--:|
| avg vehicle waiting (s) | 5.27 | 14.17 | **1.96** | **+62.9 %** |
| avg queue (veh) | 2.03 | 4.78 | **1.00** | **+50.8 %** |
| idle time (s) | 7.77 | 20.43 | **3.71** | **+52.3 %** |
| avg speed (m/s) | 6.74 | 5.93 | **9.68** | +43.6 % |
| stops / veh | 0.47 | 0.53 | 0.41 | +12.4 % |
| travel time (s) | 52.11 | 66.29 | 47.27 | +9.3 % |
| **fuel / veh (est.)** | 0.103 | 0.110 | **0.101** | **+2.6 %** |
| **CO₂ / veh (est.)** | 0.259 | 0.275 | **0.253** | **+2.4 %** |
| emergency wait (s) | 6.29 | 24.43 | 4.26 | +32.3 % |
| throughput (vph) | 2558 | 2273 | 2333 | −8.8 % |
| red-light violations / ep | 7.0 | 4.0 | **9.5** | **−35.7 %** |
| other violations / ep | 1.25 | 1.13 | 2.13 | −70 % |
| safety overrides / episode | 0.0 | 41.6 | **27.4** | — |

n = 8, wide CIs — indicative only. Report: `models/dqn/eval-20260907T171040Z.json`.

**Reading it honestly:**
- Learning is real: the greedy policy is nothing like the untrained network (which is
  catastrophic — avg waiting 14 s, 41 safety overrides/ep), Q-values evolved over training,
  and behaviour clearly differs from random.
- It **beats fixed-time on its own objective** — fuel −2.6 %, CO₂ −2.4 % per vehicle — and
  substantially on congestion/idle/speed, which feed those numbers.
- **The cost is safety.** Trained DQN runs *more* red-light violations than fixed-time
  (9.5 vs 7.0/ep) and its proposals are overridden ~27×/episode. The DQN reward already
  carries a violation penalty; the policy still trades some of it for flow. Same pattern as
  A2C ("propose aggressively, safety bounds it"). Candidate for a reward-shaping /
  penalty-weight review, and the throughput dip (−8.8 %, CIs overlap) wants a longer run.
- mean-Q drift says the run was **stopped before convergence**; a longer schedule (or a
  lower LR / larger target-update interval) is the obvious next experiment.

## Not yet (next sub-slice)

- tuned PPO full run, evaluated the same way (config tuned + smoke-verified; run pending)
- DQN convergence follow-up (longer schedule) + reward-penalty review for A2C/DQN
- `GET /api/v1/training` + `TrainingManager` progress streamed over WS
- Training Lab UI (`/training` route) and trained-vs-fixed-time comparison
- wiring a chosen (`active`) checkpoint into the live `SimulationManager` agent registry

The SQLite model registry now indexes every run's final checkpoint (`docs/persistence.md`).
The live app still runs inference-only (honest `UNTRAINED` badges) until a checkpoint is
promoted (`status = active`) and wired in.
