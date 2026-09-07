"""SimulationAdapter protocol + engine factory (spec section 9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.core.config import get_settings
from app.logging import get_logger
from app.schemas.safety import PhaseCommand
from app.schemas.scenario import ScenarioConfig
from app.schemas.simulation import SimulationState

log = get_logger("SIMULATION")


@dataclass
class SimEvent:
    """A manual event injected into the running simulation (spec section 29)."""

    kind: str  # spawn_emergency | traffic_surge | block_lane | unblock_lane | create_violation | incident
    args: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SimulationAdapter(Protocol):
    """The single seam between the control stack and a traffic engine.

    Nothing above this protocol may import TraCI/libsumo or touch engine internals
    (spec section 9). A new engine is added by implementing this and registering it in
    `get_adapter()`.
    """

    name: str

    # -- lifecycle ---------------------------------------------------------
    def reset(self, scenario: ScenarioConfig, seed: int) -> None: ...
    def step(self, dt: float) -> None: ...
    def apply_phase(self, command: PhaseCommand) -> None: ...
    def inject(self, event: SimEvent) -> list[str]: ...
    def set_mode(self, mode: str) -> None: ...

    # -- observation -------------------------------------------------------
    def get_state(self) -> SimulationState: ...
    def drain_events(self) -> list[dict[str, Any]]: ...

    # -- counters the decision loop / metrics read -------------------------
    def mark_interval(self) -> int:
        """Non-emergency departures since the previous call; resets the counter."""

    def completed_trips(self) -> list[dict[str, float]]: ...
    def emergency_trips(self) -> list[dict[str, float]]: ...
    def throughput_vph(self) -> float: ...
    def violation_totals(self) -> tuple[int, int]: ...

    @property
    def sim_time(self) -> float: ...


def get_adapter() -> SimulationAdapter:
    settings = get_settings()
    if settings.sim_adapter == "sumo":
        try:
            from app.simulation.sumo.adapter import SumoAdapter

            return SumoAdapter()
        except Exception as exc:  # pragma: no cover - depends on external SUMO
            log.error(
                "SUMO adapter unavailable, falling back to builtin",
                exc_info=False,
                detail=str(exc),
            )
    from app.simulation.builtin.engine import BuiltinAdapter

    return BuiltinAdapter()
