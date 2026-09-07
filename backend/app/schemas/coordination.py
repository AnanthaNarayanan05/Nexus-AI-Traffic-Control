"""Coordination engine contracts (spec sections 20-21, docs/coordination.md)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.agents import AgentRecommendation
from app.schemas.enums import Phase


class LadderStep(BaseModel):
    rung: str  # safety | emergency | valid_phase | weighted_score
    outcome: str  # "short_circuit" | "override" | "filter" | "score" | "pass"
    detail: str


class PhaseScore(BaseModel):
    phase: Phase
    congestion: float = 0.0
    efficiency: float = 0.0
    throughput: float = 0.0
    stability: float = 0.0
    consensus_bonus: float = 0.0
    total: float = 0.0


class CoordinationDecision(BaseModel):
    candidate_phase: Phase
    winner: str  # a2c | dqn | ppo | consensus | constraint
    basis: str  # emergency_override | weighted_score | min_green_hold | transition_lock
    ladder_trace: list[LadderStep] = Field(default_factory=list)
    scores: list[PhaseScore] = Field(default_factory=list)
    recommendations: list[AgentRecommendation] = Field(default_factory=list)

    def explanation(self) -> str:
        return f"{self.winner} won via {self.basis} -> {self.candidate_phase.value}"
