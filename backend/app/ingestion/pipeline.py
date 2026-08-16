"""Orchestrates parse -> OCR -> chunk -> embed -> upsert -> status (implementation.md §5).

`IngestionPipeline` is constructed with ports (`BlobStore`, `OcrService`, `Embedder`,
`VectorStore`) so production wires the real adapters and tests wire the fakes — see
`tests/integration/test_ingestion_pipeline.py`.
"""

import contextlib
import logging
import uuid
from itertools import islice

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk
from app.ingestion.chunker import chunk_pages
from app.ingestion.parser import UnreadablePdfError, parse_pdf
from app.ingestion.ports import (
    BlobNotFoundError,
    BlobStore,
    Embedder,
    OcrService,
    VectorRecord,
    VectorStore,
)

logger = logging.getLogger(__name__)

DEFAULT_TARGET_TOKENS = 500
DEFAULT_OVERLAP_TOKENS = 75
DEFAULT_EMBED_BATCH_SIZE = 100


def namespace_for(owner_id: str) -> str:
    """One Pinecone namespace per owner, so a query can never cross into another user's
    documents even if the `owner_id` metadata filter were ever forgotten (implementation.md
    §4, §11)."""
    return f"owner-{owner_id}"


def vector_id(document_id: str, page: int, chunk_index: int) -> str:
    return f"{document_id}:p{page}:c{chunk_index}"


def _batched(items: list, size: int):
    it = iter(items)
    while batch := list(islice(it, size)):
        yield batch


class IngestionPipeline:
    def __init__(
        self,
        blob_store: BlobStore,
        ocr: OcrService,
        embedder: Embedder,
        vector_store: VectorStore,
        target_tokens: int = DEFAULT_TARGET_TOKENS,
        overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
        embed_batch_size: int = DEFAULT_EMBED_BATCH_SIZE,
    ) -> None:
        self._blob_store = blob_store
        self._ocr = ocr
        self._embedder = embedder
        self._vector_store = vector_store
        self._target_tokens = target_tokens
        self._overlap_tokens = overlap_tokens
        self._embed_batch_size = embed_batch_size

    @property
    def blob_store(self) -> BlobStore:
        """Exposed so `api/documents.py` can store the raw upload before `ingest` reads it."""
        return self._blob_store

    def ingest(self, db: Session, document_id: uuid.UUID) -> None:
        document = db.get(Document, document_id)
        if document is None:
            raise LookupError(f"no document with id {document_id}")

        document.status = "processing"
        db.commit()

        try:
            self._run(db, document)
        except Exception as exc:  # noqa: BLE001 - any failure marks the document failed, not the request
            db.rollback()
            document = db.get(Document, document_id)
            document.status = "failed"
            document.error = str(exc)
            db.commit()
            logger.warning("ingestion failed for document %s: %s", document_id, exc)

    def _run(self, db: Session, document: Document) -> None:
        try:
            data = self._blob_store.get(document.s3_key)
        except BlobNotFoundError as exc:
            raise RuntimeError(f"document blob missing: {exc}") from exc

        try:
            pages = parse_pdf(data)
        except UnreadablePdfError as exc:
            raise RuntimeError(f"unreadable PDF: {exc}") from exc

        ocr_pages = [page.number for page in pages if page.needs_ocr]
        ocr_text = self._ocr.extract_text(data, ocr_pages) if ocr_pages else {}
        pages = [
            page
            if not page.needs_ocr or not ocr_text.get(page.number)
            else type(page)(number=page.number, text=ocr_text[page.number], needs_ocr=False)
            for page in pages
        ]
        # A page OCR could not read stays empty text and is dropped by the chunker rather
        # than failing the whole document (implementation.md §5).

        chunks = chunk_pages(
            pages, target_tokens=self._target_tokens, overlap_tokens=self._overlap_tokens
        )
        if not chunks:
            raise RuntimeError("no text could be extracted from this document")

        # Replace-not-append: clear any chunks/vectors from a previous ingest attempt.
        self._delete_existing_chunks(db, document)

        records = []
        chunk_rows = []
        for batch in _batched(chunks, self._embed_batch_size):
            vectors = self._embedder.embed([chunk.text for chunk in batch])
            for chunk, values in zip(batch, vectors, strict=True):
                vid = vector_id(str(document.id), chunk.page, chunk.index)
                records.append(
                    VectorRecord(
                        id=vid,
                        values=values,
                        metadata={
                            "document_id": str(document.id),
                            "owner_id": str(document.owner_id),
                            "filename": document.filename,
                            "page": chunk.page,
                        },
                    )
                )
                chunk_rows.append(
                    DocumentChunk(
                        document_id=document.id,
                        pinecone_id=vid,
                        page=chunk.page,
                        chunk_index=chunk.index,
                        text=chunk.text,
                    )
                )

        namespace = namespace_for(str(document.owner_id))
        self._vector_store.upsert(records, namespace)
        db.add_all(chunk_rows)
        document.status = "ready"
        document.error = None
        db.commit()

    def search(self, db: Session, owner_id: uuid.UUID, query: str, top_k: int = 5) -> list[dict]:
        """`pdf_search(query, top_k)` per implementation.md §6 — Phase 4's agent tool
        wraps this same method rather than re-implementing retrieval."""
        vector = self._embedder.embed([query])[0]
        matches = self._vector_store.query(
            vector, top_k=top_k, namespace=namespace_for(str(owner_id))
        )
        if not matches:
            return []

        rows_by_id = {
            row.pinecone_id: row
            for row in db.execute(
                select(DocumentChunk).where(
                    DocumentChunk.pinecone_id.in_([match.id for match in matches])
                )
            ).scalars()
        }
        results = []
        for match in matches:
            row = rows_by_id.get(match.id)
            if row is None:
                continue
            results.append(
                {
                    "document_id": match.metadata.get("document_id"),
                    "filename": match.metadata.get("filename"),
                    "page": match.metadata.get("page"),
                    "text": row.text,
                    "score": match.score,
                }
            )
        return results

    def remove(self, db: Session, document: Document) -> None:
        namespace = namespace_for(str(document.owner_id))
        ids = [row.pinecone_id for row in document.chunks]
        if ids:
            self._vector_store.delete(ids, namespace)
        with contextlib.suppress(BlobNotFoundError):
            self._blob_store.delete(document.s3_key)
        db.delete(document)
        db.commit()

    def _delete_existing_chunks(self, db: Session, document: Document) -> None:
        existing = (
            db.execute(select(DocumentChunk).where(DocumentChunk.document_id == document.id))
            .scalars()
            .all()
        )
        if not existing:
            return
        namespace = namespace_for(str(document.owner_id))
        self._vector_store.delete([row.pinecone_id for row in existing], namespace)
        for row in existing:
            db.delete(row)
        db.flush()
