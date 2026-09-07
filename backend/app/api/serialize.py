"""Wire formats for the WebSocket stream (spec section 71).

`simulation_state` is sent at `stream_hz`, so the vehicle list is transposed into flat
parallel arrays: at 400 vehicles that is roughly a third of the bytes of an array of
objects, and it maps straight onto the PixiJS sprite pool without per-frame allocation.
Nothing is dropped or rounded beyond the precision the renderer can show.
"""

from __future__ import annotations

from typing import Any

from app.schemas.simulation import SimulationState


def compact_vehicles(state: SimulationState) -> dict[str, list]:
    vs = state.vehicles
    return {
        "id": [v.id for v in vs],
        "type": [v.type.value for v in vs],
        "approach": [v.approach.value for v in vs],
        "lane": [v.lane for v in vs],
        "x": [v.x for v in vs],
        "y": [v.y for v in vs],
        "heading": [v.heading for v in vs],
        "speed": [v.speed_mps for v in vs],
        "wait": [v.wait_s for v in vs],
        "state": [v.state for v in vs],
        "emergency": [v.is_emergency for v in vs],
        "violator": [v.is_violator for v in vs],
    }


def compact_state(state: SimulationState) -> dict[str, Any]:
    return {
        "sim_time": state.sim_time,
        "step": state.step,
        "control_mode": state.control_mode.value,
        "signal": state.signal.model_dump(mode="json"),
        "approaches": {a.value: ap.model_dump(mode="json")
                       for a, ap in state.approaches.items()},
        "emergency": state.emergency.model_dump(mode="json"),
        "safety": state.safety.model_dump(mode="json"),
        "environment": state.environment.model_dump(mode="json"),
        "estimates": state.estimates.model_dump(mode="json"),
        "totals": {"vehicles": state.total_vehicles, "queue": state.total_queue},
        "vehicles": compact_vehicles(state),
    }


def agent_update_payload(decision: dict[str, Any]) -> dict[str, Any]:
    """Per-agent slice of a DecisionRecord - no extra inference is run.

    Full inspector payloads (features, action distributions, replay samples) are fetched
    on demand from `GET /api/v1/agents/{name}`; streaming them at 20 Hz would cost three
    forward passes per frame for data no one is looking at most of the time.
    """
    recs = decision.get("recommendations", {})
    rewards = decision.get("rewards", {})
    breakdowns = decision.get("reward_breakdowns", {})
    return {
        name: {
            "recommendation": rec,
            "reward_total": rewards.get(name),
            "reward_breakdown": breakdowns.get(name),
        }
        for name, rec in recs.items()
    }
