"""A2C agent - Emergency Vehicle Prioritization (docs/a2c.md)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from app.agents.a2c.network import ActorCritic
from app.agents.a2c.reward import a2c_reward
from app.agents.a2c.state import STATE_DIM, build_a2c_state
from app.agents.common.base import BaseAgent
from app.agents.common.features import Normalizer
from app.agents.common.resolve import demand_ring_phase, emergency_phase
from app.agents.common.rewards import RewardContext
from app.core.config import get_config
from app.logging import get_logger
from app.schemas.agents import (
    AgentInspectorPayload,
    AgentRecommendation,
    RewardBreakdown,
)
from app.schemas.enums import AgentName, Phase
from app.schemas.simulation import SimulationState

log = get_logger("A2C")


class A2CAction(IntEnum):
    MAINTAIN = 0
    EXTEND = 1
    SWITCH_EMERGENCY = 2
    REDUCE = 3
    RESTORE_NORMAL = 4


ACTION_LABELS = ["MAINTAIN", "EXTEND", "SWITCH_EMERGENCY", "REDUCE", "RESTORE_NORMAL"]


@dataclass
class _Step:
    state: np.ndarray
    action: int
    log_prob: float
    value: float
    reward: float | None = None
    done: bool = False


@dataclass
class _TrainStats:
    actor_loss: float = 0.0
    critic_loss: float = 0.0
    entropy: float = 0.0
    mean_value: float = 0.0
    mean_advantage: float = 0.0
    updates: int = 0
    episode_returns: list[float] = field(default_factory=list)


class A2CAgent(BaseAgent):
    name = AgentName.A2C
    action_labels = ACTION_LABELS
    state_dim = STATE_DIM

    def __init__(self, seed: int = 0, training: bool = False) -> None:
        super().__init__()
        cfg = get_config().rl
        torch.manual_seed(seed)
        self.device = torch.device("cpu")
        self.net = ActorCritic(STATE_DIM, len(A2CAction), int(cfg.hidden_dim)).to(self.device)
        self.opt = torch.optim.Adam(self.net.parameters(), lr=float(cfg.learning_rate))
        self.gamma = float(cfg.gamma)
        self.n_steps = int(cfg.a2c.n_steps)
        self.value_coef = float(cfg.a2c.value_coef)
        self.entropy_coef = float(cfg.a2c.entropy_coef)
        self.max_grad_norm = float(cfg.a2c.max_grad_norm)
        self.training = training
        self.norm = Normalizer()

        self._rollout: list[_Step] = []
        self.stats = _TrainStats()
        self._last_probs = np.ones(len(A2CAction), dtype=np.float32) / len(A2CAction)
        self._last_value = 0.0
        self._last_advantage = 0.0
        self._last_action = A2CAction.MAINTAIN
        self.model_version = "a2c-untrained"

    # ---------------------------------------------------------------- state
    def build_state(self, state: SimulationState):
        return build_a2c_state(state, self.norm)

    def _features(self, state: SimulationState) -> np.ndarray:
        fv = self.build_state(state)
        self._last_features = fv
        return fv.array()

    # ---------------------------------------------------------------- inference
    def act(self, state: SimulationState, *, stochastic: bool | None = None) -> AgentRecommendation:
        t0 = time.perf_counter()
        x = torch.from_numpy(self._features(state)).unsqueeze(0).to(self.device)
        logits, value = self.net(x)
        probs = torch.softmax(logits, dim=-1).squeeze(0)
        use_stochastic = self.training if stochastic is None else stochastic
        if use_stochastic:
            dist = torch.distributions.Categorical(probs=probs)
            action_t = dist.sample()
            log_prob = float(dist.log_prob(action_t).item())
            action = int(action_t.item())
        else:
            action = int(torch.argmax(probs).item())
            log_prob = float(torch.log(probs[action] + 1e-8).item())

        p = probs.detach().cpu().numpy()
        self._last_probs = p
        self._last_value = float(value.item())
        self._last_action = A2CAction(action)
        self._last_inference_ms = (time.perf_counter() - t0) * 1000.0

        if self.training:
            self._rollout.append(_Step(self._features(state), action, log_prob, float(value.item())))

        rec = self._recommendation(state, action, p, float(value.item()))
        self._record_decision(rec)
        return rec

    def _recommendation(self, state: SimulationState, action: int, probs: np.ndarray,
                        value: float) -> AgentRecommendation:
        target = self.resolve_phase(action, state)
        order = np.sort(probs)[::-1]
        confidence = float(np.clip(order[0] - (order[1] if len(order) > 1 else 0.0), 0.0, 1.0))
        priority = self._emergency_priority(state)
        score = float(probs[action])
        em = state.emergency
        if em.active:
            reason = (f"{em.type.value if em.type else 'emergency'} {em.distance_m:.0f} m on "
                      f"{em.approach.value if em.approach else '?'}, {em.speed_mps:.0f} m/s "
                      f"-> {ACTION_LABELS[action]}")
        else:
            reason = f"No emergency; {ACTION_LABELS[action]} (adaptive hold)"
        return AgentRecommendation(
            agent=self.name, action_index=action, action_name=ACTION_LABELS[action],
            target_phase=target, score=score, confidence=confidence, priority=priority,
            reason=reason,
            relevant_state={
                "emergency_active": 1.0 if em.active else 0.0,
                "emergency_distance_m": float(em.distance_m or 0.0),
                "served_phase_serves_emergency": 1.0 if (em.active and em.approach and
                    state.signal.served_phase.serves(em.approach)) else 0.0,
                "mean_queue": float(np.mean([ap.queue_length for ap in state.approaches.values()])),
            },
            action_distribution=[round(float(v), 4) for v in probs],
            value_estimate=round(value, 4),
        )

    def _emergency_priority(self, state: SimulationState) -> float:
        em = state.emergency
        if not em.active or em.approach is None:
            return 0.05
        dist = em.distance_m if em.distance_m is not None else self.norm.emergency_dist_ref
        closeness = 1.0 - float(np.clip(dist / self.norm.emergency_dist_ref, 0.0, 1.0))
        serving = state.signal.served_phase.serves(em.approach)
        priority = 0.55 + 0.4 * closeness - (0.25 if serving else 0.0)
        return float(np.clip(priority, 0.0, 1.0))

    def resolve_phase(self, action_index: int, state: SimulationState) -> Phase:
        act = A2CAction(action_index)
        served = state.signal.served_phase
        if act == A2CAction.SWITCH_EMERGENCY:
            return emergency_phase(state) or served
        if act == A2CAction.RESTORE_NORMAL:
            return demand_ring_phase(state)
        return served

    # ---------------------------------------------------------------- reward
    def compute_reward(self, ctx: RewardContext) -> RewardBreakdown:
        return a2c_reward(ctx, self.norm)

    # ---------------------------------------------------------------- learning
    def observe(self, state, action_index, reward, next_state, done, info=None) -> None:
        if not self.training or not self._rollout:
            return
        self._rollout[-1].reward = float(reward)
        self._rollout[-1].done = bool(done)

    def learn(self, *, force: bool = False) -> dict[str, float]:
        ready = [s for s in self._rollout if s.reward is not None]
        if not ready:
            return {}
        if len(ready) < self.n_steps and not force and not ready[-1].done:
            return {}
        steps = ready
        self._rollout = self._rollout[len(steps):]

        states = torch.as_tensor(np.array([s.state for s in steps]), dtype=torch.float32)
        actions = torch.as_tensor([s.action for s in steps], dtype=torch.int64)
        rewards = [s.reward or 0.0 for s in steps]

        with torch.no_grad():
            bootstrap = 0.0 if steps[-1].done else float(self.net(states[-1:].to(self.device))[1].item())
        returns = []
        acc = bootstrap
        for r, s in zip(reversed(rewards), reversed(steps), strict=True):
            acc = r + self.gamma * acc * (0.0 if s.done else 1.0)
            returns.append(acc)
        returns.reverse()
        returns_t = torch.as_tensor(returns, dtype=torch.float32)

        logits, values = self.net(states)
        dist = torch.distributions.Categorical(logits=logits)
        log_probs = dist.log_prob(actions)
        entropy = dist.entropy().mean()
        advantages = returns_t - values.detach()
        adv_norm = (advantages - advantages.mean()) / (advantages.std() + 1e-6)

        actor_loss = -(log_probs * adv_norm).mean()
        critic_loss = F.mse_loss(values, returns_t)
        loss = actor_loss + self.value_coef * critic_loss - self.entropy_coef * entropy

        self.opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.net.parameters(), self.max_grad_norm)
        self.opt.step()

        self.stats.actor_loss = float(actor_loss.item())
        self.stats.critic_loss = float(critic_loss.item())
        self.stats.entropy = float(entropy.item())
        self.stats.mean_value = float(values.mean().item())
        self.stats.mean_advantage = float(advantages.mean().item())
        self.stats.updates += 1
        self._last_advantage = float(advantages.mean().item())
        return {
            "actor_loss": self.stats.actor_loss, "critic_loss": self.stats.critic_loss,
            "entropy": self.stats.entropy, "mean_value": self.stats.mean_value,
            "mean_advantage": self.stats.mean_advantage,
        }

    def end_episode(self, episode_return: float) -> None:
        self.trained_episodes += 1
        self.stats.episode_returns.append(episode_return)
        self.note_reward(episode_return)
        self._rollout.clear()
        self.model_version = f"a2c-v1.{self.trained_episodes // 50}-dev"

    # ---------------------------------------------------------------- persistence
    def save(self, path: str | Path, meta: dict | None = None) -> None:
        payload = {
            "state_dict": self.net.state_dict(),
            "trained_episodes": self.trained_episodes,
            "model_version": (meta or {}).get("version", self.model_version),
            "meta": meta or {},
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        torch.save(payload, path)
        log.info("A2C model saved", path=str(path), episodes=self.trained_episodes)

    def load(self, path: str | Path) -> dict:
        payload = torch.load(path, map_location="cpu", weights_only=False)
        self.net.load_state_dict(payload["state_dict"])
        self.trained_episodes = int(payload.get("trained_episodes", 0))
        self.model_version = payload.get("model_version", "a2c-loaded")
        log.info("A2C model loaded", path=str(path), episodes=self.trained_episodes)
        return payload.get("meta", {})

    # ---------------------------------------------------------------- inspector
    def inspect(self, state: SimulationState) -> AgentInspectorPayload:
        with self.inspecting():
            self.act(state, stochastic=False)
        fv = self._last_features
        ctx_reward = RewardBreakdown()
        return AgentInspectorPayload(
            agent=self.name, status=self.status(),
            features=fv.labelled() if fv else [],
            action_distribution=[round(float(v), 4) for v in self._last_probs],
            action_labels=ACTION_LABELS,
            selected_action=ACTION_LABELS[int(self._last_action)],
            value_estimate=round(self._last_value, 4),
            advantage=round(self._last_advantage, 4),
            reward=ctx_reward,
            reward_history=[round(r, 3) for r in self._reward_history[-120:]],
            decision_history=self._decision_history[-40:],
            training={
                "actor_loss": round(self.stats.actor_loss, 4),
                "critic_loss": round(self.stats.critic_loss, 4),
                "entropy": round(self.stats.entropy, 4),
                "mean_value": round(self.stats.mean_value, 4),
                "updates": self.stats.updates,
                "episode_returns": [round(r, 2) for r in self.stats.episode_returns[-100:]],
            },
            extra={
                "emergency_priority": round(self._emergency_priority(state), 3),
                "emergency_active": state.emergency.active,
            },
        )
