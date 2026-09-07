"""Per-agent reward functions (docs/a2c.md/dqn.md/ppo.md section 3).

These lock the *form* of each reward: which components exist, their signs, and that
`contribution == raw * weight` with `total == sum(contributions)`. They do not assert
absolute magnitudes - those are tuning choices (docs/assumptions.md A10).
"""

from __future__ import annotations

import pytest

from app.agents.a2c.reward import a2c_reward
from app.agents.common.rewards import RewardContext
from app.agents.dqn.reward import dqn_reward
from app.agents.ppo.reward import ppo_reward
from app.core.config import get_config
from app.schemas.enums import Approach, Phase

from tests.factories import make_state


def ctx(**kw) -> RewardContext:
    base = dict(
        prev=make_state(),
        curr=make_state(),
        action_name="KEEP_PHASE",
        phase_changed=False,
        vehicles_cleared=6,
        emergency_cleared=0,
        emergency_progress_m=0.0,
        emergency_wait_delta_s=0.0,
        violations=0,
        interval_s=6.0,
    )
    base.update(kw)
    return RewardContext(**base)


def _assert_well_formed(breakdown):
    assert breakdown.components, "reward produced no components"
    for c in breakdown.components:
        assert c.contribution == pytest.approx(c.raw * c.weight, abs=1e-3)
    assert breakdown.total == pytest.approx(
        sum(c.contribution for c in breakdown.components), abs=1e-3
    )


# --------------------------------------------------------------------- A2C
def test_a2c_has_four_core_components():
    names = [c.name for c in a2c_reward(ctx()).components]
    assert names[:4] == ["emergency_wait", "normal_queue", "emergency_passage", "throughput"]


def test_a2c_well_formed():
    _assert_well_formed(a2c_reward(ctx()))


def test_a2c_emergency_wait_is_a_penalty():
    hi = a2c_reward(ctx(emergency_wait_delta_s=6.0))
    comp = next(c for c in hi.components if c.name == "emergency_wait")
    assert comp.contribution < 0


def test_a2c_emergency_passage_rewards_clearing():
    cleared = a2c_reward(ctx(emergency_cleared=1))
    none = a2c_reward(ctx(emergency_cleared=0))
    cp = next(c for c in cleared.components if c.name == "emergency_passage")
    npc = next(c for c in none.components if c.name == "emergency_passage")
    assert cp.contribution > npc.contribution >= 0


def test_a2c_switch_penalty_only_when_phase_changes_without_emergency():
    assert any(c.name == "switch_penalty" for c in a2c_reward(ctx(phase_changed=True)).components)
    assert not any(c.name == "switch_penalty" for c in a2c_reward(ctx(phase_changed=False)).components)
    em = make_state(emergency=_active_emergency())
    got = a2c_reward(ctx(phase_changed=True, curr=em))
    assert not any(c.name == "switch_penalty" for c in got.components)


def _active_emergency():
    from app.schemas.simulation import EmergencyState

    return EmergencyState(active=True, approach=Approach.E, distance_m=80.0, speed_mps=9.0, eta_s=9.0)


# --------------------------------------------------------------------- DQN
def test_dqn_has_seven_components_plus_optional_switch():
    names = [c.name for c in dqn_reward(ctx()).components]
    assert names[:7] == [
        "smooth_flow",
        "waiting_drop",
        "stop_penalty",
        "idle_penalty",
        "emission_penalty",
        "queue_penalty",
        "violation_penalty",
    ]


def test_dqn_well_formed():
    _assert_well_formed(dqn_reward(ctx()))


def test_dqn_violation_penalty_scales_with_count():
    one = next(c for c in dqn_reward(ctx(violations=1)).components if c.name == "violation_penalty")
    three = next(c for c in dqn_reward(ctx(violations=3)).components if c.name == "violation_penalty")
    assert three.contribution < one.contribution < 0
    assert three.contribution == pytest.approx(3 * one.contribution, abs=1e-3)


