"""PPO reward: R = -alpha*Q - beta*W + gamma*T  (docs/ppo.md section 3)."""

from __future__ import annotations

import numpy as np

from app.agents.common.features import Normalizer
from app.agents.common.rewards import RewardContext, component
from app.core.config import get_config
from app.schemas.agents import RewardBreakdown


def ppo_reward(ctx: RewardContext, norm: Normalizer | None = None) -> RewardBreakdown:
    n = norm or Normalizer()
    w = get_config().reward.ppo
    cur = ctx.curr
    interval = max(ctx.interval_s, 1e-3)

    q = float(np.mean([ap.queue_length for ap in cur.approaches.values()])) / n.queue_ref
    wv = float(np.mean([ap.mean_wait_s for ap in cur.approaches.values()])) / n.wait_ref
    ref = n.throughput_ref * interval / 3600.0
    t = ctx.vehicles_cleared / ref if ref > 0 else 0.0

    comps = [
        component("queue", -min(1.5, q), float(w.alpha_queue)),
        component("waiting", -min(1.5, wv), float(w.beta_waiting)),
        component("throughput", min(1.5, t), float(w.gamma_throughput)),
    ]
    if "SWITCH" in ctx.action_name.upper():
        comps.append(component("switch_penalty", -1.0, float(w.switch_penalty)))
    return RewardBreakdown.from_components(comps)
