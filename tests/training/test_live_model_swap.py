"""STEP 8 - a trained checkpoint reaches live inference, honestly.

`SimulationManager.set_model` must only report `is_trained=True` after it has actually
loaded a checkpoint whose `trained_episodes > 0` (spec 84 / 114), and `untrained` must
always restore fresh weights.
"""

from __future__ import annotations

import pytest

from app.core.simulation_manager import SimulationManager
from app.persistence import ModelRegistry
from app.schemas.enums import AgentName
from app.training.manager import TrainingManager

EP_SECONDS = 90.0


@pytest.fixture
def trained_a2c_model_id() -> str:
    mgr = TrainingManager(
        "a2c", episodes=2, scenario="emergency_heavy", seed=1,
        checkpoint_every=1, episode_seconds=EP_SECONDS,
    )
    run = mgr.run()
    model_id = f"{run.run_id}-ep002"
    reg = ModelRegistry()
    assert reg.get(model_id) is not None, "TrainingManager should have auto-registered the run"
    reg.promote(model_id)  # -> status 'active'
    return model_id


def test_untrained_by_default(client_free_manager: SimulationManager):
    st = client_free_manager.status()
    assert st["model_modes"][AgentName.A2C.value] == "untrained"
    assert st["agents"]["a2c"]["is_trained"] is False


def test_trained_checkpoint_flips_is_trained_then_reverts(
    client_free_manager: SimulationManager, trained_a2c_model_id: str
):
    sm = client_free_manager

    st = sm.set_model("a2c", "trained")
    assert st["model_modes"]["a2c"] == "trained"
    assert st["model_sources"]["a2c"] == trained_a2c_model_id
    assert st["agents"]["a2c"]["is_trained"] is True
    assert sm.agents[AgentName.A2C].trained_episodes == 2
    # the swapped-in object is the one the loop will actually call
    assert sm.a2c is sm.agents[AgentName.A2C]

    st = sm.set_model("a2c", "untrained")
    assert st["model_modes"]["a2c"] == "untrained"
    assert st["model_sources"]["a2c"] is None
    assert st["agents"]["a2c"]["is_trained"] is False
    assert sm.agents[AgentName.A2C].trained_episodes == 0


def test_trained_request_for_a_missing_checkpoint_raises(client_free_manager: SimulationManager):
    # isolated DB: no DQN checkpoint registered -> honest failure, no fake badge
    with pytest.raises(ValueError, match="no trained model"):
        client_free_manager.set_model("dqn", "trained")
    assert client_free_manager.status()["agents"]["dqn"]["is_trained"] is False


def test_ppo_is_a_live_inference_agent(client_free_manager: SimulationManager):
    # R10: PPO is one of the three active agents - it is in the live loop and its
    # untrained mode is honoured like A2C / DQN.
    st = client_free_manager.set_model("ppo", "untrained")
    assert st["model_modes"]["ppo"] == "untrained"
    assert st["agents"]["ppo"]["is_trained"] is False
    assert client_free_manager.ppo is client_free_manager.agents[AgentName.PPO]


def test_unknown_agent_is_rejected_from_live_inference(client_free_manager: SimulationManager):
    with pytest.raises(ValueError, match="unknown agent"):
        client_free_manager.set_model("sarsa", "untrained")


@pytest.fixture
def client_free_manager() -> SimulationManager:
    # constructor does not spawn the loop thread; submit() runs inline
    return SimulationManager()
