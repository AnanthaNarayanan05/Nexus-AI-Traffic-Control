"""Export REST surface (spec §23, §64-79; docs/exports.md).

    GET /api/v1/export/experiments/{id}?format=csv|json   comparison run -> download
    GET /api/v1/export/replays/{id}?format=csv|json       decision timeline -> download

Every byte served here is derived from a record the persistence layer already holds - a
real evaluation or a real captured run. Nothing is synthesised (spec §84); an id that was
never produced 404s, and a run with no completed comparison / no timeline 409s rather
than emitting an empty file.

GET (not POST) so the browser can download straight from a link. `format` defaults to
`csv`; an unknown value is a 422 (FastAPI validates the `Literal`).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.api.exporters import (
    experiment_csv,
    replay_csv,
    safe_filename,
    to_json,
)
from app.logging import get_logger
from app.persistence import ExperimentStore, ReplayStore

log = get_logger("API")

export_router = APIRouter(prefix="/api/v1", tags=["export"])

_MEDIA = {"csv": "text/csv; charset=utf-8", "json": "application/json"}


def _download(body: str, fmt: str, stem: str) -> Response:
    return Response(
        content=body,
        media_type=_MEDIA[fmt],
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename(stem, fmt)}"'
        },
    )


@export_router.get("/export/experiments/{experiment_id}")
def export_experiment(
    experiment_id: str, format: Literal["csv", "json"] = "csv"
) -> Response:
    record = ExperimentStore().get(experiment_id)
    if record is None:
        raise HTTPException(404, f"no experiment '{experiment_id}'")
    if record.get("status") != "completed" or not record.get("comparison"):
        raise HTTPException(
            409, "experiment has no completed comparison to export"
        )
    body = to_json(record) if format == "json" else experiment_csv(record)
    log.info("experiment exported", experiment_id=experiment_id, format=format)
    return _download(body, format, experiment_id)


@export_router.get("/export/replays/{replay_id}")
def export_replay(
    replay_id: str, format: Literal["csv", "json"] = "csv"
) -> Response:
    record = ReplayStore().get(replay_id)
    if record is None:
        raise HTTPException(404, f"no replay '{replay_id}'")
    if format == "csv" and not record.get("timeline"):
        raise HTTPException(409, "replay has no decision timeline to export")
    body = to_json(record) if format == "json" else replay_csv(record)
    log.info("replay exported", replay_id=replay_id, format=format)
    return _download(body, format, replay_id)
