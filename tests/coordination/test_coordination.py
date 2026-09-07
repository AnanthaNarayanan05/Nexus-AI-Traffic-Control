"""Deterministic priority-ladder coordinator (spec sections 20-21, docs/coordination.md).

These lock the *ladder*: the order rungs fire in, the emergency-override threshold,
the valid-phase filter, consensus detection, and that `resolve()` is a pure function.
They do not assert tuned score magnitudes beyond what the documented weights imply.
"""

from __future__ import annotations

import pytest

from app.coordination.engine import Coordinator
from app.core.config import get_config
from app.schemas.agents import AgentRecommendation
from app.schemas.enums import AgentName, Approach, Phase
from app.schemas.simulation import TransitionState

from tests.factories import active_emergency, make_state

APPROACHES = (Approach.N, Approach.E, Approach.S, Approach.W)


def rec(
    agent: str,
    phase: Phase,
    *,
    score: float = 0.5,
    priority: float = 0.2,
    confidence: float = 0.7,
    action_name: str = "KEEP_PHASE",
    action_index: int = 0,
) -> AgentRecommendation:
    return AgentRecommendation(
        agent=AgentName(agent),
        action_index=action_index,
        action_name=action_name,
        target_phase=phase,
        score=score,
        confidence=confidence,
        priority=priority,
        reason="test",
    )


def all_agree(phase: Phase, **kw) -> list[AgentRecommendation]:
    return [rec("a2c", phase, **kw), rec("dqn", phase, **kw), rec("ppo", phase, **kw)]


# --------------------------------------------------------------- rung 1: timing
def test_transition_lock_short_circuits_to_the_transition_target():
    st = make_state(
        transition=TransitionState(
            kind=Phase.YELLOW, elapsed_s=1.0, total_s=3.0,
            from_phase=Phase.NS, to_phase=Phase.EW,
        )
    )
    d = Coordinator().resolve(
        [rec("a2c", Phase.NS), rec("dqn", Phase.EW), rec("ppo", Phase.EW)], st
    )
    assert d.basis == "transition_lock"
    assert d.winner == "constraint"
    assert d.candidate_phase == Phase.EW
    assert d.ladder_trace[0].outcome == "short_circuit"


def test_min_green_hold_short_circuits_and_keeps_served_phase():
    st = make_state(min_remaining_s=5.0, phase_elapsed_s=3.0)  # 3s into an 8s min-green
    d = Coordinator().resolve(all_agree(Phase.EW, score=0.9), st)
    assert d.basis == "min_green_hold"
    assert d.winner == "constraint"
    assert d.candidate_phase == st.signal.served_phase == Phase.NS
    # no scoring happens on a short-circuit
    assert d.scores == []


# --------------------------------------------------------------- rung 2: emergency
def test_emergency_override_when_a2c_priority_at_or_above_threshold():
    thr = float(get_config().coordination.emergency_override_threshold)
    st = make_state(emergency=active_emergency(Approach.N))
    recs = [
        rec("a2c", Phase.N, priority=thr),  # exactly the threshold wins
        rec("dqn", Phase.NS, score=0.9),
        rec("ppo", Phase.EW, score=0.9),
    ]
    d = Coordinator().resolve(recs, st)
    assert d.basis == "emergency_override"
    assert d.winner == "a2c"
    assert d.candidate_phase == Phase.N


def test_emergency_override_declined_when_a2c_priority_below_threshold():
    thr = float(get_config().coordination.emergency_override_threshold)
    st = make_state(emergency=active_emergency(Approach.N))
    recs = [
        rec("a2c", Phase.N, priority=thr - 0.01),
        rec("dqn", Phase.NS, score=0.8),
        rec("ppo", Phase.NS, score=0.8),
    ]
    d = Coordinator().resolve(recs, st)
    assert d.basis == "weighted_score"
    # A2C's single-approach phase is not in allowed_next -> it is filtered out
    assert d.candidate_phase == Phase.NS


