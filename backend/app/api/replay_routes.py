"""Replay REST surface (spec §54-56, §18-19; docs/replay.md).

    GET    /api/v1/replay                 list captured replays (summary, newest first)
    POST   /api/v1/replay/capture         freeze the current live run into a replay now
    GET    /api/v1/replay/{id}            full replay: the decision timeline + events
    GET    /api/v1/replay/{id}/at?t=      the decision frame at-or-before sim time t
    DELETE /api/v1/replay/{id}            drop one replay (storage management, spec §90)

A replay is the ordered list of real `DecisionRecord`s from one run of the live loop -
recommendations, coordination, safety, reward decomposition and metrics at every AI
decision. Nothing here is synthesised (spec §84); an id exists only after a run captured
one. Playback is client-side (`GET /replay/{id}` returns the whole timeline); `/at` is the
scripting/seek helper.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.simulation_manager import get_manager
from app.logging import get_logger
from app.persistence.replays import ReplayStore

log = get_logger("API")

replay_router = APIRouter(prefix="/api/v1", tags=["replay"])


@replay_router.get("/replay")
def replay_list(limit: int = Query(default=50, ge=1, le=200)) -> dict:
    return {"replays": ReplayStore().list(limit=limit)}


@replay_router.post("/replay/capture", status_code=201)
def replay_capture() -> dict:
    saved = get_manager().capture_replay()
    if saved is None:
        raise HTTPException(
            409,
            "nothing to capture - the current run has fewer than the minimum decisions",
        )
    return saved


@replay_router.get("/replay/{replay_id}")
def replay_detail(replay_id: str) -> dict:
    record = ReplayStore().get(replay_id)
    if record is None:
        raise HTTPException(404, f"no replay '{replay_id}'")
    return record


@replay_router.get("/replay/{replay_id}/at")
def replay_at(replay_id: str, t: float = Query(..., ge=0.0)) -> dict:
    record = ReplayStore().get(replay_id)
    if record is None:
        raise HTTPException(404, f"no replay '{replay_id}'")
    timeline: list[dict] = record.get("timeline") or []
    if not timeline:
        raise HTTPException(404, f"replay '{replay_id}' has no timeline")

    # last frame at or before t; before the first decision, clamp to frame 0
    index = 0
    for i, frame in enumerate(timeline):
        if float(frame.get("t", 0.0)) <= t:
            index = i
        else:
            break
    return {
        "replay_id": replay_id,
        "index": index,
        "total": len(timeline),
        "t": t,
        "prev_t": timeline[index - 1]["t"] if index > 0 else None,
        "next_t": timeline[index + 1]["t"] if index + 1 < len(timeline) else None,
        "frame": timeline[index],
    }


@replay_router.delete("/replay/{replay_id}")
def replay_delete(replay_id: str) -> dict:
    try:
        get_manager().delete_replay(replay_id)
    except KeyError as exc:
        raise HTTPException(404, f"no replay '{replay_id}'") from exc
    return {"deleted": replay_id}
