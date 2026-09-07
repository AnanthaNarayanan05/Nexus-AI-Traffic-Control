"""State-builder helpers shared by A2C / DQN / PPO (docs/a2c.md,dqn.md,ppo.md section 1)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.core.config import get_config
from app.schemas.agents import LabelledFeature
from app.schemas.enums import Approach, Phase

# canonical ordering used everywhere
APPROACH_ORDER: tuple[Approach, ...] = (Approach.N, Approach.E, Approach.S, Approach.W)
PHASE_ONEHOT_ORDER: tuple[Phase, ...] = (
    Phase.NS, Phase.EW, Phase.N, Phase.E, Phase.S, Phase.W, Phase.YELLOW, Phase.ALL_RED,
)


def one_hot_phase(phase: Phase) -> list[float]:
    return [1.0 if phase == p else 0.0 for p in PHASE_ONEHOT_ORDER]


class Normalizer:
    """Normalisation references (docs/assumptions.md A10). Order-of-magnitude scaling
    for stable learning - not physical constants."""

    def __init__(self) -> None:
        g = get_config().geometry
        self.free_flow_mps = float(g.free_flow_speed_kmh) / 3.6
        self.wait_ref = 120.0
        self.queue_ref = 25.0
        self.count_ref = 40.0
        self.stops_ref = 20.0
        self.density_ref = 130.0
        self.arrival_ref = 1400.0
        self.throughput_ref = 2600.0
        self.co2_rate_ref = 0.08       # kg/s across the whole intersection
        self.violation_ref = 3.0
        self.max_green = float(get_config().signals.max_green_s)
        self.emergency_dist_ref = float(g.approach_length_m)
        self.emergency_eta_ref = 30.0

    def clip01(self, x: float) -> float:
        return float(np.clip(x, 0.0, 1.0))

    def signed_clip(self, x: float) -> float:
        return float(np.clip(x, -1.0, 1.0))


@dataclass
class FeatureVector:
    """Accumulates named, grouped features and emits both an ndarray and UI labels."""

    _names: list[str] = field(default_factory=list)
    _values: list[float] = field(default_factory=list)
    _groups: list[str] = field(default_factory=list)

    def add(self, name: str, value: float, group: str) -> None:
        self._names.append(name)
        self._values.append(float(value))
        self._groups.append(group)

    def add_many(self, prefix: str, values: list[float], group: str, labels: list[str] | None = None) -> None:
        for i, v in enumerate(values):
            label = labels[i] if labels else f"{prefix}[{i}]"
            self.add(label, v, group)

    def array(self) -> np.ndarray:
        return np.asarray(self._values, dtype=np.float32)

    def labelled(self) -> list[LabelledFeature]:
        return [
            LabelledFeature(name=n, value=round(v, 4), group=g)
            for n, v, g in zip(self._names, self._values, self._groups, strict=True)
        ]

    def __len__(self) -> int:
        return len(self._values)
