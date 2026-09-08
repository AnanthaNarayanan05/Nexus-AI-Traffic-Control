"""SimulationManager - the live decision loop (docs/architecture.md section 2).

Owns exactly one running simulation and wires the pipeline:

    A2C / DQN / PPO  ->  COORDINATION  ->  SAFETY  ->  SIGNAL  ->  SIMULATION

Three objective-specific agents (R10): A2C emergency priority, DQN efficiency /
fuel / emissions / safety, PPO adaptive congestion reduction. Each recommends; the
coordinator selects a candidate; the authoritative safety layer has the final word.

Two decoupled cadences (spec section 72):
  * physics  - every `simulation.step_length_s` of simulated time
  * decision - every `simulation.decision_interval_s` of simulated time

Everything that touches the adapter or the agents runs on this manager's own thread.
API callers mutate state only by enqueueing a command, and read state either from the
published immutable snapshot or via `submit()` (which runs on the loop thread).
"""

from __future__ import annotations

import queue
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.agents.a2c import A2CAgent
from app.agents.common.base import BaseAgent
from app.agents.common.resolve import action_to_command
from app.agents.common.rewards import make_reward_context
from app.agents.dqn import DQNAgent
from app.agents.ppo import PPOAgent
from app.control import FixedTimeController, manual_command
from app.coordination import Coordinator
from app.core.config import get_config, get_settings
from app.logging import get_logger
from app.metrics import MetricsAggregator
from app.safety import SafetyValidator
from app.scenarios import get_scenario
from app.schemas.agents import RewardBreakdown
from app.schemas.coordination import CoordinationDecision
from app.schemas.enums import AgentName, ControlMode, EventCategory, Severity
from app.schemas.events import DecisionRecord, EventMessage
from app.schemas.metrics import MetricSnapshot
from app.schemas.safety import PhaseCommand, SafetyResult
from app.schemas.scenario import ScenarioConfig
from app.schemas.simulation import SimulationState
from app.simulation.adapter import SimEvent, get_adapter

log = get_logger("SYSTEM")

_EVENT_CATEGORIES = {c.value: c for c in EventCategory}
_SEVERITIES = {s.value: s for s in Severity}

# replay capture thresholds
_MIN_REPLAY_DECISIONS = 3      # a run shorter than this is not worth persisting
_MAX_REPLAY_FRAMES = 5000      # ~8 h of sim at the decision cadence - a hard safety cap
_MAX_REPLAY_EVENTS = 8000
_REPLAY_KEEP = 40             # storage cap: prune to the newest N on each new capture


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _Pending:
    """The decision awaiting its realised reward (rewards need prev + curr state)."""

    __slots__ = ("state", "actions", "action_names", "phase_changed", "record_id")

    def __init__(self, state: SimulationState, actions: dict[AgentName, int],
                 action_names: dict[AgentName, str], record_id: str) -> None:
        self.state = state
        self.actions = actions
        self.action_names = action_names
        self.phase_changed = False
        self.record_id = record_id


