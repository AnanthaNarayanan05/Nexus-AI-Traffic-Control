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
- **PPO** — one GAE + clipped-surrogate update once the rollout reaches
  `rl.ppo.rollout_steps` (512); roughly one update per episode at the 600-decision
  cadence. Tuning the rollout length for more frequent updates is a follow-up.

## Not yet (next sub-slice)

- SQLite model registry (`models` table, `docs/experiments.md §5`) and versioning
- `GET /api/v1/training` + `TrainingManager` progress streamed over WS
- Training Lab UI (`/training` route) and trained-vs-fixed-time comparison
- wiring a chosen checkpoint into the live `SimulationManager` agent registry

Until the registry exists, `latest.pt` on disk is the record of truth and the live app
still runs inference-only (honest `UNTRAINED` badges).
