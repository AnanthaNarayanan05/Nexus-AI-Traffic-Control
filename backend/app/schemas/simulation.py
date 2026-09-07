"""Adapter-independent simulation state snapshot (spec section 10, docs/simulation.md)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.enums import Approach, ControlMode, Phase, SignalColor, VehicleType


class LaneState(BaseModel):
    index: int
    vehicle_count: int = 0
    queue_length: int = 0
    blocked: bool = False


class ApproachState(BaseModel):
    approach: Approach
    vehicle_count: int = 0
    queue_length: int = 0
    mean_speed_mps: float = 0.0
    mean_wait_s: float = 0.0
    max_wait_s: float = 0.0
    density_veh_per_km: float = 0.0
    arrival_rate_vph: float = 0.0
    stops_last_window: int = 0
    lanes: list[LaneState] = Field(default_factory=list)


class TransitionState(BaseModel):
    kind: Phase  # YELLOW | ALL_RED
    elapsed_s: float
    total_s: float
    from_phase: Phase
    to_phase: Phase


class SignalState(BaseModel):
    current_phase: Phase
    served_phase: Phase  # last non-transition green
    phase_elapsed_s: float = 0.0
    phase_remaining_min_s: float = 0.0  # time until min-green satisfied (0 => satisfied)
    phase_remaining_max_s: float = 0.0  # time until max-green forces a change
    transition: TransitionState | None = None
    allowed_next: list[Phase] = Field(default_factory=list)
    last_action: str | None = None
    # Authoritative per-approach aspect, computed by the SignalController. The renderer
    # displays this rather than re-deriving colours from the phase (spec section 114).
    approach_colors: dict[Approach, SignalColor] = Field(default_factory=dict)

    @property
    def min_green_satisfied(self) -> bool:
        return self.phase_remaining_min_s <= 1e-6


class EmergencyState(BaseModel):
    active: bool = False
    vehicle_id: str | None = None
    type: VehicleType | None = None
    approach: Approach | None = None
    distance_m: float | None = None
    speed_mps: float | None = None
    eta_s: float | None = None
    cleared_this_episode: int = 0


class ViolationEvent(BaseModel):
    id: str
    t: float
    approach: Approach
    type: str
    signal_state: str
    severity: str


class SafetySnapshot(BaseModel):
    violations_last_window: int = 0
    violations_total: int = 0
    unsafe_transitions_total: int = 0
    recent: list[ViolationEvent] = Field(default_factory=list)


class EnvironmentState(BaseModel):
    weather: str = "clear"
    time_of_day: str = "day"
    blocked_lanes: list[dict] = Field(default_factory=list)


class LiveEstimates(BaseModel):
    """Derived quantities the agents' state builders read (keeps builders pure).

    Environmental values are ESTIMATED (docs/assumptions.md A12-A13)."""

    throughput_vph: float = 0.0            # rolling 60 s window
    departures_last_interval: int = 0      # non-emergency, since last decision
    fuel_l_per_s: float = 0.0
    co2_kg_per_s: float = 0.0
    fuel_l_total: float = 0.0
    co2_kg_total: float = 0.0


class VehicleSnapshot(BaseModel):
    id: str
    type: VehicleType
    approach: Approach
    lane: int
    movement: str
    x: float
    y: float
    heading: float
    speed_mps: float
    accel_mps2: float
    wait_s: float
    stops: int
    fuel_l: float
    co2_kg: float
    is_emergency: bool = False
    is_violator: bool = False
    state: str = "driving"  # driving | queued | crossing | departed


class SimulationState(BaseModel):
    sim_time: float
    step: int
    control_mode: ControlMode
    signal: SignalState
    approaches: dict[Approach, ApproachState]
    emergency: EmergencyState
    safety: SafetySnapshot
    environment: EnvironmentState
    estimates: LiveEstimates = Field(default_factory=LiveEstimates)
    vehicles: list[VehicleSnapshot] = Field(default_factory=list)

    # convenience -----------------------------------------------------------------
    def approach(self, a: Approach) -> ApproachState:
        return self.approaches[a]

    @property
    def total_vehicles(self) -> int:
        return sum(ap.vehicle_count for ap in self.approaches.values())

    @property
    def total_queue(self) -> int:
        return sum(ap.queue_length for ap in self.approaches.values())
