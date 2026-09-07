"""Agent inference contract for A2C / DQN / PPO (spec sections 20, 41-43, 84, 111).

Covers: `act()` returns a well-formed recommendation, `resolve_phase()` agrees with it,
the inspector payload is shaped correctly, and an untrained agent says so honestly.
"""

from __future__ import annotations

import pytest

from app.agents.a2c import A2CAgent
from app.agents.dqn import DQNAgent
from app.agents.ppo import PPOAgent
from app.schemas.enums import AgentName, Approach, Phase
from app.schemas.simulation import EmergencyState

from tests.factories import make_state

AGENTS = [
    pytest.param(A2CAgent, "a2c", 31, 5, id="a2c"),
    pytest.param(DQNAgent, "dqn", 33, 5, id="dqn"),
    pytest.param(PPOAgent, "ppo", 33, 4, id="ppo"),
]


@pytest.mark.parametrize("cls,key,dim,n_actions", AGENTS)
def test_act_returns_valid_recommendation(cls, key, dim, n_actions):
    agent = cls(seed=0)
    rec = agent.act(make_state())
    assert rec.agent == AgentName(key)
    assert 0 <= rec.action_index < n_actions
    assert rec.action_name in agent.action_labels
    assert 0.0 <= rec.score <= 1.0
    assert 0.0 <= rec.confidence <= 1.0
    assert 0.0 <= rec.priority <= 1.0
    assert isinstance(rec.target_phase, Phase)
    assert rec.reason


@pytest.mark.parametrize("cls,key,dim,n_actions", AGENTS)
def test_resolve_phase_agrees_with_recommendation(cls, key, dim, n_actions):
    agent = cls(seed=0)
    st = make_state()
    rec = agent.act(st)
    assert agent.resolve_phase(rec.action_index, st) == rec.target_phase


@pytest.mark.parametrize("cls,key,dim,n_actions", AGENTS)
def test_act_is_deterministic_in_eval_mode(cls, key, dim, n_actions):
    st = make_state()
    a = cls(seed=0).act(st)
    b = cls(seed=0).act(st)
    assert a.action_index == b.action_index
    assert a.action_distribution == pytest.approx(b.action_distribution)


@pytest.mark.parametrize("cls,key,dim,n_actions", AGENTS)
def test_untrained_agent_reports_honestly(cls, key, dim, n_actions):
    agent = cls(seed=0)
    status = agent.status()
    assert status.is_trained is False
    assert status.trained_episodes == 0
    assert "untrained" in status.model_version
    # an inference-only agent's learn() is a no-op
    assert agent.learn() == {}


@pytest.mark.parametrize("cls,key,dim,n_actions", AGENTS)
def test_inspector_payload_shape(cls, key, dim, n_actions):
    agent = cls(seed=0)
    payload = agent.inspect(make_state())
    assert payload.agent == AgentName(key)
    assert len(payload.features) == dim
    assert len(payload.action_labels) == n_actions
    assert len(payload.action_distribution) == n_actions
    assert payload.selected_action in payload.action_labels


@pytest.mark.parametrize("cls,key,dim,n_actions", AGENTS)
def test_inspector_does_not_pollute_decision_history(cls, key, dim, n_actions):
    agent = cls(seed=0)
    agent.act(make_state())
    agent.act(make_state())
    before = len(agent._decision_history)
    agent.inspect(make_state())
    agent.inspect(make_state())
    assert len(agent._decision_history) == before


def test_a2c_priority_rises_with_close_emergency():
    agent = A2CAgent(seed=0)
    calm = agent.act(make_state()).priority
    urgent = agent.act(
        make_state(
            emergency=EmergencyState(
                active=True, approach=Approach.N, distance_m=25.0, speed_mps=10.0, eta_s=2.5
            )
        )
    ).priority
    assert urgent > calm


def test_a2c_action_distribution_is_a_probability_vector():
    rec = A2CAgent(seed=0).act(make_state())
    assert sum(rec.action_distribution) == pytest.approx(1.0, abs=1e-4)
    assert all(0.0 <= p <= 1.0 for p in rec.action_distribution)


def test_ppo_pressure_keyed_by_approach_and_bounded():
    agent = PPOAgent(seed=0)
    pressure = agent.pressure(
        make_state(
            queues={Approach.N: 18, Approach.E: 0, Approach.S: 2, Approach.W: 0},
            waits={Approach.N: 80.0, Approach.E: 1.0, Approach.S: 5.0, Approach.W: 0.0},
        )
    )
    assert set(pressure) == {"N", "E", "S", "W"}
    assert all(0.0 <= v <= 1.0 for v in pressure.values())
    assert pressure["N"] > pressure["E"]


def test_ppo_recommendation_text_is_nonempty():
    assert PPOAgent(seed=0).recommendation_text(make_state())


def test_dqn_exposes_raw_q_values_in_inspector():
    payload = DQNAgent(seed=0).inspect(make_state())
    q = payload.extra.get("q_values")
    assert isinstance(q, dict)
    assert set(q) == set(payload.action_labels)


def test_dqn_records_transitions_in_inference_mode_without_learning():
    # The live DQN runs in inference mode. observe() must still fill the replay buffer so
    # the Experience Replay inspector (spec section 17) has real state -> action -> reward
    # -> next-state -> done tuples to show, while learn() stays a no-op until training.
    from app.agents.dqn.agent import ACTION_LABELS

    agent = DQNAgent(seed=0)
    assert agent.training is False
    st = make_state()
    assert len(agent.buffer) == 0

    for _ in range(5):
        rec = agent.act(st)
        agent.observe(st, rec.action_index, -0.1, st, False)

    assert len(agent.buffer) == 5
    assert agent.learn() == {}  # inference mode: no gradient step

    sample = agent.replay_sample(3)
    assert len(sample) == 3
    assert set(sample[0]) == {
        "action", "reward", "done", "state_summary", "next_state_summary", "info"
    }
    assert sample[0]["action"] in ACTION_LABELS


def test_agents_keep_objective_ownership_separate():
    # the three algorithms must never be collapsed into one (PPT source of truth)
    assert A2CAgent(seed=0).name == AgentName.A2C
    assert DQNAgent(seed=0).name == AgentName.DQN
    assert PPOAgent(seed=0).name == AgentName.PPO
    assert len({A2CAgent(seed=0).state_dim, DQNAgent(seed=0).state_dim}) == 2
