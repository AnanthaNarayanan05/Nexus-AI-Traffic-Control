"""Headless evaluation — run a controller through fixed-seed episodes, aggregate metrics.

No learning, no exploration: the policy runs deterministically (`training=False` ⇒ argmax
for A2C/PPO, greedy for DQN). Used to compare a trained checkpoint against the fixed-time
baseline and against the *same* agent's untrained (random-init) network.

Spec §48–49 (real baseline + comparison), §80–83 (RL validation), §84 (measured, never
fabricated). Every number here comes from a real episode of the built-in simulation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.agents.common.resolve import action_to_command
from app.control import FixedTimeController
from app.core.config import get_config
from app.logging import get_logger
from app.metrics import MetricsAggregator
from app.metrics.aggregator import summarise_series
from app.safety import SafetyValidator
from app.scenarios import get_scenario
from app.schemas.enums import ControlMode
from app.schemas.safety import PhaseCommand
from app.schemas.simulation import SimulationState
from app.simulation.builtin.engine import BuiltinAdapter
from app.training.manager import AGENT_CLASSES, build_agent

log = get_logger("TRAINING")

# metric key -> True if a *lower* value is better
METRIC_DIRECTION: dict[str, bool] = {
    "traffic.avg_waiting_s": True,
    "traffic.avg_queue": True,
    "traffic.throughput_vph": False,
    "traffic.avg_travel_time_s": True,
    "traffic.avg_speed_mps": False,
    "traffic.stops_per_veh": True,
    "traffic.idle_time_s": True,
    "environmental.fuel_l_per_veh": True,
    "environmental.co2_kg_per_veh": True,
    "environmental.fuel_l_total": True,
    "environmental.co2_kg_total": True,
    "emergency.emergency_wait_s": True,
    "emergency.emergency_travel_time_s": True,
    "emergency.emergency_delay_s": True,
    "emergency.emergency_cleared": False,
    "safety.red_light_violations": True,
    "safety.other_violations": True,
    "safety.unsafe_transitions": True,
}
METRIC_KEYS = tuple(METRIC_DIRECTION)

Decider = Callable[[SimulationState], PhaseCommand]


@dataclass
class EvalEpisode:
    seed: int
    decisions: int
    safety_overrides: int
    metrics: dict[str, float]


@dataclass
class EvalResult:
    label: str                       # e.g. "fixed_time", "a2c untrained", "a2c a2c-v1.4-dev"
    controller: str                  # fixed_time | a2c | dqn | ppo
    scenario: str
    model_version: str | None
    checkpoint: str | None
    seeds: list[int]
    episodes: list[EvalEpisode] = field(default_factory=list)
    aggregates: dict[str, dict[str, float]] = field(default_factory=dict)

    def mean(self, key: str) -> float | None:
        agg = self.aggregates.get(key)
        return agg["mean"] if agg else None


# --------------------------------------------------------------------- one episode
def _run_episode(decider: Decider, scenario, seed: int, *, mode: str) -> EvalEpisode:
    sim = get_config().simulation
    dt = float(sim.step_length_s)
    interval = float(sim.decision_interval_s)
    duration = float(scenario.duration_s)

    adapter = BuiltinAdapter()
    adapter.reset(scenario, seed)
    adapter.set_mode(mode)
    safety = SafetyValidator()
    metrics = MetricsAggregator(adapter)

    last_decision_t = -1e9
    decisions = 0
    for _ in range(int(duration / dt) + 4):
        if adapter.sim_time >= duration:
            break
        adapter.step(dt)
        adapter.drain_events()
        t = adapter.sim_time
        if t - last_decision_t >= interval:
            last_decision_t = t
            state = adapter.get_state()
            result = safety.validate(decider(state), state)   # authoritative (§113)
            adapter.apply_phase(result.command)
            decisions += 1

    final = adapter.get_state()
    snap = metrics.episode(final, unsafe_transitions=safety.overrides_total)
    return EvalEpisode(seed=seed, decisions=decisions,
                       safety_overrides=safety.overrides_total, metrics=snap.flat())


# --------------------------------------------------------------------- deciders
def _fixed_time_decider() -> Decider:
    ctrl = FixedTimeController()
    return ctrl.decide


def _agent_decider(agent) -> Decider:
    def decide(state: SimulationState) -> PhaseCommand:
        rec = agent.act(state)  # deterministic: agent.training is False
        phase = agent.resolve_phase(rec.action_index, state)
        return action_to_command(rec.action_name, phase, state.signal.served_phase,
                                 source="evaluator")
    return decide


# --------------------------------------------------------------------- public API
def evaluate(controller: str, *, scenario_id: str, seeds: list[int],
             checkpoint: str | Path | None = None, label: str | None = None,
             episode_seconds: float | None = None) -> EvalResult:
    scenario = get_scenario(scenario_id)
    if episode_seconds is not None:
        scenario.duration_s = float(episode_seconds)

    if controller == "fixed_time":
        decider = _fixed_time_decider()
        mode = ControlMode.FIXED_TIME.value
        version: str | None = None
    elif controller in AGENT_CLASSES:
        agent = build_agent(controller, seed=0, training=False)
        version = "untrained"
        if checkpoint is not None:
            agent.load(checkpoint)
            version = agent.model_version
        decider = _agent_decider(agent)
        mode = ControlMode.AI.value
    else:
        raise KeyError(f"unknown controller '{controller}'")

    episodes = [_run_episode(decider, scenario, s, mode=mode) for s in seeds]

    aggregates: dict[str, dict[str, float]] = {
        key: summarise_series([e.metrics[key] for e in episodes]) for key in METRIC_KEYS
    }
    aggregates["safety_overrides"] = summarise_series(
        [float(e.safety_overrides) for e in episodes])

    if label is None:
        label = "fixed_time" if controller == "fixed_time" else f"{controller} {version}"
    result = EvalResult(
        label=label, controller=controller, scenario=scenario_id,
        model_version=version, checkpoint=str(checkpoint) if checkpoint else None,
        seeds=list(seeds), episodes=episodes, aggregates=aggregates,
    )
    log.info("evaluation complete", **{
        "label": label, "scenario": scenario_id, "episodes": len(episodes),
        "avg_waiting_s": result.mean("traffic.avg_waiting_s"),
        "throughput_vph": result.mean("traffic.throughput_vph"),
        "emergency_delay_s": result.mean("emergency.emergency_delay_s"),
    })
    return result


def improvement_pct(baseline: EvalResult, candidate: EvalResult, key: str) -> float | None:
    """Signed % improvement of `candidate` over `baseline` for one metric.

    Positive = candidate is better (accounting for whether lower or higher is better).
    Returns None when the baseline mean is ~0 (no meaningful ratio).
    """
    base = baseline.mean(key)
    cand = candidate.mean(key)
    if base is None or cand is None or abs(base) < 1e-9:
        return None
    lower_better = METRIC_DIRECTION.get(key, True)
    delta = (base - cand) if lower_better else (cand - base)
    return round(100.0 * delta / abs(base), 1)


def compare(results: list[EvalResult], *, baseline_label: str = "fixed_time") -> dict:
    """Build a comparison blob: per-metric mean/CI per result + improvement % vs baseline."""
    by_label = {r.label: r for r in results}
    baseline = by_label.get(baseline_label) or results[0]
    rows: dict[str, dict] = {}
    for key in METRIC_KEYS:
        rows[key] = {
            "lower_is_better": METRIC_DIRECTION[key],
            "values": {
                r.label: {
                    "mean": round(r.aggregates[key]["mean"], 4),
                    "ci_half_width": round(r.aggregates[key]["ci_half_width"], 4),
                    "improvement_pct_vs_baseline": (
                        None if r.label == baseline.label
                        else improvement_pct(baseline, r, key)
                    ),
                }
                for r in results
            },
        }
    return {
        "scenario": baseline.scenario,
        "baseline": baseline.label,
        "seeds": baseline.seeds,
        "n_episodes": len(baseline.episodes),
        "metrics": rows,
    }


def write_report(results: list[EvalResult], out_dir: str | Path, *,
                 baseline_label: str = "fixed_time") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"eval-{stamp}.json"
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "comparison": compare(results, baseline_label=baseline_label),
        "results": [asdict(r) for r in results],
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path
