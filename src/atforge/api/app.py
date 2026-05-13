"""FastAPI app factory."""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from atforge.api.routes import health, runs, strategies

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
    app.include_router(runs.router)
    app.include_router(strategies.router)

    @app.exception_handler(HTTPException)
    async def _http_exc_handler(request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
        )

    return app


app = create_app()