class SimulationManager:
    def __init__(self) -> None:
        cfg = get_config()
        sim = cfg.simulation
        self.step_length_s = float(sim.step_length_s)
        self.decision_interval_s = float(sim.decision_interval_s)
        self.stream_hz = float(sim.stream_hz)
        self.default_seed = int(sim.seed)

        self.adapter = get_adapter()
        self.a2c = A2CAgent(seed=self.default_seed)
        self.dqn = DQNAgent(seed=self.default_seed)
        self.ppo = PPOAgent(seed=self.default_seed)
        self.agents: dict[AgentName, BaseAgent] = {
            AgentName.A2C: self.a2c, AgentName.DQN: self.dqn, AgentName.PPO: self.ppo,
        }
        # Which weights each agent is running: "untrained" (fresh init) or "trained"
        # (a validated checkpoint from the registry). Starts untrained - the live app
        # makes no claim of a learned policy until a checkpoint is loaded here (§84).
        self._model_mode: dict[AgentName, str] = {n: "untrained" for n in self.agents}
        self._model_source: dict[AgentName, str | None] = {n: None for n in self.agents}
        self.coordinator = Coordinator()
        self.safety = SafetyValidator()
        self.metrics = MetricsAggregator(self.adapter)
        self.fixed_time = FixedTimeController()

        self.mode = ControlMode.AI
        self.speed = 1.0
        self.running = False
        self.scenario: ScenarioConfig = get_scenario("normal")

        # published, read by API/WS threads (single-attribute assignment is atomic)
        self._state: SimulationState | None = None
        self._metrics: MetricSnapshot = MetricSnapshot()
        self._decision: DecisionRecord | None = None
        self._coordination: CoordinationDecision | None = None
        self._safety_result: SafetyResult | None = None
        self._seq = 0

        self._events: deque[EventMessage] = deque(maxlen=500)
        self._event_seq = 0
        self._event_ids: dict[str, int] = {}
        self._decisions: deque[DecisionRecord] = deque(maxlen=400)

        # replay capture: the full (uncapped-per-run) decision + event timeline of the
        # current run, persisted to the `replays` table on episode end / teardown / capture.
        self._run_id: str = ""
        self._run_started_iso: str = ""
        self._run_seed: int = self.default_seed
        self._timeline: list[DecisionRecord] = []
        self._timeline_events: list[EventMessage] = []

        self._pending: _Pending | None = None
        self._last_decision_t = -1e9
        self._sim_budget = 0.0
        self._episode_returns: dict[AgentName, float] = {n: 0.0 for n in self.agents}
        self._episode_done = False

        self._commands: queue.Queue[tuple[Callable[[], Any], Any]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

        self._reset_locked(self.scenario, self.default_seed)

    # ================================================================= lifecycle
    def start_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="nexus-sim", daemon=True)
        self._thread.start()
        log.info("simulation loop thread started", adapter=self.adapter.name)

    def shutdown(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        try:
            self._persist_replay(complete=self._episode_done, reason="shutdown")
        except Exception:  # noqa: BLE001 - shutdown must never raise
            log.error("replay capture on shutdown failed", exc_info=True)
        log.info("simulation loop thread stopped")

    # ================================================================= commands
    def submit(self, fn: Callable[[], Any], *, timeout: float = 5.0) -> Any:
        """Run `fn` on the loop thread and return its result (or raise its exception)."""
        if self._thread is None or not self._thread.is_alive():
            return fn()  # no loop running: safe to execute inline
        box: dict[str, Any] = {}
        done = threading.Event()

        def wrapper() -> None:
            try:
                box["value"] = fn()
            except Exception as exc:  # noqa: BLE001 - surfaced to the caller
                box["error"] = exc
            finally:
                done.set()

        self._commands.put((wrapper, None))
        if not done.wait(timeout):
            raise TimeoutError("simulation command timed out")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def start(self) -> dict:
        def op() -> dict:
            self.running = True
            self._episode_done = False
            self._emit(EventCategory.SYSTEM, Severity.INFO, "Simulation started")
            return self.status()
        return self.submit(op)

    def pause(self) -> dict:
        def op() -> dict:
            self.running = False
            self._emit(EventCategory.SYSTEM, Severity.INFO, "Simulation paused")
            return self.status()
        return self.submit(op)

    def reset(self, scenario_id: str | None = None, seed: int | None = None) -> dict:
        def op() -> dict:
            sc = get_scenario(scenario_id) if scenario_id else self.scenario.model_copy(deep=True)
            self._reset_locked(sc, seed if seed is not None else sc.seed)
            self._emit(EventCategory.SYSTEM, Severity.INFO,
                       f"Reset to scenario '{sc.name}' (seed {seed if seed is not None else sc.seed})")
            return self.status()
        return self.submit(op)

    def load_scenario(self, scenario: ScenarioConfig, seed: int | None = None) -> dict:
        def op() -> dict:
            self._reset_locked(scenario, seed if seed is not None else scenario.seed)
            self._emit(EventCategory.SYSTEM, Severity.NOTICE, f"Scenario loaded: {scenario.name}")
            return self.status()
        return self.submit(op)

    def set_mode(self, mode: str) -> dict:
        def op() -> dict:
            self.mode = ControlMode(mode)
            self.adapter.set_mode(self.mode.value)
            self._pending = None  # rewards from a different controller are not comparable
            self._emit(EventCategory.SYSTEM, Severity.NOTICE, f"Control mode -> {self.mode.value}")
            return self.status()
        return self.submit(op)

    _AGENT_CLASSES = {AgentName.A2C: A2CAgent, AgentName.DQN: DQNAgent, AgentName.PPO: PPOAgent}

    def set_model(self, agent: str, mode: str, version: str | None = None) -> dict:
        """Swap an agent between fresh (``untrained``) weights and a registry checkpoint.

        A ``trained`` request is honoured only if a checkpoint file actually exists and,
        once loaded, reports ``trained_episodes > 0`` - otherwise it fails and the agent
        is left untouched (no fake ``is_trained`` badge, §84 / §114). Safety stays
        authoritative regardless of which weights run (§113).
        """
        try:
            name = AgentName(agent.lower())
        except ValueError as exc:
            raise ValueError(f"unknown agent {agent!r}") from exc
        if name not in self._AGENT_CLASSES:
            raise ValueError(f"agent {name.value!r} is not a known RL agent (A2C, DQN, PPO)")
        mode = mode.lower()
        if mode not in ("untrained", "trained"):
            raise ValueError(f"mode must be 'untrained' or 'trained' (got {mode!r})")
        cls = self._AGENT_CLASSES[name]

        if mode == "untrained":
            fresh = cls(seed=self.default_seed)
            source_id = None
            note = "fresh weights"
        else:
            from app.persistence import ModelRegistry
            reg = ModelRegistry()
            rows = reg.list(agent=name.value)
            if version:
                row = next((r for r in rows if r["version"] == version or r["id"] == version), None)
            else:
                row = reg.active(name.value) or reg.latest(name.value)
            if row is None:
                raise ValueError(f"no {'matching ' if version else 'trained '}model for {name.value}")
            ckpt = Path(row["checkpoint_path"])
            if not ckpt.is_file():
                raise ValueError(f"checkpoint missing on disk: {ckpt}")
            fresh = cls(seed=self.default_seed)
            fresh.load(ckpt)
            if not fresh.is_trained:
                raise ValueError(f"checkpoint {ckpt.name} has trained_episodes=0 - not a trained model")
            source_id = row["id"]
            note = f"{row['id']} ({fresh.model_version})"

        def op() -> dict:
            self.agents[name] = fresh
            if name == AgentName.A2C:
                self.a2c = fresh
            elif name == AgentName.DQN:
                self.dqn = fresh
            else:
                self.ppo = fresh
            self._model_mode[name] = mode
            self._model_source[name] = source_id
            self._pending = None  # mixing policies mid-decision is not comparable
            self._emit(EventCategory.SYSTEM, Severity.NOTICE,
                       f"{name.value.upper()} model -> {mode.upper()}: {note}")
            return self.status()
        return self.submit(op)

    def set_speed(self, speed: float) -> dict:
        def op() -> dict:
            self.speed = max(0.1, min(20.0, float(speed)))
            return self.status()
        return self.submit(op)

    def manual_action(self, action: str) -> dict:
        def op() -> dict:
            if self.mode != ControlMode.MANUAL:
                raise ValueError(f"manual actions require MANUAL mode (current: {self.mode.value})")
            state = self.adapter.get_state()
            cmd = manual_command(action, state)
            result = self.safety.validate(cmd, state)
            self.adapter.apply_phase(result.command)
            self._safety_result = result
            self._emit(
                EventCategory.SAFETY if result.was_override else EventCategory.AI,
                Severity.WARNING if result.was_override else Severity.INFO,
                f"Manual {action}: {result.reason}",
            )
            return {"action": action, "safety": result.model_dump(mode="json")}
        return self.submit(op)

    def inject(self, kind: str, args: dict | None = None) -> dict:
        def op() -> dict:
            ids = self.adapter.inject(SimEvent(kind=kind, args=dict(args or {})))
            self._drain_adapter_events()
            return {"injected": kind, "ids": ids}
        return self.submit(op)

    def step_once(self, ticks: int = 1) -> dict:
        """Advance the physics by N ticks while paused (single-step debugging)."""
        def op() -> dict:
            for _ in range(max(1, int(ticks))):
                self._tick()
            self._publish()
            return self.status()
        return self.submit(op)

    # ================================================================= reads
    def status(self) -> dict:
        state = self._state
        return {
            "running": self.running,
            "mode": self.mode.value,
            "speed": self.speed,
            "adapter": self.adapter.name,
            "scenario": {"id": self.scenario.id, "name": self.scenario.name,
                         "duration_s": self.scenario.duration_s, "seed": self.scenario.seed},
            "sim_time": state.sim_time if state else 0.0,
            "step": state.step if state else 0,
            "episode_done": self._episode_done,
            "seq": self._seq,
            "agents": {n.value: a.status().model_dump(mode="json") for n, a in self.agents.items()},
            "model_modes": {n.value: self._model_mode[n] for n in self.agents},
            "model_sources": {n.value: self._model_source[n] for n in self.agents},
            "safety": {"overrides_total": self.safety.overrides_total,
                       "checks_total": self.safety.checks_total},
            "config_digest": get_config().digest,
            "env": get_settings().env,
        }

    def state(self) -> SimulationState | None:
        return self._state

    def latest_metrics(self) -> MetricSnapshot:
        return self._metrics

    def latest_decision(self) -> DecisionRecord | None:
        return self._decision

    def latest_coordination(self) -> CoordinationDecision | None:
        return self._coordination

    def latest_safety(self) -> SafetyResult | None:
        return self._safety_result

    def decisions(self, limit: int = 50) -> list[DecisionRecord]:
        return list(self._decisions)[-limit:][::-1]

    def events_since(self, after: int = 0, limit: int = 200) -> list[EventMessage]:
        out = [e for e in self._events if self._event_ids.get(e.id, 0) > after]
        return out[-limit:]

    def event_cursor(self) -> int:
        return self._event_seq

    def agent_inspector(self, name: str) -> dict:
        agent = self.agents[AgentName(name)]

        def op() -> dict:
            state = self.adapter.get_state()
            return agent.inspect(state).model_dump(mode="json")
        return self.submit(op)

    def snapshot(self) -> dict:
        """Everything the dashboard needs in one immutable read."""
        state = self._state
        return {
            "seq": self._seq,
            "status": self.status(),
            "state": state.model_dump(mode="json") if state else None,
            "metrics": self._metrics.model_dump(mode="json"),
            "coordination": (self._coordination.model_dump(mode="json")
                             if self._coordination else None),
            "safety": (self._safety_result.model_dump(mode="json")
                       if self._safety_result else None),
            "decision": self._decision.model_dump(mode="json") if self._decision else None,
        }

    # ================================================================= loop
    def _loop(self) -> None:
        interval = 1.0 / max(self.stream_hz, 1.0)
        next_at = time.perf_counter()
        while not self._stop.is_set():
            now = time.perf_counter()
            if now < next_at:
                time.sleep(min(interval, next_at - now))
                continue
            frame_start = time.perf_counter()
            self._drain_commands()

            if self.running and not self._episode_done:
                self._sim_budget += interval * self.speed
                guard = 0
                while self._sim_budget >= self.step_length_s and guard < 200:
                    self._tick()
                    self._sim_budget -= self.step_length_s
                    guard += 1
                if guard >= 200:  # cannot keep up: drop the backlog rather than spiral
                    self._sim_budget = 0.0

            self._publish()
            self.metrics.record_dev(
                frame_time_ms=(time.perf_counter() - frame_start) * 1000.0,
                fps=self.stream_hz,
            )
            next_at += interval
            if next_at < time.perf_counter() - 1.0:  # long stall: resync
                next_at = time.perf_counter()

    def _drain_commands(self) -> None:
        while True:
            try:
                fn, _ = self._commands.get_nowait()
            except queue.Empty:
                return
            try:
                fn()
            except Exception:  # noqa: BLE001 - never kill the loop
                log.error("command failed", exc_info=True)

    def _tick(self) -> None:
        t0 = time.perf_counter()
        self.adapter.step(self.step_length_s)
        self.metrics.record_dev(sim_step_ms=(time.perf_counter() - t0) * 1000.0)
        self._drain_adapter_events()

        sim_t = self.adapter.sim_time
        if sim_t - self._last_decision_t >= self.decision_interval_s:
            self._last_decision_t = sim_t
            self._decide()
        if sim_t >= self.scenario.duration_s:
            self._finish_episode()

    # ================================================================= decision
    def _decide(self) -> None:
        t0 = time.perf_counter()
        state = self.adapter.get_state()

        rewards, breakdowns = self._realise_pending_rewards(state)

        if self.mode == ControlMode.AI:
            decision, result, actions, names = self._decide_ai(state)
        elif self.mode == ControlMode.FIXED_TIME:
            decision, result, actions, names = self._decide_fixed(state)
        else:  # MANUAL - the operator drives; safety still bounds the held phase
            decision, result, actions, names = self._decide_manual_hold(state)

        self.adapter.apply_phase(result.command)
        self._coordination = decision
        self._safety_result = result

        ai_latency_ms = (time.perf_counter() - t0) * 1000.0
        self.metrics.record_dev(ai_latency_ms=ai_latency_ms)
        snapshot = self.metrics.rolling(state, unsafe_transitions=0, include_dev=True)
        self._metrics = snapshot

        record = DecisionRecord(
            t=state.sim_time, step=state.step,
            state_summary=_state_summary(state),
            recommendations={r.agent.value: r.model_dump(mode="json")
                             for r in decision.recommendations},
            coordination=decision, safety=result,
            rewards=rewards, reward_breakdowns=breakdowns,
            metrics=snapshot, applied_phase=result.command.target_phase.value,
        )
        self._decision = record
        self._decisions.append(record)
        if len(self._timeline) < _MAX_REPLAY_FRAMES:
            self._timeline.append(record)

        self._emit(EventCategory.AI, Severity.INFO,
                   f"{decision.winner.upper()} -> {decision.candidate_phase.value} "
                   f"({decision.basis.replace('_', ' ')}); applied {result.command.summary()}",
                   meta={"decision_id": record.id})
        if result.was_override:
            self._emit(EventCategory.SAFETY,
                       Severity.CRITICAL if result.action_taken.value == "EMERGENCY_TIMEOUT"
                       else Severity.WARNING,
                       f"{result.action_taken.value}: {result.reason}")

        if self.mode == ControlMode.AI:
            self._pending = _Pending(state, actions, names, record.id)
        else:
            self._pending = None

    def _decide_ai(self, state: SimulationState):
        recs = [self.agents[n].act(state)
                for n in (AgentName.A2C, AgentName.DQN, AgentName.PPO)]
        decision = self.coordinator.resolve(recs, state)
        by_agent = {r.agent: r for r in recs}

        winner_rec = by_agent.get(AgentName(decision.winner)) if decision.winner in _AGENT_NAMES else None
        if winner_rec is not None:
            action_name = winner_rec.action_name
        elif decision.candidate_phase == state.signal.served_phase:
            action_name = "MAINTAIN"
        else:
            action_name = "SWITCH"

        cmd = action_to_command(action_name, decision.candidate_phase,
                                state.signal.served_phase, source="coordinator")
        result = self.safety.validate(cmd, state)
        actions = {r.agent: r.action_index for r in recs}
        names = {r.agent: r.action_name for r in recs}
        return decision, result, actions, names

    def _decide_fixed(self, state: SimulationState):
        cmd = self.fixed_time.decide(state)
        result = self.safety.validate(cmd, state)
        decision = CoordinationDecision(
            candidate_phase=cmd.target_phase, winner="fixed_time", basis="fixed_schedule",
            ladder_trace=[], scores=[], recommendations=[],
        )
        return decision, result, {}, {}

    def _decide_manual_hold(self, state: SimulationState):
        cmd = PhaseCommand(target_phase=state.signal.served_phase, source="manual")
        result = self.safety.validate(cmd, state)
        decision = CoordinationDecision(
            candidate_phase=cmd.target_phase, winner="manual", basis="operator_hold",
            ladder_trace=[], scores=[], recommendations=[],
        )
        return decision, result, {}, {}

    def _realise_pending_rewards(self, state: SimulationState) -> tuple[dict[str, float], dict[str, Any]]:
        """Close out the previous decision: real reward -> observe -> learn."""
        cleared = self.adapter.mark_interval()
        pending = self._pending
        if pending is None:
            return {}, {}

        prev = pending.state
        rewards: dict[str, float] = {}
        breakdowns: dict[str, Any] = {}
        for name, agent in self.agents.items():
            action_name = pending.action_names.get(name, "MAINTAIN")
            ctx = make_reward_context(
                prev, state, action_name=action_name,
                vehicles_cleared=cleared, interval_s=self.decision_interval_s,
            )
            rb: RewardBreakdown = agent.compute_reward(ctx)
            rewards[name.value] = round(rb.total, 4)
            breakdowns[name.value] = rb.model_dump(mode="json")
            agent.note_reward(rb.total)
            self._episode_returns[name] += rb.total
            agent.observe(prev, pending.actions.get(name, 0), rb.total, state, False)
            stats = agent.learn()
            if stats:
                log.debug("agent update", agent=name.value, **{k: round(v, 5) for k, v in stats.items()})
        return rewards, breakdowns

    # ================================================================= episode
    def _finish_episode(self) -> None:
        if self._episode_done:
            return
        self._episode_done = True
        self.running = False
        state = self.adapter.get_state()
        episode = self.metrics.episode(state)
        self._metrics = episode
        for name, agent in self.agents.items():
            agent.end_episode(self._episode_returns[name])
        self._emit(EventCategory.SYSTEM, Severity.NOTICE,
                   f"Episode complete at t={state.sim_time:.0f}s "
                   f"(throughput {episode.traffic.throughput_vph:.0f} vph, "
                   f"avg wait {episode.traffic.avg_waiting_s:.1f}s)",
                   meta={"episode_metrics": episode.flat()})
        log.info("episode complete", sim_time=state.sim_time,
                 returns={n.value: round(v, 2) for n, v in self._episode_returns.items()},
                 metrics=episode.flat())
        self._persist_replay(complete=True, reason="episode_complete")

    # ================================================================= internals
    def _reset_locked(self, scenario: ScenarioConfig, seed: int) -> None:
        # persist whatever the outgoing run captured before we wipe it (no-op on the
        # first call from __init__, and for runs with too few decisions to be useful)
        self._persist_replay(complete=self._episode_done, reason="teardown")

        self.scenario = scenario
        self.adapter.reset(scenario, seed)
        self.adapter.set_mode(self.mode.value)
        self.safety.reset()
        self.metrics.reset()
        self._pending = None
        self._last_decision_t = -1e9
        self._sim_budget = 0.0
        self._episode_returns = {n: 0.0 for n in self.agents}
        self._episode_done = False
        self._decision = None
        self._coordination = None
        self._safety_result = None
        self._decisions.clear()
        self._events.clear()
        self._event_ids.clear()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._run_id = f"replay-{stamp}-{uuid.uuid4().hex[:6]}"
        self._run_started_iso = _utcnow_iso()
        self._run_seed = int(seed)
        self._timeline = []
        self._timeline_events = []
        self._publish()

    # ---------------------------------------------------------------- replay capture
    def _build_replay_record(self, *, complete: bool) -> dict | None:
        """Freeze the current run's timeline into a `replays` row dict, or None if the
        run is too short to be worth keeping."""
        if len(self._timeline) < _MIN_REPLAY_DECISIONS:
            return None
        last_t = self._timeline[-1].t
        complete_flag = bool(complete or self._episode_done)
        tag = "episode" if complete_flag else "partial"
        return {
            "id": self._run_id or f"replay-{uuid.uuid4().hex[:12]}",
            "label": f"{self.scenario.name} · seed {self._run_seed} · "
                     f"{self.mode.value} · {tag}",
            "created_at": _utcnow_iso(),
            "scenario_id": self.scenario.id,
            "scenario_name": self.scenario.name,
            "seed": int(self._run_seed),
            "mode": self.mode.value,
            "model_modes": {n.value: self._model_mode[n] for n in self.agents},
            "config_digest": get_config().digest,
            "sim_duration_s": float(last_t),
            "decision_count": len(self._timeline),
            "episode_complete": complete_flag,
            "timeline": [d.model_dump(mode="json") for d in self._timeline],
            "events": [e.model_dump(mode="json") for e in self._timeline_events],
            "episode_metrics": self._metrics.flat() if complete_flag else None,
        }

    def _persist_replay(self, *, complete: bool, reason: str = "") -> dict | None:
        record = self._build_replay_record(complete=complete)
        if record is None:
            return None
        try:
            from app.persistence.replays import ReplayStore

            store = ReplayStore()
            saved = store.save(record)
            store.prune(keep=_REPLAY_KEEP)
        except Exception as exc:  # noqa: BLE001 - persistence is optional; never kill the loop
            log.error("replay not persisted", run=self._run_id, reason=reason, error=str(exc))
            return None
        log.info("replay captured", run=self._run_id, reason=reason,
                 decisions=saved["decision_count"], complete=saved["episode_complete"])
        return saved

    def capture_replay(self) -> dict | None:
        """Force-persist the current run even if it has not finished (user 'save run')."""
        return self.submit(lambda: self._persist_replay(complete=self._episode_done,
                                                        reason="manual"))

    def list_replays(self, limit: int = 50) -> list[dict]:
        from app.persistence.replays import ReplayStore

        return ReplayStore().list(limit=limit)

    def get_replay(self, replay_id: str) -> dict | None:
        from app.persistence.replays import ReplayStore

        return ReplayStore().get(replay_id)

    def delete_replay(self, replay_id: str) -> None:
        from app.persistence.replays import ReplayStore, ReplayStoreError

        try:
            ReplayStore().delete(replay_id)
        except ReplayStoreError as exc:
            raise KeyError(str(exc)) from exc

    def _publish(self) -> None:
        state = self.adapter.get_state()
        self._state = state
        self._seq += 1

    def _drain_adapter_events(self) -> None:
        for raw in self.adapter.drain_events():
            self._emit(
                _EVENT_CATEGORIES.get(raw.get("category", "SYSTEM"), EventCategory.SYSTEM),
                _SEVERITIES.get(raw.get("severity", "info"), Severity.INFO),
                raw.get("description", ""),
                t=raw.get("t"), meta=raw.get("meta", {}),
            )

    def _emit(self, category: EventCategory, severity: Severity, description: str,
              *, t: float | None = None, meta: dict | None = None) -> EventMessage:
        with self._lock:
            self._event_seq += 1
            ev = EventMessage(
                id=uuid.uuid4().hex[:12],
                t=float(t if t is not None else self.adapter.sim_time),
                category=category, severity=severity, description=description, meta=meta or {},
            )
            self._events.append(ev)
            self._event_ids[ev.id] = self._event_seq
            if len(self._timeline_events) < _MAX_REPLAY_EVENTS:
                self._timeline_events.append(ev)
            if len(self._event_ids) > 2000:
                live = {e.id for e in self._events}
                self._event_ids = {k: v for k, v in self._event_ids.items() if k in live}
        return ev


_AGENT_NAMES = {n.value for n in AgentName}


def _state_summary(state: SimulationState) -> dict[str, Any]:
    return {
        "sim_time": state.sim_time,
        "phase": state.signal.current_phase.value,
        "served_phase": state.signal.served_phase.value,
        "phase_elapsed_s": state.signal.phase_elapsed_s,
        "total_vehicles": state.total_vehicles,
        "total_queue": state.total_queue,
        "queues": {a.value: ap.queue_length for a, ap in state.approaches.items()},
        "emergency_active": state.emergency.active,
        "emergency_approach": (state.emergency.approach.value
                               if state.emergency.approach else None),
        "throughput_vph": state.estimates.throughput_vph,
        "violations_total": state.safety.violations_total,
    }


# ------------------------------------------------------------------ singleton
_MANAGER: SimulationManager | None = None


def get_manager() -> SimulationManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = SimulationManager()
    return _MANAGER
