"""Individual safety rules (spec section 22, docs/safety.md section 2).

Each rule is a pure predicate over (proposed command, current state, timing config).
`SafetyValidator` runs them in the documented order; the first rule that fires
determines the `SafetyResult`. Rules never mutate anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.agents.common.resolve import demand_ring_phase, other_ring
from app.schemas.enums import RING_PHASES, Phase, SafetyAction
from app.schemas.safety import PhaseCommand, SafetyResult
from app.schemas.simulation import SimulationState


class RuleId(str, Enum):
    PHASE_DEFINED = "phase_defined"
    NO_MID_TRANSITION_SWITCH = "no_mid_transition_switch"
    EMERGENCY_TIMEOUT = "emergency_timeout"
    POST_EMERGENCY_RECOVERY = "post_emergency_recovery"
    MAX_GREEN = "max_green"
    MIN_GREEN = "min_green"
    CONFLICTING_PHASE = "conflicting_phase"
    EMERGENCY_PHASE_WITHOUT_EMERGENCY = "emergency_phase_without_emergency"


@dataclass(frozen=True)
class TimingCfg:
    min_green_s: float
    max_green_s: float
    yellow_s: float
    all_red_s: float
    emergency_max_priority_s: float

    @classmethod
    def from_config(cls) -> "TimingCfg":
        from app.core.config import get_config

        s = get_config().signals
        return cls(
            min_green_s=float(s.min_green_s), max_green_s=float(s.max_green_s),
            yellow_s=float(s.yellow_s), all_red_s=float(s.all_red_s),
            emergency_max_priority_s=float(s.emergency_max_priority_s),
        )


def _hold(state: SimulationState, action: SafetyAction, rule: RuleId | None,
          reason: str) -> SafetyResult:
    served = state.signal.served_phase
    return SafetyResult(
        approved=(action == SafetyAction.APPLIED),
        command=PhaseCommand(target_phase=served, source="safety"),
        original=served, action_taken=action,
        violated_rules=[rule.value] if rule else [], reason=reason,
    )


def _force(state: SimulationState, target: Phase, action: SafetyAction,
           rule: RuleId, reason: str) -> SafetyResult:
    return SafetyResult(
        approved=False,
        command=PhaseCommand(target_phase=target, force_transition=True, source="safety"),
        original=state.signal.served_phase, action_taken=action,
        violated_rules=[rule.value], reason=reason,
    )


# --------------------------------------------------------------------------- rules
def rule_phase_defined(cmd: PhaseCommand, state: SimulationState, t: TimingCfg) -> SafetyResult | None:
    if cmd.target_phase.is_transition:
        return _hold(state, SafetyAction.BLOCKED_HOLD, RuleId.PHASE_DEFINED,
                     f"Proposed phase {cmd.target_phase.value} is a transition state, not a green phase.")
    return None


def rule_no_mid_transition_switch(cmd: PhaseCommand, state: SimulationState,
                                  t: TimingCfg) -> SafetyResult | None:
    tr = state.signal.transition
    if tr is None:
        return None
    # Only "continue the transition" is admissible.
    result = SafetyResult(
        approved=(cmd.target_phase == tr.to_phase),
        command=PhaseCommand(target_phase=tr.to_phase, force_transition=True, source="safety"),
        original=cmd.target_phase,
        action_taken=(SafetyAction.APPLIED if cmd.target_phase == tr.to_phase
                      else SafetyAction.REWRITTEN_TRANSITION),
        violated_rules=([] if cmd.target_phase == tr.to_phase else [RuleId.NO_MID_TRANSITION_SWITCH.value]),
        reason=(f"Mid-transition ({tr.kind.value} -> {tr.to_phase.value}); "
                f"{'continuing' if cmd.target_phase == tr.to_phase else 'ignoring switch request, continuing'} "
                f"to {tr.to_phase.value}."),
    )
    return result


def rule_emergency_timeout(cmd: PhaseCommand, state: SimulationState,
                           t: TimingCfg) -> SafetyResult | None:
    served = state.signal.served_phase
    if not served.is_emergency_phase:
        return None
    if state.signal.phase_elapsed_s < t.emergency_max_priority_s:
        return None
    target = demand_ring_phase(state)
    return _force(state, target, SafetyAction.EMERGENCY_TIMEOUT, RuleId.EMERGENCY_TIMEOUT,
                  f"Emergency phase {served.value} held {state.signal.phase_elapsed_s:.1f}s "
                  f">= {t.emergency_max_priority_s:.0f}s cap; forcing {target.value}.")


def rule_post_emergency_recovery(cmd: PhaseCommand, state: SimulationState,
                                 t: TimingCfg) -> SafetyResult | None:
    served = state.signal.served_phase
    if not served.is_emergency_phase or state.emergency.active:
        return None
    if not state.signal.min_green_satisfied:
        return _hold(state, SafetyAction.BLOCKED_HOLD, RuleId.MIN_GREEN,
                     f"Emergency cleared; min-green on {served.value} not yet reached "
                     f"({state.signal.phase_remaining_min_s:.1f}s left).")
    target = demand_ring_phase(state)
    if cmd.target_phase == target:
        return None  # coordinator already wants the recovery phase - let it through normally
    return _force(state, target, SafetyAction.FORCED_CHANGE, RuleId.POST_EMERGENCY_RECOVERY,
                  f"Emergency cleared; recovering from {served.value} to demand phase {target.value}.")


def rule_max_green(cmd: PhaseCommand, state: SimulationState, t: TimingCfg) -> SafetyResult | None:
    served = state.signal.served_phase
    if served.is_emergency_phase:
        return None  # emergency phases are bounded by rule_emergency_timeout instead
    if state.signal.phase_remaining_max_s > 1e-6:
        return None
    if cmd.target_phase != served:
        return None  # a change is already proposed; max-green does not need to force one
    target = other_ring(served)
    return _force(state, target, SafetyAction.FORCED_CHANGE, RuleId.MAX_GREEN,
                  f"Max-green reached on {served.value} "
                  f"({state.signal.phase_elapsed_s:.1f}s); forcing change to {target.value} "
                  f"despite hold request.")


def rule_min_green(cmd: PhaseCommand, state: SimulationState, t: TimingCfg) -> SafetyResult | None:
    served = state.signal.served_phase
    if cmd.target_phase == served:
        return None
    if state.signal.min_green_satisfied:
        return None
    return _hold(state, SafetyAction.BLOCKED_HOLD, RuleId.MIN_GREEN,
                 f"Minimum green not reached ({state.signal.phase_elapsed_s:.1f}s "
                 f"< {t.min_green_s:.0f}s); blocked switch to {cmd.target_phase.value}, held {served.value}.")


def rule_emergency_phase_without_emergency(cmd: PhaseCommand, state: SimulationState,
                                           t: TimingCfg) -> SafetyResult | None:
    if not cmd.target_phase.is_emergency_phase:
        return None
    served = state.signal.served_phase
    if cmd.target_phase == served:
        return None
    if state.emergency.active:
        return None
    return _hold(state, SafetyAction.BLOCKED_HOLD, RuleId.EMERGENCY_PHASE_WITHOUT_EMERGENCY,
                 f"Single-approach phase {cmd.target_phase.value} requested with no active "
                 f"emergency; held {served.value}.")


def rule_conflicting_phase(cmd: PhaseCommand, state: SimulationState,
                           t: TimingCfg) -> SafetyResult | None:
    """A served -> served change between antagonistic phases is legal *via* the
    YELLOW/ALL_RED sequence the controller inserts. A direct green-to-green flip
    (force_transition unset while phases differ and are antagonistic) is rejected."""
    served = state.signal.served_phase
    cand = cmd.target_phase
    if cand == served:
        return None
    antagonistic = _antagonistic(served, cand)
    if antagonistic and not cmd.force_transition:
        return _hold(state, SafetyAction.BLOCKED_HOLD, RuleId.CONFLICTING_PHASE,
                     f"Direct flip {served.value} -> {cand.value} without clearance is unsafe; "
                     f"held {served.value}.")
    return None


def _antagonistic(a: Phase, b: Phase) -> bool:
    """True if the two green phases share no compatible movement and need clearance."""
    if a == b:
        return False
    if a in RING_PHASES and b in RING_PHASES:
        return True  # NS vs EW always cross
    # ring vs single-approach, or two single-approach phases
    from app.schemas.enums import Approach

    a_appr = {ap for ap in Approach if a.serves(ap)}
    b_appr = {ap for ap in Approach if b.serves(ap)}
    # opposing approaches on the same axis are compatible (through movements don't cross)
    if a_appr and b_appr and all(x.axis == y.axis for x in a_appr for y in b_appr):
        return False
    return True


# ordered exactly as docs/safety.md section 2 evaluates them
RULES = (
    rule_phase_defined,
    rule_no_mid_transition_switch,
    rule_emergency_timeout,
    rule_post_emergency_recovery,
    rule_max_green,
    rule_min_green,
    rule_emergency_phase_without_emergency,
    rule_conflicting_phase,
)
