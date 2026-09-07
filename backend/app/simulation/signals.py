"""Signal phase state machine (spec section 12, docs/simulation.md section 5).

The controller owns phase + time. It executes only *validated* PhaseCommands (the
safety layer is what validates them). It never flips conflicting greens directly:
a served -> served change always runs served -> YELLOW -> ALL_RED -> new served.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import get_config
from app.schemas.enums import EMERGENCY_PHASES, RING_PHASES, Approach, Movement, Phase, SignalColor
from app.schemas.safety import PhaseCommand
from app.schemas.simulation import SignalState, TransitionState


@dataclass
class _Transition:
    kind: Phase  # YELLOW | ALL_RED
    from_phase: Phase
    to_phase: Phase
    elapsed: float = 0.0
    total: float = 0.0


@dataclass
class SignalController:
    served_phase: Phase = Phase.NS
    current_phase: Phase = Phase.NS
    phase_elapsed: float = 0.0          # time in the current served phase
    _extend_budget: float = 0.0         # extra green granted beyond min, consumed over time
    _transition: _Transition | None = field(default=None, repr=False)
    _pending_target: Phase | None = field(default=None, repr=False)
    last_action: str | None = None

    # -- config helpers ----------------------------------------------------
    @property
    def _cfg(self):
        return get_config().signals

    @property
    def min_green(self) -> float:
        return float(self._cfg.min_green_s)

    @property
    def max_green(self) -> float:
        return float(self._cfg.max_green_s)

    @property
    def in_transition(self) -> bool:
        return self._transition is not None

    # -- command execution ----------------------------------------------------
    def apply(self, cmd: PhaseCommand) -> None:
        """Execute a safety-validated command. Assumes legality already checked."""
        self.last_action = cmd.summary()
        if self.in_transition:
            return  # transitions run to completion; safety guarantees no command lands here

        if cmd.force_transition and cmd.target_phase != self.served_phase:
            self._begin_transition(cmd.target_phase)
            return

        if cmd.target_phase == self.served_phase:
            if cmd.request_extend_s:
                self._extend_budget = min(
                    self._extend_budget + cmd.request_extend_s,
                    self.max_green - self.min_green,
                )
            if cmd.request_reduce:
                self._extend_budget = 0.0
            return

        # different served phase requested -> transition
        self._begin_transition(cmd.target_phase)

    def _begin_transition(self, target: Phase) -> None:
        self._pending_target = target
        self._transition = _Transition(
            kind=Phase.YELLOW,
            from_phase=self.served_phase,
            to_phase=target,
            total=float(self._cfg.yellow_s),
        )
        self.current_phase = Phase.YELLOW

    # -- time advance -------------------------------------------------------
    def step(self, dt: float) -> None:
        if self._transition is not None:
            self._step_transition(dt)
        else:
            self.phase_elapsed += dt

    def _step_transition(self, dt: float) -> None:
        tr = self._transition
        assert tr is not None
        tr.elapsed += dt
        if tr.elapsed < tr.total:
            return
        if tr.kind == Phase.YELLOW:
            tr.kind = Phase.ALL_RED
            tr.elapsed = 0.0
            tr.total = float(self._cfg.all_red_s)
            self.current_phase = Phase.ALL_RED
            return
        # ALL_RED complete -> land on the new served phase
        self.served_phase = tr.to_phase
        self.current_phase = tr.to_phase
        self.phase_elapsed = 0.0
        self._extend_budget = 0.0
        self._transition = None
        self._pending_target = None

    # -- queries ----------------------------------------------------------
    def movement_color(self, approach: Approach, movement: Movement) -> SignalColor:
        if self._transition is not None:
            tr = self._transition
            if tr.kind == Phase.YELLOW and tr.from_phase.serves(approach):
                return SignalColor.YELLOW
            return SignalColor.RED
        if self.served_phase.serves(approach):
            return SignalColor.GREEN
        return SignalColor.RED

    @property
    def time_to_min_green(self) -> float:
        if self.in_transition:
            return 0.0
        return max(0.0, self.min_green - self.phase_elapsed)

    @property
    def time_to_max_green(self) -> float:
        if self.in_transition:
            return self.max_green
        return max(0.0, self.max_green + self._extend_budget - self.phase_elapsed)

    def allowed_next(self, emergency_active: bool) -> list[Phase]:
        """Phases the controller could legally move to *right now* (before safety scoring)."""
        if self.in_transition:
            return [self._transition.to_phase] if self._transition else []
        options: list[Phase] = [self.served_phase]  # hold is always allowed
        if self.time_to_min_green > 1e-6:
            return options
        for p in RING_PHASES:
            if p != self.served_phase:
                options.append(p)
        if emergency_active:
            for p in EMERGENCY_PHASES.values():
                if p != self.served_phase:
                    options.append(p)
        return options

    def to_state(self, emergency_active: bool) -> SignalState:
        transition = None
        if self._transition is not None:
            tr = self._transition
            transition = TransitionState(
                kind=tr.kind, elapsed_s=round(tr.elapsed, 2), total_s=tr.total,
                from_phase=tr.from_phase, to_phase=tr.to_phase,
            )
        return SignalState(
            current_phase=self.current_phase,
            served_phase=self.served_phase,
            phase_elapsed_s=round(self.phase_elapsed, 2),
            phase_remaining_min_s=round(self.time_to_min_green, 2),
            phase_remaining_max_s=round(self.time_to_max_green, 2),
            transition=transition,
            allowed_next=self.allowed_next(emergency_active),
            last_action=self.last_action,
            approach_colors={a: self.movement_color(a, Movement.THROUGH) for a in Approach},
        )
