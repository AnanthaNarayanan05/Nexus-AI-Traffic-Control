"""SUMO / libsumo adapter - INTERFACE STUB (spec section 9, docs/simulation.md section 6).

Not wired. Instantiation raises a clear error unless SUMO + libsumo are importable and
SUMO_HOME is set. When implemented, this maps SimulationState fields to libsumo calls
(lane.getLastStepHaltingNumber, lane.getWaitingTime, vehicle.*, trafficlight.setPhase)
and the inject() contract to vehicle.add / lane.setDisallowed.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from app.core.config import get_settings
from app.schemas.safety import PhaseCommand
from app.schemas.scenario import ScenarioConfig
from app.schemas.simulation import SimulationState
from app.simulation.adapter import SimEvent


class SumoAdapter:
    name = "sumo"

    def __init__(self) -> None:
        settings = get_settings()
        sumo_home = settings.sumo_home or os.environ.get("SUMO_HOME", "")
        if not sumo_home:
            raise RuntimeError("SUMO_HOME is not set - install SUMO and set SUMO_HOME (see docs/simulation.md)")
        if shutil.which(settings.sumo_binary) is None:
            raise RuntimeError(f"SUMO binary '{settings.sumo_binary}' not found on PATH")
        try:
            import libsumo  # noqa: F401
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "libsumo not importable - `pip install \".[sumo]\"` from backend/ (see docs/simulation.md)"
            ) from exc
        raise NotImplementedError(
            "SumoAdapter is scaffolded but not yet implemented. Use NEXUS_SIM_ADAPTER=builtin."
        )

    # The following satisfy the Protocol shape once implemented.
    def reset(self, scenario: ScenarioConfig, seed: int) -> None: ...  # pragma: no cover
    def step(self, dt: float) -> None: ...  # pragma: no cover
    def apply_phase(self, command: PhaseCommand) -> None: ...  # pragma: no cover
    def inject(self, event: SimEvent) -> list[str]: ...  # pragma: no cover
    def set_mode(self, mode: str) -> None: ...  # pragma: no cover
    def get_state(self) -> SimulationState: ...  # pragma: no cover
    def drain_events(self) -> list[dict[str, Any]]: ...  # pragma: no cover
    def mark_interval(self) -> int: ...  # pragma: no cover
    def completed_trips(self) -> list[dict[str, float]]: ...  # pragma: no cover
    def emergency_trips(self) -> list[dict[str, float]]: ...  # pragma: no cover
    def throughput_vph(self) -> float: ...  # pragma: no cover
    def violation_totals(self) -> tuple[int, int]: ...  # pragma: no cover

    @property
    def sim_time(self) -> float:  # pragma: no cover
        return 0.0
