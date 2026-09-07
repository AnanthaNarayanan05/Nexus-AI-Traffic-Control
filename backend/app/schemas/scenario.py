"""Scenario configuration (spec section 28, R9 section 8).

Preset scenarios are built in `app.scenarios.presets`; custom scenarios come in over the
API as this model. Every user-supplied field is bounded here (R9 §8B: "validation ... a
human-readable preview"). Two rules that matter for safety:

  * `model_config` forbids unknown fields, so a request can never smuggle in a knob that
    a future version might read - in particular nothing that could disable the
    authoritative safety layer (R9 §113; the safety layer has no scenario-level switch).
  * The bounds below are hard caps, not suggestions: an out-of-range value is a 422, not
    a clamp, so what the user asked for is always exactly what runs.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.enums import Approach

Difficulty = Literal["easy", "moderate", "hard", "extreme"]

# --- hard bounds on user-supplied numbers --------------------------------------
MAX_ARRIVALS_VPH = 12000.0        # ~10x nominal; past this the microsim just saturates
MIN_DURATION_S = 60.0
MAX_DURATION_S = 14400.0          # four simulated hours
MAX_EMERGENCY_PER_MIN = 60.0      # one per simulated second is already absurd
MAX_ACCIDENT_PER_MIN = 60.0
MAX_VIOLATION_SCALE = 20.0
LANES_PER_APPROACH = 3            # mirrors configs/config.yaml -> geometry (lane ids 0..2)

_WEATHER = {"clear", "rain", "fog", "snow", "storm"}
_TIME_OF_DAY = {"day", "night", "dawn", "dusk"}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class DemandProfile(BaseModel):
    """Per-approach demand weights + total arrival rate."""

    model_config = ConfigDict(extra="forbid")

    weights: dict[Approach, float] = Field(
        default_factory=lambda: {Approach.N: 0.25, Approach.E: 0.25, Approach.S: 0.25, Approach.W: 0.25}
    )
    arrivals_vph: float = 1600.0
    turn_split: dict[str, float] = Field(
        default_factory=lambda: {"left": 0.2, "through": 0.6, "right": 0.2}
    )

    def normalised(self) -> dict[Approach, float]:
        total = sum(self.weights.values()) or 1.0
        return {a: w / total for a, w in self.weights.items()}

    @field_validator("weights")
    @classmethod
    def _weights_sane(cls, v: dict[Approach, float]) -> dict[Approach, float]:
        if any(w < 0 for w in v.values()):
            raise ValueError("demand weights must be non-negative")
        if sum(v.values()) <= 0:
            raise ValueError("at least one demand weight must be positive")
        return v

    @field_validator("arrivals_vph")
    @classmethod
    def _arrivals_sane(cls, v: float) -> float:
        if not 0 < v <= MAX_ARRIVALS_VPH:
            raise ValueError(f"arrivals_vph must be in (0, {MAX_ARRIVALS_VPH:g}]")
        return v

    @field_validator("turn_split")
    @classmethod
    def _turn_split_sane(cls, v: dict[str, float]) -> dict[str, float]:
        if any(x < 0 for x in v.values()):
            raise ValueError("turn_split fractions must be non-negative")
        if sum(v.values()) <= 0:
            raise ValueError("turn_split must have a positive total")
        return v


class ScheduledChange(BaseModel):
    """A demand change that fires partway through an episode."""

    model_config = ConfigDict(extra="forbid")

    at_s: float = Field(ge=0.0)
    profile: DemandProfile


class ScenarioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = "custom"
    name: str = Field(default="Custom scenario", min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)

    # R9 §8A presentation metadata - display only, never touches the simulation.
    objective: str = Field(default="", max_length=500)     # what a viewer should watch for
    ai_focus: str = Field(default="", max_length=500)      # which agent / metric family this exercises
    difficulty: Difficulty = "moderate"

    demand: DemandProfile = Field(default_factory=DemandProfile)
    scheduled_changes: list[ScheduledChange] = Field(default_factory=list)

    emergency_probability_per_min: float = Field(default=0.0, ge=0.0, le=MAX_EMERGENCY_PER_MIN)
    violation_probability_scale: float = Field(default=1.0, ge=0.0, le=MAX_VIOLATION_SCALE)
    accident_probability_per_min: float = Field(default=0.0, ge=0.0, le=MAX_ACCIDENT_PER_MIN)

    blocked_lanes: list[dict] = Field(default_factory=list)  # [{"approach": "N", "lane": 2}]
    weather: str = "clear"
    time_of_day: str = "day"

    duration_s: float = Field(default=3600.0, ge=MIN_DURATION_S, le=MAX_DURATION_S)
    seed: int = Field(default=42, ge=0)

    @field_validator("id")
    @classmethod
    def _id_is_slug(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError(
                "id must be a slug: a letter or digit followed by letters, digits, "
                "'-' or '_' (max 64 chars)")
        return v

    @field_validator("weather")
    @classmethod
    def _weather_known(cls, v: str) -> str:
        if v not in _WEATHER:
            raise ValueError(f"weather must be one of {sorted(_WEATHER)}")
        return v

    @field_validator("time_of_day")
    @classmethod
    def _time_of_day_known(cls, v: str) -> str:
        if v not in _TIME_OF_DAY:
            raise ValueError(f"time_of_day must be one of {sorted(_TIME_OF_DAY)}")
        return v

    @field_validator("blocked_lanes")
    @classmethod
    def _blocked_lanes_valid(cls, v: list[dict]) -> list[dict]:
        seen: set[tuple[str, int]] = set()
        per_approach: dict[str, int] = {}
        for spec in v:
            if not isinstance(spec, dict) or set(spec) != {"approach", "lane"}:
                raise ValueError('each blocked lane must be {"approach": "N|E|S|W", "lane": int}')
            try:
                approach = Approach(spec["approach"]).value
            except ValueError as exc:
                raise ValueError(f"blocked lane approach {spec['approach']!r} is not N/E/S/W") from exc
            lane = spec["lane"]
            if not isinstance(lane, int) or isinstance(lane, bool) or not 0 <= lane < LANES_PER_APPROACH:
                raise ValueError(f"blocked lane index must be an int in [0, {LANES_PER_APPROACH - 1}]")
            key = (approach, lane)
            if key in seen:
                raise ValueError(f"blocked lane {key} listed twice")
            seen.add(key)
            per_approach[approach] = per_approach.get(approach, 0) + 1
        for approach, n in per_approach.items():
            if n >= LANES_PER_APPROACH:
                raise ValueError(
                    f"approach {approach} would have every lane blocked; leave at least one open")
        return [{"approach": Approach(s["approach"]).value, "lane": int(s["lane"])} for s in v]

    @model_validator(mode="after")
    def _scheduled_changes_within_episode(self) -> ScenarioConfig:
        for change in self.scheduled_changes:
            if change.at_s >= self.duration_s:
                raise ValueError(
                    f"scheduled change at {change.at_s}s is at or past the episode end "
                    f"({self.duration_s}s)")
        return self
