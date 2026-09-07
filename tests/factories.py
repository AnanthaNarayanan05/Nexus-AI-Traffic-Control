"""Synthetic `SimulationState` builders and adapter helpers for unit tests.

Kept separate from `conftest.py` so test modules can import the helpers directly
(`from tests.factories import make_state`) rather than only through fixtures.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.schemas.enums import Approach, ControlMode, Phase
from app.schemas.simulation import (
    ApproachState,
    EmergencyState,
    EnvironmentState,
    LiveEstimates,
    SafetySnapshot,
    SignalState,
    SimulationState,
    TransitionState,
)

APPROACHES = (Approach.N, Approach.E, Approach.S, Approach.W)


def make_state(
    *,
    sim_time: float = 300.0,
    step: int = 600,
    served: Phase = Phase.NS,
    current: Phase | None = None,
    phase_elapsed_s: float = 20.0,
    min_remaining_s: float = 0.0,
    max_remaining_s: float = 40.0,
    transition: TransitionState | None = None,
    allowed_next: list[Phase] | None = None,
    queues: dict[Approach, int] | None = None,
    counts: dict[Approach, int] | None = None,
    waits: dict[Approach, float] | None = None,
    speeds: dict[Approach, float] | None = None,
    emergency: EmergencyState | None = None,
    co2_rate: float = 0.0,
    violations_total: int = 0,
    violations_last_window: int = 0,
    control_mode: ControlMode = ControlMode.AI,
) -> SimulationState:
    """Build a synthetic SimulationState for pure-unit tests.

    Defaults: a calm intersection on NS green, past min-green, with headroom before
    max-green and no emergency. Override only the fields a test cares about.
    """
    queues = queues or dict.fromkeys(APPROACHES, 2)
    counts = counts or {a: max(queues[a], 4) for a in APPROACHES}
    waits = waits or dict.fromkeys(APPROACHES, 6.0)
    speeds = speeds or dict.fromkeys(APPROACHES, 8.0)

    approaches = {
        a: ApproachState(
            approach=a,
            vehicle_count=counts[a],
            queue_length=queues[a],
            mean_speed_mps=speeds[a],
            mean_wait_s=waits[a],
            max_wait_s=waits[a] * 1.5,
            density_veh_per_km=counts[a] * 4.0,
            arrival_rate_vph=400.0,
            stops_last_window=queues[a],
        )
        for a in APPROACHES
    }

    if allowed_next is None:
        other = Phase.EW if served == Phase.NS else Phase.NS
        allowed_next = [served] if min_remaining_s > 1e-6 else [served, other]

    signal = SignalState(
        current_phase=current or served,
        served_phase=served,
        phase_elapsed_s=phase_elapsed_s,
        phase_remaining_min_s=min_remaining_s,
        phase_remaining_max_s=max_remaining_s,
        transition=transition,
        allowed_next=allowed_next,
    )

    return SimulationState(
        sim_time=sim_time,
        step=step,
        control_mode=control_mode,
        signal=signal,
        approaches=approaches,
        emergency=emergency or EmergencyState(),
        safety=SafetySnapshot(
            violations_total=violations_total, violations_last_window=violations_last_window
        ),
        environment=EnvironmentState(),
        estimates=LiveEstimates(co2_kg_per_s=co2_rate),
    )


def active_emergency(approach: Approach = Approach.E, *, distance_m: float = 80.0,
                     speed_mps: float = 9.0, eta_s: float = 9.0) -> EmergencyState:
    return EmergencyState(
        active=True, vehicle_id="emg-1", approach=approach,
        distance_m=distance_m, speed_mps=speed_mps, eta_s=eta_s,
    )


def advance(eng, seconds: float, dt: float = 0.5):
    """Step an adapter forward `seconds` of sim time and return the fresh state."""
    for _ in range(int(round(seconds / dt))):
        eng.step(dt)
    return eng.get_state()
