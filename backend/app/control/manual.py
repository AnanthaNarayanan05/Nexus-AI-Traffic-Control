"""Manual control mode (spec section 61).

The operator issues a discrete action; it is translated to a `PhaseCommand` and then
validated by the safety layer exactly like an AI or fixed-time command. A manual action
that violates a timing constraint is rejected with the same reason string the AI would
get - the UI shows it rather than silently swallowing it.
"""

from __future__ import annotations

from app.agents.common.resolve import extend_step_s, other_ring
from app.schemas.enums import Phase
from app.schemas.safety import PhaseCommand
from app.schemas.simulation import SimulationState

MANUAL_ACTIONS = ("HOLD", "SWITCH", "EXTEND", "REDUCE", "SET_NS", "SET_EW",
                  "SET_N", "SET_E", "SET_S", "SET_W")


def manual_command(action: str, state: SimulationState) -> PhaseCommand:
    a = action.strip().upper()
    served = state.signal.served_phase
    if a not in MANUAL_ACTIONS:
        raise ValueError(f"unknown manual action '{action}' (known: {', '.join(MANUAL_ACTIONS)})")
    if a == "HOLD":
        return PhaseCommand(target_phase=served, source="manual")
    if a == "SWITCH":
        return PhaseCommand(target_phase=other_ring(served), force_transition=True, source="manual")
    if a == "EXTEND":
        return PhaseCommand(target_phase=served, request_extend_s=extend_step_s(), source="manual")
    if a == "REDUCE":
        return PhaseCommand(target_phase=served, request_reduce=True, source="manual")
    target = Phase(a.removeprefix("SET_"))
    if target == served:
        return PhaseCommand(target_phase=served, source="manual")
    return PhaseCommand(target_phase=target, force_transition=True, source="manual")
