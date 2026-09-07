"""Model registry - the queryable index over trained checkpoints (Slice 2, STEP 4).

The `_isolated_db` autouse fixture (tests/conftest.py) points NEXUS_DB_URL at a fresh
temp SQLite file per test, so every test starts with an empty `models` table.
"""

from __future__ import annotations

import pytest

from app.persistence import ModelRegistry, RegistryError


def _register(reg: ModelRegistry, model_id: str, agent: str = "a2c", **over) -> dict:
    kw = dict(
        model_id=model_id, agent=agent, version=f"{agent}-v1.0-dev",
        checkpoint_path=f"models/{agent}/{model_id}.pt", run_id=model_id.rsplit("-ep", 1)[0],
        scenario="emergency_heavy", seed=42, episodes=200,
        training_config={"n_steps": 20}, reward_config={"emergency_clear": 1.0},
        env_version="cfgdigest0001", code_version="abc1234", torch_version="2.5.1",
    )
    kw.update(over)
    return reg.register(**kw)


@pytest.fixture
def reg() -> ModelRegistry:
    return ModelRegistry()


def test_register_then_get_roundtrips(reg):
    out = _register(reg, "a2c-run1-ep200")
    assert out["status"] == "trained"
    got = reg.get("a2c-run1-ep200")
    assert got["agent"] == "a2c"
    assert got["seed"] == 42
    assert got["episodes"] == 200
    assert got["training_config"] == {"n_steps": 20}
    assert got["reward_config"] == {"emergency_clear": 1.0}
    assert got["env_version"] == "cfgdigest0001"
    assert got["code_version"] == "abc1234"
    assert got["created_at"]
    assert got["eval_metrics"] is None


def test_get_unknown_is_none(reg):
    assert reg.get("nope") is None


def test_register_is_upsert(reg):
    _register(reg, "a2c-run1-ep200", version="a2c-v1.0-dev")
    created = reg.get("a2c-run1-ep200")["created_at"]
    _register(reg, "a2c-run1-ep200", version="a2c-v1.4-dev")
    row = reg.get("a2c-run1-ep200")
    assert row["version"] == "a2c-v1.4-dev"
    assert row["created_at"] == created  # created_at is preserved on re-register


def test_register_rejects_unknown_status(reg):
    with pytest.raises(RegistryError):
        _register(reg, "a2c-run1-ep200", status="banana")


def test_attach_evaluation_moves_to_evaluated(reg):
    _register(reg, "dqn-run1-ep200", agent="dqn")
    blob = {"fixed_time": {"traffic.avg_waiting_s": {"mean": 5.3}},
            "dqn": {"traffic.avg_waiting_s": {"mean": 2.0}},
            "improvement_pct": {"dqn": {"traffic.avg_waiting_s": 62.3}}}
    out = reg.attach_evaluation("dqn-run1-ep200", scenario="high_stop_go", metrics=blob)
    assert out["status"] == "evaluated"
    got = reg.get("dqn-run1-ep200")
    assert got["eval_scenario"] == "high_stop_go"
    assert got["eval_metrics"]["improvement_pct"]["dqn"]["traffic.avg_waiting_s"] == 62.3
    assert got["evaluated_at"]


def test_attach_evaluation_unknown_model_raises(reg):
    with pytest.raises(RegistryError):
        reg.attach_evaluation("ghost", scenario="x", metrics={})


def test_promote_is_exclusive_per_agent(reg):
    _register(reg, "ppo-run1-ep200", agent="ppo")
    _register(reg, "ppo-run2-ep200", agent="ppo")
    _register(reg, "a2c-run1-ep200", agent="a2c")

    reg.promote("ppo-run1-ep200")
    assert reg.active("ppo")["id"] == "ppo-run1-ep200"

    reg.promote("ppo-run2-ep200")
    assert reg.active("ppo")["id"] == "ppo-run2-ep200"
    # the previously-active ppo model is demoted, not deleted
    assert reg.get("ppo-run1-ep200")["status"] == "trained"
    # promoting a ppo model never touches a2c
    assert reg.active("a2c") is None


def test_promoted_model_demotes_to_evaluated_if_it_had_eval(reg):
    _register(reg, "ppo-a-ep200", agent="ppo")
    _register(reg, "ppo-b-ep200", agent="ppo")
    reg.attach_evaluation("ppo-a-ep200", scenario="rush_hour", metrics={"x": 1})
    reg.promote("ppo-a-ep200")
    reg.promote("ppo-b-ep200")
    assert reg.get("ppo-a-ep200")["status"] == "evaluated"  # not "trained"


def test_list_filters_by_agent_and_status(reg):
    _register(reg, "a2c-r1-ep200", agent="a2c")
    _register(reg, "dqn-r1-ep200", agent="dqn")
    _register(reg, "dqn-r2-ep200", agent="dqn")
    reg.promote("dqn-r2-ep200")

    assert {m["id"] for m in reg.list()} == {"a2c-r1-ep200", "dqn-r1-ep200", "dqn-r2-ep200"}
    assert {m["id"] for m in reg.list(agent="dqn")} == {"dqn-r1-ep200", "dqn-r2-ep200"}
    assert [m["id"] for m in reg.list(status="active")] == ["dqn-r2-ep200"]


def test_latest_is_most_recent_for_agent(reg):
    _register(reg, "a2c-old-ep200", agent="a2c", created_at="2026-01-01T00:00:00+00:00")
    _register(reg, "a2c-new-ep200", agent="a2c", created_at="2026-09-01T00:00:00+00:00")
    assert reg.latest("a2c")["id"] == "a2c-new-ep200"
    assert reg.latest("ppo") is None


def test_training_manager_registers_final_checkpoint(tmp_path):
    from app.training import TrainingManager

    mgr = TrainingManager("a2c", episodes=2, scenario="emergency_heavy", seed=42,
                          checkpoint_every=2, out_dir=tmp_path, episode_seconds=180.0)
    run = mgr.run()

    reg = ModelRegistry()
    row = reg.latest("a2c")
    assert row is not None
    assert row["run_id"] == run.run_id
    assert row["scenario"] == "emergency_heavy"
    assert row["seed"] == 42
    assert row["episodes"] == 2
    assert row["status"] == "trained"
    assert row["checkpoint_path"] == run.final_checkpoint
    assert row["env_version"] == run.reproducibility["config_digest"]


def test_training_manager_register_false_skips_db(tmp_path):
    from app.training import TrainingManager

    TrainingManager("a2c", episodes=1, scenario="emergency_heavy", seed=1,
                    out_dir=tmp_path, episode_seconds=120.0, register=False).run()
    assert ModelRegistry().list() == []
