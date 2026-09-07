"""REST + WebSocket surface (spec section 88, docs/system-flow.md section 3).

Drives the real FastAPI app through Starlette's TestClient (lifespan on, so the
simulation loop thread is live). Endpoints still deferred to a later slice (experiments,
replay) are asserted to 404 rather than stubbed (spec §98).
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

# factories puts backend/ on sys.path and is imported for that side effect
from tests import factories  # noqa: F401

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
def test_scenarios_list_and_detail(client):
    r = client.get("/api/v1/scenarios")
    assert r.status_code == 200
    ids = {s["id"] for s in r.json()["scenarios"]}
    assert {"normal", "rush_hour", "emergency_heavy"} <= ids

    r = client.get("/api/v1/scenarios/rush_hour")
    assert r.status_code == 200
    assert r.json()["id"] == "rush_hour"

    assert client.get("/api/v1/scenarios/does_not_exist").status_code == 404


def test_scenario_load_by_id(client):
    r = client.post("/api/v1/scenarios/load", json={"id": "uneven", "seed": 7})
    assert r.status_code == 200
    assert r.json()["scenario"]["id"] == "uneven"
    assert client.get("/api/v1/simulation/status").json()["scenario"]["id"] == "uneven"


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
        # inference-only in this slice: never claim training that did not happen
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


def test_deferred_endpoints_are_absent_not_stubbed(client):
    # spec section 98: still-unimplemented features must not be faked
    for path in ("/api/v1/experiments", "/api/v1/replay"):
        assert client.get(path).status_code == 404


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
