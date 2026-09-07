"""PPO agent - Adaptive Traffic Congestion Reduction (docs/ppo.md)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from app.agents.common.base import BaseAgent
from app.agents.common.features import APPROACH_ORDER, Normalizer
from app.agents.common.resolve import other_ring
from app.agents.common.rewards import RewardContext
from app.agents.ppo.network import PolicyValueNet
from app.agents.ppo.reward import ppo_reward
from app.agents.ppo.state import STATE_DIM, build_ppo_state
from app.core.config import get_config
from app.logging import get_logger
from app.schemas.agents import AgentInspectorPayload, AgentRecommendation, RewardBreakdown
from app.schemas.enums import AgentName, Phase
from app.schemas.simulation import SimulationState

log = get_logger("PPO")


class PPOAction(IntEnum):
    KEEP_PHASE = 0
    EXTEND_GREEN = 1
    REDUCE_GREEN = 2
    SWITCH_PHASE = 3


ACTION_LABELS = ["KEEP_PHASE", "EXTEND_GREEN", "REDUCE_GREEN", "SWITCH_PHASE"]


@dataclass
class _Step:
    state: np.ndarray
    action: int
    log_prob: float
    value: float
    reward: float = 0.0
    done: bool = False


@dataclass
class _TrainStats:
    policy_loss: float = 0.0
    value_loss: float = 0.0
    entropy: float = 0.0
    approx_kl: float = 0.0
    clip_fraction: float = 0.0
    updates: int = 0
    episode_returns: list[float] = field(default_factory=list)


class PPOAgent(BaseAgent):
    name = AgentName.PPO
    action_labels = ACTION_LABELS
    state_dim = STATE_DIM

    def __init__(self, seed: int = 0, training: bool = False) -> None:
        super().__init__()
        cfg = get_config().rl
        torch.manual_seed(seed)
        self.net = PolicyValueNet(STATE_DIM, len(PPOAction), int(cfg.hidden_dim))
        self.opt = torch.optim.Adam(self.net.parameters(), lr=float(cfg.learning_rate))
        self.gamma = float(cfg.gamma)
        self.lam = float(cfg.gae_lambda)
        p = cfg.ppo
        self.rollout_steps = int(p.rollout_steps)
        self.epochs = int(p.epochs)
        self.minibatch = int(p.minibatch_size)
        self.clip_range = float(p.clip_range)
        self.value_coef = float(p.value_coef)
        self.entropy_coef = float(p.entropy_coef)
        self.max_grad_norm = float(p.max_grad_norm)
        self.update_at_episode_end = bool(p.get("update_at_episode_end", True))
        self.training = training
        self.norm = Normalizer()
        self._rng = np.random.default_rng(seed)  # seeded minibatch shuffling (reproducible)

        self._rollout: list[_Step] = []
        self.stats = _TrainStats()
        self._last_probs = np.ones(len(PPOAction), dtype=np.float32) / len(PPOAction)
        self._last_value = 0.0
        self._last_advantage = 0.0
        self._last_action = PPOAction.KEEP_PHASE
        self.model_version = "ppo-untrained"

    # ---------------------------------------------------------------- state
    def build_state(self, state: SimulationState):
        return build_ppo_state(state, self.norm)

    def _features(self, state: SimulationState) -> np.ndarray:
        fv = self.build_state(state)
        self._last_features = fv
        return fv.array()

    # ---------------------------------------------------------------- inference
    def act(self, state: SimulationState, *, stochastic: bool | None = None) -> AgentRecommendation:
        t0 = time.perf_counter()
        x = torch.from_numpy(self._features(state)).unsqueeze(0)
        with torch.no_grad():
            logits, value = self.net(x)
            probs = torch.softmax(logits, dim=-1).squeeze(0)
        use_stoch = self.training if stochastic is None else stochastic
        if use_stoch:
            dist = torch.distributions.Categorical(probs=probs)
            a_t = dist.sample()
            log_prob = float(dist.log_prob(a_t).item())
            action = int(a_t.item())
        else:
            action = int(torch.argmax(probs).item())
            log_prob = float(torch.log(probs[action] + 1e-8).item())

        p = probs.numpy()
        self._last_probs = p
        self._last_value = float(value.item())
        self._last_action = PPOAction(action)
        self._last_inference_ms = (time.perf_counter() - t0) * 1000.0
        if self.training:
            self._rollout.append(_Step(self._features(state), action, log_prob, float(value.item())))

        rec = self._recommendation(state, action, p, float(value.item()))
        self._record_decision(rec)
        return rec

    def _recommendation(self, state: SimulationState, action: int, probs: np.ndarray,
                        value: float) -> AgentRecommendation:
        order = np.sort(probs)[::-1]
        confidence = float(np.clip(order[0] - (order[1] if len(order) > 1 else 0.0), 0.0, 1.0))
        pressure = self.pressure(state)
        worst = max(pressure, key=pressure.get)
        priority = float(np.clip(0.1 + 0.85 * pressure[worst], 0.0, 1.0))
        reason = (f"{worst} queue pressure {pressure[worst]:.2f}; "
                  f"{ACTION_LABELS[action]}")
        return AgentRecommendation(
            agent=self.name, action_index=action, action_name=ACTION_LABELS[action],
            target_phase=self.resolve_phase(action, state),
            score=float(probs[action]), confidence=confidence, priority=priority, reason=reason,
            relevant_state={f"pressure_{k}": round(v, 3) for k, v in pressure.items()},
            action_distribution=[round(float(v), 4) for v in probs],
            value_estimate=round(value, 4),
        )

    def pressure(self, state: SimulationState) -> dict[str, float]:
        """Normalised per-approach queue pressure (docs/ppo.md section 5)."""
        out: dict[str, float] = {}
        for a in APPROACH_ORDER:
            ap = state.approach(a)
            out[a.value] = float(np.clip(
                0.6 * ap.queue_length / self.norm.queue_ref
                + 0.4 * ap.mean_wait_s / self.norm.wait_ref, 0.0, 1.0,
            ))
        return out

    def recommendation_text(self, state: SimulationState) -> str:
        pr = self.pressure(state)
        worst = max(pr, key=pr.get)
        served = state.signal.served_phase
        if served.serves(_approach(worst)):
            return f"EXTEND {worst} GREEN"
        return f"SWITCH TO SERVE {worst}"

    def resolve_phase(self, action_index: int, state: SimulationState) -> Phase:
        if PPOAction(action_index) == PPOAction.SWITCH_PHASE:
            return other_ring(state.signal.served_phase)
        return state.signal.served_phase

    # ---------------------------------------------------------------- reward
    def compute_reward(self, ctx: RewardContext) -> RewardBreakdown:
        return ppo_reward(ctx, self.norm)

    # ---------------------------------------------------------------- learning
    def observe(self, state, action_index, reward, next_state, done, info=None) -> None:
        if not self.training or not self._rollout:
            return
        self._rollout[-1].reward = float(reward)
        self._rollout[-1].done = bool(done)

    _MIN_UPDATE_STEPS = 16

    def learn(self, *, force: bool = False) -> dict[str, float]:
        if not self.training:
            return {}
        n_buffered = len(self._rollout)
        # normal cadence: update once the rollout is full. force=True (episode end)
        # updates on a short rollout so trailing on-policy steps are not discarded -
        # but a handful of steps is too few for a stable advantage estimate.
        if force:
            if n_buffered < self._MIN_UPDATE_STEPS:
                return {}
        elif n_buffered < self.rollout_steps:
            return {}
        steps = self._rollout
        self._rollout = []

        states = torch.as_tensor(np.array([s.state for s in steps]), dtype=torch.float32)
        actions = torch.as_tensor([s.action for s in steps], dtype=torch.int64)
        old_log_probs = torch.as_tensor([s.log_prob for s in steps], dtype=torch.float32)
        rewards = np.array([s.reward for s in steps], dtype=np.float32)
        values = np.array([s.value for s in steps], dtype=np.float32)
        dones = np.array([s.done for s in steps], dtype=np.float32)

        # GAE
        adv = np.zeros_like(rewards)
        last_gae = 0.0
        for t in reversed(range(len(steps))):
            next_value = values[t + 1] if t + 1 < len(steps) else 0.0
            next_nonterminal = 1.0 - dones[t]
            delta = rewards[t] + self.gamma * next_value * next_nonterminal - values[t]
            last_gae = delta + self.gamma * self.lam * next_nonterminal * last_gae
            adv[t] = last_gae
        returns = adv + values
        adv_t = torch.as_tensor((adv - adv.mean()) / (adv.std() + 1e-8), dtype=torch.float32)
        ret_t = torch.as_tensor(returns, dtype=torch.float32)

        n = len(steps)
        idx = np.arange(n)
        kl_acc = clip_acc = 0.0
        batches = 0
        for _ in range(self.epochs):
            self._rng.shuffle(idx)
            for start in range(0, n, self.minibatch):
                mb = idx[start:start + self.minibatch]
                mb_t = torch.as_tensor(mb, dtype=torch.int64)
                logits, v = self.net(states[mb_t])
                dist = torch.distributions.Categorical(logits=logits)
                new_log = dist.log_prob(actions[mb_t])
                ratio = torch.exp(new_log - old_log_probs[mb_t])
                a = adv_t[mb_t]
                unclipped = ratio * a
                clipped = torch.clamp(ratio, 1 - self.clip_range, 1 + self.clip_range) * a
                policy_loss = -torch.min(unclipped, clipped).mean()
                value_loss = F.mse_loss(v, ret_t[mb_t])
                entropy = dist.entropy().mean()
                loss = policy_loss + self.value_coef * value_loss - self.entropy_coef * entropy

                self.opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.net.parameters(), self.max_grad_norm)
                self.opt.step()

                with torch.no_grad():
                    kl_acc += float((old_log_probs[mb_t] - new_log).mean().item())
                    clip_acc += float((torch.abs(ratio - 1.0) > self.clip_range).float().mean().item())
                batches += 1

        self.stats.policy_loss = float(policy_loss.item())
        self.stats.value_loss = float(value_loss.item())
        self.stats.entropy = float(entropy.item())
        self.stats.approx_kl = kl_acc / max(batches, 1)
        self.stats.clip_fraction = clip_acc / max(batches, 1)
        self.stats.updates += 1
        self._last_advantage = float(adv.mean())
        return {
            "policy_loss": self.stats.policy_loss, "value_loss": self.stats.value_loss,
            "entropy": self.stats.entropy, "approx_kl": self.stats.approx_kl,
            "clip_fraction": self.stats.clip_fraction,
        }

    def end_episode(self, episode_return: float) -> None:
        if self.training and self.update_at_episode_end:
            self.learn(force=True)
        self._rollout = []  # a rollout never carries across an episode / seed boundary
        self.trained_episodes += 1
        self.stats.episode_returns.append(episode_return)
        self.note_reward(episode_return)
        self.model_version = f"ppo-v1.{self.trained_episodes // 50}-dev"

    # ---------------------------------------------------------------- persistence
    def save(self, path: str | Path, meta: dict | None = None) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "state_dict": self.net.state_dict(), "trained_episodes": self.trained_episodes,
            "model_version": (meta or {}).get("version", self.model_version), "meta": meta or {},
        }, path)
        log.info("PPO model saved", path=str(path), episodes=self.trained_episodes)

    def load(self, path: str | Path) -> dict:
        payload = torch.load(path, map_location="cpu", weights_only=False)
        self.net.load_state_dict(payload["state_dict"])
        self.trained_episodes = int(payload.get("trained_episodes", 0))
        self.model_version = payload.get("model_version", "ppo-loaded")
        log.info("PPO model loaded", path=str(path), episodes=self.trained_episodes)
        return payload.get("meta", {})

    # ---------------------------------------------------------------- inspector
    def inspect(self, state: SimulationState) -> AgentInspectorPayload:
        with self.inspecting():
            self.act(state, stochastic=False)
        fv = self._last_features
        return AgentInspectorPayload(
            agent=self.name, status=self.status(),
            features=fv.labelled() if fv else [],
            action_distribution=[round(float(v), 4) for v in self._last_probs],
            action_labels=ACTION_LABELS,
            selected_action=ACTION_LABELS[int(self._last_action)],
            value_estimate=round(self._last_value, 4),
            advantage=round(self._last_advantage, 4),
            reward=RewardBreakdown(),
            reward_history=[round(r, 3) for r in self._reward_history[-120:]],
            decision_history=self._decision_history[-40:],
            training={
                "policy_loss": round(self.stats.policy_loss, 4),
                "value_loss": round(self.stats.value_loss, 4),
                "entropy": round(self.stats.entropy, 4),
                "approx_kl": round(self.stats.approx_kl, 4),
                "clip_fraction": round(self.stats.clip_fraction, 4),
                "updates": self.stats.updates,
                "episode_returns": [round(r, 2) for r in self.stats.episode_returns[-100:]],
            },
            extra={
                "queue_pressure": self.pressure(state),
                "recommendation": self.recommendation_text(state),
            },
        )


def _approach(value: str):
    from app.schemas.enums import Approach
    return Approach(value)
