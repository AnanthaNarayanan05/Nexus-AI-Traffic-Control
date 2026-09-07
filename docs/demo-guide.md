# Demo guide

Spec §60–63, §108. Presentation mode is deterministic under a fixed seed.

## Launch

```bash
make dev            # backend :8000 + frontend :5173
# open http://127.0.0.1:5173  → press  P  (or open /#/present)
```

Presentation mode: minimal nav, enlarged panels, a scripted scenario sequence, seed pinned to
`configs/config.yaml → simulation.seed`.

## Default demo script (§108)

| Step | Action | What to point at |
|---|---|---|
| 1 | Launch NEXUS, `NORMAL` scenario | the live intersection is the centre of the screen |
| 2 | Let it settle ~20 s | metrics row stabilises; AI mode active |
| 3 | Scenario → `UNEVEN DEMAND` | PPO strip: N–S queue pressure climbs |
| 4 | — | PPO recommendation flips to "EXTEND N–S GREEN"; coordination bar shows PPO winning on `congestion` |
| 5 | Press **E** (spawn ambulance N) | red alert; A2C panel activates |
| 6 | — | A2C actor bars shift to `SWITCH_EMERGENCY`; critic value shown |
| 7 | — | DQN Q-value bars update live |
| 8 | — | PPO still pushing congestion relief |
| 9 | Coordination bar | "Emergency priority overrides efficiency preference" — basis `emergency_override` |
| 10 | Safety bar | `EW → YELLOW → ALL_RED → N` transition validated |
| 11 | — | signal changes on the canvas; ambulance route highlighted |
| 12 | — | ambulance crosses; `emergency_delay` metric updates |
| 13 | — | A2C issues `RESTORE_NORMAL`; adaptive control resumes |
| 14 | — | recovery — E–W queues drain |
| 15 | Open `/#/experiments` → run `mixed_crisis` (5 seeds, ai + fixed_time) | progress streams in |
| 16 | Comparison table | fixed-time vs. NEXUS AI with improvement % and CIs |

## Flagship demos

- **Emergency Response Challenge** — `scenarios/emergency_response.yaml`. A2C end-to-end.
- **Efficiency Challenge** — `scenarios/efficiency_challenge.yaml`. DQN: stop-and-go → smooth, fuel/CO₂
  curves fall, a scripted violation is penalised.
- **Mixed Crisis** — `scenarios/mixed_crisis.yaml`. High N traffic + ambulance on N + moderate E +
  violation event + uneven demand, exercising all three agents, coordination, and safety at once.

## Reliability checklist (§105) — run before presenting

`scripts/validation/demo_check.py` runs each flagship scenario headless 3× and asserts: no crash, no
vehicle stuck > 180 s, no signal stuck > `max_green + transition`, WS stays connected, all three agents
produce recommendations every cycle, metrics advance, and no value in the stream is flagged `mock`.
