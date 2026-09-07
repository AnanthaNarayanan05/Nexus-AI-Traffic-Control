"""Action -> concrete phase / command resolution shared by agents + manager."""

from __future__ import annotations

from app.core.config import get_config
from app.schemas.enums import EMERGENCY_PHASES, RING_PHASES, Approach, Phase
from app.schemas.safety import PhaseCommand
from app.schemas.simulation import SimulationState


def demand_ring_phase(state: SimulationState) -> Phase:
    ns = state.approach(Approach.N).vehicle_count + state.approach(Approach.S).vehicle_count
    ew = state.approach(Approach.E).vehicle_count + state.approach(Approach.W).vehicle_count
    return Phase.NS if ns >= ew else Phase.EW


def other_ring(served: Phase) -> Phase:
    if served in RING_PHASES:
        return Phase.EW if served == Phase.NS else Phase.NS
    # currently on an emergency single-approach phase -> restore by demand
    return Phase.NS


def emergency_phase(state: SimulationState) -> Phase | None:
    if state.emergency.active and state.emergency.approach is not None:
        return EMERGENCY_PHASES[state.emergency.approach]
    return None


def extend_step_s() -> float:
    # a green "extension" quantum: half the min-green, bounded (docs/a2c.md action 1)
    return max(4.0, float(get_config().signals.min_green_s) * 0.75)


def action_to_command(action_name: str, target_phase: Phase, served_phase: Phase,
                      source: str = "coordinator") -> PhaseCommand:
    """Translate a winning action into a concrete PhaseCommand for the safety layer."""
    name = action_name.upper()
    if target_phase != served_phase:
        return PhaseCommand(target_phase=target_phase, force_transition=True, source=source)
    if "EXTEND" in name:
        return PhaseCommand(target_phase=served_phase, request_extend_s=extend_step_s(), source=source)
    if "REDUCE" in name:
        return PhaseCommand(target_phase=served_phase, request_reduce=True, source=source)
    if "TRANSITION" in name:
        return PhaseCommand(target_phase=other_ring(served_phase), force_transition=True, source=source)
    return PhaseCommand(target_phase=served_phase, source=source)
