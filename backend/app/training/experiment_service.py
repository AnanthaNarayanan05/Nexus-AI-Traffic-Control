"""In-process experiment service: run one Fixed-Time vs AI comparison on a background
thread and expose its live progress (spec §48-56; docs/experiments.md).

Design mirrors `TrainingService`: the heavy work (headless evaluation episodes) runs on
its own thread and only ever *publishes* an immutable snapshot; readers (REST handlers,
the WS hub) poll `snapshot()`. Nothing here touches the live simulation - evaluation
builds its own adapters.

One job at a time. `start()` raises `ExperimentBusy` if a run is already active.
Every number persisted is a real episode measurement (spec §84); on any failure the
experiment row is marked ``failed`` with the error rather than left half-written.
"""

from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from app.core.config import get_config
from app.logging import get_logger
from app.persistence import ExperimentStore, ModelRegistry
from app.scenarios import get_scenario
from app.training.evaluation import EvalEpisode, EvalResult, compare
from app.training.evaluation import evaluate as run_evaluation
from app.training.manager import ACTIVE_AGENTS, _git_commit

log = get_logger("EXPERIMENT")

CONTROLLERS = ("fixed_time", *ACTIVE_AGENTS)   # fixed_time | a2c | dqn
MODEL_MODES = ("untrained", "active", "latest")
MAX_SEEDS = 16
MIN_EPISODE_SECONDS = 60.0
MAX_EPISODE_SECONDS = 7200.0


class ExperimentBusy(RuntimeError):
    """An experiment is already active; only one runs at a time."""


class ExperimentPhase(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _JobState:
    experiment_id: str
    name: str
    scenario: str
    controllers: list[str]
    seeds: list[int]
    baseline: str
    episode_seconds: float | None
    phase: ExperimentPhase = ExperimentPhase.RUNNING
    current_controller: str | None = None
    episodes_done: int = 0
    episodes_total: int = 0
    started_at: str = field(default_factory=_utcnow)
    finished_at: str | None = None
    wall_time_s: float = 0.0
    error: str | None = None
    comparison: dict | None = None
    results: list | None = None
    reproducibility: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "scenario": self.scenario,
            "controllers": list(self.controllers),
            "seeds": list(self.seeds),
            "baseline": self.baseline,
            "episode_seconds": self.episode_seconds,
            "phase": self.phase.value,
            "current_controller": self.current_controller,
            "episodes_done": self.episodes_done,
            "episodes_total": self.episodes_total,
            "progress": (self.episodes_done / self.episodes_total
                         if self.episodes_total else 0.0),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "wall_time_s": round(self.wall_time_s, 2),
            "error": self.error,
            "comparison": self.comparison,
            "results": self.results,
            "reproducibility": self.reproducibility,
        }


# --------------------------------------------------------------------- validation
def _clean_controllers(raw: list[str]) -> list[str]:
    seen: list[str] = []
    for c in raw:
        c = str(c).strip().lower()
        if c not in CONTROLLERS:
            raise ValueError(
                f"unknown controller '{c}' (choose from {list(CONTROLLERS)}; "
                f"PPO is out of the R9 active scope)"
            )
        if c not in seen:
            seen.append(c)
    if not seen:
        raise ValueError("at least one controller is required")
    return seen


def _clean_seeds(raw: list[int]) -> list[int]:
    seeds: list[int] = []
    for s in raw:
        try:
            v = int(s)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"seed {s!r} is not an integer") from exc
        if v not in seeds:
            seeds.append(v)
    if not seeds:
        raise ValueError("at least one seed is required")
    if len(seeds) > MAX_SEEDS:
        raise ValueError(f"at most {MAX_SEEDS} seeds per experiment (got {len(seeds)})")
    return seeds


