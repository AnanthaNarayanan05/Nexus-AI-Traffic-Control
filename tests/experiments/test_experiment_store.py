"""`ExperimentStore` - the queryable index over comparison runs (R9 P1).

The `_isolated_db` autouse fixture (tests/conftest.py) points NEXUS_DB_URL at a fresh
temp SQLite file per test, so every test starts with an empty `experiments` table.
"""

from __future__ import annotations

import pytest

from app.persistence import ExperimentStore, ExperimentStoreError


@pytest.fixture
def store() -> ExperimentStore:
    return ExperimentStore()


def _create(store: ExperimentStore, eid: str = "exp-1", **over) -> dict:
    kw = dict(
        experiment_id=eid, name="normal · fixed_time vs a2c", scenario="normal",
        controllers=["fixed_time", "a2c"], seeds=[1, 2, 3], baseline="fixed_time",
        episode_seconds=180.0, reproducibility={"config_digest": "abc", "seeds": [1, 2, 3]},
    )
    kw.update(over)
    return store.create(**kw)


def test_create_is_running_and_carries_the_repro_blob(store):
    row = _create(store)
    assert row["status"] == "running"
    assert row["reproducibility"]["config_digest"] == "abc"
    assert row["comparison"] is None
    assert store.get("exp-1")["seeds"] == [1, 2, 3]


def test_duplicate_id_is_rejected(store):
    _create(store)
    with pytest.raises(ExperimentStoreError):
        _create(store)


def test_complete_writes_results_in_place(store):
    _create(store)
    row = store.complete("exp-1", comparison={"baseline": "fixed_time", "metrics": {}},
                         results=[{"label": "fixed_time"}], wall_time_s=12.3)
    assert row["status"] == "completed"
    assert row["comparison"]["baseline"] == "fixed_time"
    assert row["wall_time_s"] == 12.3
    assert row["finished_at"] is not None


def test_fail_records_the_error(store):
    _create(store)
    row = store.fail("exp-1", error="ValueError: boom", wall_time_s=1.0)
    assert row["status"] == "failed"
    assert "boom" in row["error"]


def test_list_is_newest_first_and_summary_only(store):
    _create(store, eid="exp-1")
    _create(store, eid="exp-2")
    store.complete("exp-2", comparison={"x": 1}, results=[], wall_time_s=1.0)
    rows = store.list()
    assert [r["id"] for r in rows] == ["exp-2", "exp-1"]
    assert "comparison" not in rows[0]  # list payload is summary-only


def test_complete_unknown_experiment_raises(store):
    with pytest.raises(ExperimentStoreError):
        store.complete("exp-nope", comparison={}, results=[], wall_time_s=0.0)
