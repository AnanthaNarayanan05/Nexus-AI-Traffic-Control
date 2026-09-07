"""`ScenarioStore` - the write/read API over the `scenarios` table (R9 §8B).

Presets are code and never touch this table; only user-created / API-created scenarios
are persisted here so they survive a restart. A save is an upsert on the scenario id.
The store is deliberately dumb: it validates nothing about the blob it is handed - the
caller (`app.scenarios.presets.register_scenario`) has already built it from a validated
`ScenarioConfig`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.logging import get_logger
from app.persistence.db import init_db, session_scope
from app.persistence.models import ScenarioRecord

log = get_logger("PERSISTENCE")


class ScenarioStoreError(RuntimeError):
    """Scenario-store precondition failed (unknown id, ...)."""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScenarioStore:
    """Thin, synchronous facade. Safe to construct per call - it holds no state."""

    def __init__(self, *, ensure_schema: bool = True) -> None:
        if ensure_schema:
            init_db()

    # ------------------------------------------------------------------ writes
    def save(self, scenario_id: str, payload: dict) -> dict:
        """Upsert: insert a new row or replace the config blob of an existing one."""
        name = str(payload.get("name", "")) if isinstance(payload, dict) else ""
        with session_scope() as s:
            row = s.get(ScenarioRecord, scenario_id)
            if row is None:
                row = ScenarioRecord(
                    id=scenario_id, name=name, config=dict(payload),
                    created_at=_utcnow_iso(), updated_at=_utcnow_iso(),
                )
                s.add(row)
            else:
                row.name = name
                row.config = dict(payload)
                row.updated_at = _utcnow_iso()
            s.flush()
            out = row.as_dict()
        log.info("scenario saved", scenario=scenario_id, name=name)
        return out

    def delete(self, scenario_id: str) -> None:
        with session_scope() as s:
            row = s.get(ScenarioRecord, scenario_id)
            if row is None:
                raise ScenarioStoreError(f"no scenario {scenario_id!r}")
            s.delete(row)
        log.info("scenario deleted", scenario=scenario_id)

    # ------------------------------------------------------------------ reads
    def get(self, scenario_id: str) -> dict | None:
        """The stored `ScenarioConfig` blob, or ``None`` if this id was never saved."""
        with session_scope() as s:
            row = s.get(ScenarioRecord, scenario_id)
            return dict(row.config or {}) if row else None

    def list(self) -> list[dict]:
        """Every stored `ScenarioConfig` blob, newest first."""
        stmt = select(ScenarioRecord).order_by(ScenarioRecord.created_at.desc())
        with session_scope() as s:
            rows = s.scalars(stmt).all()
            return [dict(r.config or {}) for r in rows]
