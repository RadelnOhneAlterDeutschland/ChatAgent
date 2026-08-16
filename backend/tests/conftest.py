"""Shared fixtures: an app wired to a throwaway in-memory database.

Environment is set at import time, before any test module imports `app.*`, so
settings resolve without a real `.env` or AWS Secrets Manager.
"""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET", "test-secret-not-used-in-production")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key")
os.environ.setdefault("PINECONE_INDEX_NAME", "test-index")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")


@pytest.fixture
def db_engine():
    """One SQLite in-memory engine per test, shared across connections."""
    from app.db.models import Base

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Iterator[Session]:
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def ingestion_fakes() -> dict:
    """One set of in-memory ingestion adapters per test, shared by the `client` fixture's
    dependency overrides and reachable directly by step defs that need to pre-seed them
    (e.g. the OCR scenario configuring what the "scanner" returns)."""
    from tests.fakes import FakeBlobStore, FakeEmbedder, FakeOcrService, FakeVectorStore

    return {
        "blob_store": FakeBlobStore(),
        "vector_store": FakeVectorStore(),
        "embedder": FakeEmbedder(),
        "ocr": FakeOcrService(),
    }


@pytest.fixture
def agent_fakes() -> dict:
    """The scriptable fake LLM provider, shared by `client`'s override and reachable
    directly by chat step defs that need to script turns or inspect what was sent."""
    from tests.fakes.llm_provider import FakeLLMProvider

    return {"llm_provider": FakeLLMProvider()}


@pytest.fixture
def client(db_engine, ingestion_fakes: dict, agent_fakes: dict) -> Iterator[TestClient]:
    from app.agent.deps import get_llm_provider
    from app.db.session import get_db
    from app.ingestion.deps import get_blob_store, get_embedder, get_ocr_service, get_vector_store
    from app.main import create_app

    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    def override_get_db() -> Iterator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_blob_store] = lambda: ingestion_fakes["blob_store"]
    app.dependency_overrides[get_vector_store] = lambda: ingestion_fakes["vector_store"]
    app.dependency_overrides[get_embedder] = lambda: ingestion_fakes["embedder"]
    app.dependency_overrides[get_ocr_service] = lambda: ingestion_fakes["ocr"]
    app.dependency_overrides[get_llm_provider] = lambda: agent_fakes["llm_provider"]
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
