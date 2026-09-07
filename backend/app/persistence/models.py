"""ORM tables: the model registry (`models`), experiments (`experiments`) and
user-saved scenarios (`scenarios`), docs/experiments.md §5."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.db import Base


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# status lifecycle for a registered checkpoint
MODEL_STATUSES = ("trained", "evaluated", "active", "archived")

# status lifecycle for an experiment run
EXPERIMENT_STATUSES = ("running", "completed", "failed")


class ScenarioRecord(Base):
    """One user-saved (custom) scenario, R9 §8B.

    Presets are code (`app.scenarios.presets`) and never live here. A row is the full
    `ScenarioConfig` JSON blob plus a couple of denormalised columns for cheap listing.
    The scenario id is the primary key, so a save is an upsert and preset ids are
    rejected before they ever reach this table.
    """

    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)   # full ScenarioConfig blob
    created_at: Mapped[str] = mapped_column(String(40), default=_utcnow_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=_utcnow_iso)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "config": self.config or {},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


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


class ExperimentRecord(Base):
    """One Fixed-Time vs AI comparison run (docs/experiments.md §2-3, spec §48-56).

    An experiment evaluates one or more *controllers* (``fixed_time`` and/or an RL agent,
    trained or untrained) over the same held-out seeds on one scenario, then stores the
    per-controller aggregates, the honest baseline-vs-candidate comparison blob, and a
    frozen reproducibility blob. Every number is a real episode measurement (spec §84).
    """

    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # "exp-<UTC stamp>"
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[str] = mapped_column(String(40), default=_utcnow_iso, index=True)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    wall_time_s: Mapped[float] = mapped_column(default=0.0)

    scenario: Mapped[str] = mapped_column(String(48))
    controllers: Mapped[list] = mapped_column(JSON, default=list)   # ["fixed_time","a2c",...]
    seeds: Mapped[list] = mapped_column(JSON, default=list)         # [1,2,3,...]
    episode_seconds: Mapped[float | None] = mapped_column(nullable=True)
    baseline: Mapped[str] = mapped_column(String(24), default="fixed_time")

    reproducibility: Mapped[dict] = mapped_column(JSON, default=dict)   # frozen blob
    comparison: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # compare() output
    results: Mapped[list | None] = mapped_column(JSON, nullable=True)     # per-controller detail

    status: Mapped[str] = mapped_column(String(16), default="running", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def as_dict(self, *, full: bool = True) -> dict:
        out = {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "wall_time_s": round(self.wall_time_s or 0.0, 2),
            "scenario": self.scenario,
            "controllers": list(self.controllers or []),
            "seeds": list(self.seeds or []),
            "episode_seconds": self.episode_seconds,
            "baseline": self.baseline,
            "status": self.status,
            "error": self.error,
        }
        if full:
            out["reproducibility"] = self.reproducibility or {}
            out["comparison"] = self.comparison
            out["results"] = self.results
        return out
