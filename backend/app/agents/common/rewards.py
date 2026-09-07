"""Reward context + helpers (spec sections 13, 15, 18, 85)."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.agents import RewardComponent
from app.schemas.simulation import SimulationState


@dataclass
class RewardContext:
    """Everything the reward functions need about one decision interval.

    Built by the SimulationManager from adapter counters so rewards stay pure.
    """

    prev: SimulationState
    curr: SimulationState
    action_name: str
    phase_changed: bool
    vehicles_cleared: int          # non-emergency departures this interval
    emergency_cleared: int         # emergency departures this interval
    emergency_progress_m: float    # distance an active emergency vehicle closed
    emergency_wait_delta_s: float  # extra waiting accrued by active emergency vehicles
    violations: int                # violation events this interval
    interval_s: float

    def mean(self, field: str, *, exclude_emergency: bool = False) -> tuple[float, float]:
        """Return (prev_mean, curr_mean) of an ApproachState field across approaches."""
        def m(state: SimulationState) -> float:
            vals = [getattr(ap, field) for ap in state.approaches.values()]
            return sum(vals) / len(vals) if vals else 0.0

        return m(self.prev), m(self.curr)


def component(name: str, raw: float, weight: float) -> RewardComponent:
    return RewardComponent(name=name, raw=round(raw, 4), weight=weight,
                           contribution=round(raw * weight, 4))
