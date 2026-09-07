"""Request bodies for the REST surface."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.scenario import ScenarioConfig


class ResetRequest(BaseModel):
    scenario_id: str | None = None
    seed: int | None = None


class ModeRequest(BaseModel):
    mode: str = Field(description="AI | FIXED_TIME | MANUAL")


class SpeedRequest(BaseModel):
    speed: float = Field(ge=0.1, le=20.0)


class ManualRequest(BaseModel):
    action: str


class InjectRequest(BaseModel):
    event: str = Field(description="spawn_emergency | traffic_surge | block_lane | "
                                   "unblock_lane | create_violation | incident")
    args: dict[str, Any] = Field(default_factory=dict)


class StepRequest(BaseModel):
    ticks: int = Field(default=1, ge=1, le=2000)


class LoadScenarioRequest(BaseModel):
    id: str | None = None
    config: ScenarioConfig | None = None
    seed: int | None = None


class StartTrainingRequest(BaseModel):
    agent: str = Field(description="a2c | dqn | ppo")
    episodes: int = Field(ge=1, le=1000)
    scenario: str | None = Field(default=None, description="preset id; default = agent's own stress scenario")
    seed: int | None = None
    checkpoint_every: int = Field(default=25, ge=1, le=1000)
