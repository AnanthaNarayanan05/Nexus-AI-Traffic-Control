"""In-process training service: run one `TrainingManager` job on a background thread
and expose its live progress (spec §64-79 training progress; docs/training.md).

Design mirrors `SimulationManager`: the heavy work runs on its own thread and only ever
*publishes* an immutable snapshot; readers (REST handlers, the WS hub) poll `snapshot()`.
Nothing here touches the live simulation - training builds its own adapters.

One job at a time. `start()` raises `TrainingBusy` if a run is already active.
"""

from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from app.core.config import get_config, get_settings
from app.logging import get_logger
from app.training.environment import EpisodeResult
from app.training.manager import ACTIVE_AGENTS, AGENT_CLASSES, DEFAULT_SCENARIO, TrainingManager

log = get_logger("TRAINING")

MAX_EPISODES = 1000


class TrainingBusy(RuntimeError):
    """A training run is already active; only one runs at a time."""


class RunPhase(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _JobState:
    run_id: str
    agent: str
    scenario: str
    seed: int
    episodes_requested: int
    phase: RunPhase = RunPhase.RUNNING
    episode: int = 0
    started_at: str = field(default_factory=_utcnow)
    finished_at: str | None = None
    wall_time_s: float = 0.0
    error: str | None = None
    returns: list[float] = field(default_factory=list)
    last_episode: dict | None = None
    final_checkpoint: str | None = None
    final_model_version: str | None = None
    registered_model_id: str | None = None

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "agent": self.agent,
            "scenario": self.scenario,
            "seed": self.seed,
            "episodes_requested": self.episodes_requested,
            "phase": self.phase.value,
            "episode": self.episode,
            "progress": (self.episode / self.episodes_requested
                         if self.episodes_requested else 0.0),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "wall_time_s": round(self.wall_time_s, 2),
            "error": self.error,
            "returns": list(self.returns),
            "last_episode": self.last_episode,
            "final_checkpoint": self.final_checkpoint,
            "final_model_version": self.final_model_version,
            "registered_model_id": self.registered_model_id,
        }


