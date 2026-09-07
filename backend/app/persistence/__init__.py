"""SQLite persistence (spec §55, §90; docs/experiments.md §5, docs/replay.md).

Four tables so far: the model registry (`models`), experiment runs (`experiments`),
user-saved scenarios (`scenarios`) and captured replays (`replays`). This package is
laid out so tables can be added next to the existing ones without reshaping anything.
"""

from __future__ import annotations

from app.persistence.db import Base, get_engine, get_sessionmaker, init_db, session_scope
from app.persistence.experiments import ExperimentStore, ExperimentStoreError
from app.persistence.models import (
    ExperimentRecord,
    ModelRecord,
    ReplayRecord,
    ScenarioRecord,
)
from app.persistence.registry import ModelRegistry, RegistryError
from app.persistence.replays import ReplayStore, ReplayStoreError
from app.persistence.scenarios import ScenarioStore, ScenarioStoreError

__all__ = [
    "Base",
    "ModelRecord",
    "ExperimentRecord",
    "ScenarioRecord",
    "ReplayRecord",
    "ModelRegistry",
    "RegistryError",
    "ExperimentStore",
    "ExperimentStoreError",
    "ScenarioStore",
    "ScenarioStoreError",
    "ReplayStore",
    "ReplayStoreError",
    "get_engine",
    "get_sessionmaker",
    "init_db",
    "session_scope",
]
