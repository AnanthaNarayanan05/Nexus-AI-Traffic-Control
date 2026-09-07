"""SafetyValidator - the authoritative final check (spec sections 22, 113, docs/safety.md).

One test per rule, in the order `RULES` evaluates them, plus the APPLIED pass-through.
Each asserts the `SafetyAction` taken and the phase the `SignalController` is left with.
No RL recommendation may bypass this layer, so a "better" phase that violates a rule
must still be rewritten or blocked.
"""

from __future__ import annotations

from app.core.config import get_config
from app.safety.rules import RuleId
from app.safety.validator import SafetyValidator
from app.schemas.enums import Approach, Phase, SafetyAction
from app.schemas.safety import PhaseCommand
from app.schemas.simulation import TransitionState

from tests.factories import active_emergency, make_state


def cmd(phase: Phase, **kw) -> PhaseCommand:
    return PhaseCommand(target_phase=phase, source="coordinator", **kw)


def validate(command: PhaseCommand, state):
    return SafetyValidator().validate(command, state)


# --------------------------------------------------------- 1. phase_defined
def test_transition_phase_proposal_is_blocked_and_held():
    st = make_state(served=Phase.NS)
    r = validate(cmd(Phase.YELLOW), st)
    assert r.action_taken == SafetyAction.BLOCKED_HOLD
    assert r.command.target_phase == Phase.NS
    assert r.approved is False
    assert RuleId.PHASE_DEFINED.value in r.violated_rules


# --------------------------------------------------------- 2. no_mid_transition_switch
def test_switch_during_a_transition_is_rewritten_to_continue_it():
    tr = TransitionState(
        kind=Phase.YELLOW, elapsed_s=1.0, total_s=3.0,
        from_phase=Phase.NS, to_phase=Phase.EW,
    )
    st = make_state(served=Phase.NS, transition=tr)
    r = validate(cmd(Phase.NS), st)  # asking to go back to NS mid-yellow
    assert r.action_taken == SafetyAction.REWRITTEN_TRANSITION
    assert r.command.target_phase == Phase.EW
    assert r.command.force_transition is True


def test_continuing_the_transition_is_applied_cleanly():
    tr = TransitionState(
        kind=Phase.ALL_RED, elapsed_s=1.0, total_s=2.0,
        from_phase=Phase.NS, to_phase=Phase.EW,
    )
    st = make_state(served=Phase.NS, transition=tr)
    r = validate(cmd(Phase.EW), st)
    assert r.action_taken == SafetyAction.APPLIED
    assert r.approved is True
    assert r.command.target_phase == Phase.EW


# --------------------------------------------------------- 3. emergency_timeout
def test_emergency_phase_past_the_cap_is_force_ended():
    cap = float(get_config().signals.emergency_max_priority_s)
    st = make_state(
        served=Phase.N, current=Phase.N, phase_elapsed_s=cap + 1.0,
        counts={Approach.N: 2, Approach.S: 2, Approach.E: 9, Approach.W: 9},
    )
    r = validate(cmd(Phase.N), st)  # A2C wants to keep holding for the emergency
    assert r.action_taken == SafetyAction.EMERGENCY_TIMEOUT
    assert r.command.target_phase == Phase.EW  # highest ring demand
    assert r.command.force_transition is True
    assert r.approved is False


def test_emergency_phase_within_the_cap_is_not_touched_by_the_timeout_rule():
    cap = float(get_config().signals.emergency_max_priority_s)
    st = make_state(
        served=Phase.N, current=Phase.N, phase_elapsed_s=cap - 5.0,
        emergency=active_emergency(Approach.N, distance_m=30.0),
    )
    r = validate(cmd(Phase.N), st)
    assert r.action_taken != SafetyAction.EMERGENCY_TIMEOUT


# --------------------------------------------------------- 4. post_emergency_recovery
def test_recovery_forces_the_demand_phase_once_the_emergency_clears():
    st = make_state(
        served=Phase.E, current=Phase.E, phase_elapsed_s=20.0, min_remaining_s=0.0,
        emergency=None,  # emergency already gone
        counts={Approach.N: 12, Approach.S: 12, Approach.E: 1, Approach.W: 1},
    )
    r = validate(cmd(Phase.E), st)  # coordinator still asking to hold the single-approach phase
    assert r.action_taken == SafetyAction.FORCED_CHANGE
    assert r.command.target_phase == Phase.NS
    assert RuleId.POST_EMERGENCY_RECOVERY.value in r.violated_rules


def test_recovery_waits_for_min_green_on_the_emergency_phase():
    st = make_state(
        served=Phase.S, current=Phase.S, phase_elapsed_s=3.0, min_remaining_s=5.0,
        emergency=None,
    )
    r = validate(cmd(Phase.NS), st)
    assert r.action_taken == SafetyAction.BLOCKED_HOLD
    assert r.command.target_phase == Phase.S


