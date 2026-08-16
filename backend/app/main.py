"""FastAPI entrypoint. `create_app()` is a factory so tests get an isolated instance."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api import auth, chat, documents
from app.core.config import get_settings


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)

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
