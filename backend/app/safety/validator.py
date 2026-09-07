"""SafetyValidator - the authoritative final check (spec sections 22, 113).

Given the coordinator's proposed `PhaseCommand`, it returns a `SafetyResult` whose
`command` is what the `SignalController` will actually execute this tick. Every result
with `action_taken != APPLIED` is logged (component = SAFETY) and kept in a bounded
history for `GET /api/v1/safety/overrides` and the Safety inspector.
"""

from __future__ import annotations

from collections import deque

from app.logging import get_logger
from app.safety.rules import RULES, TimingCfg
from app.schemas.enums import SafetyAction
from app.schemas.safety import PhaseCommand, SafetyResult
from app.schemas.simulation import SimulationState

log = get_logger("SAFETY")


class SafetyValidator:
    def __init__(self, history: int = 200) -> None:
        self._timing = TimingCfg.from_config()
        self._history: deque[dict] = deque(maxlen=history)
        self._overrides_total = 0
        self._checks_total = 0

    def validate(self, command: PhaseCommand, state: SimulationState) -> SafetyResult:
        self._checks_total += 1
        for rule in RULES:
            result = rule(command, state, self._timing)
            if result is not None:
                self._finalise(result, state)
                return result

        # nothing fired -> the command is admissible as-is
        approved = SafetyResult(
            approved=True,
            command=PhaseCommand(
                target_phase=command.target_phase,
                request_extend_s=command.request_extend_s,
                request_reduce=command.request_reduce,
                force_transition=command.force_transition or (
                    command.target_phase != state.signal.served_phase),
                source=command.source,
            ),
            original=command.target_phase,
            action_taken=SafetyAction.APPLIED,
            reason=f"Approved {command.summary()}.",
        )
        self._finalise(approved, state)
        return approved

    # ------------------------------------------------------------------ history
    def _finalise(self, result: SafetyResult, state: SimulationState) -> None:
        if result.was_override:
            self._overrides_total += 1
            entry = {
                "t": round(state.sim_time, 1),
                "step": state.step,
                "action_taken": result.action_taken.value,
                "original": result.original.value,
                "command": result.command.summary(),
                "violated_rules": list(result.violated_rules),
                "reason": result.reason,
            }
            self._history.append(entry)
            log.warning("safety override", **entry)

    @property
    def overrides_total(self) -> int:
        return self._overrides_total

    @property
    def checks_total(self) -> int:
        return self._checks_total

    def recent_overrides(self, limit: int = 50) -> list[dict]:
        items = list(self._history)
        return items[-limit:][::-1]

    def reset(self) -> None:
        self._history.clear()
        self._overrides_total = 0
        self._checks_total = 0