# --------------------------------------------------------- 5. max_green
def test_max_green_forces_a_change_despite_a_hold_request():
    st = make_state(served=Phase.NS, phase_elapsed_s=60.0, max_remaining_s=0.0)
    r = validate(cmd(Phase.NS), st)
    assert r.action_taken == SafetyAction.FORCED_CHANGE
    assert r.command.target_phase == Phase.EW
    assert RuleId.MAX_GREEN.value in r.violated_rules


def test_max_green_does_not_fire_when_a_change_is_already_proposed():
    st = make_state(served=Phase.NS, phase_elapsed_s=60.0, max_remaining_s=0.0)
    r = validate(cmd(Phase.EW, force_transition=True), st)
    assert r.action_taken == SafetyAction.APPLIED
    assert r.command.target_phase == Phase.EW


# --------------------------------------------------------- 6. min_green
def test_min_green_blocks_an_early_switch():
    st = make_state(served=Phase.NS, phase_elapsed_s=3.0, min_remaining_s=5.0)
    r = validate(cmd(Phase.EW, force_transition=True), st)
    assert r.action_taken == SafetyAction.BLOCKED_HOLD
    assert r.command.target_phase == Phase.NS
    assert RuleId.MIN_GREEN.value in r.violated_rules


# --------------------------------------------------------- 7. emergency_phase_without_emergency
def test_single_approach_phase_without_an_emergency_is_blocked():
    st = make_state(served=Phase.NS)  # no emergency
    r = validate(cmd(Phase.W, force_transition=True), st)
    assert r.action_taken == SafetyAction.BLOCKED_HOLD
    assert r.command.target_phase == Phase.NS
    assert RuleId.EMERGENCY_PHASE_WITHOUT_EMERGENCY.value in r.violated_rules


def test_single_approach_phase_with_a_matching_emergency_is_allowed():
    st = make_state(served=Phase.NS, emergency=active_emergency(Approach.W))
    r = validate(cmd(Phase.W, force_transition=True), st)
    assert r.action_taken == SafetyAction.APPLIED
    assert r.command.target_phase == Phase.W


# --------------------------------------------------------- 8. conflicting_phase
def test_direct_green_to_green_flip_without_clearance_is_blocked():
    st = make_state(served=Phase.NS)
    r = validate(cmd(Phase.EW, force_transition=False), st)
    assert r.action_taken == SafetyAction.BLOCKED_HOLD
    assert RuleId.CONFLICTING_PHASE.value in r.violated_rules


# --------------------------------------------------------- APPLIED pass-through
def test_clean_change_request_is_applied_and_marked_as_a_transition():
    st = make_state(served=Phase.NS, emergency=active_emergency(Approach.N))
    r = validate(cmd(Phase.N), st)  # NS -> N, compatible axis, emergency present
    assert r.action_taken == SafetyAction.APPLIED
    assert r.approved is True
    assert r.command.target_phase == Phase.N
    # a served -> different-phase change must carry force_transition so the
    # controller inserts YELLOW/ALL_RED
    assert r.command.force_transition is True
    assert r.original == Phase.N


def test_hold_request_is_applied_without_forcing_a_transition():
    st = make_state(served=Phase.NS)
    r = validate(cmd(Phase.NS), st)
    assert r.action_taken == SafetyAction.APPLIED
    assert r.command.force_transition is False


# --------------------------------------------------------- validator bookkeeping
def test_validator_records_overrides_but_not_clean_applications():
    v = SafetyValidator()
    v.validate(cmd(Phase.NS), make_state(served=Phase.NS))  # APPLIED
    assert v.overrides_total == 0
    assert v.recent_overrides() == []

    v.validate(cmd(Phase.YELLOW), make_state(served=Phase.NS))  # BLOCKED_HOLD
    assert v.overrides_total == 1
    assert v.checks_total == 2
    hist = v.recent_overrides()
    assert len(hist) == 1
    assert hist[0]["action_taken"] == SafetyAction.BLOCKED_HOLD.value


def test_rules_are_evaluated_in_documented_order():
    # a transition-state target during an active transition: rule 1 (phase_defined)
    # fires before rule 2 (no_mid_transition_switch)
    tr = TransitionState(
        kind=Phase.YELLOW, elapsed_s=1.0, total_s=3.0,
        from_phase=Phase.NS, to_phase=Phase.EW,
    )
    st = make_state(served=Phase.NS, transition=tr)
    r = validate(cmd(Phase.ALL_RED), st)
    assert r.violated_rules == [RuleId.PHASE_DEFINED.value]
