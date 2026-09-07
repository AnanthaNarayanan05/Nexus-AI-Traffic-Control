"""State builders for A2C / DQN / PPO (docs/*.md section 1).

Locks the observation contract each agent's network depends on: fixed dimensionality,
float32, finite, every feature normalised into [0, 1], and a label per element.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.agents.a2c.state import STATE_DIM as A2C_DIM
from app.agents.a2c.state import build_a2c_state
from app.agents.dqn.state import STATE_DIM as DQN_DIM
from app.agents.dqn.state import build_dqn_state
from app.agents.ppo.state import STATE_DIM as PPO_DIM
from app.agents.ppo.state import build_ppo_state
from app.schemas.enums import Approach, Phase
from app.schemas.simulation import EmergencyState

from tests.factories import make_state

BUILDERS = [
    pytest.param(build_a2c_state, A2C_DIM, id="a2c"),
    pytest.param(build_dqn_state, DQN_DIM, id="dqn"),
    pytest.param(build_ppo_state, PPO_DIM, id="ppo"),
]

EXPECTED_DIMS = {"a2c": 31, "dqn": 33, "ppo": 33}


def test_documented_dims_unchanged():
    assert (A2C_DIM, DQN_DIM, PPO_DIM) == (31, 33, 33)


@pytest.mark.parametrize("build,dim", BUILDERS)
def test_dim_matches_constant(build, dim):
    fv = build(make_state())
    assert len(fv) == dim
    assert fv.array().shape == (dim,)


@pytest.mark.parametrize("build,dim", BUILDERS)
def test_array_is_float32_and_finite(build, dim):
    arr = build(make_state()).array()
    assert arr.dtype == np.float32
    assert np.isfinite(arr).all()


@pytest.mark.parametrize("build,dim", BUILDERS)
def test_every_feature_normalised_into_unit_interval(build, dim):
    # extreme state: gridlock on every approach, active emergency, high emissions
    extreme = make_state(
        queues=dict.fromkeys(Approach, 999),
        counts=dict.fromkeys(Approach, 999),
        waits=dict.fromkeys(Approach, 9999.0),
        speeds=dict.fromkeys(Approach, 99.0),
        co2_rate=5.0,
        phase_elapsed_s=9999.0,
        emergency=EmergencyState(
            active=True, approach=Approach.E, distance_m=5.0, speed_mps=25.0, eta_s=1.0
        ),
    )
    arr = build(extreme).array()
    assert arr.min() >= -1e-6
    assert arr.max() <= 1.0 + 1e-6


@pytest.mark.parametrize("build,dim", BUILDERS)
def test_labels_cover_every_element(build, dim):
    fv = build(make_state())
    labels = fv.labelled()
    assert len(labels) == dim
    assert all(lf.name for lf in labels)
    assert all(lf.group for lf in labels)
    assert len({lf.name for lf in labels}) == dim  # names are unique


@pytest.mark.parametrize("build,dim", BUILDERS)
def test_phase_one_hot_is_exactly_one(build, dim):
    fv = build(make_state(served=Phase.NS, current=Phase.NS))
    ph = [lf.value for lf in fv.labelled() if lf.name.startswith("ph_")]
    assert ph.count(1.0) == 1
    assert sum(ph) == pytest.approx(1.0)


def test_a2c_encodes_emergency_direction():
    fv = build_a2c_state(
        make_state(emergency=EmergencyState(active=True, approach=Approach.S, distance_m=60.0))
    )
    by_name = {lf.name: lf.value for lf in fv.labelled()}
    assert by_name["emergency_active"] == 1.0
    assert by_name["emergency_dir_S"] == 1.0
    assert by_name["emergency_dir_N"] == 0.0


def test_a2c_no_emergency_zeros_direction():
    fv = build_a2c_state(make_state())
    by_name = {lf.name: lf.value for lf in fv.labelled()}
    assert by_name["emergency_active"] == 0.0
    assert all(by_name[f"emergency_dir_{a.value}"] == 0.0 for a in Approach)


@pytest.mark.parametrize("build,dim", BUILDERS)
def test_builder_is_pure(build, dim):
    st = make_state()
    a = build(st).array()
    b = build(st).array()
    assert np.array_equal(a, b)
