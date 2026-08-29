"""FastAPI entrypoint. `create_app()` is a factory so tests get an isolated instance."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api import auth, chat, documents
from app.core.config import Settings, get_settings
from app.ingestion.scheduler import IngestionScheduler, build_folder_sync_fn


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


def _build_scheduler(settings: Settings) -> IngestionScheduler | None:
    """`None` when no folder is configured (the default in tests — plan.md Phase 8's
    scheduler is inert unless `INGESTION_FOLDER_PATHS` is actually set)."""
    folders = [path.strip() for path in settings.ingestion_folder_paths.split(",") if path.strip()]
    if not folders:
        return None
    return IngestionScheduler(
        sync_fn=build_folder_sync_fn(folders),
        interval_seconds=settings.ingestion_poll_minutes * 60,
    )


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        scheduler = _build_scheduler(settings)
        if scheduler is not None:
            scheduler.start()
        yield
        if scheduler is not None:
            scheduler.stop()

    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok", version=settings.app_version, environment=settings.environment
        )

    app.include_router(auth.router)
    app.include_router(documents.router)
    app.include_router(chat.router)
    return app


app = create_app()
