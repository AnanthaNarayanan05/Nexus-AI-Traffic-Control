"""BaseAgent - the common contract for A2C / DQN / PPO (spec section 111)."""

from __future__ import annotations

import abc
import contextlib
from pathlib import Path
from typing import Any

import numpy as np

from app.agents.common.features import FeatureVector
from app.agents.common.rewards import RewardContext
from app.schemas.agents import (
    AgentInspectorPayload,
    AgentRecommendation,
    AgentStatus,
    RewardBreakdown,
)
from app.schemas.enums import AgentName, Phase
from app.schemas.safety import PhaseCommand
from app.schemas.simulation import SimulationState


class BaseAgent(abc.ABC):
    name: AgentName
    action_labels: list[str]
    state_dim: int

    def __init__(self) -> None:
        self.model_version = "untrained"
        self.trained_episodes = 0
        self._reward_history: list[float] = []
        self._decision_history: list[dict[str, Any]] = []
        self._last_features: FeatureVector | None = None
        self._last_inference_ms: float | None = None
        self._inspecting = False

    # -- state ------------------------------------------------------------
    @abc.abstractmethod
    def build_state(self, state: SimulationState) -> FeatureVector: ...

    # -- inference ------------------------------------------------------------
    @abc.abstractmethod
    def act(self, state: SimulationState) -> AgentRecommendation: ...

    @abc.abstractmethod
    def resolve_phase(self, action_index: int, state: SimulationState) -> Phase:
        """Concrete phase the agent's chosen action maps to, given current state."""

    # -- reward ------------------------------------------------------------
    @abc.abstractmethod
    def compute_reward(self, ctx: RewardContext) -> RewardBreakdown: ...

    # -- learning ------------------------------------------------------------
    @abc.abstractmethod
    def observe(self, state: SimulationState, action_index: int, reward: float,
                next_state: SimulationState, done: bool, info: dict | None = None) -> None: ...

    @abc.abstractmethod
    def learn(self) -> dict[str, float]:
        """Run at most one update step; return training metrics (may be empty)."""

    # -- persistence ------------------------------------------------------------
    @abc.abstractmethod
    def save(self, path: str | Path, meta: dict | None = None) -> None: ...

    @abc.abstractmethod
    def load(self, path: str | Path) -> dict: ...

    # -- introspection ------------------------------------------------------------
    @property
    def is_trained(self) -> bool:
        return self.trained_episodes > 0

    def status(self) -> AgentStatus:
        return AgentStatus(
            agent=self.name,
            model_version=self.model_version,
            trained_episodes=self.trained_episodes,
            is_trained=self.is_trained,
            device="cpu",
            last_action=(self._decision_history[-1]["action"] if self._decision_history else None),
            last_reward=(self._reward_history[-1] if self._reward_history else None),
            inference_latency_ms=self._last_inference_ms,
        )

    @contextlib.contextmanager
    def inspecting(self):
        """Suppress decision recording for the forward pass an inspector runs.

        `inspect()` re-runs `act()` deterministically to expose the current activations.
        That pass is an observation, not a control decision, so it must not appear in the
        decision history the inspector then displays (spec section 84).
        """
        previous = self._inspecting
        self._inspecting = True
        try:
            yield
        finally:
            self._inspecting = previous

    def _record_decision(self, rec: AgentRecommendation, reward_total: float | None = None) -> None:
        if self._inspecting:
            return
        entry = {
            "action": rec.action_name,
            "target_phase": rec.target_phase.value,
            "score": round(rec.score, 3),
            "priority": round(rec.priority, 3),
            "reason": rec.reason,
        }
        if reward_total is not None:
            entry["reward"] = round(reward_total, 3)
        self._decision_history.append(entry)
        if len(self._decision_history) > 200:
            self._decision_history = self._decision_history[-200:]

    def note_reward(self, total: float) -> None:
        self._reward_history.append(total)
        if len(self._reward_history) > 500:
            self._reward_history = self._reward_history[-500:]
        if self._decision_history:
            self._decision_history[-1]["reward"] = round(total, 3)

    @abc.abstractmethod
    def inspect(self, state: SimulationState) -> AgentInspectorPayload: ...


def softmax(x: np.ndarray) -> np.ndarray:
    z = x - np.max(x)
    e = np.exp(z)
    return e / e.sum()
