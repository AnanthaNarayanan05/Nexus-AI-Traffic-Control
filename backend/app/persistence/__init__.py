"""SQLite persistence (spec §55, §90; docs/experiments.md §5).

Two tables so far: the model registry (`models`) and experiment runs (`experiments`).
The replay table lands with its slice; this package is laid out so tables can be added
next to the existing ones without reshaping anything.
"""

from __future__ import annotations

from app.persistence.db import Base, get_engine, get_sessionmaker, init_db, session_scope
from app.persistence.experiments import ExperimentStore, ExperimentStoreError
from app.persistence.models import ExperimentRecord, ModelRecord
from app.persistence.registry import ModelRegistry, RegistryError

__all__ = [
    "Base",
    "ModelRecord",
    "ExperimentRecord",
    "ModelRegistry",
    "RegistryError",
    "ExperimentStore",
    "ExperimentStoreError",
    "get_engine",
    "get_sessionmaker",
    "init_db",
    "session_scope",
]
