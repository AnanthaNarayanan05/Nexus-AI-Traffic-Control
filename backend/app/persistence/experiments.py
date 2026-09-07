"""`ExperimentStore` - the write/read API over the `experiments` table.

An experiment row is created ``running`` the moment a comparison job is accepted, then
completed in place with the per-controller aggregates, the comparison blob and the
frozen reproducibility blob - or marked ``failed`` with the error. Nothing is fabricated:
a row exists only after a real evaluation job has run (spec §84).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.logging import get_logger
from app.persistence.db import init_db, session_scope
from app.persistence.models import EXPERIMENT_STATUSES, ExperimentRecord

log = get_logger("REGISTRY")


class ExperimentStoreError(RuntimeError):
    """Experiment-store precondition failed (unknown id, bad status, ...)."""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExperimentStore:
    """Thin, synchronous facade. Safe to construct per call - it holds no state."""

    def __init__(self, *, ensure_schema: bool = True) -> None:
        if ensure_schema:
            init_db()

    # ------------------------------------------------------------------ writes
    def create(
        self,
        *,
        experiment_id: str,
        name: str,
        scenario: str,
        controllers: list[str],
        seeds: list[int],
        baseline: str,
        episode_seconds: float | None,
        reproducibility: dict,
    ) -> dict:
        with session_scope() as s:
            if s.get(ExperimentRecord, experiment_id) is not None:
                raise ExperimentStoreError(f"experiment {experiment_id!r} already exists")
            row = ExperimentRecord(
                id=experiment_id,
                name=name,
                created_at=_utcnow_iso(),
                scenario=scenario,
                controllers=list(controllers),
                seeds=list(seeds),
                episode_seconds=episode_seconds,
                baseline=baseline,
                reproducibility=reproducibility or {},
                status="running",
            )
            s.add(row)
            s.flush()
            out = row.as_dict()
        log.info("experiment created", experiment_id=experiment_id, scenario=scenario,
                 controllers=controllers)
        return out

    def complete(self, experiment_id: str, *, comparison: dict, results: list,
                 wall_time_s: float) -> dict:
        with session_scope() as s:
            row = s.get(ExperimentRecord, experiment_id)
            if row is None:
                raise ExperimentStoreError(f"no experiment {experiment_id!r}")
            row.comparison = comparison
            row.results = results
            row.wall_time_s = float(wall_time_s)
            row.finished_at = _utcnow_iso()
            row.status = "completed"
            s.flush()
            out = row.as_dict()
        log.info("experiment completed", experiment_id=experiment_id,
                 wall_time_s=round(wall_time_s, 1))
        return out

    def fail(self, experiment_id: str, *, error: str, wall_time_s: float) -> dict:
        with session_scope() as s:
            row = s.get(ExperimentRecord, experiment_id)
            if row is None:
                raise ExperimentStoreError(f"no experiment {experiment_id!r}")
            row.error = error
            row.wall_time_s = float(wall_time_s)
            row.finished_at = _utcnow_iso()
            row.status = "failed"
            s.flush()
            out = row.as_dict()
        log.error("experiment failed", experiment_id=experiment_id, error=error)
        return out

    def set_status(self, experiment_id: str, status: str) -> dict:
        if status not in EXPERIMENT_STATUSES:
            raise ExperimentStoreError(
                f"unknown status {status!r} (known: {EXPERIMENT_STATUSES})")
        with session_scope() as s:
            row = s.get(ExperimentRecord, experiment_id)
            if row is None:
                raise ExperimentStoreError(f"no experiment {experiment_id!r}")
            row.status = status
            s.flush()
            return row.as_dict()

    # ------------------------------------------------------------------ reads
    def get(self, experiment_id: str) -> dict | None:
        with session_scope() as s:
            row = s.get(ExperimentRecord, experiment_id)
            return row.as_dict(full=True) if row else None

    def list(self, *, limit: int = 50, scenario: str | None = None,
             status: str | None = None) -> list[dict]:
        stmt = select(ExperimentRecord).order_by(ExperimentRecord.created_at.desc())
        if scenario:
            stmt = stmt.where(ExperimentRecord.scenario == scenario)
        if status:
            stmt = stmt.where(ExperimentRecord.status == status)
        with session_scope() as s:
            rows = s.scalars(stmt.limit(int(limit))).all()
            return [r.as_dict(full=False) for r in rows]
