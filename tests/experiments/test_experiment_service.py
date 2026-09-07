"""ExperimentService - background Fixed-Time vs AI comparison job + live progress (R9 P1).

Runs a real, short (90 s sim) 2-seed comparison through the service and checks the
published snapshot the REST/WS layer reads, plus the persisted experiment row.
Every metric is a real evaluation-episode measurement (spec §84).
"""

from __future__ import annotations

import time

import pytest

from app.persistence import ExperimentStore
from app.training.evaluation import METRIC_DIRECTION
from app.training.experiment_service import (
    ExperimentBusy,
    ExperimentService,
    _reset_experiment_service_for_tests,
    get_experiment_service,
)

EP_SECONDS = 90.0
SEEDS = [1, 2]


@pytest.fixture
def svc() -> ExperimentService:
    _reset_experiment_service_for_tests()
    return get_experiment_service()


def _wait(svc: ExperimentService, *, timeout: float = 180.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = svc.snapshot()
        if snap["job"] and snap["job"]["phase"] in ("completed", "failed"):
            return snap
        time.sleep(0.5)
    raise AssertionError("experiment job did not finish in time")


def test_idle_snapshot(svc):
    snap = svc.snapshot()
    assert snap["running"] is False
    assert snap["job"] is None
    assert snap["seq"] == 0


def test_run_publishes_progress_then_completes(svc):
    before = svc.seq
    svc.start(name="smoke", scenario="normal", controllers=["fixed_time", "a2c"],
              seeds=SEEDS, episode_seconds=EP_SECONDS)

    started = svc.snapshot()
    assert started["running"] is True
    assert started["job"]["experiment_id"].startswith("exp-")
    assert started["job"]["episodes_total"] == 4  # 2 controllers x 2 seeds
    assert svc.seq > before

    final = _wait(svc)
    job = final["job"]
    assert job["phase"] == "completed"
    assert job["episodes_done"] == 4
    assert job["progress"] == pytest.approx(1.0)
    assert final["running"] is False

    # honest comparison blob: baseline present, every metric keyed, direction carried
    blob = job["comparison"]
    assert blob["baseline"] == "fixed_time"
    for key in METRIC_DIRECTION:
        row = blob["metrics"][key]
        assert row["lower_is_better"] == METRIC_DIRECTION[key]
        # baseline never gets an improvement % against itself
        assert row["values"]["fixed_time"]["improvement_pct_vs_baseline"] is None
        assert "mean" in row["values"]["fixed_time"]

    # the AI result carries its untrained provenance, not a fake trained badge
    ai = [r for r in job["results"] if r["controller"] == "a2c"][0]
    assert ai["model_mode"] == "untrained"
    assert ai["model_version"] == "untrained"
    assert ai["registry_id"] is None
    assert len(ai["episodes"]) == 2


def test_completed_run_is_persisted_and_in_history(svc):
    svc.start(name=None, scenario="normal", controllers=["fixed_time", "dqn"],
              seeds=SEEDS, episode_seconds=EP_SECONDS)
    final = _wait(svc)
    eid = final["job"]["experiment_id"]

    hist = svc.history()
    assert any(r["id"] == eid for r in hist)

    row = ExperimentStore().get(eid)
    assert row["status"] == "completed"
    assert row["reproducibility"]["config_digest"]
    assert row["reproducibility"]["seeds"] == SEEDS
    assert row["comparison"]["baseline"] == "fixed_time"
    assert row["results"][0]["controller"] == "fixed_time"


def test_second_run_while_running_is_rejected(svc):
    # agent controllers over 3 seeds -> enough work that the first job is still
    # running when the second start() is attempted.
    svc.start(name=None, scenario="normal", controllers=["fixed_time", "a2c", "dqn"],
              seeds=[1, 2, 3], episode_seconds=EP_SECONDS)
    with pytest.raises(ExperimentBusy):
        svc.start(name=None, scenario="normal", controllers=["fixed_time"], seeds=SEEDS,
                  episode_seconds=EP_SECONDS)
    _wait(svc)


def test_start_rejects_bad_input(svc):
    with pytest.raises(ValueError, match="controller"):
        svc.start(name=None, scenario="normal", controllers=["ppo"], seeds=[1])
    with pytest.raises(KeyError):
        svc.start(name=None, scenario="nope", controllers=["fixed_time"], seeds=[1])
    with pytest.raises(ValueError, match="seed"):
        svc.start(name=None, scenario="normal", controllers=["fixed_time"], seeds=[])
    with pytest.raises(ValueError, match="active checkpoint"):
        svc.start(name=None, scenario="normal", controllers=["a2c"], seeds=[1],
                  models={"a2c": "active"})
    # nothing was persisted for the rejected starts
    assert ExperimentStore().list() == []


def test_trained_checkpoint_is_used_when_selected(svc, tmp_path):
    """A registered checkpoint selected by id actually loads - version is not 'untrained'."""
    from app.persistence import ModelRegistry
    from app.training import TrainingManager

    mgr = TrainingManager("a2c", episodes=2, scenario="emergency_heavy", seed=3,
                          out_dir=tmp_path, episode_seconds=EP_SECONDS, register=False)
    run = mgr.run()
    reg = ModelRegistry()
    row = reg.register_training_run(run)
    model_id = row["id"]

    svc.start(name=None, scenario="normal", controllers=["fixed_time", "a2c"],
              seeds=SEEDS, models={"a2c": model_id}, episode_seconds=EP_SECONDS)
    final = _wait(svc)
    ai = [r for r in final["job"]["results"] if r["controller"] == "a2c"][0]
    assert ai["model_mode"] == model_id
    assert ai["registry_id"] == model_id
    assert ai["model_version"] != "untrained"
