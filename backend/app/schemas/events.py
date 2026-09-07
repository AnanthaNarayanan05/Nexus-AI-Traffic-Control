"""Event timeline + decision record contracts (spec sections 40, 87)."""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.coordination import CoordinationDecision
from app.schemas.enums import EventCategory, Severity
from app.schemas.metrics import MetricSnapshot
from app.schemas.safety import SafetyResult


class EventMessage(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    t: float  # sim time
    wall_t: float = Field(default_factory=time.time)
    category: EventCategory
    severity: Severity = Severity.INFO
    description: str
    meta: dict[str, Any] = Field(default_factory=dict)


class DecisionRecord(BaseModel):
    """Full record of one decision cycle (spec section 87) -> timeline, replay, history, experiments."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    t: float
    step: int
    state_summary: dict[str, Any]
    recommendations: dict[str, Any]  # agent -> AgentRecommendation dump
    coordination: CoordinationDecision
    safety: SafetyResult
    rewards: dict[str, float]  # agent -> total reward
    reward_breakdowns: dict[str, Any] = Field(default_factory=dict)
    metrics: MetricSnapshot
    applied_phase: str
