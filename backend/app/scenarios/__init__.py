"""Scenario presets + registry (spec section 28)."""

from app.scenarios.presets import (
    PRESET_IDS,
    get_scenario,
    list_scenarios,
    register_scenario,
)

__all__ = ["PRESET_IDS", "get_scenario", "list_scenarios", "register_scenario"]
