"""DQN reward: smoothness reward - violation penalty (docs/dqn.md section 3)."""

from __future__ import annotations

import numpy as np

from app.agents.common.features import Normalizer
from app.agents.common.rewards import RewardContext, component
from app.core.config import get_config
from app.schemas.agents import RewardBreakdown


def dqn_reward(ctx: RewardContext, norm: Normalizer | None = None) -> RewardBreakdown:
    n = norm or Normalizer()
    w = get_config().reward.dqn
    cur = ctx.curr

    speeds = [ap.mean_speed_mps for ap in cur.approaches.values()]
    smooth = float(np.mean(speeds)) / n.free_flow_mps if speeds else 0.0

    wait_prev, wait_curr = ctx.mean("mean_wait_s")
    waiting_drop = max(0.0, (wait_prev - wait_curr) / n.wait_ref)

    stops = float(np.mean([ap.stops_last_window for ap in cur.approaches.values()])) / n.stops_ref
    counts = [ap.vehicle_count for ap in cur.approaches.values()]
    queues = [ap.queue_length for ap in cur.approaches.values()]
    idle_frac = (sum(queues) / sum(counts)) if sum(counts) > 0 else 0.0
    emission = cur.estimates.co2_kg_per_s / n.co2_rate_ref
    queue = float(np.mean(queues)) / n.queue_ref

    comps = [
        component("smooth_flow", min(1.0, smooth), float(w.smooth_flow)),
        component("waiting_drop", min(1.0, waiting_drop), float(w.waiting_drop)),
        component("stop_penalty", -min(1.0, stops), float(w.stop_penalty)),
        component("idle_penalty", -min(1.0, idle_frac), float(w.idle_penalty)),
        component("emission_penalty", -min(1.5, emission), float(w.emission_penalty)),
        component("queue_penalty", -min(1.0, queue), float(w.queue_penalty)),
        component("violation_penalty", -float(ctx.violations), float(w.violation_penalty)),
    ]
    if "SWITCH" in ctx.action_name.upper() or "TRANSITION" in ctx.action_name.upper():
        comps.append(component("switch_penalty", -1.0, float(w.switch_penalty)))
    return RewardBreakdown.from_components(comps)
