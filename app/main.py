# FastAPI app factory for the Artifact Relay challenge.

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.logging_config import configure_logging, get_logger
from app.routes import artifacts, auth, flag, meta, relay, releases, tickets

log = get_logger(__name__)


# Configure logging and seed the DB on startup.
@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    await init_db()
    log.info("app.startup", service="artifact-relay")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Artifact Relay",
        version="1.0.0",
        description="An internal software-artifact review portal (CTF environment).",
        lifespan=lifespan,
    )
    app.include_router(meta.router)
    app.include_router(meta.internal)
    app.include_router(auth.router)
    app.include_router(releases.router)
    app.include_router(artifacts.router)
    app.include_router(tickets.router)
    app.include_router(relay.router)
    app.include_router(flag.router)
    return app


app = create_app()
