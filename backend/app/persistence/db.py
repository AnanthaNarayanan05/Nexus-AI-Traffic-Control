"""Engine / session wiring for the SQLite store.

One process-wide engine, created lazily from ``get_settings().db_url`` (override with
``NEXUS_DB_URL`` - tests point it at a temp file). SQLite only: the parent directory is
created on first use and ``check_same_thread`` is relaxed because the training thread and
the API event loop share the engine.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings
from app.logging import get_logger

log = get_logger("PERSISTENCE")


class Base(DeclarativeBase):
    """Declarative base for every ORM table in this package."""


_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None
_bound_url: str | None = None


def _sqlite_path(url: str) -> Path | None:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    tail = url[len(prefix):]
    if not tail or tail == ":memory:":
        return None
    return Path(tail)


def get_engine() -> Engine:
    """The process-wide engine, created (and its SQLite dir ensured) on first call."""
    global _engine, _Session, _bound_url
    url = get_settings().db_url
    if _engine is not None and _bound_url == url:
        return _engine

    path = _sqlite_path(url)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)

    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, future=True, connect_args=connect_args)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk_pragma(dbapi_conn, _record):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    _engine = engine
    _Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    _bound_url = url
    log.info("persistence engine bound", url=url)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    get_engine()
    assert _Session is not None
    return _Session


def init_db() -> None:
    """Create any missing tables. Import-registers every model, then ``create_all``."""
    from app.persistence import models  # noqa: F401  (registers tables on Base.metadata)

    Base.metadata.create_all(get_engine())
    log.info("persistence tables ensured", tables=sorted(Base.metadata.tables))


@contextlib.contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope: commit on success, roll back on error, always close."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine_for_tests() -> None:
    """Drop the cached engine so the next call rebinds to the current ``db_url``."""
    global _engine, _Session, _bound_url
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _Session = None
    _bound_url = None
