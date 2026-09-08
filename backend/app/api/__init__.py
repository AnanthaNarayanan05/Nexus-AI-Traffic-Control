"""HTTP + WebSocket surface (spec sections 71, 88; docs/system-flow.md sections 2-3)."""

from app.api.experiment_routes import experiment_router
from app.api.export_routes import export_router
from app.api.replay_routes import replay_router
from app.api.routes import api_router
from app.api.training_routes import training_router
from app.api.ws import ws_router

__all__ = ["api_router", "training_router", "experiment_router", "replay_router",
           "export_router", "ws_router"]
