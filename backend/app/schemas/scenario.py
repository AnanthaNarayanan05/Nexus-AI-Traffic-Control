"""Scenario configuration (spec section 28)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.enums import Approach


class DemandProfile(BaseModel):
    """Per-approach demand weights + total arrival rate."""

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


class ScheduledChange(BaseModel):
    """A demand change that fires partway through an episode."""

    at_s: float
    profile: DemandProfile


class ScenarioConfig(BaseModel):
    id: str = "custom"
    name: str = "Custom scenario"
    description: str = ""

    demand: DemandProfile = Field(default_factory=DemandProfile)
    scheduled_changes: list[ScheduledChange] = Field(default_factory=list)

    emergency_probability_per_min: float = 0.0
    violation_probability_scale: float = 1.0
    accident_probability_per_min: float = 0.0

    blocked_lanes: list[dict] = Field(default_factory=list)  # [{"approach": "N", "lane": 2}]
    weather: str = "clear"
    time_of_day: str = "day"

    duration_s: float = 3600.0
    seed: int = 42
