"""`ReplayStore` - the read/write API over the `replays` table (R9 P3; docs/replay.md).

The `_isolated_db` autouse fixture (tests/conftest.py) points NEXUS_DB_URL at a fresh
temp SQLite file per test, so every test starts with an empty `replays` table.
"""

from __future__ import annotations

import pytest

from app.persistence.replays import ReplayStore, ReplayStoreError


def _record(replay_id: str, *, decisions: int = 5, complete: bool = False, **over) -> dict:
    frames = [
        {"id": f"d{i}", "t": 6.0 * (i + 1), "step": 12 * (i + 1),
         "applied_phase": "NS", "rewards": {"a2c": 0.1 * i, "dqn": -0.2 * i}}
        for i in range(decisions)
    ]
    rec = dict(
        id=replay_id,
        label=f"Normal traffic · seed 42 · AI · {'episode' if complete else 'partial'}",
        scenario_id="normal", scenario_name="Normal traffic", seed=42, mode="AI",
        model_modes={"a2c": "untrained", "dqn": "untrained"},
        config_digest="cfgdigest0001",
        sim_duration_s=frames[-1]["t"] if frames else 0.0,
        decision_count=len(frames), episode_complete=complete,
        timeline=frames, events=[{"id": "e0", "t": 1.0, "category": "SYSTEM",
                                  "severity": "info", "description": "started"}],
        episode_metrics={"traffic.avg_waiting_s": 12.3} if complete else None,
    )
    rec.update(over)
    return rec


@pytest.fixture
def store() -> ReplayStore:
    return ReplayStore()


def test_save_then_get_roundtrips(store):
    store.save(_record("replay-1", decisions=4, complete=True))
    got = store.get("replay-1")
    assert got is not None
    assert got["scenario_id"] == "normal"
    assert got["seed"] == 42
    assert got["decision_count"] == 4
    assert got["episode_complete"] is True
    assert len(got["timeline"]) == 4
    assert got["timeline"][0]["t"] == pytest.approx(6.0)
    assert got["episode_metrics"] == {"traffic.avg_waiting_s": 12.3}
    assert got["events"][0]["description"] == "started"


def test_get_unknown_is_none(store):
    assert store.get("nope") is None


def test_save_is_an_upsert(store):
    store.save(_record("replay-1", decisions=3))
    store.save(_record("replay-1", decisions=9, complete=True, label="relabelled"))
    got = store.get("replay-1")
    assert got["decision_count"] == 9
    assert got["episode_complete"] is True
    assert got["label"] == "relabelled"
    assert store.count() == 1


def test_list_is_summary_only_and_newest_first(store):
    store.save(_record("replay-a", created_at="2026-09-08T10:00:00+00:00"))
    store.save(_record("replay-b", created_at="2026-09-08T12:00:00+00:00"))
    rows = store.list()
    assert [r["id"] for r in rows] == ["replay-b", "replay-a"]
    assert "timeline" not in rows[0]  # summaries never carry the (large) frame list
    assert "events" not in rows[0]


def test_delete_removes_and_missing_raises(store):
    store.save(_record("replay-1"))
    store.delete("replay-1")
    assert store.get("replay-1") is None
    with pytest.raises(ReplayStoreError):
        store.delete("replay-1")


def test_prune_keeps_the_newest_n(store):
    for i in range(6):
        store.save(_record(f"replay-{i}", created_at=f"2026-09-08T{10 + i:02d}:00:00+00:00"))
    removed = store.prune(keep=3)
    assert removed == 3
    assert store.count() == 3
    assert {r["id"] for r in store.list()} == {"replay-5", "replay-4", "replay-3"}
