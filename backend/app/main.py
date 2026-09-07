"""FastAPI application entry point.

    uvicorn app.main:app --reload --port 8000        (from backend/)
    make backend                                     (from the repo root)
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router, experiment_router, training_router, ws_router
from app.core.config import get_config, get_settings
from app.core.simulation_manager import get_manager
from app.logging import configure, get_logger

log = get_logger("SYSTEM")

_ALLOWED_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:4173", "http://127.0.0.1:4173",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure(settings.log_level)
    cfg = get_config()

    from app.persistence import init_db
    init_db()  # ensure the model-registry table exists

    manager = get_manager()
    manager.start_thread()
    log.info("NEXUS backend ready", adapter=manager.adapter.name,
             config_digest=cfg.digest, env=settings.env,
             scenario=manager.scenario.id)
    try:
        yield
    finally:
        manager.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(
        title="NEXUS AI Traffic Control",
        version="0.1.0",
        description=(
            "Two objective-specific RL agents (A2C emergency priority, DQN efficiency/fuel/"
            "emission/safety) coordinated at the signal level, with an authoritative safety "
            "constraint layer. (PPO is a legacy agent, out of the R9 active scope.)"
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    app.include_router(training_router)
    app.include_router(experiment_router)
    app.include_router(ws_router)

    @app.get("/")
    def root() -> dict:
        return {"name": "NEXUS AI Traffic Control", "docs": "/docs", "api": "/api/v1",
                "websocket": "/ws"}

    return app


app = create_app()
