"""Structured logging (spec section 68).

Every record carries ``component`` and optional ``meta``. Components:
SIMULATION, A2C, DQN, PPO, COORDINATION, SAFETY, API, EXPERIMENT, TRAINING, SYSTEM.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "t": round(time.time(), 3),
            "level": record.levelname,
            "component": getattr(record, "component", "SYSTEM"),
            "message": record.getMessage(),
        }
        meta = getattr(record, "meta", None)
        if meta:
            payload["meta"] = meta
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger("nexus")
    root.setLevel(level.upper())
    root.handlers = [handler]
    root.propagate = False
    _CONFIGURED = True


class ComponentLogger:
    """Thin adapter that stamps ``component`` on every record."""

    def __init__(self, component: str) -> None:
        self._component = component
        self._log = logging.getLogger("nexus")

    def _emit(self, level: int, msg: str, meta: dict[str, Any] | None, exc_info: bool) -> None:
        self._log.log(
            level, msg, extra={"component": self._component, "meta": meta}, exc_info=exc_info
        )

    def debug(self, msg: str, **meta: Any) -> None:
        self._emit(logging.DEBUG, msg, meta or None, False)

    def info(self, msg: str, **meta: Any) -> None:
        self._emit(logging.INFO, msg, meta or None, False)

    def warning(self, msg: str, **meta: Any) -> None:
        self._emit(logging.WARNING, msg, meta or None, False)

    def error(self, msg: str, exc_info: bool = False, **meta: Any) -> None:
        self._emit(logging.ERROR, msg, meta or None, exc_info)


def get_logger(component: str) -> ComponentLogger:
    return ComponentLogger(component)