def _resolve_model(agent: str, selector: str) -> dict:
    """Resolve a per-agent model selector to a checkpoint + provenance.

    selector: "untrained" | "active" | "latest" | "<registry model id>".
    Raises ValueError when a requested checkpoint does not exist - never a fake one.
    """
    selector = str(selector or "untrained").strip()
    if selector == "untrained":
        return {"mode": "untrained", "version": "untrained", "checkpoint": None,
                "registry_id": None}

    reg = ModelRegistry()
    if selector == "active":
        row = reg.active(agent)
        if row is None:
            raise ValueError(f"{agent}: no active checkpoint in the registry - "
                             f"promote one, pick 'latest', or use 'untrained'")
    elif selector == "latest":
        row = reg.latest(agent)
        if row is None:
            raise ValueError(f"{agent}: no checkpoints in the registry yet - "
                             f"train one or use 'untrained'")
    else:
        row = reg.get(selector)
        if row is None:
            raise ValueError(f"{agent}: no registry model '{selector}'")
        if row.get("agent") != agent:
            raise ValueError(f"model '{selector}' belongs to {row.get('agent')}, not {agent}")

    ckpt = row.get("checkpoint_path")
    if not ckpt or not Path(ckpt).is_file():
        raise ValueError(f"{agent}: checkpoint file for '{row.get('id')}' is missing "
                         f"({ckpt}) - cannot evaluate a model that is not on disk")
    return {"mode": selector, "version": row.get("version"), "checkpoint": ckpt,
            "registry_id": row.get("id")}


