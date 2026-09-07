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


def emergency_wait_total(state: SimulationState) -> float:
    """Total waiting time currently accrued by emergency vehicles on the network."""
    return sum(v.wait_s for v in state.vehicles if v.is_emergency)


def make_reward_context(prev: SimulationState, curr: SimulationState, *, action_name: str,
                        vehicles_cleared: int, interval_s: float) -> RewardContext:
    """Assemble a :class:`RewardContext` from a (prev -> curr) state transition.

    This is the single source of truth for reward-context construction. Both the live
    :class:`~app.core.simulation_manager.SimulationManager` and the headless
    :class:`~app.training.environment.TrainingEnv` call it, so a policy learns against
    exactly the reward signal it is later evaluated on (spec section 84).

    ``vehicles_cleared`` is the adapter's non-emergency departure count for the interval
    (``adapter.mark_interval()``); everything else is derived from the two states.
    """
    em_prev, em_curr = prev.emergency, curr.emergency
    emergency_cleared = max(0, em_curr.cleared_this_episode - em_prev.cleared_this_episode)

    progress = 0.0
    if em_prev.active and em_curr.active and em_prev.vehicle_id == em_curr.vehicle_id:
        progress = max(0.0, (em_prev.distance_m or 0.0) - (em_curr.distance_m or 0.0))
    elif em_prev.active and emergency_cleared:
        progress = em_prev.distance_m or 0.0

    wait_delta = 0.0
    if em_curr.active:
        wait_delta = max(0.0, emergency_wait_total(curr) - emergency_wait_total(prev))

    violations = max(0, curr.safety.violations_total - prev.safety.violations_total)
    phase_changed = curr.signal.served_phase != prev.signal.served_phase

    return RewardContext(
        prev=prev, curr=curr, action_name=action_name, phase_changed=phase_changed,
        vehicles_cleared=vehicles_cleared, emergency_cleared=emergency_cleared,
        emergency_progress_m=progress, emergency_wait_delta_s=wait_delta,
        violations=violations, interval_s=interval_s,
    )
