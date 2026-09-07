"""Scenario presets + registry (spec section 28, R9 §8A/§8B)."""

from app.scenarios.presets import (
    PRESET_IDS,
    REQUIRED_PRESET_IDS,
    delete_scenario,
    get_scenario,
    list_scenarios,
    register_scenario,
)

__all__ = [
    "PRESET_IDS",
    "REQUIRED_PRESET_IDS",
    "delete_scenario",
    "get_scenario",
    "list_scenarios",
    "register_scenario",
]
