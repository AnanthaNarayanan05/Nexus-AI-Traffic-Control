"""Built-in microsimulation determinism + geometry sanity (docs/simulation.md section 2).

The adapter's contract (spec section 10): given (scenario, seed, action sequence) the
run is reproducible. These tests fingerprint a run and assert same-seed runs match,
different-seed runs diverge, and the resolved geometry follows config.yaml.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.core.config import get_config
from app.schemas.enums import Approach
from app.schemas.scenario import ScenarioConfig
from app.simulation.adapter import SimEvent
from app.simulation.builtin.engine import BuiltinAdapter
from app.simulation.geometry import Geometry

DT = 0.5


def run(seed: int, ticks: int = 240, *, inject_at: dict[int, SimEvent] | None = None) -> BuiltinAdapter:
    eng = BuiltinAdapter()
    eng.reset(ScenarioConfig(seed=seed), seed=seed)
    inject_at = inject_at or {}
    for i in range(ticks):
        if i in inject_at:
            eng.inject(inject_at[i])
        eng.step(DT)
    return eng


def fingerprint(eng: BuiltinAdapter) -> tuple:
    st = eng.get_state()
    return (
        st.step,
        round(st.sim_time, 2),
        st.total_vehicles,
        st.total_queue,
        st.safety.violations_total,
        round(st.estimates.co2_kg_total, 6),
        round(st.estimates.fuel_l_total, 6),
        st.signal.served_phase.value,
        st.signal.current_phase.value,
        tuple(round(v.x, 3) for v in st.vehicles),
        tuple(round(v.y, 3) for v in st.vehicles),
        tuple(round(st.approach(a).mean_wait_s, 3) for a in Approach),
    )


def test_same_seed_same_scenario_reproduces_exactly():
    assert fingerprint(run(7)) == fingerprint(run(7))


def test_same_seed_reproduces_across_a_longer_horizon():
    assert fingerprint(run(1234, ticks=600)) == fingerprint(run(1234, ticks=600))


def test_different_seeds_diverge():
    assert fingerprint(run(1)) != fingerprint(run(2))


def test_injected_emergency_is_deterministic():
    ev = SimEvent("spawn_emergency", {"approach": "N"})
    a = run(42, inject_at={20: ev})
    b = run(42, inject_at={20: ev})
    assert fingerprint(a) == fingerprint(b)
    # and the emergency actually entered the run
    assert a.get_state().emergency.cleared_this_episode >= 0
    assert any(v.is_emergency for v in a.get_state().vehicles) or \
        a.get_state().emergency.cleared_this_episode > 0


def test_reset_rewinds_all_counters():
    eng = run(3, ticks=300)
    assert eng.get_state().step == 300
    eng.reset(ScenarioConfig(seed=3), seed=3)
    st = eng.get_state()
    assert st.step == 0
    assert st.sim_time == 0.0
    assert st.total_vehicles == 0
    assert st.safety.violations_total == 0
    assert st.estimates.co2_kg_total == 0.0


def test_advance_helper_matches_manual_stepping():
    from tests.factories import advance

    manual = run(9, ticks=120)
    eng = BuiltinAdapter()
    eng.reset(ScenarioConfig(seed=9), seed=9)
    advance(eng, 60.0, dt=DT)  # 60s / 0.5 = 120 ticks
    assert fingerprint(eng) == fingerprint(manual)


# --------------------------------------------------------------- geometry
def test_geometry_reads_lane_width_from_config():
    g = Geometry()
    cfg = get_config().geometry
    assert g.lane_width == pytest.approx(float(cfg.lane_width_m))
    assert g.lanes == int(cfg.lanes_per_approach)
    assert g.box == pytest.approx(float(cfg.intersection_size_m))


def test_stop_line_distance_is_half_the_box_plus_the_offset():
    g = Geometry()
    cfg = get_config().geometry
    assert g.stop_line_dist == pytest.approx(
        float(cfg.intersection_size_m) / 2.0 + float(cfg.stop_line_offset_m)
    )


def test_entry_point_is_upstream_of_the_stop_line_on_every_approach():
    g = Geometry()
    for a in Approach:
        entry = np.array(g.entry_point(a, 1))
        stop = np.array(g.stop_line_point(a, 1))
        # entry is further from the centre than the stop line
        assert np.linalg.norm(entry) > np.linalg.norm(stop)


def test_world_pose_places_a_queued_vehicle_before_the_stop_line():
    g = Geometry()
    from app.schemas.enums import Movement

    x, y, _ = g.world_pose(Approach.N, 1, Movement.THROUGH, pos=5.0)
    # 5 m upstream of the N stop line: north of centre, |y| > stop_line_dist
    assert y > g.stop_line_dist
    assert abs(x) < g.lanes * g.lane_width