class TrainingService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._job: _JobState | None = None
        self._seq = 0  # bumps on every published change; WS hub watches this

    # ------------------------------------------------------------------ reads
    @property
    def seq(self) -> int:
        return self._seq

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._job is not None and self._job.phase == RunPhase.RUNNING

    def snapshot(self) -> dict:
        with self._lock:
            job = self._job.as_dict() if self._job else None
        return {"seq": self._seq, "running": job is not None and job["phase"] == "running",
                "job": job}

    def history(self, limit: int = 50) -> list[dict]:
        """Finished runs, newest first, from the on-disk ``<run_id>.json`` records.

        Restricted to the active-scope agents; legacy PPO run records stay on disk but
        are not surfaced through the Training Lab (R9).
        """
        out: list[dict] = []
        models_dir = get_settings().models_dir
        for agent in ACTIVE_AGENTS:
            d = models_dir / agent
            if not d.is_dir():
                continue
            for rec in d.glob(f"{agent}-*.json"):
                if rec.name.startswith("eval-"):
                    continue
                out.append(_summarise_run_record(rec))
        out.sort(key=lambda r: r.get("finished_at") or r.get("started_at") or "", reverse=True)
        return out[:limit]

    def run_detail(self, run_id: str) -> dict | None:
        models_dir = get_settings().models_dir
        for agent in sorted(AGENT_CLASSES):
            rec = models_dir / agent / f"{run_id}.json"
            if rec.is_file():
                import json
                return json.loads(rec.read_text(encoding="utf-8"))
        return None

    # ------------------------------------------------------------------ writes
    def start(self, *, agent: str, episodes: int, scenario: str | None = None,
              seed: int | None = None, checkpoint_every: int = 25,
              episode_seconds: float | None = None) -> dict:
        agent = agent.lower()
        if agent not in AGENT_CLASSES:
            raise KeyError(f"unknown agent '{agent}' (known: {sorted(AGENT_CLASSES)})")
        if agent not in ACTIVE_AGENTS:
            raise ValueError(
                f"agent '{agent}' is deprecated and out of scope - train {list(ACTIVE_AGENTS)} only"
            )
        episodes = int(episodes)
        if not 1 <= episodes <= MAX_EPISODES:
            raise ValueError(f"episodes must be in 1..{MAX_EPISODES}")
        scenario_id = scenario or DEFAULT_SCENARIO[agent]

        with self._lock:
            if self._job is not None and self._job.phase == RunPhase.RUNNING:
                raise TrainingBusy(f"run {self._job.run_id} is still active")
            seed_val = int(seed if seed is not None else get_config().simulation.seed)
            run_id = f"{agent}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
            self._job = _JobState(
                run_id=run_id, agent=agent, scenario=scenario_id, seed=seed_val,
                episodes_requested=episodes,
            )
            self._seq += 1
            self._thread = threading.Thread(
                target=self._run, name=f"nexus-train-{agent}", daemon=True,
                kwargs={"agent": agent, "episodes": episodes, "scenario_id": scenario_id,
                        "seed": seed_val, "run_id": run_id,
                        "checkpoint_every": int(checkpoint_every),
                        "episode_seconds": episode_seconds},
            )
            self._thread.start()
        log.info("training run accepted", run_id=run_id, agent=agent,
                 scenario=scenario_id, episodes=episodes, seed=seed_val)
        return self.snapshot()

    # ------------------------------------------------------------------ worker
    def _publish(self, mutate) -> None:
        with self._lock:
            mutate(self._job)
            self._seq += 1

    def _run(self, *, agent: str, episodes: int, scenario_id: str, seed: int,
             run_id: str, checkpoint_every: int,
             episode_seconds: float | None = None) -> None:
        t0 = time.perf_counter()
        try:
            mgr = TrainingManager(
                agent, episodes=episodes, scenario=scenario_id, seed=seed,
                checkpoint_every=checkpoint_every, episode_seconds=episode_seconds,
            )
            mgr.run_id = run_id  # use the run_id already announced in the snapshot

            def on_episode(result: EpisodeResult) -> None:
                self._publish(lambda j: _apply_episode(j, result))

            run = mgr.run(on_episode=on_episode)

            def _finish(j: _JobState) -> None:
                j.phase = RunPhase.COMPLETED
                j.finished_at = _utcnow()
                j.wall_time_s = time.perf_counter() - t0
                j.final_checkpoint = run.final_checkpoint
                j.final_model_version = run.final_model_version
                j.registered_model_id = f"{run.run_id}-ep{episodes:03d}"

            self._publish(_finish)
            log.info("training run complete", run_id=run_id,
                     final_return=run.episode_returns[-1] if run.episode_returns else None)
        except Exception as exc:  # noqa: BLE001 - surfaced to the client, never crashes the app
            msg = f"{type(exc).__name__}: {exc}"
            log.error("training run failed", run_id=run_id, error=msg,
                      trace=traceback.format_exc())

            def _fail(j: _JobState) -> None:
                j.phase = RunPhase.FAILED
                j.finished_at = _utcnow()
                j.wall_time_s = time.perf_counter() - t0
                j.error = msg

            self._publish(_fail)


def _apply_episode(job: _JobState, result: EpisodeResult) -> None:
    job.episode = result.index
    job.returns.append(result.episode_return)
    job.last_episode = {
        "episode": result.index,
        "return": result.episode_return,
        "mean_reward": result.mean_reward,
        "decisions": result.decisions,
        "updates": result.updates,
        "safety_overrides": result.safety_overrides,
        "losses": result.losses,
        "wall_time_s": result.wall_time_s,
        "metrics": result.metrics.flat(),
    }


def _summarise_run_record(path: Path) -> dict:
    import json

    rec = json.loads(path.read_text(encoding="utf-8"))
    returns = rec.get("episode_returns", [])
    return {
        "run_id": rec.get("run_id", path.stem),
        "agent": rec.get("agent"),
        "scenario": rec.get("scenario"),
        "seed": rec.get("seed"),
        "episodes": len(returns),
        "started_at": rec.get("started_at"),
        "finished_at": rec.get("finished_at"),
        "wall_time_s": rec.get("wall_time_s"),
        "final_model_version": rec.get("final_model_version"),
        "final_checkpoint": rec.get("final_checkpoint"),
        "first_return": returns[0] if returns else None,
        "last_return": returns[-1] if returns else None,
        "config_digest": (rec.get("reproducibility") or {}).get("config_digest"),
    }


_SERVICE: TrainingService | None = None


def get_training_service() -> TrainingService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = TrainingService()
    return _SERVICE


def _reset_training_service_for_tests() -> None:
    global _SERVICE
    _SERVICE = None
