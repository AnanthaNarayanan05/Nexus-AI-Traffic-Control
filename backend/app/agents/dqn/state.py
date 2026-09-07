"""DQN state builder - Fuel / Emission / Efficiency / Safety (docs/dqn.md section 1)."""

from __future__ import annotations

from app.agents.common.features import APPROACH_ORDER, FeatureVector, Normalizer, one_hot_phase
from app.core.config import get_config
from app.schemas.simulation import SimulationState

STATE_DIM = 33


def build_dqn_state(state: SimulationState, norm: Normalizer | None = None) -> FeatureVector:
    n = norm or Normalizer()
    fv = FeatureVector()

    for a in APPROACH_ORDER:
        fv.add(f"count_{a.value}", n.clip01(state.approach(a).vehicle_count / n.count_ref), "count")
    for a in APPROACH_ORDER:
        fv.add(f"queue_{a.value}", n.clip01(state.approach(a).queue_length / n.queue_ref), "queue")
    for a in APPROACH_ORDER:
        fv.add(f"wait_{a.value}", n.clip01(state.approach(a).mean_wait_s / n.wait_ref), "waiting")
    for a in APPROACH_ORDER:
        fv.add(f"speed_{a.value}", n.clip01(state.approach(a).mean_speed_mps / n.free_flow_mps), "speed")
    for a in APPROACH_ORDER:
        fv.add(f"stops_{a.value}", n.clip01(state.approach(a).stops_last_window / n.stops_ref), "stops")

    for label, val in zip(
        ["ph_NS", "ph_EW", "ph_N", "ph_E", "ph_S", "ph_W", "ph_YEL", "ph_RED"],
        one_hot_phase(state.signal.current_phase), strict=True,
    ):
        fv.add(label, val, "phase")
    fv.add("phase_elapsed", n.clip01(state.signal.phase_elapsed_s / n.max_green), "phase")
    fv.add("min_green_ok", 1.0 if state.signal.min_green_satisfied else 0.0, "phase")

    fv.add("emission_rate", n.clip01(state.estimates.co2_kg_per_s / n.co2_rate_ref), "environment")
    fv.add("violations", n.clip01(state.safety.violations_last_window / n.violation_ref), "safety")
    fv.add("total_load", n.clip01(state.total_vehicles / float(get_config().simulation.max_vehicles)), "count")

    return fv
