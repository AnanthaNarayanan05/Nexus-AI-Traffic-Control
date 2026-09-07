"""Preset scenarios: the R9 §8A completeness + metadata contract.

The eight required presets must all build, each carrying an objective, an AI focus and a
difficulty for the presentation UI. `surge_midway` is an allowed ninth (it exercises
`scheduled_changes`); nothing else may appear.
"""

from __future__ import annotations

import pytest

from app.scenarios.presets import (
    PRESET_IDS,
    REQUIRED_PRESET_IDS,
    _build,
    get_scenario,
    list_scenarios,
)
from app.schemas.scenario import Difficulty

DIFFICULTIES = set(Difficulty.__args__)  # type: ignore[attr-defined]


def test_required_presets_are_exactly_the_eight():
    assert set(REQUIRED_PRESET_IDS) == {
        "normal", "rush_hour", "emergency_heavy", "uneven",
        "high_stop_go", "incident", "safety_violation", "mixed_crisis",
    }
    assert set(PRESET_IDS) == set(REQUIRED_PRESET_IDS) | {"surge_midway"}


@pytest.mark.parametrize("pid", PRESET_IDS)
def test_every_preset_builds_with_full_metadata(pid):
    sc = _build(pid)
    assert sc.id == pid
    assert sc.name and sc.description
    assert sc.objective, f"{pid} has no objective"
    assert sc.ai_focus, f"{pid} has no ai_focus"
    assert sc.difficulty in DIFFICULTIES
    assert sc.duration_s > 0
    assert sc.demand.arrivals_vph > 0


def test_list_marks_presets_and_surfaces_metadata():
    rows = {r["id"]: r for r in list_scenarios()}
    for pid in PRESET_IDS:
        assert rows[pid]["preset"] is True
        assert rows[pid]["objective"] and rows[pid]["ai_focus"]
        assert rows[pid]["difficulty"] in DIFFICULTIES
        assert isinstance(rows[pid]["scheduled_changes"], int)


def test_get_scenario_returns_a_fresh_copy():
    a = get_scenario("normal")
    a.emergency_probability_per_min = 99.0
    b = get_scenario("normal")
    assert b.emergency_probability_per_min != 99.0


def test_safety_violation_and_mixed_crisis_are_the_stress_cases():
    sv = _build("safety_violation")
    assert sv.violation_probability_scale > 1.0
    assert sv.difficulty == "hard"

    mc = _build("mixed_crisis")
    assert mc.difficulty == "extreme"
    assert mc.emergency_probability_per_min > 1.0
    assert mc.blocked_lanes and mc.scheduled_changes  # every stressor at once


def test_unknown_preset_id_raises():
    with pytest.raises(KeyError):
        _build("no_such_preset")
