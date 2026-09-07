"""Shared fixtures.

`tests/factories.py` puts `backend/` on `sys.path`; importing it here means every test
session has `app.*` importable before collection, whether pytest is run from the repo
root or from `backend/` (pyproject sets `testpaths = ["../tests"]`).
"""

from __future__ import annotations

import pytest

from tests.factories import advance, make_state  # noqa: F401  (re-exported for convenience)


@pytest.fixture
def state():
    return make_state()


@pytest.fixture
def adapter():
    """A fresh deterministic BuiltinAdapter (seed 0), reset and ready to step."""
    from app.schemas.scenario import ScenarioConfig
    from app.simulation.builtin.engine import BuiltinAdapter

    eng = BuiltinAdapter()
    eng.reset(ScenarioConfig(seed=0), seed=0)
    return eng
