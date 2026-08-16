"""Ports the ingestion pipeline depends on, and the value objects that cross them.

Production wires the real adapters (`blob_store.py`, `vector_store.py`, `embedder.py`,
`ocr.py`). Tests wire the in-memory fakes in `tests/fakes/`, kept honest by
`tests/contract/test_port_contracts.py`. See `.claude/skills/bdd-tdd/SKILL.md` §"Ports
and adapters".
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

# Matches `text-embedding-3-small`'s default output size (implementation.md §4).
EMBEDDING_DIMENSION = 1536


class BlobNotFoundError(Exception):
    """Raised when a blob store key has no object (implementation.md §11: never silent)."""

    def __init__(self, key: str) -> None:
        super().__init__(f"no object at key: {key}")
        self.key = key


@dataclass(frozen=True)
class Page:
    """One extracted PDF page."""

    number: int
    text: str
    needs_ocr: bool


@dataclass(frozen=True)
class Chunk:
    """One chunk produced by the splitter, still tied to its source page."""

    text: str
    page: int
    index: int


@dataclass(frozen=True)
class VectorRecord:
    id: str
    values: list[float]
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Match:
    id: str
    score: float
    metadata: dict = field(default_factory=dict)


class BlobStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str = "application/pdf") -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class VectorStore(Protocol):
    def upsert(self, records: Sequence[VectorRecord], namespace: str) -> None: ...
    def query(self, vector: Sequence[float], top_k: int, namespace: str) -> list[Match]: ...
    def delete(self, ids: Sequence[str], namespace: str) -> None: ...


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OcrService(Protocol):
    def extract_text(self, data: bytes, pages: Sequence[int]) -> dict[int, str]: ...
