# System flow

## 1. One decision cycle (AI mode)

```
physics loop  ── every 0.5 s sim ──▶  BuiltinAdapter.step(dt)
                                        (arrivals, car-following, signal SM, fuel/emission accrual,
                                         violation draws)

decision loop ── every 6 s sim ──▶  SimulationManager.decide()
   1. state = adapter.get_state()
   2. f_a2c = A2CStateBuilder(state) ; f_dqn = ... ; f_ppo = ...
   3. rec_a2c = A2CAgent.act(f_a2c)   →  AgentRecommendation(action, score, confidence, reason, priority)
      rec_dqn = DQNAgent.act(f_dqn)
      rec_ppo = PPOAgent.act(f_ppo)
   4. decision = Coordinator.resolve([rec_a2c, rec_dqn, rec_ppo], state)   → CoordinationDecision
   5. result  = SafetyValidator.validate(decision.candidate, state)        → SafetyResult
                (approved | rejected+fallback ; every override logged)
   6. adapter.apply_phase(result.command)
   7. reward_a2c = A2CReward(prev_state, action, state) ; ... (for learning + display)
   8. record = DecisionRecord(t, state_summary, rec_a2c, rec_dqn, rec_ppo, decision, result,
                              rewards, metrics)  →  rollout buffer + event timeline + decisions deque
                              + the run's replay timeline (persisted as a `replays` row on
                                episode-complete / reset / capture / shutdown — see replay.md)
   9. if training_enabled: agent.observe(transition) ; agent.maybe_learn()

stream loop  ── 20 Hz real ──▶  WS hub broadcasts latest:
   simulation_state · agent_update · coordination_update · signal_update · metric_update · event
```

## 2. WebSocket message model (spec §71)

All frames: `{ "type": <string>, "seq": <int>, "t": <sim_time>, "payload": {...} }`.

| `type` | Direction | Payload |
|---|---|---|
| `hello` | S→C | protocol version, config digest, scenario, control mode |
| `simulation_state` | S→C | compacted `SimulationState` (vehicles as flat arrays) |
| `agent_update` | S→C | `{ a2c, dqn, ppo }` — each: features, outputs, selected action, reward decomposition |
| `coordination_update` | S→C | recommendations, priority ladder trace, winner, reason |
| `signal_update` | S→C | phase, transition, timers, `allowed_next`, last final action |
| `metric_update` | S→C | rolling + episode metric snapshot |
| `event` | S→C | one `EventMessage` (category, severity, description) |
| `experiment_update` | S→C | progress of a running experiment batch |
| `training_update` | S→C | per-agent training curve points |
| `error` | S→C | `{ code, message, detail }` |
| `command` | C→S | `{ action: "start"|"pause"|"reset"|"set_mode"|"manual"|"inject"|"load_scenario"|..., args }` |
| `subscribe` | C→S | channel filter (e.g. drop `simulation_state` while on the Training page) |

Client commands are also available as REST (`POST /api/v1/...`) for scripting and tests.

## 3. REST surface (spec §88)

```
GET  /api/v1/health
GET  /api/v1/config                       resolved config digest
GET  /api/v1/simulation/state             one full snapshot incl. per-vehicle detail (Vehicle inspector polls this)
POST /api/v1/simulation/start|pause|reset
POST /api/v1/simulation/mode              { mode }
POST /api/v1/simulation/manual            { action }           (MANUAL mode)
POST /api/v1/simulation/inject            { event, args }      ambulance / surge / blockage / violation
GET  /api/v1/scenarios                    presets + saved (summary + §8A metadata)
GET  /api/v1/scenarios/{id}               full ScenarioConfig blob
POST /api/v1/scenarios                    create / save custom (422 bad input, 409 preset id)
POST /api/v1/scenarios/{id}/duplicate     { new_id, name? }  copy any scenario to a custom id
DELETE /api/v1/scenarios/{id}             delete custom (409 preset, 404 unknown)
POST /api/v1/scenarios/load               { id | inline config }
GET  /api/v1/agents                       status of all three
GET  /api/v1/agents/{a2c|dqn|ppo}         full inspector payload (+ ?paused_at=); dqn carries extra.replay_sample for the §17 inspector
GET  /api/v1/coordination/last
GET  /api/v1/safety/overrides             recent override log
GET  /api/v1/metrics                      current + history window
POST /api/v1/experiments                  configure + queue a batch
GET  /api/v1/experiments/{id}
GET  /api/v1/experiments                  list
POST /api/v1/training                     start/stop a training run
GET  /api/v1/models                       registry
POST /api/v1/models/load                  { agent, version }
GET  /api/v1/replay                       captured runs of the live loop (summary, newest first)
POST /api/v1/replay/capture               freeze the current live run into a replay now (409 if < 3 decisions)
GET  /api/v1/replay/{id}                  full decision timeline + events + episode metrics
GET  /api/v1/replay/{id}/at?t=            the decision frame (agents + coordination + safety + metrics) at-or-before t
DELETE /api/v1/replay/{id}                drop one replay (storage management, §90)
GET  /api/v1/export/experiments/{id}      ?format=csv|json   comparison run download (R9 P4)
GET  /api/v1/export/replays/{id}          ?format=csv|json   decision timeline download (R9 P4)
```

## 4. Determinism contract

Given `(scenario, seed, controller, model versions, config digest)` a headless run reproduces the same
metric series. The live UI loop is wall-clock paced, so a *live* session is only reproducible when run
through the experiment runner (fixed sim-step count, no frame skipping). Documented in
[`experiments.md`](experiments.md) §4.
