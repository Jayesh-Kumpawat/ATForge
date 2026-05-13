"""FastAPI app factory."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from atforge.api.routes import health

log = logging.getLogger("atforge.api")


def create_app() -> FastAPI:
    app = FastAPI(
        title="ATForge API",
        version="0.1.0",
        description="Read-only HTTP API for ATForge dashboard (Track C).",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(health.router, tags=["health"])

    return app


app = create_app()
