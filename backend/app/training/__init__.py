"""Headless agent training (spec sections 100, 111, 113; docs/training.md).

`TrainingEnv` runs one agent through full episodes against a fresh built-in simulation;
`TrainingManager` runs N episodes, checkpoints the policy, and writes a run-metrics
artifact. Nothing here fabricates numbers - every return, loss and metric comes from a
real episode and a real gradient step (spec section 84).
"""

from app.training.environment import EpisodeResult, TrainingEnv
from app.training.manager import (
    AGENT_CLASSES,
    DEFAULT_SCENARIO,
    TrainingManager,
    TrainingRun,
    build_agent,
)

__all__ = [
    "EpisodeResult",
    "TrainingEnv",
    "TrainingManager",
    "TrainingRun",
    "build_agent",
    "AGENT_CLASSES",
    "DEFAULT_SCENARIO",
]
