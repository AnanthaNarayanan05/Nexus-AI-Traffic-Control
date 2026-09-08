"""Training + model-registry REST surface (spec §64-79, STEP 5).

    GET  /api/v1/training                  service status + current job + recent history
    POST /api/v1/training/runs             start a run (one at a time -> 409 if busy)
    GET  /api/v1/training/runs             finished runs (from on-disk run records)
    GET  /api/v1/training/runs/{run_id}    full run record (per-episode rows + reproducibility)
    GET  /api/v1/models                    model registry rows (filter: ?agent= &status=)
    GET  /api/v1/models/{model_id}         one registry row

Every number served here is a real training / evaluation measurement (spec §84). No
run is fabricated: the history list is exactly the `<run_id>.json` files on disk.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.models import StartTrainingRequest
from app.logging import get_logger
from app.persistence import ModelRegistry
from app.training.service import TrainingBusy, get_training_service

log = get_logger("API")

training_router = APIRouter(prefix="/api/v1", tags=["training"])


@training_router.get("/training")
def training_status(history: int = Query(default=20, ge=0, le=200)) -> dict:
    svc = get_training_service()
    out = svc.snapshot()
    if history:
        out["history"] = svc.history(history)
    return out


@training_router.post("/training/runs", status_code=202)
def training_start(body: StartTrainingRequest) -> dict:
    svc = get_training_service()
    try:
        return svc.start(
            agent=body.agent, episodes=body.episodes, scenario=body.scenario,
            seed=body.seed, checkpoint_every=body.checkpoint_every,
        )
    except TrainingBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@training_router.get("/training/runs")
def training_runs(limit: int = Query(default=50, ge=1, le=200)) -> dict:
    return {"runs": get_training_service().history(limit)}


@training_router.get("/training/runs/{run_id}")
def training_run_detail(run_id: str) -> dict:
    detail = get_training_service().run_detail(run_id)
    if detail is None:
        raise HTTPException(404, f"no training run '{run_id}'")
    return detail


@training_router.get("/models")
def models(agent: str | None = Query(default=None),
           status: str | None = Query(default=None)) -> dict:
    from app.training.manager import ACTIVE_AGENTS

    rows = ModelRegistry().list(agent=agent, status=status)
    # the three active agents (a2c, dqn, ppo); any other agent key is a stale row
    rows = [r for r in rows if r.get("agent") in ACTIVE_AGENTS]
    return {"models": rows}


@training_router.get("/models/{model_id}")
def model_detail(model_id: str) -> dict:
    row = ModelRegistry().get(model_id)
    if row is None:
        raise HTTPException(404, f"no model '{model_id}'")
    return row