class ExperimentService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._job: _JobState | None = None
        self._seq = 0  # bumps on every published change; the WS hub watches this

    # ------------------------------------------------------------------ reads
    @property
    def seq(self) -> int:
        return self._seq

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._job is not None and self._job.phase == ExperimentPhase.RUNNING

    def snapshot(self) -> dict:
        with self._lock:
            job = self._job.as_dict() if self._job else None
        return {"seq": self._seq,
                "running": job is not None and job["phase"] == "running",
                "job": job}

    def history(self, limit: int = 50) -> list[dict]:
        return ExperimentStore().list(limit=limit)

    def detail(self, experiment_id: str) -> dict | None:
        return ExperimentStore().get(experiment_id)

    # ------------------------------------------------------------------ writes
    def start(self, *, name: str | None, scenario: str, controllers: list[str],
              seeds: list[int], models: dict[str, str] | None = None,
              episode_seconds: float | None = None) -> dict:
        controllers = _clean_controllers(controllers)
        seeds = _clean_seeds(seeds)
        models = {k.lower(): v for k, v in (models or {}).items()}

        try:
            scenario_obj = get_scenario(scenario)
        except KeyError as exc:
            raise KeyError(str(exc)) from exc

        if episode_seconds is not None:
            episode_seconds = float(episode_seconds)
            if not MIN_EPISODE_SECONDS <= episode_seconds <= MAX_EPISODE_SECONDS:
                raise ValueError(
                    f"episode_seconds must be in "
                    f"{MIN_EPISODE_SECONDS:.0f}..{MAX_EPISODE_SECONDS:.0f}")

        baseline = "fixed_time" if "fixed_time" in controllers else controllers[0]

        # resolve every agent controller's checkpoint up front - fail fast, before the
        # row is created, if a requested model is not on disk.
        model_plan: dict[str, dict] = {}
        for c in controllers:
            if c in ACTIVE_AGENTS:
                model_plan[c] = _resolve_model(c, models.get(c, "untrained"))

        cfg = get_config()
        reproducibility = {
            "created_at": _utcnow(),
            "scenario": scenario,
            "scenario_name": scenario_obj.name,
            "seeds": seeds,
            "controllers": controllers,
            "baseline": baseline,
            "episode_seconds": episode_seconds or float(scenario_obj.duration_s),
            "models": model_plan,
            "config_digest": cfg.digest,
            "git_commit": _git_commit(),
            "decision_interval_s": float(cfg.simulation.decision_interval_s),
            "step_length_s": float(cfg.simulation.step_length_s),
            "reward_weights": {
                c: dict(cfg.reward.get(c, {})) for c in controllers if c in ACTIVE_AGENTS
            },
            "safety": dict(cfg.get("safety", {})),
        }
        try:
            import torch
            reproducibility["torch_version"] = torch.__version__
        except Exception:  # noqa: BLE001 - torch always present, defensive
            reproducibility["torch_version"] = None

        with self._lock:
            if self._job is not None and self._job.phase == ExperimentPhase.RUNNING:
                raise ExperimentBusy(
                    f"experiment {self._job.experiment_id} is still active")
            now = datetime.now(timezone.utc)
            stamp = f"{now:%Y%m%dT%H%M%S}{now.microsecond // 1000:03d}Z"
            experiment_id = f"exp-{stamp}"
            job_name = (name or "").strip() or f"{scenario} · {' vs '.join(controllers)}"
            self._job = _JobState(
                experiment_id=experiment_id, name=job_name, scenario=scenario,
                controllers=controllers, seeds=seeds, baseline=baseline,
                episode_seconds=episode_seconds,
                episodes_total=len(controllers) * len(seeds),
                reproducibility=reproducibility,
            )
            self._seq += 1
            self._thread = threading.Thread(
                target=self._run, name=f"nexus-{experiment_id}", daemon=True,
                kwargs={"experiment_id": experiment_id, "name": job_name,
                        "scenario": scenario, "controllers": controllers, "seeds": seeds,
                        "baseline": baseline, "episode_seconds": episode_seconds,
                        "model_plan": model_plan, "reproducibility": reproducibility},
            )
            self._thread.start()
        log.info("experiment accepted", experiment_id=experiment_id, scenario=scenario,
                 controllers=controllers, seeds=seeds)
        return self.snapshot()

    # ------------------------------------------------------------------ worker
    def _publish(self, mutate) -> None:
        with self._lock:
            if self._job is not None:
                mutate(self._job)
            self._seq += 1

    def _run(self, *, experiment_id: str, name: str, scenario: str,
             controllers: list[str], seeds: list[int], baseline: str,
             episode_seconds: float | None, model_plan: dict[str, dict],
             reproducibility: dict) -> None:
        t0 = time.perf_counter()
        store = ExperimentStore()
        store.create(
            experiment_id=experiment_id, name=name, scenario=scenario,
            controllers=controllers, seeds=seeds, baseline=baseline,
            episode_seconds=episode_seconds, reproducibility=reproducibility,
        )
        try:
            results: list[EvalResult] = []
            for controller in controllers:
                self._publish(lambda j, c=controller: setattr(j, "current_controller", c))
                checkpoint = None
                label = None
                if controller in model_plan:
                    checkpoint = model_plan[controller]["checkpoint"]
                    if checkpoint is None:
                        label = f"{controller} untrained"

                def _on_ep(_ep: EvalEpisode) -> None:
                    self._publish(lambda j: setattr(j, "episodes_done", j.episodes_done + 1))

                res = run_evaluation(
                    controller, scenario_id=scenario, seeds=seeds,
                    checkpoint=checkpoint, label=label, episode_seconds=episode_seconds,
                    on_episode=_on_ep,
                )
                results.append(res)

            blob = compare(results, baseline_label=baseline)
            results_payload = [_result_payload(r, model_plan) for r in results]
            wall = time.perf_counter() - t0
            store.complete(experiment_id, comparison=blob, results=results_payload,
                           wall_time_s=wall)

            def _finish(j: _JobState) -> None:
                j.phase = ExperimentPhase.COMPLETED
                j.finished_at = _utcnow()
                j.wall_time_s = wall
                j.current_controller = None
                j.comparison = blob
                j.results = results_payload

            self._publish(_finish)
            log.info("experiment complete", experiment_id=experiment_id,
                     wall_time_s=round(wall, 1))
        except Exception as exc:  # noqa: BLE001 - surfaced to the client, never fatal
            msg = f"{type(exc).__name__}: {exc}"
            wall = time.perf_counter() - t0
            log.error("experiment failed", experiment_id=experiment_id, error=msg,
                      trace=traceback.format_exc())
            try:
                store.fail(experiment_id, error=msg, wall_time_s=wall)
            except Exception:  # noqa: BLE001
                log.error("could not mark experiment failed", experiment_id=experiment_id)

            def _fail(j: _JobState) -> None:
                j.phase = ExperimentPhase.FAILED
                j.finished_at = _utcnow()
                j.wall_time_s = wall
                j.error = msg

            self._publish(_fail)


def _result_payload(r: EvalResult, model_plan: dict[str, dict]) -> dict:
    prov = model_plan.get(r.controller, {})
    return {
        "label": r.label,
        "controller": r.controller,
        "scenario": r.scenario,
        "model_version": r.model_version,
        "checkpoint": r.checkpoint,
        "registry_id": prov.get("registry_id"),
        "model_mode": prov.get("mode", "fixed_time" if r.controller == "fixed_time"
                               else "untrained"),
        "seeds": list(r.seeds),
        "aggregates": r.aggregates,
        "episodes": [
            {"seed": e.seed, "decisions": e.decisions,
             "safety_overrides": e.safety_overrides, "metrics": e.metrics}
            for e in r.episodes
        ],
    }


_SERVICE: ExperimentService | None = None


def get_experiment_service() -> ExperimentService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = ExperimentService()
    return _SERVICE


def _reset_experiment_service_for_tests() -> None:
    global _SERVICE
    _SERVICE = None
