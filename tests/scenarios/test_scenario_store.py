"""Custom scenarios: validation, the `ScenarioStore` CRUD facade, and the
save / load / duplicate / delete lifecycle through `app.scenarios.presets` (R9 §8B).

The `_isolated_db` autouse fixture gives each test a fresh temp SQLite file and calls
`_reset_custom_for_tests()`, so the in-process `_CUSTOM` cache and the `scenarios` table
both start empty.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.persistence import ScenarioStore, ScenarioStoreError
from app.persistence.db import reset_engine_for_tests
from app.scenarios.presets import (
    _reset_custom_for_tests,
    delete_scenario,
    get_scenario,
    list_scenarios,
    register_scenario,
)
from app.schemas.scenario import ScenarioConfig


def _cfg(**over) -> ScenarioConfig:
    base = dict(
        id="custom-a", name="Custom A", description="a custom scenario",
        objective="watch the queues", ai_focus="dqn", difficulty="moderate",
    )
    base.update(over)
    return ScenarioConfig(**base)


# --------------------------------------------------------------- validation
def test_validation_rejects_out_of_range_and_unknown_fields():
    with pytest.raises(ValidationError):
        _cfg(emergency_probability_per_min=-1.0)
    with pytest.raises(ValidationError):
        _cfg(duration_s=5.0)  # below the 60s floor
    with pytest.raises(ValidationError):
        ScenarioConfig(id="x", disable_safety_layer=True)  # extra field forbidden
    with pytest.raises(ValidationError):
        _cfg(id="not a slug")
    with pytest.raises(ValidationError):
        _cfg(weather="hurricane")


def test_validation_rejects_bad_blocked_lanes_and_full_closures():
    with pytest.raises(ValidationError):
        _cfg(blocked_lanes=[{"approach": "Z", "lane": 0}])
    with pytest.raises(ValidationError):
        _cfg(blocked_lanes=[{"approach": "N", "lane": 9}])
    with pytest.raises(ValidationError):
        # blocking every lane of an approach would seal it shut
        _cfg(blocked_lanes=[{"approach": "N", "lane": i} for i in range(3)])
    ok = _cfg(blocked_lanes=[{"approach": "N", "lane": 0}, {"approach": "N", "lane": 1}])
    assert len(ok.blocked_lanes) == 2


def test_validation_rejects_scheduled_change_past_episode_end():
    prof = {"weights": {"N": 1, "E": 1, "S": 1, "W": 1}, "arrivals_vph": 1600}
    with pytest.raises(ValidationError):
        _cfg(duration_s=600.0, scheduled_changes=[{"at_s": 900.0, "profile": prof}])
    ok = _cfg(duration_s=600.0, scheduled_changes=[{"at_s": 300.0, "profile": prof}])
    assert ok.scheduled_changes[0].at_s == 300.0


def test_zero_demand_is_rejected():
    with pytest.raises(ValidationError):
        _cfg(demand={"weights": {"N": 0, "E": 0, "S": 0, "W": 0}, "arrivals_vph": 1600})


# --------------------------------------------------------------- ScenarioStore
def test_store_crud_round_trip():
    store = ScenarioStore()
    assert store.list() == []

    store.save("s1", {"id": "s1", "name": "One", "difficulty": "hard"})
    store.save("s2", {"id": "s2", "name": "Two"})
    assert store.get("s1")["name"] == "One"
    assert {b["id"] for b in store.list()} == {"s1", "s2"}

    # save is an upsert
    store.save("s1", {"id": "s1", "name": "One (edited)"})
    assert store.get("s1")["name"] == "One (edited)"
    assert len(store.list()) == 2

    store.delete("s1")
    assert store.get("s1") is None
    with pytest.raises(ScenarioStoreError):
        store.delete("s1")


# --------------------------------------------------------------- lifecycle
def test_register_persists_and_survives_a_reload():
    register_scenario(_cfg(id="persisted-1", name="Persisted"))
    assert any(r["id"] == "persisted-1" for r in list_scenarios())

    # simulate a process restart: drop caches, rebind the engine
    _reset_custom_for_tests()
    reset_engine_for_tests()

    reloaded = get_scenario("persisted-1")
    assert reloaded.name == "Persisted"
    assert any(r["id"] == "persisted-1" and r["preset"] is False for r in list_scenarios())


def test_register_rejects_preset_ids():
    with pytest.raises(ValueError):
        register_scenario(_cfg(id="normal"))


def test_delete_custom_then_reload_is_gone():
    register_scenario(_cfg(id="temp-1"))
    delete_scenario("temp-1")

    _reset_custom_for_tests()
    reset_engine_for_tests()

    assert not any(r["id"] == "temp-1" for r in list_scenarios())
    with pytest.raises(KeyError):
        get_scenario("temp-1")


def test_delete_rejects_presets_and_unknown():
    with pytest.raises(ValueError):
        delete_scenario("rush_hour")
    with pytest.raises(KeyError):
        delete_scenario("never-registered")


def test_custom_scenario_actually_runs():
    """A saved custom scenario must be loadable into a real episode, not just stored."""
    from app.schemas.scenario import ScenarioConfig as SC
    from app.simulation.builtin.engine import BuiltinAdapter

    register_scenario(_cfg(id="runnable-1", demand={
        "weights": {"N": 0.4, "E": 0.1, "S": 0.4, "W": 0.1}, "arrivals_vph": 2000}))
    sc = get_scenario("runnable-1")
    assert isinstance(sc, SC)

    eng = BuiltinAdapter()
    eng.reset(sc, seed=1)
    for _ in range(20):
        eng.step(0.5)
    assert eng.get_state().sim_time == pytest.approx(10.0)
