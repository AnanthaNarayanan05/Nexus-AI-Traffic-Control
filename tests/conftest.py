"""Shared fixtures.

`tests/factories.py` puts `backend/` on `sys.path`; importing it here means every test
session has `app.*` importable before collection, whether pytest is run from the repo
root or from `backend/` (pyproject sets `testpaths = ["../tests"]`).
"""

from __future__ import annotations

import pytest

from tests.factories import advance, make_state  # noqa: F401  (re-exported for convenience)


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path_factory, monkeypatch):
    """Point the SQLite store at a per-test temp file.

    Keeps every test off the real `data/nexus.db` and gives registry/persistence
    tests a clean database each. No-op for tests that never touch persistence.
    """
    from app.core import config as _cfg
    from app.persistence.db import reset_engine_for_tests

    db_path = tmp_path_factory.mktemp("db") / "nexus.db"
    monkeypatch.setenv("NEXUS_DB_URL", f"sqlite:///{db_path.as_posix()}")
    _cfg.get_settings.cache_clear()
    reset_engine_for_tests()
    yield
    reset_engine_for_tests()
    _cfg.get_settings.cache_clear()


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
