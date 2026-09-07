"""Headless single-agent training environment (spec sections 100, 113; docs/training.md).

Drives one agent through complete episodes against a fresh built-in simulation, using
exactly the pipeline the live `SimulationManager` uses for that one agent:

    agent.act  ->  resolve_phase  ->  action_to_command  ->  SafetyValidator  ->  apply_phase

The other two agents are absent: each policy is trained against its own objective in
isolation (PPT slide 20 - "three reward functions, one behind each algorithm").
Coordination is an inference-time concern and plays no part in single-agent training.

Safety stays authoritative here exactly as in production (spec section 113): the policy
never observes the effect of an action the safety layer would have rewritten or blocked -
it observes the effect of `result.command`, the command that was actually applied.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.agents.common.base import BaseAgent
from app.agents.common.resolve import action_to_command
from app.agents.common.rewards import make_reward_context
from app.core.config import get_config
from app.metrics import MetricsAggregator
from app.safety import SafetyValidator
from app.schemas.enums import ControlMode
from app.schemas.metrics import MetricSnapshot
from app.schemas.scenario import ScenarioConfig
from app.schemas.simulation import SimulationState
from app.simulation.builtin.engine import BuiltinAdapter


@dataclass
class EpisodeResult:
    """Everything one episode produced. All fields are measured, none estimated."""

    index: int
    episode_return: float
    decisions: int
    updates: int              # number of gradient steps that actually ran
    safety_overrides: int     # safety-layer interventions during the episode
    safety_checks: int
    mean_reward: float
    losses: dict[str, float]  # episode-mean of whatever the agent's learn() reported
    metrics: MetricSnapshot
    wall_time_s: float


class TrainingEnv:
    """One agent, one scenario, repeatable episodes."""

    def __init__(self, agent: BaseAgent, scenario: ScenarioConfig, *, seed: int) -> None:
        sim = get_config().simulation
        self.agent = agent
        self.scenario = scenario
        self.seed = int(seed)
        self.step_length_s = float(sim.step_length_s)
        self.decision_interval_s = float(sim.decision_interval_s)
        self.adapter = BuiltinAdapter()
        self.safety = SafetyValidator()
        self.metrics = MetricsAggregator(self.adapter)

    def run_episode(self, index: int, *, episode_seed: int | None = None) -> EpisodeResult:
        seed = self.seed if episode_seed is None else int(episode_seed)
        self.adapter.reset(self.scenario, seed)
        self.adapter.set_mode(ControlMode.AI.value)
        self.safety.reset()
        self.metrics.reset()

        t0 = time.perf_counter()
        duration_s = float(self.scenario.duration_s)
        last_decision_t = -1e9
        pending: tuple[SimulationState, int, str] | None = None
        episode_return = 0.0
        decisions = 0
        loss_sums: dict[str, float] = {}
        loss_n = 0

        def realise(curr: SimulationState, *, done: bool) -> None:
            nonlocal pending, episode_return, loss_n
            cleared = self.adapter.mark_interval()
            if pending is None:
                return
            prev, action_index, action_name = pending
            ctx = make_reward_context(
                prev, curr, action_name=action_name,
                vehicles_cleared=cleared, interval_s=self.decision_interval_s,
            )
            rb = self.agent.compute_reward(ctx)
            self.agent.note_reward(rb.total)
            episode_return += rb.total
            self.agent.observe(prev, action_index, rb.total, curr, done)
            stats = self.agent.learn()
            if stats:
                for key, val in stats.items():
                    loss_sums[key] = loss_sums.get(key, 0.0) + float(val)
                loss_n += 1
            pending = None

        # physics ticks at step_length_s; a decision every decision_interval_s of sim time
        max_ticks = int(duration_s / self.step_length_s) + 4
        for _ in range(max_ticks):
            if self.adapter.sim_time >= duration_s:
                break
            self.adapter.step(self.step_length_s)
            self.adapter.drain_events()
            sim_t = self.adapter.sim_time
            if sim_t - last_decision_t >= self.decision_interval_s:
                last_decision_t = sim_t
                state = self.adapter.get_state()
                realise(state, done=False)                     # close out the prior decision
                rec = self.agent.act(state)                    # stochastic: agent.training is True
                phase = self.agent.resolve_phase(rec.action_index, state)
                cmd = action_to_command(rec.action_name, phase, state.signal.served_phase,
                                        source="trainer")
                result = self.safety.validate(cmd, state)      # authoritative (spec section 113)
                self.adapter.apply_phase(result.command)
                pending = (state, rec.action_index, rec.action_name)
                decisions += 1

        final_state = self.adapter.get_state()
        realise(final_state, done=True)                        # terminal transition
        flushed = self.agent.learn(force=True)                 # drain any on-policy remainder
        if flushed:
            for key, val in flushed.items():
                loss_sums[key] = loss_sums.get(key, 0.0) + float(val)
            loss_n += 1
        self.agent.end_episode(episode_return)

        episode_metrics = self.metrics.episode(
            final_state, unsafe_transitions=self.safety.overrides_total)
        losses = {k: round(v / loss_n, 5) for k, v in loss_sums.items()} if loss_n else {}
        mean_reward = episode_return / decisions if decisions else 0.0
        return EpisodeResult(
            index=index,
            episode_return=round(episode_return, 4),
            decisions=decisions,
            updates=loss_n,
            safety_overrides=self.safety.overrides_total,
            safety_checks=self.safety.checks_total,
            mean_reward=round(mean_reward, 4),
            losses=losses,
            metrics=episode_metrics,
            wall_time_s=round(time.perf_counter() - t0, 2),
        )
