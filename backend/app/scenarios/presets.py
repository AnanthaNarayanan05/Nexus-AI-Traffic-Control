"""Scenario presets, built from `configs/config.yaml -> demand.profiles`.

Nothing here hard-codes traffic numbers: the per-approach weights and arrival rates
come from config (spec section 92). Scenario-level knobs (emergency rate, blockages,
violation scaling) are the scenario's own definition and are documented in
docs/experiments.md.
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_config
from app.logging import get_logger
from app.schemas.enums import Approach
from app.schemas.scenario import DemandProfile, ScenarioConfig, ScheduledChange

log = get_logger("SYSTEM")

PRESET_IDS = (
    "normal", "rush_hour", "uneven", "high_stop_go",
    "emergency_heavy", "incident", "surge_midway",
)

# user-saved / API-created scenarios live here for the process lifetime
_CUSTOM: dict[str, ScenarioConfig] = {}


def _profile(name: str) -> DemandProfile:
    """Build a DemandProfile from the named entry in config.demand.profiles."""
    cfg = get_config().demand
    raw: dict[str, Any] = dict(cfg.profiles[name])
    arrivals = float(raw.pop("arrivals_vph", cfg.default_arrivals_vph))
    weights = {Approach(k): float(v) for k, v in raw.items()}
    return DemandProfile(weights=weights, arrivals_vph=arrivals,
                         turn_split=dict(cfg.turn_split))


def _base(pid: str, name: str, description: str, profile: str, **kw: Any) -> ScenarioConfig:
    sim = get_config().simulation
    return ScenarioConfig(
        id=pid, name=name, description=description,
        demand=_profile(profile),
        duration_s=float(sim.episode_length_s),
        seed=int(sim.seed),
        **kw,
    )


def _build(pid: str) -> ScenarioConfig:
    if pid == "normal":
        return _base("normal", "Normal flow",
                     "Baseline urban demand, light emergency traffic.", "normal",
                     emergency_probability_per_min=0.25)
    if pid == "rush_hour":
        return _base("rush_hour", "Rush hour",
                     "Heavy, north-dominant demand - the congestion stress case (PPT slide 21).",
                     "rush_hour", emergency_probability_per_min=0.4)
    if pid == "uneven":
        return _base("uneven", "Uneven demand",
                     "Strongly asymmetric arrivals; tests adaptive phase splitting.", "uneven",
                     emergency_probability_per_min=0.25)
    if pid == "high_stop_go":
        return _base("high_stop_go", "High stop-and-go",
                     "Dense, evenly-loaded arrivals producing repeated stops - the fuel/emission "
                     "stress case.", "high_stop_go",
                     emergency_probability_per_min=0.25, violation_probability_scale=1.5)
    if pid == "emergency_heavy":
        return _base("emergency_heavy", "Emergency heavy",
                     "Normal demand with frequent emergency vehicles - the A2C stress case.",
                     "normal", emergency_probability_per_min=3.0)
    if pid == "incident":
        return _base("incident", "Lane incident",
                     "A blocked east-bound lane forces re-distribution across the remaining lanes.",
                     "normal", emergency_probability_per_min=0.5,
                     blocked_lanes=[{"approach": "E", "lane": 1}],
                     accident_probability_per_min=0.0)
    if pid == "surge_midway":
        sc = _base("surge_midway", "Mid-episode surge",
                   "Normal demand that switches to rush-hour demand halfway through the episode.",
                   "normal", emergency_probability_per_min=0.3)
        sc.scheduled_changes = [ScheduledChange(at_s=sc.duration_s / 2.0, profile=_profile("rush_hour"))]
        return sc
    raise KeyError(pid)


def get_scenario(pid: str) -> ScenarioConfig:
    if pid in _CUSTOM:
        return _CUSTOM[pid].model_copy(deep=True)
    if pid in PRESET_IDS:
        return _build(pid)
    raise KeyError(f"unknown scenario '{pid}' (known: {sorted(set(PRESET_IDS) | set(_CUSTOM))})")


def list_scenarios() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pid in PRESET_IDS:
        sc = _build(pid)
        out.append({
            "id": sc.id, "name": sc.name, "description": sc.description, "preset": True,
            "arrivals_vph": sc.demand.arrivals_vph,
            "weights": {a.value: round(w, 3) for a, w in sc.demand.normalised().items()},
            "emergency_probability_per_min": sc.emergency_probability_per_min,
            "duration_s": sc.duration_s,
        })
    for sc in _CUSTOM.values():
        out.append({
            "id": sc.id, "name": sc.name, "description": sc.description, "preset": False,
            "arrivals_vph": sc.demand.arrivals_vph,
            "weights": {a.value: round(w, 3) for a, w in sc.demand.normalised().items()},
            "emergency_probability_per_min": sc.emergency_probability_per_min,
            "duration_s": sc.duration_s,
        })
    return out


def register_scenario(scenario: ScenarioConfig) -> ScenarioConfig:
    if scenario.id in PRESET_IDS:
        raise ValueError(f"'{scenario.id}' is a preset id and cannot be overwritten")
    _CUSTOM[scenario.id] = scenario
    log.info("scenario registered", scenario=scenario.id, name=scenario.name)
    return scenario
