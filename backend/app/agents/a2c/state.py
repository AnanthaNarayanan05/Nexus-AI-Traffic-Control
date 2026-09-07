"""A2C state builder - Emergency Vehicle Prioritization (docs/a2c.md section 1)."""

from __future__ import annotations

from app.agents.common.features import APPROACH_ORDER, FeatureVector, Normalizer, one_hot_phase
from app.schemas.enums import Approach
from app.schemas.simulation import SimulationState

STATE_DIM = 31


def build_a2c_state(state: SimulationState, norm: Normalizer | None = None) -> FeatureVector:
    n = norm or Normalizer()
    fv = FeatureVector()
    em = state.emergency

    # -- emergency presence + direction ------------------------------------
    fv.add("emergency_active", 1.0 if em.active else 0.0, "emergency")
    for a in APPROACH_ORDER:
        fv.add(f"emergency_dir_{a.value}", 1.0 if (em.active and em.approach == a) else 0.0, "emergency")

    # -- emergency kinematics --------------------------------------------------
    dist = (em.distance_m if em.distance_m is not None else n.emergency_dist_ref)
    speed = (em.speed_mps if em.speed_mps is not None else 0.0)
    eta = (em.eta_s if em.eta_s is not None else n.emergency_eta_ref)
    fv.add("emergency_distance", n.clip01(dist / n.emergency_dist_ref), "emergency")
    fv.add("emergency_speed", n.clip01(speed / n.free_flow_mps), "emergency")
    fv.add("emergency_eta", n.clip01(eta / n.emergency_eta_ref), "emergency")

    # -- per-approach queue / waiting / density ------------------------------
    for a in APPROACH_ORDER:
        ap = state.approach(a)
        fv.add(f"queue_{a.value}", n.clip01(ap.queue_length / n.queue_ref), "queue")
    for a in APPROACH_ORDER:
        ap = state.approach(a)
        fv.add(f"wait_{a.value}", n.clip01(ap.mean_wait_s / n.wait_ref), "waiting")
    for a in APPROACH_ORDER:
        ap = state.approach(a)
        fv.add(f"density_{a.value}", n.clip01(ap.density_veh_per_km / n.density_ref), "density")

    # -- current phase one-hot ----------------------------------------------
    for label, val in zip(
        ["ph_NS", "ph_EW", "ph_N", "ph_E", "ph_S", "ph_W", "ph_YEL", "ph_RED"],
        one_hot_phase(state.signal.current_phase),
        strict=True,
    ):
        fv.add(label, val, "phase")

    # -- phase timing ------------------------------------------------------
    fv.add("phase_elapsed", n.clip01(state.signal.phase_elapsed_s / n.max_green), "phase")
    fv.add("min_green_ok", 1.0 if state.signal.min_green_satisfied else 0.0, "phase")

    # -- normal traffic flow ------------------------------------------------
    fv.add("throughput", n.clip01(state.estimates.throughput_vph / n.throughput_ref), "flow")

    return fv
