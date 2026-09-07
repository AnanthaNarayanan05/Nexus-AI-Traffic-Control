"""Agent recommendation + inspector contracts (spec sections 20, 41-43)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.enums import AgentName, Phase


class LabelledFeature(BaseModel):
    name: str
    value: float
    group: str


class RewardComponent(BaseModel):
    name: str
    raw: float
    weight: float
    contribution: float  # raw * weight (signed)


class RewardBreakdown(BaseModel):
    components: list[RewardComponent] = Field(default_factory=list)
    total: float = 0.0

    @classmethod
    def from_components(cls, components: list[RewardComponent]) -> "RewardBreakdown":
        return cls(components=components, total=sum(c.contribution for c in components))


class AgentRecommendation(BaseModel):
    """What each agent hands to the coordinator (spec section 20)."""

    agent: AgentName
    action_index: int
    action_name: str
    target_phase: Phase
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    priority: float = Field(ge=0.0, le=1.0)
    reason: str
    relevant_state: dict[str, float] = Field(default_factory=dict)

    # extra diagnostics carried for the UI (never fabricated)
    action_distribution: list[float] = Field(default_factory=list)  # policy probs OR normalised Q
    value_estimate: float | None = None


class AgentStatus(BaseModel):
    agent: AgentName
    model_version: str
    trained_episodes: int
    is_trained: bool
    device: str
    last_action: str | None = None
    last_reward: float | None = None
    inference_latency_ms: float | None = None


class AgentInspectorPayload(BaseModel):
    agent: AgentName
    status: AgentStatus
    features: list[LabelledFeature]
    action_distribution: list[float]
    action_labels: list[str]
    selected_action: str
    value_estimate: float | None = None
    advantage: float | None = None
    reward: RewardBreakdown
    reward_history: list[float] = Field(default_factory=list)
    decision_history: list[dict[str, Any]] = Field(default_factory=list)
    training: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)  # e.g. epsilon, replay size, queue pressure
