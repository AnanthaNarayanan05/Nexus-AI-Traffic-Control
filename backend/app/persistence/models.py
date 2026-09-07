"""ORM tables. Slice 2: the model registry only (`models`, docs/experiments.md §5)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.db import Base


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# status lifecycle for a registered checkpoint
MODEL_STATUSES = ("trained", "evaluated", "active", "archived")


class ModelRecord(Base):
    """One trained checkpoint and everything needed to trust / reproduce / serve it.

    Rows are written by `TrainingManager` at the end of a run and updated in place when
    an evaluation is attached (`status` -> "evaluated") or the checkpoint is promoted to
    serve live inference (`status` -> "active"; at most one active row per agent).
    """

    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)  # e.g. "<run_id>-ep200"
    agent: Mapped[str] = mapped_column(String(8), index=True)      # a2c | dqn | ppo
    version: Mapped[str] = mapped_column(String(32))               # agent.model_version
    checkpoint_path: Mapped[str] = mapped_column(Text)

    run_id: Mapped[str] = mapped_column(String(64), index=True)
    scenario: Mapped[str] = mapped_column(String(32))
    seed: Mapped[int] = mapped_column(Integer)
    episodes: Mapped[int] = mapped_column(Integer)

    training_config: Mapped[dict] = mapped_column(JSON, default=dict)   # rl hyperparams
    reward_config: Mapped[dict] = mapped_column(JSON, default=dict)     # reward weights
    env_version: Mapped[str] = mapped_column(String(32))               # config digest
    code_version: Mapped[str | None] = mapped_column(String(64), nullable=True)  # git sha
    torch_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[str] = mapped_column(String(40), default=_utcnow_iso)
    evaluated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    eval_scenario: Mapped[str | None] = mapped_column(String(32), nullable=True)
    eval_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {label: {metric: {...}}}

    status: Mapped[str] = mapped_column(String(16), default="trained", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "agent": self.agent,
            "version": self.version,
            "checkpoint_path": self.checkpoint_path,
            "run_id": self.run_id,
            "scenario": self.scenario,
            "seed": self.seed,
            "episodes": self.episodes,
            "training_config": self.training_config or {},
            "reward_config": self.reward_config or {},
            "env_version": self.env_version,
            "code_version": self.code_version,
            "torch_version": self.torch_version,
            "created_at": self.created_at,
            "evaluated_at": self.evaluated_at,
            "eval_scenario": self.eval_scenario,
            "eval_metrics": self.eval_metrics,
            "status": self.status,
            "notes": self.notes,
        }
