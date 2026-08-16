"""Wires the real adapters behind `app.ingestion.ports` for FastAPI request handling.

Tests override the four leaf providers (`get_blob_store` etc.) with fakes via
`app.dependency_overrides` — see `tests/conftest.py::client`. `get_pipeline` itself is
never overridden directly; it just assembles whatever providers are in effect.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.ingestion.blob_store import S3BlobStore
from app.ingestion.embedder import OpenAIEmbedder
from app.ingestion.ocr import TextractOcrService
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.ports import BlobStore, Embedder, OcrService, VectorStore
from app.ingestion.vector_store import PineconeVectorStore


@lru_cache
def get_blob_store() -> BlobStore:
    settings = get_settings()
    return S3BlobStore(bucket=settings.s3_bucket_name, region=settings.aws_region)


@lru_cache
def get_vector_store() -> VectorStore:
    settings = get_settings()
    return PineconeVectorStore(
        api_key=settings.pinecone_api_key, index_name=settings.pinecone_index_name
    )


@lru_cache
def get_embedder() -> Embedder:
    return OpenAIEmbedder(api_key=get_settings().openai_api_key)


@lru_cache
def get_ocr_service() -> OcrService:
    return TextractOcrService(region=get_settings().aws_region)


def get_pipeline(
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
    ocr: Annotated[OcrService, Depends(get_ocr_service)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
) -> IngestionPipeline:
    return IngestionPipeline(
        blob_store=blob_store, ocr=ocr, embedder=embedder, vector_store=vector_store
    )


PipelineDep = Annotated[IngestionPipeline, Depends(get_pipeline)]
