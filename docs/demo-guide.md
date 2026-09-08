# Demo guide

MASTER_PROMPT §24, §60–63, §108. Presentation mode is a reduced-chrome shell around the
live loop, built for projecting on a room-sized screen. Every flagship demo is pinned to a
fixed seed, so a run on stage is bit-for-bit the run you rehearsed.

## Launch

```bash
make dev            # backend :8000 + frontend :5173
# open http://localhost:5173  →  click the "Presentation" tab  (or open /#/present)
```

Presentation mode replaces the command bar and the view tabs with:

- a slim header — NEXUS brand, the active demo name, a LIVE / PAUSED badge, the pinned
  seed, and one **✕ Exit presentation** control (or press `Esc`);
- the intersection stage, the coordinator → authoritative-safety pipeline, and the
  measured-metrics row, all enlarged;
- a rail with the four flagship-demo launchers and, once one is running, its plain-English
  brief and a "what to watch" list.

The seed is **42** (`configs/config.yaml → simulation.seed`), shared by all four demos.

## Flagship demos (§60–63)

Each launcher fires three ordinary WebSocket commands — the same channel the command bar
uses: `set_mode {mode: "AI"}` → `load_scenario {id, seed: 42}` → `start`. Nothing is
pre-recorded; the agents, the coordinator and the safety layer run exactly as they do on
the dashboard.

| # | Demo | Key | Scenario preset | Owner algorithm | What to point at |
|---|---|---|---|---|---|
| 1 | Emergency Response Challenge | `1` | `emergency_heavy` | A2C — emergency prioritization | Emergency wait falls as A2C holds green for the approach; the coordination basis flips to an emergency override; every forced change is still bounded by the safety layer. |
| 2 | Efficiency Challenge | `2` | `high_stop_go` | DQN — fuel / CO₂ / stops | Stops per vehicle trend down; fuel and CO₂ per vehicle (both `ESTIMATED`) settle lower; average speed rises without the queue blowing up. |
| 3 | Congestion Reduction | `3` | `uneven` | PPO — adaptive congestion reduction | Demand is lopsided across the four approaches; PPO reweights the green split toward the busy ones, so queue and average wait trend down while throughput holds; the coordination basis shows the congestion term carrying the decision. |
| 4 | Mixed Crisis | `4` | `mixed_crisis` | Full AI — coordination + safety | All three agents produce a recommendation every cycle; the coordinator picks a winner and the safety layer has the final say; no unsafe transitions even under load. |

`Restart this demo` reloads the current scenario at the pinned seed and starts it again.

## Suggested narration (Mixed Crisis)

1. Launch demo 4. The stage fills with heavy N–S demand; the metrics row starts from zero.
2. An ambulance appears — the stage banner shows its approach and ETA.
3. In the coordination panel, the A2C, DQN and PPO recommendations are shown
   side by side, then the coordinator's pick, then what the safety layer actually applied.
4. When safety rewrites or blocks a change, the amber banner says so — "no agent
   recommendation can bypass this layer".
5. Watch **Unsafe transitions** stay at 0 in the metrics row while everything else moves.
6. For the numbers-vs-fixed-time story, exit and open `/#/experiments` — run `mixed_crisis`
   with `ai` + `fixed_time` over several seeds and read the comparison table (improvement %
   with confidence intervals). That is a measured experiment, not a demo effect.

## Honesty notes (§84, §114)

- The metrics row is the live `MetricSnapshot` — nothing is smoothed or compared against a
  baseline in the browser.
- Fuel and CO₂ are parametric estimates and are labelled `ESTIMATED` (see
  [`assumptions.md`](assumptions.md) A12–A13).
- Presentation mode never disables or hides the safety layer; it only reduces navigation
  chrome.

## Not built

- A scripted multi-step auto-advancing tour (the demos are launched by hand).
- A headless `demo_check` reliability harness. The equivalent coverage today:
  `tests/scenarios/test_presets.py` builds every preset, and `tests/training/` runs the
  scenarios headless for determinism and safety-consultation checks.
