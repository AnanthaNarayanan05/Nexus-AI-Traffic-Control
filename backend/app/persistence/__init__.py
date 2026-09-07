"""SQLite persistence (spec §55, §90; docs/experiments.md §5).

Slice 2 ships one table - the model registry (`models`). The experiment / run /
replay tables from `docs/experiments.md §5` land with their slices; this package is
laid out so they can be added next to `ModelRecord` without reshaping anything.
"""

from __future__ import annotations

from app.persistence.db import Base, get_engine, get_sessionmaker, init_db, session_scope
from app.persistence.models import ModelRecord
from app.persistence.registry import ModelRegistry, RegistryError

__all__ = [
    "Base",
    "ModelRecord",
    "ModelRegistry",
    "RegistryError",
    "get_engine",
    "get_sessionmaker",
    "init_db",
    "session_scope",
]
