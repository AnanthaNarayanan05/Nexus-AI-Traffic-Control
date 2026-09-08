"""REST + WebSocket surface (spec section 88, docs/system-flow.md section 3).

Drives the real FastAPI app through Starlette's TestClient (lifespan on, so the
simulation loop thread is live). Experiments (R9 P1), replay (R9 P3) and export (R9 P4)
are all live; export still 404s an id that no run produced (spec §98).
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

# factories puts backend/ on sys.path and is imported for that side effect
from tests import factories  # noqa: F401

# Three active RL agents (R10): A2C emergency, DQN efficiency, PPO congestion.
OWNERS = {
    "a2c": "Anantha Narayanan A",
    "dqn": "Shaun Joseph Sabu",
    "ppo": "Delna Liz Denny",
}


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_sim(client):
    """Each test starts paused, on the 'normal' scenario, seed 42, in AI mode."""
    client.post("/api/v1/simulation/pause")
    client.post("/api/v1/simulation/mode", json={"mode": "AI"})
    client.post("/api/v1/simulation/reset", json={"scenario_id": "normal", "seed": 42})
    yield
    client.post("/api/v1/simulation/pause")


# --------------------------------------------------------------- system
def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["adapter"] == "builtin"


def test_config_exposes_digest_and_geometry(client):
    r = client.get("/api/v1/config")
    assert r.status_code == 200
    body = r.json()
    assert body["digest"]
    assert body["geometry"]["lane_width_m"] == pytest.approx(3.4)
    assert "phases" not in body["signals"]  # phases list is stripped from the config payload


# --------------------------------------------------------------- scenarios
REQUIRED_PRESETS = {
    "normal", "rush_hour", "emergency_heavy", "uneven",
    "high_stop_go", "incident", "safety_violation", "mixed_crisis",
}


def test_scenarios_list_and_detail(client):
    r = client.get("/api/v1/scenarios")
    assert r.status_code == 200
    rows = r.json()["scenarios"]
    ids = {s["id"] for s in rows}
    assert REQUIRED_PRESETS <= ids  # all 8 R9 §8A presets present

    for s in rows:
        if s["id"] in REQUIRED_PRESETS:
            assert s["preset"] is True
            assert s["objective"] and s["ai_focus"]  # presentation metadata is filled in
            assert s["difficulty"] in {"easy", "moderate", "hard", "extreme"}

    r = client.get("/api/v1/scenarios/rush_hour")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "rush_hour"
    assert body["objective"] and body["difficulty"] == "hard"

    assert client.get("/api/v1/scenarios/does_not_exist").status_code == 404


def test_scenario_load_by_id(client):
    r = client.post("/api/v1/scenarios/load", json={"id": "uneven", "seed": 7})
    assert r.status_code == 200
    assert r.json()["scenario"]["id"] == "uneven"
    assert client.get("/api/v1/simulation/status").json()["scenario"]["id"] == "uneven"


def test_scenario_create_validates_and_persists(client):
    good = {
        "id": "api-custom-1", "name": "API custom", "description": "made over REST",
        "objective": "watch queues", "ai_focus": "dqn", "difficulty": "moderate",
        "demand": {"weights": {"N": 0.3, "E": 0.2, "S": 0.3, "W": 0.2}, "arrivals_vph": 1800},
        "emergency_probability_per_min": 0.5,
    }
    r = client.post("/api/v1/scenarios", json=good)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "api-custom-1"

    # it now shows up in the list as a non-preset
    listed = {s["id"]: s for s in client.get("/api/v1/scenarios").json()["scenarios"]}
    assert listed["api-custom-1"]["preset"] is False

    # a preset id cannot be overwritten
    assert client.post("/api/v1/scenarios", json={**good, "id": "normal"}).status_code == 409

    # out-of-range values are a 422, not a clamp
    bad = {**good, "id": "api-bad", "emergency_probability_per_min": 999}
    assert client.post("/api/v1/scenarios", json=bad).status_code == 422
    # unknown field is rejected (can't smuggle a knob past validation)
    smuggle = {**good, "id": "api-smuggle", "disable_safety_layer": True}
    assert client.post("/api/v1/scenarios", json=smuggle).status_code == 422


def test_scenario_duplicate_and_delete(client):
    src = {
        "id": "dup-src", "name": "Dup source", "difficulty": "hard",
        "demand": {"weights": {"N": 1, "E": 1, "S": 1, "W": 1}, "arrivals_vph": 1600},
    }
    assert client.post("/api/v1/scenarios", json=src).status_code == 200

    r = client.post("/api/v1/scenarios/dup-src/duplicate", json={"new_id": "dup-copy"})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "dup-copy" and r.json()["name"] == "Copy of Dup source"

    # duplicating a preset into a custom id is allowed
    r = client.post("/api/v1/scenarios/normal/duplicate",
                    json={"new_id": "my-normal", "name": "My normal"})
    assert r.status_code == 200 and r.json()["id"] == "my-normal"

    # can't duplicate onto a preset id
    assert client.post("/api/v1/scenarios/dup-src/duplicate",
                       json={"new_id": "rush_hour"}).status_code in (409, 422)

    # delete the custom one; preset deletion is refused
    assert client.delete("/api/v1/scenarios/dup-copy").status_code == 200
    assert client.get("/api/v1/scenarios/dup-copy").status_code == 404
    assert client.delete("/api/v1/scenarios/normal").status_code == 409
    assert client.delete("/api/v1/scenarios/never-existed").status_code == 404


# --------------------------------------------------------------- simulation control
def test_state_and_status(client):
    r = client.get("/api/v1/simulation/state")
    assert r.status_code == 200
    state = r.json()
    assert state["step"] == 0
    assert set(state["approaches"]) == {"N", "E", "S", "W"}

    r = client.get("/api/v1/simulation/status")
    assert r.status_code == 200
    status = r.json()
    assert status["running"] is False
    assert status["mode"] == "AI"
    assert status["scenario"]["id"] == "normal"


def _vehicle_count(state: dict) -> int:
    return sum(ap["vehicle_count"] for ap in state["approaches"].values())


def test_step_advances_physics_deterministically(client):
    a = client.post("/api/v1/simulation/step", json={"ticks": 40})
    assert a.status_code == 200
    assert a.json()["step"] == 40
    state_a = client.get("/api/v1/simulation/state").json()

    client.post("/api/v1/simulation/reset", json={"scenario_id": "normal", "seed": 42})
    client.post("/api/v1/simulation/step", json={"ticks": 40})
    state_b = client.get("/api/v1/simulation/state").json()

    assert state_a["sim_time"] == state_b["sim_time"]
    assert _vehicle_count(state_a) == _vehicle_count(state_b)
    assert state_a["estimates"]["co2_kg_total"] == state_b["estimates"]["co2_kg_total"]


def test_start_then_pause_toggles_running(client):
    assert client.post("/api/v1/simulation/start").json()["running"] is True
    assert client.post("/api/v1/simulation/pause").json()["running"] is False


def test_speed_is_clamped(client):
    assert client.post("/api/v1/simulation/speed", json={"speed": 4.0}).json()["speed"] == 4.0
    # out of the declared [0.1, 20] range -> 422 from the request model
    assert client.post("/api/v1/simulation/speed", json={"speed": 999}).status_code == 422


def test_mode_switch_and_invalid_mode(client):
    assert client.post("/api/v1/simulation/mode", json={"mode": "FIXED_TIME"}).json()["mode"] == "FIXED_TIME"
    assert client.post("/api/v1/simulation/mode", json={"mode": "TELEPORT"}).status_code == 400


def test_model_mode_defaults_untrained_and_is_in_status(client):
    st = client.get("/api/v1/simulation/status").json()
    assert st["model_modes"] == {"a2c": "untrained", "dqn": "untrained", "ppo": "untrained"}
    assert st["model_sources"] == {"a2c": None, "dqn": None, "ppo": None}
    for a in ("a2c", "dqn", "ppo"):
        assert st["agents"][a]["is_trained"] is False


def test_model_trained_request_without_a_checkpoint_is_rejected(client):
    # per-test isolated DB is empty -> no trained model to load, and no fake badge (spec 84)
    r = client.post("/api/v1/simulation/model", json={"agent": "a2c", "mode": "trained"})
    assert r.status_code == 400
    assert "no trained model" in r.json()["detail"]
    assert client.get("/api/v1/simulation/status").json()["agents"]["a2c"]["is_trained"] is False


def test_model_mode_bad_input_is_rejected(client):
    assert client.post("/api/v1/simulation/model",
                       json={"agent": "a2c", "mode": "sideways"}).status_code == 400
    assert client.post("/api/v1/simulation/model",
                       json={"agent": "nope", "mode": "untrained"}).status_code == 400
    # explicit untrained is always allowed and idempotent
    r = client.post("/api/v1/simulation/model", json={"agent": "dqn", "mode": "untrained"})
    assert r.status_code == 200
    assert r.json()["model_modes"]["dqn"] == "untrained"


def test_manual_action_requires_manual_mode(client):
    # default mode is AI -> rejected
    r = client.post("/api/v1/simulation/manual", json={"action": "SWITCH"})
    assert r.status_code == 400

    client.post("/api/v1/simulation/mode", json={"mode": "MANUAL"})
    r = client.post("/api/v1/simulation/manual", json={"action": "SWITCH"})
    assert r.status_code == 200
    assert "safety" in r.json()

    r = client.post("/api/v1/simulation/manual", json={"action": "NOT_A_REAL_ACTION"})
    assert r.status_code == 400


def test_inject_emergency(client):
    r = client.post("/api/v1/simulation/inject",
                    json={"event": "spawn_emergency", "args": {"approach": "N"}})
    assert r.status_code == 200
    assert r.json()["injected"] == "spawn_emergency"
    assert r.json()["ids"]

    # a known event missing its required argument is a 400
    r = client.post("/api/v1/simulation/inject", json={"event": "block_lane", "args": {}})
    assert r.status_code == 400


# --------------------------------------------------------------- agents
def test_agents_report_status_and_ownership(client):
    body = client.get("/api/v1/agents").json()
    assert set(body["agents"]) == {"a2c", "dqn", "ppo"}
    for key, owner in OWNERS.items():
        assert body["ownership"][key]["owner"] == owner
        # inference-only by default: never claim training that did not happen
        assert body["agents"][key]["is_trained"] is False
        assert "untrained" in body["agents"][key]["model_version"]


@pytest.mark.parametrize("agent", ["a2c", "dqn", "ppo"])
def test_agent_inspector(client, agent):
    r = client.get(f"/api/v1/agents/{agent}")
    assert r.status_code == 200
    body = r.json()
    assert body["agent"] == agent
    assert body["features"]
    assert body["action_labels"]
    assert len(body["action_distribution"]) == len(body["action_labels"])


def test_unknown_agent_is_404(client):
    assert client.get("/api/v1/agents/sarsa").status_code == 404


# --------------------------------------------------------------- decisions / safety / metrics / events
def test_coordination_last_appears_after_a_decision(client):
    # no decision yet on a fresh reset
    assert client.get("/api/v1/coordination/last").status_code == 404

    # one decision interval is 6s sim = 12 physics ticks; step past it
    client.post("/api/v1/simulation/step", json={"ticks": 30})
    r = client.get("/api/v1/coordination/last")
    assert r.status_code == 200
    body = r.json()
    assert body["coordination"]["candidate_phase"]
    assert body["safety"]["action_taken"]


def test_safety_overrides_endpoint(client):
    client.post("/api/v1/simulation/step", json={"ticks": 30})
    body = client.get("/api/v1/safety/overrides").json()
    assert "overrides" in body
    assert body["checks_total"] >= 1
    assert isinstance(body["overrides"], list)


def test_metrics_and_events(client):
    client.post("/api/v1/simulation/step", json={"ticks": 30})
    m = client.get("/api/v1/metrics").json()
    assert "current" in m

    e = client.get("/api/v1/events").json()
    assert "events" in e and "cursor" in e
    assert any(ev["category"] == "SYSTEM" for ev in e["events"])


def test_export_unknown_ids_404_and_bad_format_422(client):
    # R9 P4: export never fabricates - an id that was never produced 404s.
    assert client.get("/api/v1/export/experiments/exp-nope").status_code == 404
    assert client.get("/api/v1/export/replays/replay-nope").status_code == 404
    # `format` is a Literal -> FastAPI rejects an unknown value
    assert client.get(
        "/api/v1/export/replays/replay-nope", params={"format": "xml"}
    ).status_code == 422


def test_export_experiment_csv_and_json(client):
    # write a completed comparison straight to the store (a full headless run is minutes);
    # the export path itself is what is under test.
    from app.persistence import ExperimentStore

    store = ExperimentStore()
    eid = "exp-20260908T000000000Z"
    store.create(
        experiment_id=eid, name="normal · fixed_time vs a2c", scenario="normal",
        controllers=["fixed_time", "a2c"], seeds=[1, 2], baseline="fixed_time",
        episode_seconds=120.0, reproducibility={"config_digest": "abc", "seeds": [1, 2]},
    )

    # an experiment with no comparison yet cannot be exported
    assert client.get(f"/api/v1/export/experiments/{eid}").status_code == 409

    store.complete(
        eid,
        comparison={
            "baseline": "fixed_time",
            "metrics": {
                "traffic.avg_waiting_s": {
                    "lower_is_better": True,
                    "values": {
                        "fixed_time": {"mean": 40.0, "improvement_pct_vs_baseline": None},
                        "a2c untrained": {"mean": 30.0,
                                          "improvement_pct_vs_baseline": 25.0},
                    },
                }
            },
        },
        results=[
            {"label": "fixed_time", "controller": "fixed_time", "model_mode": "fixed_time",
             "aggregates": {"traffic.avg_waiting_s": {"n": 2, "mean": 40.0, "median": 40.0,
                                                     "std": 2.0, "min": 38.0, "max": 42.0,
                                                     "ci_half_width": 1.0}}},
            {"label": "a2c untrained", "controller": "a2c", "model_mode": "untrained",
             "aggregates": {"traffic.avg_waiting_s": {"n": 2, "mean": 30.0, "median": 30.0,
                                                     "std": 3.0, "min": 27.0, "max": 33.0,
                                                     "ci_half_width": 1.5}}},
        ],
        wall_time_s=5.0,
    )

    csv_res = client.get(f"/api/v1/export/experiments/{eid}", params={"format": "csv"})
    assert csv_res.status_code == 200
    assert csv_res.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv_res.headers["content-disposition"]
    assert f"{eid}.csv" in csv_res.headers["content-disposition"]
    lines = csv_res.text.strip().splitlines()
    assert lines[0].startswith("experiment_id,scenario,metric")
    assert any("a2c" in ln and "25.0" in ln for ln in lines[1:])

    json_res = client.get(f"/api/v1/export/experiments/{eid}", params={"format": "json"})
    assert json_res.status_code == 200
    assert json_res.headers["content-type"].startswith("application/json")
    assert json_res.json()["id"] == eid
    assert json_res.json()["comparison"]["baseline"] == "fixed_time"


def test_export_replay_csv_after_a_real_capture(client):
    client.post("/api/v1/simulation/reset", json={"scenario_id": "normal", "seed": 7})
    client.post("/api/v1/simulation/step", json={"ticks": 90})   # ~7 decisions
    rid = client.post("/api/v1/replay/capture").json()["id"]

    res = client.get(f"/api/v1/export/replays/{rid}", params={"format": "csv"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    lines = res.text.strip().splitlines()
    assert lines[0].startswith("replay_id,index,t,step")
    assert "applied_phase" in lines[0] and "safety_action" in lines[0]
    assert len(lines) - 1 >= 3          # one row per decision

    j = client.get(f"/api/v1/export/replays/{rid}", params={"format": "json"})
    assert j.json()["id"] == rid and j.json()["timeline"]

    client.delete(f"/api/v1/replay/{rid}")   # keep the store tidy


def test_replay_capture_list_seek_and_delete(client):
    # R9 P3: the replay surface. A run has to actually make decisions before there is
    # anything to capture - nothing is fabricated (spec §84, §98).
    client.post("/api/v1/simulation/reset", json={"scenario_id": "normal", "seed": 5})
    assert client.post("/api/v1/replay/capture").status_code == 409  # 0 decisions yet

    client.post("/api/v1/simulation/step", json={"ticks": 90})       # 45 s sim -> ~7 decisions
    cap = client.post("/api/v1/replay/capture")
    assert cap.status_code == 201
    rid = cap.json()["id"]
    assert cap.json()["decision_count"] >= 3
    assert cap.json()["episode_complete"] is False                   # run did not finish
    assert cap.json()["seed"] == 5

    rows = client.get("/api/v1/replay").json()["replays"]
    assert any(r["id"] == rid for r in rows)
    assert "timeline" not in rows[0]                                 # list is summary-only

    detail = client.get(f"/api/v1/replay/{rid}").json()
    frames = detail["timeline"]
    assert len(frames) == detail["decision_count"] >= 3
    f0 = frames[0]
    assert {"t", "coordination", "safety", "rewards", "metrics", "applied_phase"} <= set(f0)

    at = client.get(f"/api/v1/replay/{rid}/at", params={"t": frames[2]["t"] + 0.1}).json()
    assert at["index"] == 2
    assert at["frame"]["t"] == frames[2]["t"]
    assert at["total"] == len(frames)

    assert client.delete(f"/api/v1/replay/{rid}").json() == {"deleted": rid}
    assert client.get(f"/api/v1/replay/{rid}").status_code == 404
    assert client.delete(f"/api/v1/replay/{rid}").status_code == 404
    assert client.get("/api/v1/replay/unknown-id/at", params={"t": 1}).status_code == 404


def test_replay_captured_on_reset_of_a_run_with_decisions(client):
    client.post("/api/v1/simulation/reset", json={"scenario_id": "normal", "seed": 11})
    client.post("/api/v1/simulation/step", json={"ticks": 60})       # 30 s -> ~5 decisions
    before = len(client.get("/api/v1/replay").json()["replays"])
    # resetting tears the run down; a run with enough decisions is persisted as 'partial'
    client.post("/api/v1/simulation/reset", json={"scenario_id": "normal", "seed": 12})
    rows = client.get("/api/v1/replay").json()["replays"]
    assert len(rows) == before + 1
    assert rows[0]["episode_complete"] is False
    assert rows[0]["seed"] == 11
    client.delete(f"/api/v1/replay/{rows[0]['id']}")                  # keep the store tidy


def test_experiments_status_endpoint(client):
    body = client.get("/api/v1/experiments").json()
    assert "seq" in body and "running" in body
    assert "job" in body                   # None until a run starts - never fabricated
    assert body["job"] is None or body["job"]["phase"] in (
        "running", "completed", "failed")
    assert isinstance(body["history"], list)
    assert client.get("/api/v1/experiments/exp-nope").status_code == 404


def test_experiment_start_validates_input(client):
    # unknown controller -> 422 (a2c/dqn/ppo/fixed_time are the only valid ones)
    r = client.post("/api/v1/experiments", json={
        "scenario": "normal", "controllers": ["fixed_time", "sarsa"], "seeds": [1]})
    assert r.status_code == 422
    # unknown scenario -> 404
    r = client.post("/api/v1/experiments", json={
        "scenario": "does_not_exist", "controllers": ["fixed_time"], "seeds": [1]})
    assert r.status_code == 404
    # no seeds -> 422
    r = client.post("/api/v1/experiments", json={
        "scenario": "normal", "controllers": ["fixed_time"], "seeds": []})
    assert r.status_code == 422
    # a trained model that was never registered -> 422, no row created
    r = client.post("/api/v1/experiments", json={
        "scenario": "normal", "controllers": ["a2c"], "seeds": [1],
        "models": {"a2c": "active"}})
    assert r.status_code == 422
    assert client.get("/api/v1/experiments").json()["history"] == []


def test_training_status_endpoint(client):
    body = client.get("/api/v1/training").json()
    assert "seq" in body and "running" in body
    assert "job" in body            # None until a run starts - not fabricated
    assert isinstance(body["history"], list)


def test_training_run_detail_unknown_is_404(client):
    assert client.get("/api/v1/training/runs/nope-20200101T000000Z").status_code == 404


def test_training_start_validates_input(client):
    assert client.post("/api/v1/training/runs",
                       json={"agent": "sarsa", "episodes": 1}).status_code == 404
    assert client.post("/api/v1/training/runs",
                       json={"agent": "a2c", "episodes": 0}).status_code == 422
    # a2c / dqn / ppo are all valid agents; episode bound is still enforced
    assert client.post("/api/v1/training/runs",
                       json={"agent": "ppo", "episodes": 0}).status_code == 422


def test_models_registry_endpoint(client):
    body = client.get("/api/v1/models").json()
    assert isinstance(body["models"], list)   # empty on a fresh temp DB, never faked
    assert client.get("/api/v1/models/does-not-exist").status_code == 404


# --------------------------------------------------------------- websocket
def test_websocket_hello_frame(client):
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
    assert hello["type"] == "hello"
    assert hello["payload"]["protocol_version"]
    assert "simulation_state" in hello["payload"]["channels"]
    assert hello["payload"]["adapter"] == "builtin"


def test_websocket_ping_pong(client):
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        ws.send_json({"type": "ping"})
        for _ in range(50):
            frame = ws.receive_json()
            if frame["type"] == "pong":
                assert "server_time" in frame["payload"]
                break
        else:
            pytest.fail("no pong received")


def test_websocket_streams_training_update(client):
    """A real (short) training job's progress reaches the WS as `training_update`."""
    from app.training.service import _reset_training_service_for_tests, get_training_service

    _reset_training_service_for_tests()
    svc = get_training_service()
    svc.start(agent="a2c", episodes=2, scenario="emergency_heavy", seed=3,
              episode_seconds=90.0)
    try:
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "hello"
            seen = None
            for _ in range(400):
                frame = ws.receive_json()
                if frame["type"] == "training_update":
                    seen = frame["payload"]
                    if seen["job"]["phase"] in ("completed", "failed"):
                        break
            assert seen is not None, "no training_update frame received"
            assert seen["job"]["agent"] == "a2c"
            assert seen["job"]["phase"] in ("running", "completed")
    finally:
        # make sure the worker thread is done before the next test
        for _ in range(240):
            if not svc.is_running:
                break
            time.sleep(0.5)
        _reset_training_service_for_tests()
