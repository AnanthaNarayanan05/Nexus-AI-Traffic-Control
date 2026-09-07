# Metrics

Spec §38–39, §52. Four families (PPT slide 21). Every metric is computed from the vehicle set / event
log — none is invented.

## 1. Families

### Traffic efficiency
| Metric | Definition |
|---|---|
| `avg_waiting_s` | mean cumulative wait over vehicles present |
| `avg_queue` | mean over approaches of vehicles below 2 m/s upstream of the stop line |
| `throughput_vph` | vehicles departed in a rolling 60 s window, scaled to /hour |
| `avg_travel_time_s` | mean (depart_time − enter_time) over completed trips |
| `avg_speed_mps` | mean speed over vehicles present |
| `stops_per_veh` | mean stop events per completed trip |
| `idle_time_s` | vehicle-seconds below 0.3 m/s per completed trip |

### Environmental (estimated — see [`assumptions.md`](assumptions.md))
| Metric | Definition |
|---|---|
| `fuel_l_per_veh` | mean estimated litres per completed trip |
| `co2_kg_per_veh` | mean estimated kg CO₂ per completed trip |
| `fuel_l_total`, `co2_kg_total` | cumulative for the run |

### Emergency response
| Metric | Definition |
|---|---|
| `emergency_wait_s` | mean wait accrued by emergency vehicles |
| `emergency_travel_time_s` | mean emergency trip duration |
| `emergency_delay_s` | emergency travel time − free-flow travel time for the same route |
| `emergency_cleared` | count cleared this run |

### Safety / violations
| Metric | Definition |
|---|---|
| `red_light_violations` | count |
| `other_violations` | lane / unsafe-cross count |
| `unsafe_transitions` | count of safety-layer `action_taken` in the unsafe set (always 0 by construction — reported to prove it) |

## 2. Aggregation

- **Rolling** (`MetricsAggregator.rolling`) — exponential + fixed-window (60 s) estimates, pushed every
  `metric_update` for the live dashboard.
- **Episode** (`MetricsAggregator.episode`) — full-run means / totals, emitted on episode end and stored
  on the `simulation_run`.
- **Experiment** — mean, median, std, min, max, and a `confidence_level` CI over episodes
  (`scipy.stats.t` for n < 30). Improvement % vs. baseline is `(baseline − ai) / baseline` for
  minimise-metrics, sign-flipped for throughput. Significance is reported only when the CI excludes 0
  (spec §53 — no overstating).

## 3. Developer metrics (spec §74)

`fps`, `frame_time_ms`, `ai_latency_ms` (decision-cycle wall time), `sim_step_ms`, `ws_latency_ms`,
`memory_mb` — surfaced in the command bar and `/api/v1/metrics?dev=1`. Reported as measured; no target
is claimed as achieved without a measurement (spec §104).