def test_emergency_override_needs_an_active_emergency():
    thr = float(get_config().coordination.emergency_override_threshold)
    st = make_state()  # no emergency
    d = Coordinator().resolve(
        [rec("a2c", Phase.NS, priority=thr + 0.3), rec("dqn", Phase.NS), rec("ppo", Phase.NS)],
        st,
    )
    assert d.basis == "weighted_score"


# --------------------------------------------------------------- rung 3: valid phase
def test_valid_phase_filter_drops_targets_not_in_allowed_next():
    st = make_state(allowed_next=[Phase.NS])  # EW not yet a legal successor
    d = Coordinator().resolve(all_agree(Phase.EW, score=0.9), st)
    assert d.candidate_phase == Phase.NS
    step = next(s for s in d.ladder_trace if s.rung == "valid_phase")
    assert "EW" in step.detail and "dropped" in step.detail


def test_served_phase_is_always_a_candidate():
    st = make_state()
    d = Coordinator().resolve(all_agree(Phase.NS), st)
    assert d.candidate_phase == Phase.NS


# --------------------------------------------------------------- rungs 4-7: scoring
def test_consensus_wins_when_two_or_more_agents_agree():
    st = make_state()
    recs = [
        rec("a2c", Phase.NS),
        rec("dqn", Phase.EW, score=0.6),
        rec("ppo", Phase.EW, score=0.6),
    ]
    d = Coordinator().resolve(recs, st)
    assert d.candidate_phase == Phase.EW
    assert d.winner == "consensus"
    assert d.basis == "weighted_score"


def test_single_agent_is_named_as_the_winner():
    st = make_state()
    recs = [
        rec("a2c", Phase.NS),
        rec("dqn", Phase.NS),
        rec("ppo", Phase.EW, score=1.0),  # strong lone congestion signal
    ]
    d = Coordinator().resolve(recs, st)
    assert d.candidate_phase == Phase.EW
    assert d.winner == "ppo"


def test_consensus_bonus_scales_with_agreeing_agents():
    cfg = get_config().coordination
    st = make_state()
    scored = Coordinator()._score_phase(
        Phase.EW,
        [rec("a2c", Phase.EW), rec("dqn", Phase.EW), rec("ppo", Phase.EW)],
        st,
        served=Phase.NS,
    )
    assert scored.consensus_bonus == pytest.approx(2 * float(cfg.consensus_bonus))


def test_stability_penalty_applies_only_when_leaving_the_served_phase():
    cfg = get_config().coordination
    st = make_state()
    stay = Coordinator()._score_phase(Phase.NS, [rec("a2c", Phase.NS)], st, served=Phase.NS)
    leave = Coordinator()._score_phase(Phase.EW, [rec("a2c", Phase.EW)], st, served=Phase.NS)
    assert stay.stability == 0.0
    assert leave.stability == pytest.approx(-float(cfg.stability_penalty))


def test_busiest_phase_tracks_vehicle_counts():
    ns_heavy = make_state(
        counts={Approach.N: 20, Approach.S: 20, Approach.E: 1, Approach.W: 1},
        queues=dict.fromkeys(APPROACHES, 1),
    )
    ew_heavy = make_state(
        counts={Approach.N: 1, Approach.S: 1, Approach.E: 20, Approach.W: 20},
        queues=dict.fromkeys(APPROACHES, 1),
    )
    assert Coordinator._busiest_phase(ns_heavy) == Phase.NS
    assert Coordinator._busiest_phase(ew_heavy) == Phase.EW


# --------------------------------------------------------------- purity
def test_resolve_is_a_pure_function():
    st = make_state()
    recs = [
        rec("a2c", Phase.EW, score=0.6),
        rec("dqn", Phase.EW, score=0.6),
        rec("ppo", Phase.NS),
    ]
    a = Coordinator().resolve(recs, st)
    b = Coordinator().resolve(recs, st)
    assert a.model_dump() == b.model_dump()


def test_resolve_never_returns_a_transition_phase_as_the_candidate():
    for target in (Phase.NS, Phase.EW):
        st = make_state(served=target)
        d = Coordinator().resolve(all_agree(target), st)
        assert not d.candidate_phase.is_transition
