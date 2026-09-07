"""`ModelRegistry` - the write/read API over the `models` table.

Every checkpoint the training pipeline keeps (the final one, and any the caller asks to
register) becomes a row here. Evaluation results are attached later, in place. At most one
row per agent is ``active`` (served by live inference); ``promote`` enforces that.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.logging import get_logger
from app.persistence.db import init_db, session_scope
from app.persistence.models import MODEL_STATUSES, ModelRecord

log = get_logger("REGISTRY")


class RegistryError(RuntimeError):
    """Registry precondition failed (unknown id, bad status, ...)."""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ModelRegistry:
    """Thin, synchronous facade. Safe to construct per call - it holds no state."""

    def __init__(self, *, ensure_schema: bool = True) -> None:
        if ensure_schema:
            init_db()

    # ------------------------------------------------------------------ writes
    def register(
        self,
        *,
        model_id: str,
        agent: str,
        version: str,
        checkpoint_path: str,
        run_id: str,
        scenario: str,
        seed: int,
        episodes: int,
        training_config: dict | None = None,
        reward_config: dict | None = None,
        env_version: str = "",
        code_version: str | None = None,
        torch_version: str | None = None,
        status: str = "trained",
        notes: str | None = None,
        created_at: str | None = None,
    ) -> dict:
        if status not in MODEL_STATUSES:
            raise RegistryError(f"unknown status {status!r} (known: {MODEL_STATUSES})")
        with session_scope() as s:
            row = s.get(ModelRecord, model_id)
            if row is None:
                row = ModelRecord(id=model_id, created_at=created_at or _utcnow_iso())
                s.add(row)
            row.agent = agent.lower()
            row.version = version
            row.checkpoint_path = str(checkpoint_path)
            row.run_id = run_id
            row.scenario = scenario
            row.seed = int(seed)
            row.episodes = int(episodes)
            row.training_config = training_config or {}
            row.reward_config = reward_config or {}
            row.env_version = env_version
            row.code_version = code_version
            row.torch_version = torch_version
            row.status = status
            row.notes = notes
            if not row.created_at:
                row.created_at = _utcnow_iso()
            s.flush()
            out = row.as_dict()
        log.info("model registered", model_id=model_id, agent=out["agent"], status=status)
        return out

    def register_training_run(self, run, *, checkpoint: str | None = None,
                              model_id: str | None = None) -> dict:
        """Register the checkpoint a `TrainingRun` produced (default: its final one)."""
        repro = run.reproducibility or {}
        ckpt = checkpoint or run.final_checkpoint
        if ckpt is None:
            raise RegistryError(f"run {run.run_id} has no checkpoint to register")
        mid = model_id or f"{run.run_id}-ep{run.episodes_requested:03d}"
        return self.register(
            model_id=mid,
            agent=run.agent,
            version=run.final_model_version or f"{run.agent}-loaded",
            checkpoint_path=ckpt,
            run_id=run.run_id,
            scenario=run.scenario,
            seed=run.seed,
            episodes=len(run.episode_returns),
            training_config=repro.get("rl_hyperparams", {}),
            reward_config=repro.get("reward_weights", {}),
            env_version=repro.get("config_digest", ""),
            code_version=repro.get("git_commit"),
            torch_version=repro.get("torch_version"),
            status="trained",
        )

    def attach_evaluation(self, model_id: str, *, scenario: str, metrics: dict) -> dict:
        """Store an eval blob against a model and move it to ``evaluated``.

        ``metrics`` is whatever the evaluation harness produced - typically the
        ``compare(...)`` dict (per-controller aggregates + improvement %).
        """
        with session_scope() as s:
            row = s.get(ModelRecord, model_id)
            if row is None:
                raise RegistryError(f"no model {model_id!r} to attach evaluation to")
            row.eval_scenario = scenario
            row.eval_metrics = metrics
            row.evaluated_at = _utcnow_iso()
            if row.status == "trained":
                row.status = "evaluated"
            s.flush()
            out = row.as_dict()
        log.info("evaluation attached", model_id=model_id, scenario=scenario)
        return out

    def promote(self, model_id: str) -> dict:
        """Make this the one ``active`` checkpoint for its agent (demotes any other)."""
        with session_scope() as s:
            row = s.get(ModelRecord, model_id)
            if row is None:
                raise RegistryError(f"no model {model_id!r} to promote")
            others = s.scalars(
                select(ModelRecord).where(
                    ModelRecord.agent == row.agent,
                    ModelRecord.status == "active",
                    ModelRecord.id != model_id,
                )
            ).all()
            for other in others:
                other.status = "evaluated" if other.eval_metrics else "trained"
            row.status = "active"
            s.flush()
            out = row.as_dict()
        log.info("model promoted to active", model_id=model_id, agent=out["agent"])
        return out

    def set_status(self, model_id: str, status: str) -> dict:
        if status not in MODEL_STATUSES:
            raise RegistryError(f"unknown status {status!r} (known: {MODEL_STATUSES})")
        if status == "active":
            return self.promote(model_id)
        with session_scope() as s:
            row = s.get(ModelRecord, model_id)
            if row is None:
                raise RegistryError(f"no model {model_id!r}")
            row.status = status
            s.flush()
            return row.as_dict()

    # ------------------------------------------------------------------ reads
    def get(self, model_id: str) -> dict | None:
        with session_scope() as s:
            row = s.get(ModelRecord, model_id)
            return row.as_dict() if row else None

    def list(self, *, agent: str | None = None, status: str | None = None) -> list[dict]:
        stmt = select(ModelRecord).order_by(ModelRecord.created_at.desc())
        if agent:
            stmt = stmt.where(ModelRecord.agent == agent.lower())
        if status:
            stmt = stmt.where(ModelRecord.status == status)
        with session_scope() as s:
            return [r.as_dict() for r in s.scalars(stmt).all()]

    def active(self, agent: str) -> dict | None:
        """The checkpoint currently serving live inference for ``agent`` (if any)."""
        with session_scope() as s:
            row = s.scalars(
                select(ModelRecord).where(
                    ModelRecord.agent == agent.lower(),
                    ModelRecord.status == "active",
                )
            ).first()
            return row.as_dict() if row else None

    def latest(self, agent: str) -> dict | None:
        """Most recently created row for ``agent`` regardless of status."""
        with session_scope() as s:
            row = s.scalars(
                select(ModelRecord)
                .where(ModelRecord.agent == agent.lower())
                .order_by(ModelRecord.created_at.desc())
            ).first()
            return row.as_dict() if row else None
