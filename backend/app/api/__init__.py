"""HTTP + WebSocket surface (spec sections 71, 88; docs/system-flow.md sections 2-3)."""

from app.api.routes import api_router
from app.api.ws import ws_router

__all__ = ["api_router", "ws_router"]
