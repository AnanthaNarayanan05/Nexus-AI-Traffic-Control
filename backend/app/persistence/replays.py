"""`ReplayStore` - the write/read API over the `replays` table (spec §54-56; docs/replay.md).

A replay row is the frozen record of one run of the live decision loop: the ordered
`DecisionRecord` timeline, the events that fired, and the final episode metrics. The
`SimulationManager` builds the blob (it is the only writer); this store just persists it
and reads it back. Like `ScenarioStore` it is deliberately dumb - it trusts its caller.

`prune()` is the storage-management control (spec §90): keep the newest N, drop the rest.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.logging import get_logger
from app.persistence.db import init_db, session_scope
from app.persistence.models import ReplayRecord

log = get_logger("PERSISTENCE")


class ReplayStoreError(RuntimeError):
    """Replay-store precondition failed (unknown id, ...)."""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReplayStore:
    """Thin, synchronous facade. Safe to construct per call - it holds no state."""

    def __init__(self, *, ensure_schema: bool = True) -> None:
        if ensure_schema:
            init_db()

    # ------------------------------------------------------------------ writes
    def save(self, record: dict) -> dict:
        """Upsert one replay. `record` carries every column; `id` is required."""
        replay_id = str(record["id"])
        with session_scope() as s:
            row = s.get(ReplayRecord, replay_id)
            if row is None:
                row = ReplayRecord(id=replay_id)
                s.add(row)
            row.label = str(record.get("label", ""))
            row.created_at = str(record.get("created_at") or _utcnow_iso())
            row.scenario_id = str(record.get("scenario_id", ""))
            row.scenario_name = str(record.get("scenario_name", ""))
            row.seed = int(record.get("seed", 0))
            row.mode = str(record.get("mode", "AI"))
            row.model_modes = dict(record.get("model_modes") or {})
            row.config_digest = str(record.get("config_digest", ""))
            row.sim_duration_s = float(record.get("sim_duration_s", 0.0))
            row.decision_count = int(record.get("decision_count", 0))
            row.episode_complete = bool(record.get("episode_complete", False))
            row.timeline = list(record.get("timeline") or [])
            row.events = list(record.get("events") or [])
            row.episode_metrics = record.get("episode_metrics")
            s.flush()
            out = row.as_dict(full=False)
        log.info("replay saved", replay=replay_id, decisions=out["decision_count"],
                 complete=out["episode_complete"])
        return out

    def delete(self, replay_id: str) -> None:
        with session_scope() as s:
            row = s.get(ReplayRecord, replay_id)
            if row is None:
                raise ReplayStoreError(f"no replay {replay_id!r}")
            s.delete(row)
        log.info("replay deleted", replay=replay_id)

    def prune(self, *, keep: int) -> int:
        """Delete all but the newest `keep` replays. Returns the number removed."""
        keep = max(0, int(keep))
        stmt = select(ReplayRecord).order_by(ReplayRecord.created_at.desc())
        removed = 0
        with session_scope() as s:
            for row in s.scalars(stmt).all()[keep:]:
                s.delete(row)
                removed += 1
        if removed:
            log.info("replays pruned", removed=removed, kept=keep)
        return removed

    # ------------------------------------------------------------------ reads
    def get(self, replay_id: str) -> dict | None:
        with session_scope() as s:
            row = s.get(ReplayRecord, replay_id)
            return row.as_dict(full=True) if row else None

    def list(self, *, limit: int = 50) -> list[dict]:
        """Replay summaries (no timeline), newest first."""
        stmt = select(ReplayRecord).order_by(ReplayRecord.created_at.desc()).limit(int(limit))
        with session_scope() as s:
            return [r.as_dict(full=False) for r in s.scalars(stmt).all()]

    def count(self) -> int:
        with session_scope() as s:
            return len(s.scalars(select(ReplayRecord.id)).all())
