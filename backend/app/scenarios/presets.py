"""Scenario presets, built from `configs/config.yaml -> demand.profiles`.

Nothing here hard-codes traffic numbers: the per-approach weights and arrival rates
come from config (spec section 92). Scenario-level knobs (emergency rate, blockages,
violation scaling) are the scenario's own definition and are documented in
docs/scenarios.md.

R9 section 8A requires eight preset scenarios, each carrying an objective, an AI focus
and a difficulty rating for the presentation UI:

    normal          - NORMAL TRAFFIC       (baseline)
    rush_hour       - RUSH HOUR            (congestion)
    emergency_heavy - EMERGENCY RESPONSE   (A2C)
    uneven          - UNEQUAL DEMAND       (adaptive splitting)
    high_stop_go    - STOP-GO EFFICIENCY   (DQN fuel / emissions)
    incident        - ROAD BLOCKAGE        (re-routing under a closed lane)
    safety_violation- SAFETY / VIOLATION   (safety layer + DQN violation penalty)
    mixed_crisis    - MIXED CRISIS         (everything at once)

`surge_midway` is kept as a ninth, non-required preset - it is the one that exercises
`scheduled_changes`, and pre-R9 runs / registry rows may still reference it.
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_config
from app.logging import get_logger
from app.schemas.enums import Approach
from app.schemas.scenario import DemandProfile, ScenarioConfig, ScheduledChange

log = get_logger("SYSTEM")

# The eight R9 §8A required presets, in presentation order, then the extra.
REQUIRED_PRESET_IDS = (
    "normal", "rush_hour", "emergency_heavy", "uneven",
    "high_stop_go", "incident", "safety_violation", "mixed_crisis",
)
PRESET_IDS = (*REQUIRED_PRESET_IDS, "surge_midway")

# user-saved / API-created scenarios live here; ScenarioStore keeps them across restarts
_CUSTOM: dict[str, ScenarioConfig] = {}
_custom_loaded = False


def _profile(name: str) -> DemandProfile:
    """Build a DemandProfile from the named entry in config.demand.profiles."""
    cfg = get_config().demand
    raw: dict[str, Any] = dict(cfg.profiles[name])
    arrivals = float(raw.pop("arrivals_vph", cfg.default_arrivals_vph))
    weights = {Approach(k): float(v) for k, v in raw.items()}
    return DemandProfile(weights=weights, arrivals_vph=arrivals,
                         turn_split=dict(cfg.turn_split))


def _base(pid: str, name: str, description: str, profile: str, *,
          objective: str, ai_focus: str, difficulty: str, **kw: Any) -> ScenarioConfig:
    sim = get_config().simulation
    return ScenarioConfig(
        id=pid, name=name, description=description,
        objective=objective, ai_focus=ai_focus, difficulty=difficulty,
        demand=_profile(profile),
        duration_s=float(sim.episode_length_s),
        seed=int(sim.seed),
        **kw,
    )


def _build(pid: str) -> ScenarioConfig:
    if pid == "normal":
        return _base("normal", "Normal traffic",
                     "Baseline urban demand, light emergency traffic.", "normal",
                     objective="Establish the reference - queues and waits should stay low.",
                     ai_focus="Both agents; the control case for every comparison.",
                     difficulty="easy",
                     emergency_probability_per_min=0.25)
    if pid == "rush_hour":
        return _base("rush_hour", "Rush hour",
                     "Heavy, north-dominant demand - the congestion stress case (PPT slide 21).",
                     "rush_hour",
                     objective="Keep the intersection from locking up under sustained overload.",
                     ai_focus="DQN throughput / waiting; coordination under saturation.",
                     difficulty="hard",
                     emergency_probability_per_min=0.4)
    if pid == "emergency_heavy":
        return _base("emergency_heavy", "Emergency response",
                     "Normal demand with frequent emergency vehicles - the A2C stress case.",
                     "normal",
                     objective="Clear every emergency vehicle fast without wrecking normal flow.",
                     ai_focus="A2C emergency prioritization; emergency wait / delay metrics.",
                     difficulty="hard",
                     emergency_probability_per_min=3.0)
    if pid == "uneven":
        return _base("uneven", "Unequal demand",
                     "Strongly asymmetric arrivals; tests adaptive phase splitting.", "uneven",
                     objective="Give green time where the cars actually are, not a fixed split.",
                     ai_focus="DQN / coordination adaptive phase splitting.",
                     difficulty="moderate",
                     emergency_probability_per_min=0.25)
    if pid == "high_stop_go":
        return _base("high_stop_go", "Stop-go efficiency",
                     "Dense, evenly-loaded arrivals producing repeated stops - the fuel/emission "
                     "stress case.", "high_stop_go",
                     objective="Cut stop-and-go cycling; smoother flow means less fuel and CO2.",
                     ai_focus="DQN fuel / CO2 / stops-per-vehicle.",
                     difficulty="moderate",
                     emergency_probability_per_min=0.25, violation_probability_scale=1.5)
    if pid == "incident":
        return _base("incident", "Road blockage",
                     "A blocked east-bound lane forces re-distribution across the remaining lanes.",
                     "normal",
                     objective="Absorb a closed lane without the approach backing up for good.",
                     ai_focus="Coordination / DQN queue balancing around a bottleneck.",
                     difficulty="hard",
                     emergency_probability_per_min=0.5,
                     blocked_lanes=[{"approach": "E", "lane": 1}],
                     accident_probability_per_min=0.0)
    if pid == "safety_violation":
        return _base("safety_violation", "Safety / violation",
                     "Heavy, balanced demand with elevated red-running pressure - the case where "
                     "the authoritative safety layer earns its keep.", "safety_stress",
                     objective="Zero red-light violations and unsafe transitions, whatever the AI asks for.",
                     ai_focus="Safety constraint layer (authoritative); DQN violation penalty.",
                     difficulty="hard",
                     emergency_probability_per_min=0.3,
                     violation_probability_scale=2.5,
                     accident_probability_per_min=0.15)
    if pid == "mixed_crisis":
        sc = _base("mixed_crisis", "Mixed crisis",
                   "Very heavy demand, frequent emergencies, a blocked lane and a mid-episode "
                   "demand spike - every stressor at once.", "mixed_crisis",
                   objective="Hold it together when nothing is nominal - the demo finale.",
                   ai_focus="All three: A2C emergencies, DQN efficiency, safety layer.",
                   difficulty="extreme",
                   emergency_probability_per_min=2.0,
                   violation_probability_scale=1.5,
                   accident_probability_per_min=0.2,
                   blocked_lanes=[{"approach": "S", "lane": 1}])
        sc.scheduled_changes = [
            ScheduledChange(at_s=sc.duration_s / 2.0, profile=_profile("rush_hour")),
        ]
        return sc
    if pid == "surge_midway":
        sc = _base("surge_midway", "Mid-episode surge",
                   "Normal demand that switches to rush-hour demand halfway through the episode.",
                   "normal",
                   objective="React to a step change in demand instead of a tuned fixed cycle.",
                   ai_focus="DQN / coordination adapting to a regime change.",
                   difficulty="moderate",
                   emergency_probability_per_min=0.3)
        sc.scheduled_changes = [ScheduledChange(at_s=sc.duration_s / 2.0, profile=_profile("rush_hour"))]
        return sc
    raise KeyError(pid)


def _load_custom() -> None:
    """Populate `_CUSTOM` from the persistent store on first use (lazy - avoids a DB
    hit at import time and keeps the tests' per-test SQLite isolation intact)."""
    global _custom_loaded
    if _custom_loaded:
        return
    _custom_loaded = True
    try:
        from app.persistence.scenarios import ScenarioStore

        for payload in ScenarioStore().list():
            try:
                sc = ScenarioConfig.model_validate(payload)
            except Exception as exc:  # noqa: BLE001 - a bad stored row must not break startup
                log.error("skipping unreadable stored scenario", error=str(exc))
                continue
            if sc.id not in PRESET_IDS:
                _CUSTOM[sc.id] = sc
    except Exception as exc:  # noqa: BLE001 - persistence is optional; presets still work
        log.error("could not load custom scenarios", error=str(exc))


def _summary(sc: ScenarioConfig, *, preset: bool) -> dict[str, Any]:
    return {
        "id": sc.id, "name": sc.name, "description": sc.description, "preset": preset,
        "objective": sc.objective, "ai_focus": sc.ai_focus, "difficulty": sc.difficulty,
        "arrivals_vph": sc.demand.arrivals_vph,
        "weights": {a.value: round(w, 3) for a, w in sc.demand.normalised().items()},
        "emergency_probability_per_min": sc.emergency_probability_per_min,
        "violation_probability_scale": sc.violation_probability_scale,
        "blocked_lanes": list(sc.blocked_lanes),
        "scheduled_changes": len(sc.scheduled_changes),
        "duration_s": sc.duration_s,
    }


def get_scenario(pid: str) -> ScenarioConfig:
    _load_custom()
    if pid in _CUSTOM:
        return _CUSTOM[pid].model_copy(deep=True)
    if pid in PRESET_IDS:
        return _build(pid)
    raise KeyError(f"unknown scenario '{pid}' (known: {sorted(set(PRESET_IDS) | set(_CUSTOM))})")


def list_scenarios() -> list[dict[str, Any]]:
    _load_custom()
    out = [_summary(_build(pid), preset=True) for pid in PRESET_IDS]
    out.extend(_summary(sc, preset=False) for sc in _CUSTOM.values())
    return out


def register_scenario(scenario: ScenarioConfig, *, persist: bool = True) -> ScenarioConfig:
    _load_custom()
    if scenario.id in PRESET_IDS:
        raise ValueError(f"'{scenario.id}' is a preset id and cannot be overwritten")
    _CUSTOM[scenario.id] = scenario
    if persist:
        try:
            from app.persistence.scenarios import ScenarioStore

            ScenarioStore().save(scenario.id, scenario.model_dump(mode="json"))
        except Exception as exc:  # noqa: BLE001 - keep the in-process copy even if the DB write fails
            log.error("scenario not persisted", scenario=scenario.id, error=str(exc))
    log.info("scenario registered", scenario=scenario.id, name=scenario.name)
    return scenario


def delete_scenario(pid: str) -> None:
    _load_custom()
    if pid in PRESET_IDS:
        raise ValueError(f"'{pid}' is a preset and cannot be deleted")
    if pid not in _CUSTOM:
        raise KeyError(pid)
    del _CUSTOM[pid]
    try:
        from app.persistence.scenarios import ScenarioStore

        ScenarioStore().delete(pid)
    except Exception as exc:  # noqa: BLE001
        log.error("scenario delete not persisted", scenario=pid, error=str(exc))
    log.info("scenario deleted", scenario=pid)


def _reset_custom_for_tests() -> None:
    global _custom_loaded
    _CUSTOM.clear()
    _custom_loaded = False
