"""PPO state builder - Adaptive Traffic Congestion Reduction (docs/ppo.md section 1)."""

from __future__ import annotations

from app.agents.common.features import APPROACH_ORDER, FeatureVector, Normalizer, one_hot_phase
from app.schemas.simulation import SimulationState

STATE_DIM = 33


def build_ppo_state(state: SimulationState, norm: Normalizer | None = None) -> FeatureVector:
    n = norm or Normalizer()
    fv = FeatureVector()

    for a in APPROACH_ORDER:
        fv.add(f"queue_{a.value}", n.clip01(state.approach(a).queue_length / n.queue_ref), "queue")
    for a in APPROACH_ORDER:
        fv.add(f"count_{a.value}", n.clip01(state.approach(a).vehicle_count / n.count_ref), "count")
    for a in APPROACH_ORDER:
        fv.add(f"wait_{a.value}", n.clip01(state.approach(a).mean_wait_s / n.wait_ref), "waiting")
    for a in APPROACH_ORDER:
        fv.add(f"arrival_{a.value}", n.clip01(state.approach(a).arrival_rate_vph / n.arrival_ref), "arrival")
    for a in APPROACH_ORDER:
        fv.add(f"speed_{a.value}", n.clip01(state.approach(a).mean_speed_mps / n.free_flow_mps), "speed")
    for a in APPROACH_ORDER:
        fv.add(f"density_{a.value}", n.clip01(state.approach(a).density_veh_per_km / n.density_ref), "density")

    for label, val in zip(
        ["ph_NS", "ph_EW", "ph_N", "ph_E", "ph_S", "ph_W", "ph_YEL", "ph_RED"],
        one_hot_phase(state.signal.current_phase), strict=True,
    ):
        fv.add(label, val, "phase")
    fv.add("phase_duration", n.clip01(state.signal.phase_elapsed_s / n.max_green), "phase")

    return fv
