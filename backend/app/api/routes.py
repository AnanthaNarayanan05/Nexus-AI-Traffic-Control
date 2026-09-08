"""REST surface (spec section 88, docs/system-flow.md section 3).

The simulation / scenario / agent / metrics endpoints live here; training, experiments,
replay and export have their own routers (`app/api/*_routes.py`). Anything still
unbuilt is left absent rather than stubbed with placeholder data - see docs/STATUS.md
(spec section 98).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.api.models import (
    DuplicateScenarioRequest,
    InjectRequest,
    LoadScenarioRequest,
    ManualRequest,
    ModelRequest,
    ModeRequest,
    ResetRequest,
    SpeedRequest,
    StepRequest,
)
from app.core.config import get_config, get_settings
from app.core.simulation_manager import get_manager
from app.scenarios import (
    PRESET_IDS,
    delete_scenario,
    get_scenario,
    list_scenarios,
    register_scenario,
)
from app.schemas.enums import AgentName
from app.schemas.scenario import ScenarioConfig

api_router = APIRouter(prefix="/api/v1")


def _dump(model: Any) -> Any:
    return model.model_dump(mode="json") if model is not None else None


# ----------------------------------------------------------------- system
@api_router.get("/health")
def health() -> dict:
    mgr = get_manager()
    return {"status": "ok", "adapter": mgr.adapter.name, "running": mgr.running,
            "sim_time": mgr.state().sim_time if mgr.state() else 0.0}


@api_router.get("/config")
def config() -> dict:
    cfg = get_config()
    settings = get_settings()
    return {
        "digest": cfg.digest,
        "env": settings.env,
        "adapter": settings.sim_adapter,
        "simulation": cfg.simulation,
        "geometry": cfg.geometry,
        "signals": {k: v for k, v in cfg.signals.items() if k != "phases"},
        "coordination": cfg.coordination,
        "reward": cfg.reward,
        "render": cfg.render,
    }


# ----------------------------------------------------------------- simulation
@api_router.get("/simulation/state")
def simulation_state() -> dict:
    mgr = get_manager()
    state = mgr.state()
    if state is None:
        raise HTTPException(503, "simulation not initialised")
    return _dump(state)


@api_router.get("/simulation/status")
def simulation_status() -> dict:
    return get_manager().status()


@api_router.post("/simulation/start")
def simulation_start() -> dict:
    return get_manager().start()


@api_router.post("/simulation/pause")
def simulation_pause() -> dict:
    return get_manager().pause()


@api_router.post("/simulation/reset")
def simulation_reset(body: ResetRequest) -> dict:
    try:
        return get_manager().reset(body.scenario_id, body.seed)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@api_router.post("/simulation/step")
def simulation_step(body: StepRequest) -> dict:
    return get_manager().step_once(body.ticks)


@api_router.post("/simulation/mode")
def simulation_mode(body: ModeRequest) -> dict:
    try:
        return get_manager().set_mode(body.mode)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@api_router.post("/simulation/speed")
def simulation_speed(body: SpeedRequest) -> dict:
    return get_manager().set_speed(body.speed)


@api_router.post("/simulation/model")
def simulation_model(body: ModelRequest) -> dict:
    try:
        return get_manager().set_model(body.agent, body.mode, body.version)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@api_router.post("/simulation/manual")
def simulation_manual(body: ManualRequest) -> dict:
    try:
        return get_manager().manual_action(body.action)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@api_router.post("/simulation/inject")
def simulation_inject(body: InjectRequest) -> dict:
    try:
        return get_manager().inject(body.event, body.args)
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


# ----------------------------------------------------------------- scenarios
@api_router.get("/scenarios")
def scenarios() -> dict:
    return {"scenarios": list_scenarios()}


@api_router.get("/scenarios/{scenario_id}")
def scenario_detail(scenario_id: str) -> dict:
    try:
        return _dump(get_scenario(scenario_id))
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@api_router.post("/scenarios")
def scenario_create(body: ScenarioConfig) -> dict:
    # Field / bound validation already happened when FastAPI parsed the body (422).
    try:
        return _dump(register_scenario(body))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@api_router.post("/scenarios/{scenario_id}/duplicate")
def scenario_duplicate(scenario_id: str, body: DuplicateScenarioRequest) -> dict:
    try:
        source = get_scenario(scenario_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    copy = source.model_copy(deep=True)
    copy.id = body.new_id
    copy.name = body.name or f"Copy of {source.name}"
    try:
        copy = ScenarioConfig.model_validate(copy.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        return _dump(register_scenario(copy))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@api_router.delete("/scenarios/{scenario_id}")
def scenario_delete(scenario_id: str) -> dict:
    if scenario_id in PRESET_IDS:
        raise HTTPException(409, f"'{scenario_id}' is a preset and cannot be deleted")
    try:
        delete_scenario(scenario_id)
    except KeyError as exc:
        raise HTTPException(404, f"unknown scenario '{scenario_id}'") from exc
    except ValueError as exc:  # defensive - preset guard already handled above
        raise HTTPException(409, str(exc)) from exc
    return {"deleted": scenario_id}


@api_router.post("/scenarios/load")
def scenario_load(body: LoadScenarioRequest) -> dict:
    mgr = get_manager()
    if body.config is not None:
        return mgr.load_scenario(body.config, body.seed)
    if body.id:
        try:
            return mgr.load_scenario(get_scenario(body.id), body.seed)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
    raise HTTPException(400, "provide either 'id' or 'config'")


# ----------------------------------------------------------------- agents
@api_router.get("/agents")
def agents() -> dict:
    mgr = get_manager()
    return {
        "agents": {n.value: _dump(a.status()) for n, a in mgr.agents.items()},
        "ownership": {
            "a2c": {"objective": "Emergency vehicle prioritization", "owner": "Anantha Narayanan A"},
            "dqn": {"objective": "Efficiency, fuel, emissions and safety", "owner": "Shaun Joseph Sabu"},
        },
    }


@api_router.get("/agents/{agent}")
def agent_inspector(agent: str) -> dict:
    mgr = get_manager()
    try:
        name = AgentName(agent)
    except ValueError as exc:
        raise HTTPException(404, f"unknown agent '{agent}'") from exc
    if name not in mgr.agents:
        raise HTTPException(404, f"agent '{agent}' is not in the active scope (A2C + DQN)")
    return mgr.agent_inspector(agent)


# ----------------------------------------------------------------- decisions
@api_router.get("/coordination/last")
def coordination_last() -> dict:
    mgr = get_manager()
    decision = mgr.latest_coordination()
    if decision is None:
        raise HTTPException(404, "no coordination decision yet")
    return {"coordination": _dump(decision), "safety": _dump(mgr.latest_safety())}


@api_router.get("/decisions")
def decisions(limit: int = Query(default=50, ge=1, le=400)) -> dict:
    return {"decisions": [_dump(d) for d in get_manager().decisions(limit)]}


@api_router.get("/safety/overrides")
def safety_overrides(limit: int = Query(default=50, ge=1, le=200)) -> dict:
    mgr = get_manager()
    return {
        "overrides": mgr.safety.recent_overrides(limit),
        "overrides_total": mgr.safety.overrides_total,
        "checks_total": mgr.safety.checks_total,
    }


# ----------------------------------------------------------------- metrics / events
@api_router.get("/metrics")
def metrics(dev: bool = Query(default=False), history: int = Query(default=0, ge=0, le=2000)) -> dict:
    mgr = get_manager()
    out: dict[str, Any] = {"current": _dump(mgr.latest_metrics())}
    if dev:
        out["dev"] = _dump(mgr.metrics.dev_metrics())
    if history:
        out["history"] = mgr.metrics.history(history)
    return out


@api_router.get("/events")
def events(after: int = Query(default=0, ge=0), limit: int = Query(default=200, ge=1, le=500)) -> dict:
    mgr = get_manager()
    return {"cursor": mgr.event_cursor(),
            "events": [_dump(e) for e in mgr.events_since(after, limit)]}
