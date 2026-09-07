"""LEGACY - PPO (adaptive congestion reduction) is out of the R9 active scope.

The class is retained so pre-R9 checkpoints and run records stay loadable and
inspectable, but PPO is not built into the live loop and new training runs are
blocked (see app/training/manager.py::ACTIVE_AGENTS, docs/STATUS.md). Do not
re-add PPO to the coordination pipeline or the frontend workflow.
"""

from app.agents.ppo.agent import PPOAction, PPOAgent

__all__ = ["PPOAgent", "PPOAction"]
