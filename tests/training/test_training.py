"""Headless training loop — the behaviour Slice 2 locks in.

Fast: every test uses a short (~4 min sim) episode. The point is the *plumbing*
(safety authoritative, episodes advance, gradients run, checkpoints round-trip),
not that a policy converges in four episodes.
"""

from __future__ import annotations

import pytest

from app.scenarios import get_scenario
from app.scenarios.presets import PRESET_IDS
from app.training import (
    DEFAULT_SCENARIO,
    TrainingEnv,
    TrainingManager,
    build_agent,
)

EP_SECONDS = 240.0


def _env(agent_name: str, scenario_id: str, *, seed: int = 42) -> TrainingEnv:
    sc = get_scenario(scenario_id)
    sc.duration_s = EP_SECONDS
    agent = build_agent(agent_name, seed=seed, training=True)
    return TrainingEnv(agent, sc, seed=seed)


# --------------------------------------------------------------------- contract
def test_build_agent_rejects_unknown():
    with pytest.raises(KeyError):
        build_agent("dfp", seed=0, training=False)


def test_default_scenarios_are_real_presets():
    assert set(DEFAULT_SCENARIO) == {"a2c", "dqn", "ppo"}
    for sid in DEFAULT_SCENARIO.values():
        assert sid in PRESET_IDS


# --------------------------------------------------------------------- §113 safety
def test_safety_is_consulted_on_every_decision():
    """Every applied phase went through SafetyValidator — none bypassed it (spec §113)."""
    env = _env("a2c", "emergency_heavy")
    result = env.run_episode(1)
    # one validate() call per decision, exactly
    assert env.safety.checks_total == result.decisions
    assert result.decisions > 0


def test_emergency_heavy_produces_real_safety_overrides():
    env = _env("a2c", "emergency_heavy")
    result = env.run_episode(1)
    # emergency_heavy floods emergencies; the safety layer must step in at least once,
    # and the episode still completes (safety bounds the policy, never crashes it)
    assert result.safety_overrides >= 1
    assert result.safety_overrides <= result.decisions


# --------------------------------------------------------------------- episodes
@pytest.mark.parametrize("agent_name", ["a2c", "dqn", "ppo"])
def test_episode_trains_and_advances(agent_name):
    env = _env(agent_name, DEFAULT_SCENARIO[agent_name])
    assert env.agent.trained_episodes == 0
    assert not env.agent.is_trained
    assert env.agent.model_version.endswith("untrained")

    r1 = env.run_episode(1)
    r2 = env.run_episode(2)

    assert env.agent.trained_episodes == 2
    assert env.agent.is_trained
    assert "untrained" not in env.agent.model_version
    for r in (r1, r2):
        assert r.decisions > 0
        assert r.metrics.window == "episode"
        # return is a finite number that actually accumulated over the episode
        assert r.episode_return == pytest.approx(r.mean_reward * r.decisions, rel=1e-3)


def test_a2c_runs_real_gradient_steps():
    env = _env("a2c", "emergency_heavy")
    r = env.run_episode(1)
    assert r.updates >= 1
    assert {"actor_loss", "critic_loss", "entropy"} <= set(r.losses)


def test_same_seed_reproduces_episode():
    a = _env("ppo", "rush_hour", seed=7).run_episode(1)
    b = _env("ppo", "rush_hour", seed=7).run_episode(1)
    assert a.episode_return == b.episode_return
    assert a.decisions == b.decisions
    assert a.metrics.flat() == b.metrics.flat()


def test_different_seed_diverges():
    a = _env("ppo", "rush_hour", seed=7).run_episode(1)
    b = _env("ppo", "rush_hour", seed=8).run_episode(1)
    assert a.episode_return != b.episode_return


# --------------------------------------------------------------------- manager + checkpoints
def test_manager_run_checkpoints_and_writes_metrics(tmp_path):
    mgr = TrainingManager(
        "a2c", episodes=4, scenario="emergency_heavy", seed=42,
        checkpoint_every=2, out_dir=tmp_path, episode_seconds=EP_SECONDS,
    )
    run = mgr.run()

    assert len(run.episode_returns) == 4
    assert run.episode_seeds == [42, 43, 44, 45]
    assert run.final_checkpoint is not None
    assert run.reproducibility["scenario_id"] == "emergency_heavy"
    assert run.reproducibility["config_digest"]

    agent_dir = tmp_path / "a2c"
    assert (agent_dir / "latest.pt").exists()
    assert (agent_dir / f"{run.run_id}.json").exists()
    # cadence: ep2 (mid), ep4 (final) — ep4 is not double-written as "-ep002"
    ckpts = sorted(p.name for p in agent_dir.glob("*.pt"))
    assert "latest.pt" in ckpts
    assert any(name.endswith("-ep002.pt") for name in ckpts)
    assert any(name.endswith("-ep004.pt") for name in ckpts)

    # the checkpoint the app would load restores a trained policy
    fresh = build_agent("a2c", seed=0, training=False)
    meta = fresh.load(agent_dir / "latest.pt")
    assert fresh.trained_episodes == 4
    assert fresh.is_trained
    assert meta["run_id"] == run.run_id
    assert meta["scenario"] == "emergency_heavy"
    assert meta["seed"] == 42


def test_manager_rejects_unknown_agent():
    with pytest.raises(KeyError):
        TrainingManager("sarsa", episodes=1)
