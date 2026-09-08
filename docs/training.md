# Training — headless single-agent RL

Spec §100 (vertical slices), §111 (agent contract), §113 (safety authoritative),
§84 (no fabricated numbers). Code: `backend/app/training/`, CLI
`scripts/training/train.py`.

Slice 2, first cut. Each policy is trained **on its own**, against its own reward,
against a fresh built-in simulation. The coordination engine plays no part in
training — it is an inference-time concern (PPT slide 20: *"three reward functions,
one behind each algorithm — rather than one shared equation"*).

> **R10 (2026-09-09):** active training scope is **A2C + DQN + PPO**. PPO
> (adaptive congestion reduction, owner Delna Liz Denny) is a first-class agent
> again — trainable here, in `TrainingService`, and from the CLI, on the `uneven`
> scenario by default. See [`STATUS.md`](STATUS.md).

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
| DQN | efficiency / fuel / emissions / safety | `high_stop_go` |
| PPO | adaptive congestion reduction (R = −αQ − βW + γT) | `uneven` |

Override with `--scenario <preset id>`.

## Seeds

`--seed S` is the **base** seed. Episode *N* runs with seed `S + (N − 1)` — the whole
run is reproducible from `S`, while episodes still vary so the policy sees a spread of
traffic. Default `S` is `simulation.seed` (42).

## CLI

```bash
python -m scripts.training.train --agent a2c --episodes 200
python -m scripts.training.train --agent dqn --episodes 50 --episode-seconds 900   # quick
python -m scripts.training.train --agent ppo --episodes 200 --scenario uneven --seed 7
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

## REST + WebSocket

`app/training/service.py` runs **one** job at a time on its own thread (mirrors
`SimulationManager`: heavy work off the event loop, readers poll an immutable snapshot).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/training` | service status + current job + `?history=` recent finished runs |
| `POST` | `/api/v1/training/runs` | start a run `{agent, episodes, scenario?, seed?, checkpoint_every?}` — `409` if one is already running, `422` on bad input |
| `GET` | `/api/v1/training/runs` | finished runs (from the on-disk `<run_id>.json` records) |
| `GET` | `/api/v1/training/runs/{run_id}` | full run record |
| `GET` | `/api/v1/models` | model-registry rows — `?agent=` `?status=` |
| `GET` | `/api/v1/models/{model_id}` | one registry row |

WebSocket: a `training_update` frame is pushed on every published change —
`{seq, running, job: {run_id, agent, scenario, seed, phase, episode, progress, returns,
last_episode: {return, mean_reward, decisions, updates, safety_overrides, losses, metrics},
final_checkpoint, registered_model_id, error}}`. `phase ∈ idle | running | completed | failed`.
Every value is a real measurement from that episode (§84); a failed run reports the
exception, it is never hidden.

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

### PPO — `ppo-v1.4-dev`, `uneven`, seeds 1–8 (held out from training seed 7)  *(R10 retrain)*

*R10 restored PPO as a first-class active agent (adaptive congestion reduction,
`R = −αQ − βW + γT`). The historical `rush_hour` checkpoint is config-incompatible (the
config digest changed since it trained), so PPO was retrained from scratch on `uneven` —
lopsided demand `{N .45, E .30, S .15, W .10}` at 2200 vph, the scenario whose whole point
is a persistent asymmetric queue for PPO to rebalance. The old run/checkpoint/eval stay on
disk (destructive-change rule); the numbers below supersede them.*

Run `ppo-20260908T193352Z`: 200 episodes, 858 s, **3 real PPO updates/episode** (GAE +
clipped surrogate, 6 epochs × 64-minibatch). **Return is essentially flat** — block-mean
+189.0 (first 5) → +190.4 (last 5), delta **+1.3**. Entropy holds ~1.2–1.4, clip-fraction
~0.09, approx-KL ~0.005 (stable, not collapsing — just not improving). On this scenario the
reward is dominated by the throughput term `γT`, which is demand-bounded and near-constant
across policies, so the gradient signal PPO can actually act on is small. This is the
measured curve; it has not been reshaped to look like learning.

| Metric | dir | fixed-time | untrained PPO | **trained PPO** | trained vs fixed |
|---|:--:|--:|--:|--:|--:|
| avg vehicle waiting (s) | ↓ | 6.23 ±1.10 | 11.27 ±4.03 | **5.38 ±1.49** | +13.7 % *(CIs overlap)* |
| avg queue (veh) | ↓ | 2.41 ±0.71 | 2.53 ±1.18 | 2.34 ±0.65 | +2.6 % *(within noise)* |
| avg travel time (s) | ↓ | 53.41 ±0.27 | 62.75 ±0.65 | 62.47 ±0.59 | **−17.0 % (CIs disjoint)** |
| avg speed (m/s) | ↑ | 6.25 ±0.59 | 7.47 ±1.17 | 7.82 ±0.68 | +25.1 % |
| **throughput (vph)** | ↑ | 2430 ±288 | 2445 ±393 | **2168 ±133** | **−10.8 %** |
| safety overrides / episode | — | 0.0 | 71.9 | **54.0** | — |

n = 8, wide CIs — indicative, not a significance claim. Report:
`models/ppo/eval-20260908T194951Z.json`.

**Reading it honestly (§18):**
- **Training helps relative to untrained** — trained PPO nearly halves untrained's waiting
  (5.4 vs 11.3 s), matches its travel time, and cuts safety overrides 72 → 54/ep. The
  policy is doing something real and deterministic, not random.
- **Trained PPO does not beat fixed-time overall on `uneven`.** It trims the stop-line
  queue and average wait (+2.6 % / +13.7 %, both inside the noise band), but pays for it
  with **−10.8 % throughput** and a **−17.0 % end-to-end travel time regression whose CIs
  do not overlap fixed-time's** — a genuine loss, not noise. It holds green on the busy
  approaches, so cars near the stop line clear faster while the network as a whole moves
  fewer vehicles and each trip takes longer.
- Same throughput-vs-delay trade seen in A2C and DQN, more sharply here because the
  reward barely rewards raw vehicles-served. Flagged for a reward-weight review
  (raise `alpha_queue` / add an explicit travel-time term), not a training bug.
- 54 safety overrides/episode — the policy proposes aggressively and the authoritative
  safety layer bounds it (§113-compliant).
- **No improvement is claimed or manufactured.** PPO is a first-class *active* agent under
  R10 — real objective, real PPO updates, real checkpoint, real held-out eval — and this
  is what that eval measured.

### Cross-agent notes

Two findings recur across A2C, DQN and PPO and belong in the write-up:
1. **Throughput dips** (A2C −7.7 % / DQN −8.8 % / PPO −10.8 %) while the delay/queue/stop
   metrics improve. Consistent trade, driven by reward weighting, not a bug. For PPO on
   `uneven` the trade is not worth it — travel time regresses with disjoint CIs.
2. **Heavy reliance on the safety layer** (147 / 27 / 54 overrides per episode). The
   safety controller is authoritative and doing its job; "learned behaviour" is partly
   "propose aggressively, get bounded". Reward-shaping to discourage the aggressive
   proposals is the follow-up.

## Trained checkpoints in live inference (STEP 8)

`POST /api/v1/simulation/model {agent, mode, version?}` (or the `set_model` WS command)
swaps a live agent between:

- **`untrained`** — a fresh `AgentClass(seed=...)`. Always available, idempotent.
- **`trained`** — the agent's `active` registry row (else the most recent). The manager
  checks the checkpoint file exists, loads it into a fresh instance, and **only keeps it
  if `trained_episodes > 0` after load**. Any failure → HTTP 400 and the running agent is
  left exactly as it was. No path sets `is_trained` without a real checkpoint behind it
  (§84 / §114).

`status()` gains `model_modes` and `model_sources` (the registry id the weights came
from). The safety layer is unchanged and still authoritative for both modes (§113). The
dashboard's `ModelModeBar` drives this per agent; the badge mirrors the backend's honest
`is_trained`.

Promote a checkpoint to `active` with `ModelRegistry.promote(model_id)` (see
`docs/persistence.md`) so `mode:"trained"` picks it up without an explicit `version`.

## Not yet (next sub-slice)

- DQN convergence follow-up (longer schedule); reward-penalty / throughput-weight review for all three
- Trained-vs-fixed-time comparison surfaced inside the Training Lab (the eval JSON reports already exist)
