# Simulation

## 1. Engine strategy (spec §9, decision recorded in §122 style)

**Assumption:** SUMO + `libsumo` are not available in the target environment, so the default engine is a
self-contained **pure-Python microsimulation**. Everything above `SimulationAdapter` is engine-agnostic,
so a `SumoAdapter` can be dropped in without touching agents, coordination, safety, metrics, or the UI.

```python
class SimulationAdapter(Protocol):
    def reset(self, scenario: ScenarioConfig, seed: int) -> None: ...
    def step(self, dt: float) -> None: ...                  # advance physics by dt seconds
    def apply_phase(self, phase: PhaseCommand) -> None: ...  # request a signal phase / transition
    def inject(self, event: SimEvent) -> None: ...           # ambulance, surge, blockage, violation
    def get_state(self) -> SimulationState: ...              # typed, adapter-independent snapshot
    @property
    def sim_time(self) -> float: ...
```

| Adapter | Module | Status |
|---|---|---|
| `BuiltinAdapter` | `backend/app/simulation/builtin/` | implemented |
| `SumoAdapter` | `backend/app/simulation/sumo/` | interface stub + install guide; not wired |

## 2. Built-in microsimulation model

- **Geometry:** one 4-way intersection. Four approaches `N, E, S, W`, each with 3 incoming lanes
  (`0` left-turn, `1` through, `2` through+right) over `approach_length_m` (220 m default).
- **Vehicles:** discrete objects with kinematic longitudinal dynamics — a simplified IDM-style
  car-following rule (desired speed, safe gap to leader, comfortable acceleration/braking). Lateral
  behaviour is lane-locked; turning is a curved path through the intersection box.
- **Signals:** the `SignalController` owns the phase state machine. Green phases `NS` / `EW`;
  emergency-only single-approach phases `N` / `E` / `S` / `W`; transition states `YELLOW` / `ALL_RED`.
  Vehicles read their movement's signal (`GREEN` / `YELLOW` / `RED`) and brake for the stop line on
  non-green.
- **Arrivals:** per-approach Poisson process; rate from the scenario demand profile
  (`arrivals_vph × approach_fraction`). Turn movement sampled from `turn_split`.
- **Emergency vehicles:** injected on demand; higher desired speed, shorter reaction gap; surrounding
  vehicles yield (a lane-clear nudge). Detection range configurable.
- **Violations:** a small per-vehicle probability of entering on `RED` (`red_run`) or crossing unsafely
  during a transition (`unsafe_cross`); flagged, logged, and fed to DQN state + reward + safety metrics.
- **Determinism:** a single seeded `numpy.random.Generator` drives every stochastic draw. Same seed +
  same action sequence ⇒ identical trajectory (see [`experiments.md`](experiments.md) for limits).

## 3. `SimulationState` schema

Adapter-independent snapshot consumed by state builders and (compacted) by the UI.

```
SimulationState
  sim_time: float                        seconds since reset
  step: int
  control_mode: "AI" | "FIXED_TIME" | "MANUAL"

  signal: SignalState
    current_phase: "NS"|"EW"|"N"|"E"|"S"|"W"|"YELLOW"|"ALL_RED"
    served_phase:  last non-transition green phase
    phase_elapsed_s: float
    phase_remaining_min_s: float         time until min-green satisfied (0 if satisfied)
    phase_remaining_max_s: float         time until max-green forces a change
    transition: null | { kind: "YELLOW"|"ALL_RED", elapsed_s, total_s, from_phase, to_phase }
    allowed_next: list[phase id]         phases the safety layer would currently accept
    last_action: FinalAction | null

  approaches: { N: ApproachState, E: ..., S: ..., W: ... }
    ApproachState
      vehicle_count: int
      queue_length: int                  vehicles stopped or crawling (< 2 m/s) upstream of stop line
      mean_speed_mps: float
      mean_wait_s: float                 mean accumulated wait of vehicles on the approach
      max_wait_s: float
      density_veh_per_km: float
      arrival_rate_vph: float            short-window empirical estimate
      stops_last_window: int
      lanes: list[LaneState]  (count, queue, blocked: bool)

  emergency: EmergencyState
    active: bool
    vehicle_id: str | null
    type: "ambulance"|"fire_truck"|"police" | null
    approach: "N"|"E"|"S"|"W" | null
    distance_m: float | null              to stop line
    speed_mps: float | null
    eta_s: float | null
    cleared_this_episode: int

  safety: SafetySnapshot
    violations_last_window: int
    violations_total: int
    unsafe_transitions_total: int
    recent: list[ViolationEvent]          id, t, approach, type, signal_state, severity

  environment:
    weather: "clear"|"rain"|"fog"
    time_of_day: "day"|"night"|"peak"
    blocked_lanes: list[{approach, lane}]

  vehicles: list[VehicleSnapshot]         (compacted for UI; full objects stay server-side)
    id, type, approach, lane, movement, x, y, heading, speed_mps, accel_mps2,
    wait_s, stops, fuel_l, co2_kg, is_emergency, is_violator, state
```

## 4. Vehicle model (spec §11)

| Field | Notes |
|---|---|
| `id` | `v{n}` / `e{n}` for emergency |
| `type` | `car, suv, bus, truck, ambulance, fire_truck, police` — properties in `config.yaml` |
| `lane`, `movement` | movement ∈ `left, through, right` |
| `route` | `(entry approach, exit approach)` |
| `x, y, heading` | world coordinates for rendering (interpolated client-side) |
| `speed_mps`, `accel_mps2` | from the car-following update |
| `wait_s` | cumulative time below 0.3 m/s |
| `stops` | count of decel-to-standstill events |
| `fuel_l`, `co2_kg` | running estimates — see [`assumptions.md`](assumptions.md) |
| `is_emergency`, `is_violator` | booleans |

## 5. Signal model (spec §12)

Phase constraints (`config.yaml → signals`): `min_green_s`, `max_green_s`, `yellow_s`, `all_red_s`,
`emergency_max_priority_s`. The controller **never** flips conflicting greens directly — a phase change is
always `served → YELLOW → ALL_RED → new served`. The safety layer (below) is what enforces this; the
controller just executes validated commands.

## 6. SUMO adapter (future)

`docs` and `simulation/networks/intersection.{nod,edg,con,tll}.xml` will describe a matching 4-way
network. The `SumoAdapter` maps `SimulationState` fields to `libsumo` calls
(`lane.getLastStepHaltingNumber`, `lane.getWaitingTime`, `vehicle.*`, `trafficlight.setPhase`). The
`inject()` contract maps to `vehicle.add` / `lane.setDisallowed`. Until then `NEXUS_SIM_ADAPTER=sumo`
raises a clear, logged error and the app stays on `builtin`.
