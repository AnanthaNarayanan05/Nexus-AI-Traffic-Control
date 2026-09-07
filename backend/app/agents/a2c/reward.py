"""A2C reward: R = -alpha*We - beta*Q + gamma*Pe + delta*T  (docs/a2c.md section 3)."""

from __future__ import annotations

from app.agents.common.features import Normalizer
from app.agents.common.rewards import RewardContext, component
from app.core.config import get_config
from app.schemas.agents import RewardBreakdown


def a2c_reward(ctx: RewardContext, norm: Normalizer | None = None) -> RewardBreakdown:
    n = norm or Normalizer()
    w = get_config().reward.a2c
    interval = max(ctx.interval_s, 1e-3)

    # We - emergency waiting time (fraction of the interval spent waiting)
    we = min(1.0, ctx.emergency_wait_delta_s / interval) if ctx.curr.emergency.active or ctx.emergency_wait_delta_s else 0.0

    # Q - normal traffic queue (mean across approaches, current)
    q_prev, q_curr = ctx.mean("queue_length")
    q = min(1.0, q_curr / n.queue_ref)

    # Pe - emergency passage / priority progress
    progress = ctx.emergency_progress_m / n.emergency_dist_ref
    pe = float(ctx.emergency_cleared) + max(0.0, min(1.0, progress))

    # T - throughput (non-emergency departures vs a per-interval reference)
    ref = n.throughput_ref * interval / 3600.0
    t = ctx.vehicles_cleared / ref if ref > 0 else 0.0

    comps = [
        component("emergency_wait", -we, float(w.alpha_emergency_wait)),
        component("normal_queue", -q, float(w.beta_normal_queue)),
        component("emergency_passage", pe, float(w.gamma_emergency_passage)),
        component("throughput", t, float(w.delta_throughput)),
    ]
    if ctx.phase_changed and not ctx.curr.emergency.active:
        comps.append(component("switch_penalty", -1.0, float(w.switch_penalty)))

    return RewardBreakdown.from_components(comps)
