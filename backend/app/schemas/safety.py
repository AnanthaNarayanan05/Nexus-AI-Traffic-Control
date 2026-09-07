"""Safety layer contracts (spec section 22, docs/safety.md)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.enums import Phase, SafetyAction


class PhaseCommand(BaseModel):
    """A concrete instruction for the SignalController."""

    target_phase: Phase
    # If set, the controller is being asked to (re)start a bounded green.
    request_extend_s: float | None = None
    request_reduce: bool = False
    force_transition: bool = False
    source: str = "coordinator"  # coordinator | safety | fixed_time | manual

    def summary(self) -> str:
        bits = [self.target_phase.value]
        if self.request_extend_s:
            bits.append(f"+{self.request_extend_s:.0f}s")
        if self.request_reduce:
            bits.append("reduce")
        if self.force_transition:
            bits.append("transition")
        return " ".join(bits)


class SafetyResult(BaseModel):
    approved: bool
    command: PhaseCommand
    original: Phase
    action_taken: SafetyAction
    violated_rules: list[str] = Field(default_factory=list)
    reason: str = ""

    @property
    def was_override(self) -> bool:
        return self.action_taken != SafetyAction.APPLIED
