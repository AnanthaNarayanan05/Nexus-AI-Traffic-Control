"""Experiment (Fixed-Time vs AI comparison) REST surface (spec §48-56, docs/experiments.md).

    GET  /api/v1/experiments               service status + current job + recent history
    POST /api/v1/experiments               start a comparison run (one at a time -> 409 if busy)
    GET  /api/v1/experiments/{id}          full record: per-controller aggregates + comparison
                                           blob + frozen reproducibility blob

Every number served here is a real evaluation-episode measurement (spec §84). An
experiment row exists only after a job has actually run.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.models import StartExperimentRequest
from app.logging import get_logger
from app.training.experiment_service import ExperimentBusy, get_experiment_service

log = get_logger("API")

experiment_router = APIRouter(prefix="/api/v1", tags=["experiments"])


@experiment_router.get("/experiments")
def experiments_status(history: int = Query(default=20, ge=0, le=200)) -> dict:
    svc = get_experiment_service()
    out = svc.snapshot()
    if history:
        out["history"] = svc.history(history)
    return out


@experiment_router.post("/experiments", status_code=202)
def experiments_start(body: StartExperimentRequest) -> dict:
    svc = get_experiment_service()
    try:
        return svc.start(
            name=body.name, scenario=body.scenario, controllers=body.controllers,
            seeds=body.seeds, models=body.models, episode_seconds=body.episode_seconds,
        )
    except ExperimentBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip('"')) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@experiment_router.get("/experiments/{experiment_id}")
def experiment_detail(experiment_id: str) -> dict:
    detail = get_experiment_service().detail(experiment_id)
    if detail is None:
        raise HTTPException(404, f"no experiment '{experiment_id}'")
    return detail
