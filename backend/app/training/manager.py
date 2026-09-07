"""TrainingManager - run N episodes for one agent, checkpoint, write run metrics.

Spec sections 100 (vertical slice), 111 (agent contract), 84 (no fabricated numbers),
docs/architecture.md ("TrainingManager - agent training runs"), docs/training.md.

A run produces, on disk under ``models/<agent>/``:
  * ``<run_id>-ep<NNN>.pt``  - torch checkpoints at the configured cadence + the final one
  * ``latest.pt``            - a copy of the final checkpoint (what the app loads)
  * ``<run_id>.json``        - the full run record: per-episode returns / losses /
                               safety-override counts / wall time + a reproducibility blob

At the end of a run the final checkpoint is also recorded in the SQLite model registry
(`app/persistence`, `models` table). The JSON artifact remains the full record; the
registry row is the queryable index (agent, version, scenario, seed, config digest,
git sha, and - once attached - evaluation metrics and serving status).
"""

from __future__ import annotations

import contextlib
import json
import logging
import platform
import subprocess
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import torch

from app.agents.a2c import A2CAgent
from app.agents.common.base import BaseAgent
from app.agents.dqn import DQNAgent
from app.agents.ppo import PPOAgent
from app.core.config import get_config, get_settings
from app.logging import get_logger
from app.scenarios import get_scenario
from app.schemas.scenario import ScenarioConfig
from app.training.environment import EpisodeResult, TrainingEnv

log = get_logger("TRAINING")

AGENT_CLASSES: dict[str, type[BaseAgent]] = {
    "a2c": A2CAgent,
    "dqn": DQNAgent,
    "ppo": PPOAgent,
}

# Each agent's own stress scenario (see app/scenarios/presets.py descriptions):
#   a2c -> emergency-vehicle prioritisation, dqn -> fuel/emission/violations, ppo -> congestion
DEFAULT_SCENARIO: dict[str, str] = {
    "a2c": "emergency_heavy",
    "dqn": "high_stop_go",
    "ppo": "rush_hour",
}


def build_agent(agent: str, *, seed: int, training: bool) -> BaseAgent:
    key = agent.lower()
    if key not in AGENT_CLASSES:
        raise KeyError(f"unknown agent '{agent}' (known: {sorted(AGENT_CLASSES)})")
    return AGENT_CLASSES[key](seed=seed, training=training)  # type: ignore[call-arg]


