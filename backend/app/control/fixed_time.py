"""Fixed-time baseline controller (spec section 49, PPT slide 21).

The comparison baseline the AI controller is measured against. It is a plain cyclic
schedule read from `configs/config.yaml -> fixed_time.schedule`; it has no state beyond
the schedule itself, so a run is reproducible from (scenario, seed) alone.

Its output still goes through the safety layer - safety is authoritative in every
control mode (spec section 113).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_config
from app.schemas.enums import Phase
from app.schemas.safety import PhaseCommand
from app.schemas.simulation import SimulationState


@dataclass(frozen=True)
class _Slot:
    phase: Phase
    green_s: float


class FixedTimeController:
    """Cyclic baseline. `decide(state)` is a pure function of the schedule + state."""

    source = "fixed_time"

    def __init__(self) -> None:
        raw = get_config().fixed_time.schedule
        self.schedule: tuple[_Slot, ...] = tuple(
            _Slot(phase=Phase(s["phase"]), green_s=float(s["green_s"])) for s in raw
        )
        if not self.schedule:
            raise ValueError("fixed_time.schedule is empty in config.yaml")

    @property
    def cycle_s(self) -> float:
        return sum(s.green_s for s in self.schedule)

    def _slot_index(self, phase: Phase) -> int:
        for i, s in enumerate(self.schedule):
            if s.phase == phase:
                return i
        return 0  # served phase is not in the schedule (e.g. after an emergency phase)

    def green_for(self, phase: Phase) -> float:
        return self.schedule[self._slot_index(phase)].green_s

    def decide(self, state: SimulationState) -> PhaseCommand:
        served = state.signal.served_phase
        idx = self._slot_index(served)
        if served != self.schedule[idx].phase:
            # off-schedule (emergency phase left over) -> return to the schedule head
            return PhaseCommand(target_phase=self.schedule[idx].phase,
                                force_transition=True, source=self.source)
        if state.signal.phase_elapsed_s >= self.schedule[idx].green_s:
            nxt = self.schedule[(idx + 1) % len(self.schedule)].phase
            return PhaseCommand(target_phase=nxt, force_transition=True, source=self.source)
        return PhaseCommand(target_phase=served, source=self.source)

    def describe(self) -> dict:
        return {
            "controller": "fixed_time",
            "cycle_s": self.cycle_s,
            "schedule": [{"phase": s.phase.value, "green_s": s.green_s} for s in self.schedule],
        }
