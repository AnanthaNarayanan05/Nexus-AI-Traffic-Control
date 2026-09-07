"""Put ``backend/`` on ``sys.path`` so scripts can ``import app.*``.

The backend is not installed as a package (it runs via ``uvicorn --app-dir backend``),
so every script under ``scripts/`` imports this first.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Windows terminals default to cp1252; training/eval output uses a few non-ASCII glyphs.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):  # pragma: no cover - non-reconfigurable stream
        pass