class _DropSafetyOverrideNoise(logging.Filter):
    """Suppress the per-event 'safety override' WARNING during a training run.

    The safety layer still runs and still overrides (spec section 113); only its
    per-line log spam is muted. The per-episode override *count* is recorded in the
    run metrics, so nothing observable is lost.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not (
            getattr(record, "component", "") == "SAFETY"
            and record.levelno <= logging.WARNING
        )


@contextlib.contextmanager
def _quiet_safety_logs(enabled: bool) -> Iterator[None]:
    if not enabled:
        yield
        return
    logger = logging.getLogger("nexus")
    flt = _DropSafetyOverrideNoise()
    logger.addFilter(flt)
    try:
        yield
    finally:
        logger.removeFilter(flt)


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3, check=False,
            cwd=str(get_settings().models_dir.parent),
        )
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001 - git is optional
        return None


@dataclass
class TrainingRun:
    run_id: str
    agent: str
    scenario: str
    seed: int
    episodes_requested: int
    started_at: str
    finished_at: str | None = None
    wall_time_s: float = 0.0
    episode_seeds: list[int] = field(default_factory=list)
    episode_returns: list[float] = field(default_factory=list)
    episodes: list[dict] = field(default_factory=list)
    checkpoints: list[str] = field(default_factory=list)
    final_checkpoint: str | None = None
    final_model_version: str | None = None
    reproducibility: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)


class TrainingManager:
    def __init__(self, agent: str, *, episodes: int, scenario: str | None = None,
                 seed: int | None = None, checkpoint_every: int = 25,
                 out_dir: Path | None = None, quiet_safety_logs: bool = True,
                 episode_seconds: float | None = None, register: bool = True) -> None:
        self.agent_name = agent.lower()
        if self.agent_name not in AGENT_CLASSES:
            raise KeyError(f"unknown agent '{agent}' (known: {sorted(AGENT_CLASSES)})")
        self.episodes = int(episodes)
        self.scenario_id = scenario or DEFAULT_SCENARIO[self.agent_name]
        self.scenario: ScenarioConfig = get_scenario(self.scenario_id)
        if episode_seconds is not None:
            self.scenario.duration_s = float(episode_seconds)
        self.seed = int(seed if seed is not None else get_config().simulation.seed)
        self.checkpoint_every = max(1, int(checkpoint_every))
        self.quiet_safety_logs = quiet_safety_logs
        self.register = register
        self.out_dir = (out_dir or get_settings().models_dir) / self.agent_name
        self.run_id = f"{self.agent_name}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"

        self.agent = build_agent(self.agent_name, seed=self.seed, training=True)
        self.env = TrainingEnv(self.agent, self.scenario, seed=self.seed)

    # ------------------------------------------------------------------ run
    def run(self, *, on_episode: Callable[[EpisodeResult], None] | None = None) -> TrainingRun:
        cfg = get_config()
        run = TrainingRun(
            run_id=self.run_id, agent=self.agent_name, scenario=self.scenario_id,
            seed=self.seed, episodes_requested=self.episodes,
            started_at=_utcnow(),
            reproducibility={
                "scenario_id": self.scenario_id,
                "base_seed": self.seed,
                "episode_seed_rule": "base_seed + (episode_index - 1)",
                "config_digest": cfg.digest,
                "decision_interval_s": float(cfg.simulation.decision_interval_s),
                "step_length_s": float(cfg.simulation.step_length_s),
                "episode_length_s": float(self.scenario.duration_s),
                "reward_weights": dict(cfg.reward.get(self.agent_name, {})),
                "rl_hyperparams": dict(cfg.rl.get(self.agent_name, {})),
                "git_commit": _git_commit(),
                "torch_version": torch.__version__,
                "python_version": platform.python_version(),
                "platform": platform.platform(),
            },
        )
        log.info("training run started", **{
            "run_id": self.run_id, "agent": self.agent_name, "scenario": self.scenario_id,
            "episodes": self.episodes, "seed": self.seed, "out_dir": str(self.out_dir),
        })
        t0 = time.perf_counter()

        with _quiet_safety_logs(self.quiet_safety_logs):
            for i in range(1, self.episodes + 1):
                episode_seed = self.seed + (i - 1)
                result = self.env.run_episode(i, episode_seed=episode_seed)
                run.episode_seeds.append(episode_seed)
                run.episode_returns.append(result.episode_return)
                run.episodes.append(_episode_row(result))
                log.info("episode complete", **{
                    "run_id": self.run_id, "episode": i, "return": result.episode_return,
                    "mean_reward": result.mean_reward, "decisions": result.decisions,
                    "updates": result.updates, "safety_overrides": result.safety_overrides,
                    "losses": result.losses, "wall_time_s": result.wall_time_s,
                })
                if on_episode is not None:
                    on_episode(result)
                if i % self.checkpoint_every == 0 and i != self.episodes:
                    run.checkpoints.append(self._checkpoint(i))

        final = self._checkpoint(self.episodes)
        run.checkpoints.append(final)
        run.final_checkpoint = final
        run.final_model_version = self.agent.model_version
        latest = self._checkpoint(self.episodes, name="latest")
        run.finished_at = _utcnow()
        run.wall_time_s = round(time.perf_counter() - t0, 2)

        metrics_path = self.out_dir / f"{self.run_id}.json"
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(run.to_json(), encoding="utf-8")
        log.info("training run finished", **{
            "run_id": self.run_id, "wall_time_s": run.wall_time_s,
            "final_return": run.episode_returns[-1] if run.episode_returns else None,
            "final_checkpoint": final, "latest": latest, "metrics": str(metrics_path),
        })

        if self.register:
            self._register(run)
        return run

    def _register(self, run: TrainingRun) -> None:
        """Record the final checkpoint in the SQLite model registry.

        A registry failure never fails a completed run - the ``<run_id>.json`` on disk
        is still the record of truth (spec §98: degrade, log, continue).
        """
        try:
            from app.persistence import ModelRegistry

            row = ModelRegistry().register_training_run(
                run, checkpoint=run.final_checkpoint,
                model_id=f"{run.run_id}-ep{self.episodes:03d}",
            )
            log.info("model registered", model_id=row["id"], status=row["status"])
        except Exception as exc:  # noqa: BLE001 - persistence is best-effort here
            log.warning("model registry write failed; run artifacts still on disk",
                        run_id=self.run_id, error=str(exc))

    # ------------------------------------------------------------------ internals
    def _checkpoint(self, episode: int, *, name: str | None = None) -> str:
        fname = f"{name}.pt" if name else f"{self.run_id}-ep{episode:03d}.pt"
        path = self.out_dir / fname
        self.agent.save(path, meta={
            "version": self.agent.model_version,
            "run_id": self.run_id,
            "agent": self.agent_name,
            "scenario": self.scenario_id,
            "seed": self.seed,
            "episode": episode,
            "config_digest": get_config().digest,
            "trained_at": _utcnow(),
        })
        return str(path)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _episode_row(r: EpisodeResult) -> dict:
    return {
        "episode": r.index,
        "return": r.episode_return,
        "mean_reward": r.mean_reward,
        "decisions": r.decisions,
        "updates": r.updates,
        "safety_overrides": r.safety_overrides,
        "safety_checks": r.safety_checks,
        "losses": r.losses,
        "wall_time_s": r.wall_time_s,
        "metrics": r.metrics.flat(),
    }
