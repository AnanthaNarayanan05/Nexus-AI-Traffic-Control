"""DQN agent - Fuel / Emission / Efficiency / Safety (docs/dqn.md)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from app.agents.common.base import BaseAgent, softmax
from app.agents.common.features import Normalizer
from app.agents.common.networks import soft_update
from app.agents.common.replay import ReplayBuffer, Transition
from app.agents.common.resolve import other_ring
from app.agents.common.rewards import RewardContext
from app.agents.dqn.network import QNetwork
from app.agents.dqn.reward import dqn_reward
from app.agents.dqn.state import STATE_DIM, build_dqn_state
from app.core.config import get_config
from app.logging import get_logger
from app.schemas.agents import AgentInspectorPayload, AgentRecommendation, RewardBreakdown
from app.schemas.enums import AgentName, Phase
from app.schemas.simulation import SimulationState

log = get_logger("DQN")


class DQNAction(IntEnum):
    KEEP_GREEN = 0
    EXTEND_GREEN = 1
    SWITCH_PHASE = 2
    REDUCE_GREEN = 3
    TRANSITION = 4


ACTION_LABELS = ["KEEP_GREEN", "EXTEND_GREEN", "SWITCH_PHASE", "REDUCE_GREEN", "TRANSITION"]


@dataclass
class _TrainStats:
    q_loss: float = 0.0
    td_error: float = 0.0
    mean_q: float = 0.0
    updates: int = 0
    episode_returns: list[float] = field(default_factory=list)


class DQNAgent(BaseAgent):
    name = AgentName.DQN
    action_labels = ACTION_LABELS
    state_dim = STATE_DIM

    def __init__(self, seed: int = 0, training: bool = False) -> None:
        super().__init__()
        cfg = get_config().rl
        torch.manual_seed(seed)
        self.device = torch.device("cpu")
        self.q = QNetwork(STATE_DIM, len(DQNAction), int(cfg.hidden_dim))
        self.target = QNetwork(STATE_DIM, len(DQNAction), int(cfg.hidden_dim))
        self.target.load_state_dict(self.q.state_dict())
        self.opt = torch.optim.Adam(self.q.parameters(), lr=float(cfg.learning_rate))
        self.gamma = float(cfg.gamma)
        d = cfg.dqn
        self.buffer = ReplayBuffer(int(d.replay_capacity), STATE_DIM, seed=seed)
        self.learning_starts = int(d.learning_starts)
        self.target_update_interval = int(d.target_update_interval)
        self.train_freq = int(d.train_freq)
        self.batch_size = int(cfg.batch_size)
        self.eps_start = float(d.epsilon_start)
        self.eps_end = float(d.epsilon_end)
        self.eps_decay_steps = int(d.epsilon_decay_steps)
        self.training = training
        self.norm = Normalizer()

        self._env_steps = 0
        self._train_steps = 0
        self.stats = _TrainStats()
        self._rng = np.random.default_rng(seed)
        self._last_q = np.zeros(len(DQNAction), dtype=np.float32)
        self._last_action = DQNAction.KEEP_GREEN
        self.model_version = "dqn-untrained"

    # ---------------------------------------------------------------- epsilon
    @property
    def epsilon(self) -> float:
        if not self.training:
            return self.eps_end
        frac = min(1.0, self._env_steps / max(1, self.eps_decay_steps))
        return self.eps_start + frac * (self.eps_end - self.eps_start)

    # ---------------------------------------------------------------- state
    def build_state(self, state: SimulationState):
        return build_dqn_state(state, self.norm)

    def _features(self, state: SimulationState) -> np.ndarray:
        fv = self.build_state(state)
        self._last_features = fv
        return fv.array()

    # ---------------------------------------------------------------- inference
    def act(self, state: SimulationState, *, explore: bool | None = None) -> AgentRecommendation:
        t0 = time.perf_counter()
        feats = self._features(state)
        with torch.no_grad():
            q = self.q(torch.from_numpy(feats).unsqueeze(0)).squeeze(0).numpy()
        self._last_q = q
        do_explore = self.training if explore is None else explore
        if do_explore and self._rng.random() < self.epsilon:
            action = int(self._rng.integers(0, len(DQNAction)))
        else:
            action = int(np.argmax(q))
        self._last_action = DQNAction(action)
        self._env_steps += 1
        self._last_inference_ms = (time.perf_counter() - t0) * 1000.0

        rec = self._recommendation(state, action, q)
        self._record_decision(rec)
        return rec

    def _recommendation(self, state: SimulationState, action: int, q: np.ndarray) -> AgentRecommendation:
        dist = softmax(q / max(0.5, np.std(q) + 1e-6))
        order = np.sort(q)[::-1]
        gap = float(order[0] - (order[1] if len(order) > 1 else order[0]))
        confidence = float(np.clip(gap / (abs(order[0]) + 1e-3), 0.0, 1.0))
        priority = self._safety_priority(state)
        reason = (f"Q* {ACTION_LABELS[action]}={q[action]:.2f}; emissions "
                  f"{state.estimates.co2_kg_per_s * 1000:.1f} g/s, "
                  f"{state.safety.violations_last_window} recent violation(s)")
        return AgentRecommendation(
            agent=self.name, action_index=action, action_name=ACTION_LABELS[action],
            target_phase=self.resolve_phase(action, state),
            score=float(dist[action]), confidence=confidence, priority=priority, reason=reason,
            relevant_state={
                "co2_kg_per_s": round(state.estimates.co2_kg_per_s, 5),
                "violations_last_window": float(state.safety.violations_last_window),
                "mean_speed": round(float(np.mean([a.mean_speed_mps for a in state.approaches.values()])), 2),
                "mean_stops": round(float(np.mean([a.stops_last_window for a in state.approaches.values()])), 2),
            },
            action_distribution=[round(float(v), 4) for v in dist],
            value_estimate=round(float(np.max(q)), 4),
        )

    def _safety_priority(self, state: SimulationState) -> float:
        viol = state.safety.violations_last_window / self.norm.violation_ref
        emit = state.estimates.co2_kg_per_s / self.norm.co2_rate_ref
        return float(np.clip(0.18 + 0.5 * viol + 0.35 * emit, 0.0, 1.0))

    def resolve_phase(self, action_index: int, state: SimulationState) -> Phase:
        act = DQNAction(action_index)
        served = state.signal.served_phase
        if act in (DQNAction.SWITCH_PHASE, DQNAction.TRANSITION):
            return other_ring(served)
        return served

    # ---------------------------------------------------------------- reward
    def compute_reward(self, ctx: RewardContext) -> RewardBreakdown:
        return dqn_reward(ctx, self.norm)

    # ---------------------------------------------------------------- learning
    def observe(self, state, action_index, reward, next_state, done, info=None) -> None:
        # Transitions are recorded whether or not the agent is training: in inference
        # mode `learn()` is a no-op, but the buffer still feeds the Experience Replay
        # inspector (spec section 17) with real state -> action -> reward -> next-state
        # -> done tuples from the live loop. The buffer is a fixed-capacity ring.
        self.buffer.add(Transition(
            state=self._features(state), action=int(action_index), reward=float(reward),
            next_state=self._features(next_state), done=bool(done),
            info=info or {"action": ACTION_LABELS[int(action_index)]},
        ))

    def learn(self, *, force: bool = False) -> dict[str, float]:
        # DQN is off-policy (replay buffer); `force` is a no-op for it.
        if not self.training or len(self.buffer) < self.learning_starts:
            return {}
        if self._env_steps % self.train_freq != 0:
            return {}
        s, a, r, ns, d = self.buffer.sample(self.batch_size)
        s_t = torch.as_tensor(s); ns_t = torch.as_tensor(ns)
        a_t = torch.as_tensor(a, dtype=torch.int64)
        r_t = torch.as_tensor(r); d_t = torch.as_tensor(d)

        q_sa = self.q(s_t).gather(1, a_t.unsqueeze(1)).squeeze(1)
        with torch.no_grad():
            next_q = self.target(ns_t).max(dim=1).values
            target = r_t + self.gamma * (1.0 - d_t) * next_q
        loss = F.smooth_l1_loss(q_sa, target)

        self.opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.q.parameters(), 10.0)
        self.opt.step()
        self._train_steps += 1
        if self._train_steps % max(1, self.target_update_interval // self.train_freq) == 0:
            soft_update(self.target, self.q, tau=1.0)

        self.stats.q_loss = float(loss.item())
        self.stats.td_error = float((q_sa - target).abs().mean().item())
        self.stats.mean_q = float(q_sa.mean().item())
        self.stats.updates = self._train_steps
        return {"q_loss": self.stats.q_loss, "td_error": self.stats.td_error,
                "mean_q": self.stats.mean_q, "epsilon": self.epsilon}

    def end_episode(self, episode_return: float) -> None:
        self.trained_episodes += 1
        self.stats.episode_returns.append(episode_return)
        self.note_reward(episode_return)
        self.model_version = f"dqn-v1.{self.trained_episodes // 50}-dev"

    # ---------------------------------------------------------------- persistence
    def save(self, path: str | Path, meta: dict | None = None) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "state_dict": self.q.state_dict(), "trained_episodes": self.trained_episodes,
            "model_version": (meta or {}).get("version", self.model_version),
            "env_steps": self._env_steps, "meta": meta or {},
        }, path)
        log.info("DQN model saved", path=str(path), episodes=self.trained_episodes)

    def load(self, path: str | Path) -> dict:
        payload = torch.load(path, map_location="cpu", weights_only=False)
        self.q.load_state_dict(payload["state_dict"])
        self.target.load_state_dict(self.q.state_dict())
        self.trained_episodes = int(payload.get("trained_episodes", 0))
        self._env_steps = int(payload.get("env_steps", 0))
        self.model_version = payload.get("model_version", "dqn-loaded")
        log.info("DQN model loaded", path=str(path), episodes=self.trained_episodes)
        return payload.get("meta", {})

    # ---------------------------------------------------------------- inspector
    def replay_sample(self, n: int = 8) -> list[dict]:
        out = []
        for t in self.buffer.sample_readable(n):
            out.append({
                "action": ACTION_LABELS[t.action],
                "reward": round(t.reward, 3),
                "done": t.done,
                "state_summary": _summarise(t.state),
                "next_state_summary": _summarise(t.next_state),
                "info": t.info,
            })
        return out

    def inspect(self, state: SimulationState) -> AgentInspectorPayload:
        with self.inspecting():
            self.act(state, explore=False)
        fv = self._last_features
        dist = softmax(self._last_q / max(0.5, np.std(self._last_q) + 1e-6))
        return AgentInspectorPayload(
            agent=self.name, status=self.status(),
            features=fv.labelled() if fv else [],
            action_distribution=[round(float(v), 4) for v in dist],
            action_labels=ACTION_LABELS,
            selected_action=ACTION_LABELS[int(self._last_action)],
            value_estimate=round(float(np.max(self._last_q)), 4),
            advantage=None,
            reward=RewardBreakdown(),
            reward_history=[round(r, 3) for r in self._reward_history[-120:]],
            decision_history=self._decision_history[-40:],
            training={
                "q_loss": round(self.stats.q_loss, 4), "td_error": round(self.stats.td_error, 4),
                "mean_q": round(self.stats.mean_q, 4), "updates": self.stats.updates,
                "episode_returns": [round(r, 2) for r in self.stats.episode_returns[-100:]],
            },
            extra={
                "epsilon": round(self.epsilon, 4),
                "replay_size": len(self.buffer),
                "q_values": {ACTION_LABELS[i]: round(float(v), 4) for i, v in enumerate(self._last_q)},
                "replay_sample": self.replay_sample(6),
            },
        )


def _summarise(vec: np.ndarray) -> dict[str, float]:
    return {
        "queue_mean": round(float(np.mean(vec[4:8])), 3),
        "wait_mean": round(float(np.mean(vec[8:12])), 3),
        "speed_mean": round(float(np.mean(vec[12:16])), 3),
        "emission_rate": round(float(vec[30]), 3),
        "violations": round(float(vec[31]), 3),
    }
