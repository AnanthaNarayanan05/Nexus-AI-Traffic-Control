"""TrainingService - background training job + live progress (Slice 2 STEP 5/6).

Runs a real 2-episode job on short (~2 min sim) episodes through the service and
checks the published snapshot the REST/WS layer reads.
"""

from __future__ import annotations

import time

import pytest

from app.training.service import (
    RunPhase,
    TrainingBusy,
    TrainingService,
    _reset_training_service_for_tests,
    get_training_service,
)

EP_SECONDS = 120.0


@pytest.fixture
def svc() -> TrainingService:
    _reset_training_service_for_tests()
    return get_training_service()


def _wait(svc: TrainingService, *, timeout: float = 120.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = svc.snapshot()
        if snap["job"] and snap["job"]["phase"] in ("completed", "failed"):
            return snap
        time.sleep(0.5)
    raise AssertionError("training job did not finish in time")


def test_idle_snapshot(svc):
    snap = svc.snapshot()
    assert snap["running"] is False
    assert snap["job"] is None
    assert snap["seq"] == 0


def test_run_publishes_progress_then_completes(svc):
    before = svc.seq
    svc.start(agent="a2c", episodes=2, scenario="emergency_heavy", seed=42,
              episode_seconds=EP_SECONDS)

    started = svc.snapshot()
    assert started["running"] is True
    assert started["job"]["run_id"].startswith("a2c-")
    assert started["job"]["episodes_requested"] == 2
    assert svc.seq > before

    final = _wait(svc)
    job = final["job"]
    assert job["phase"] == "completed"
    assert job["episode"] == 2
    assert len(job["returns"]) == 2
    assert job["last_episode"]["decisions"] > 0
    assert job["last_episode"]["metrics"]["traffic.avg_waiting_s"] >= 0.0
    assert job["final_checkpoint"] is not None
    assert job["registered_model_id"] == f"{job['run_id']}-ep002"
    assert final["running"] is False


def test_second_run_while_running_is_rejected(svc):
    svc.start(agent="a2c", episodes=2, scenario="emergency_heavy", seed=1,
              episode_seconds=EP_SECONDS)
    with pytest.raises(TrainingBusy):
        svc.start(agent="dqn", episodes=2, episode_seconds=EP_SECONDS)
    _wait(svc)  # let the first one finish so the thread is not left running


def test_start_rejects_bad_input(svc):
    with pytest.raises(KeyError):
        svc.start(agent="sarsa", episodes=1)
    with pytest.raises(ValueError):
        svc.start(agent="a2c", episodes=0)
    with pytest.raises(ValueError):
        svc.start(agent="a2c", episodes=5000)


def test_completed_run_appears_in_history(svc):
    svc.start(agent="a2c", episodes=2, scenario="emergency_heavy", seed=7,
              episode_seconds=EP_SECONDS)
    final = _wait(svc)
    run_id = final["job"]["run_id"]

    hist = svc.history()
    assert any(r["run_id"] == run_id for r in hist)
    detail = svc.run_detail(run_id)
    assert detail is not None
    assert detail["agent"] == "a2c"
    assert len(detail["episodes"]) == 2
    assert detail["reproducibility"]["config_digest"]