def test_dqn_emission_penalty_negative_when_co2_present():
    hi = dqn_reward(ctx(curr=make_state(co2_rate=0.06)))
    comp = next(c for c in hi.components if c.name == "emission_penalty")
    assert comp.contribution < 0


def test_dqn_switch_penalty_on_switch_actions():
    assert any(c.name == "switch_penalty" for c in dqn_reward(ctx(action_name="SWITCH_PHASE")).components)
    assert any(c.name == "switch_penalty" for c in dqn_reward(ctx(action_name="TRANSITION")).components)
    assert not any(c.name == "switch_penalty" for c in dqn_reward(ctx(action_name="KEEP_GREEN")).components)


def test_dqn_smoother_flow_scores_higher():
    fast = dqn_reward(ctx(curr=make_state(speeds=dict.fromkeys(Approach, 12.0))))
    slow = dqn_reward(ctx(curr=make_state(speeds=dict.fromkeys(Approach, 2.0))))
    f = next(c for c in fast.components if c.name == "smooth_flow")
    s = next(c for c in slow.components if c.name == "smooth_flow")
    assert f.contribution > s.contribution


# --------------------------------------------------------------------- PPO
def test_ppo_has_three_core_components():
    names = [c.name for c in ppo_reward(ctx()).components]
    assert names[:3] == ["queue", "waiting", "throughput"]


def test_ppo_well_formed():
    _assert_well_formed(ppo_reward(ctx()))


def test_ppo_queue_and_waiting_are_penalties():
    big = ppo_reward(ctx(curr=make_state(queues=dict.fromkeys(Approach, 20), waits=dict.fromkeys(Approach, 90.0))))
    q = next(c for c in big.components if c.name == "queue")
    w = next(c for c in big.components if c.name == "waiting")
    assert q.contribution < 0 and w.contribution < 0


def test_ppo_throughput_is_a_reward():
    lots = ppo_reward(ctx(vehicles_cleared=20))
    none = ppo_reward(ctx(vehicles_cleared=0))
    lp = next(c for c in lots.components if c.name == "throughput")
    np_ = next(c for c in none.components if c.name == "throughput")
    assert lp.contribution > np_.contribution >= 0


def test_ppo_switch_penalty_only_on_switch():
    assert any(c.name == "switch_penalty" for c in ppo_reward(ctx(action_name="SWITCH_PHASE")).components)
    assert not any(c.name == "switch_penalty" for c in ppo_reward(ctx(action_name="EXTEND_GREEN")).components)


# --------------------------------------------------------------------- cross-cutting
def test_rewards_are_deterministic():
    for fn in (a2c_reward, dqn_reward, ppo_reward):
        a = fn(ctx(vehicles_cleared=7, violations=1))
        b = fn(ctx(vehicles_cleared=7, violations=1))
        assert a.model_dump() == b.model_dump()


def test_reward_weights_match_config():
    cfg = get_config().reward
    a2c_weights = {c.name: c.weight for c in a2c_reward(ctx(phase_changed=True)).components}
    assert a2c_weights["emergency_wait"] == pytest.approx(float(cfg.a2c.alpha_emergency_wait))
    assert a2c_weights["switch_penalty"] == pytest.approx(float(cfg.a2c.switch_penalty))
    ppo_weights = {c.name: c.weight for c in ppo_reward(ctx()).components}
    assert ppo_weights["throughput"] == pytest.approx(float(cfg.ppo.gamma_throughput))


def test_phase_change_helper_used_by_a2c_reads_curr_emergency():
    # phase_changed=True but emergency active -> no flapping penalty (safety-motivated switch)
    st = make_state(served=Phase.EW, emergency=_active_emergency())
    got = a2c_reward(ctx(phase_changed=True, curr=st))
    assert [c.name for c in got.components] == [
        "emergency_wait",
        "normal_queue",
        "emergency_passage",
        "throughput",
    ]
