"""The pipeline wired to fakes: parse -> OCR -> chunk -> embed -> upsert -> status."""

import fitz
import pytest

from app.db.models import Document, DocumentChunk, User
from app.ingestion.pipeline import IngestionPipeline, namespace_for, vector_id
from tests.fakes import FakeBlobStore, FakeEmbedder, FakeOcrService, FakeVectorStore


def build_pdf(page_texts: list[str]) -> bytes:
    document = fitz.open()
    for text in page_texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=11)
    return document.tobytes()


TEXT_PAGE = "The quarterly revenue figure was four point two million dollars this year."


@pytest.fixture
def owner(db_session) -> User:
    user = User(email="ana@example.com", password_hash="x")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def blob_store() -> FakeBlobStore:
    return FakeBlobStore()


@pytest.fixture
def vector_store() -> FakeVectorStore:
    return FakeVectorStore()


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder(dimension=64)


@pytest.fixture
def ocr() -> FakeOcrService:
    return FakeOcrService()


@pytest.fixture
def pipeline(blob_store, ocr, embedder, vector_store) -> IngestionPipeline:
    return IngestionPipeline(
        blob_store=blob_store,
        ocr=ocr,
        embedder=embedder,
        vector_store=vector_store,
        target_tokens=40,
        overlap_tokens=8,
        embed_batch_size=2,
    )


@pytest.fixture
def stored_document(db_session, owner, blob_store):
    def _store(page_texts: list[str], filename: str = "report.pdf") -> Document:
        document = Document(owner_id=owner.id, filename=filename, s3_key=f"{owner.id}/{filename}")
        db_session.add(document)
        db_session.commit()
        blob_store.put(document.s3_key, build_pdf(page_texts), "application/pdf")
        return document

    return _store


class TestVectorIdentity:
    def test_a_vector_id_is_derived_from_document_page_and_chunk(self) -> None:
        assert vector_id("doc-1", page=3, chunk_index=2) == "doc-1:p3:c2"

    def test_a_namespace_isolates_one_owner_from_another(self) -> None:
        assert namespace_for("owner-a") != namespace_for("owner-b")


class TestHappyPath:
    def test_a_processed_document_is_marked_ready(self, pipeline, db_session, stored_document):
        document = stored_document([TEXT_PAGE])

        pipeline.ingest(db_session, document.id)

        db_session.refresh(document)
        assert document.status == "ready"

    def test_chunk_rows_map_vector_ids_back_to_pages(self, pipeline, db_session, stored_document):
        document = stored_document([TEXT_PAGE, TEXT_PAGE])

        pipeline.ingest(db_session, document.id)

        rows = db_session.query(DocumentChunk).order_by(DocumentChunk.chunk_index).all()
        assert {row.page for row in rows} == {1, 2}
        assert all(row.pinecone_id.startswith(str(document.id)) for row in rows)

    def test_the_chunk_text_is_stored_for_citation_display(
        self, pipeline, db_session, stored_document
    ):
        document = stored_document([TEXT_PAGE])

        pipeline.ingest(db_session, document.id)

        assert "revenue" in db_session.query(DocumentChunk).first().text.lower()

    def test_vectors_land_in_the_owner_namespace_with_citation_metadata(
        self, pipeline, db_session, stored_document, vector_store, owner
    ):
        document = stored_document([TEXT_PAGE])

        pipeline.ingest(db_session, document.id)

        bucket = vector_store.namespaces[namespace_for(str(owner.id))]
        metadata = next(iter(bucket.values())).metadata
        assert metadata["document_id"] == str(document.id)
        assert metadata["owner_id"] == str(owner.id)
        assert metadata["page"] == 1
        assert metadata["filename"] == "report.pdf"

    def test_every_stored_chunk_has_a_matching_vector(
        self, pipeline, db_session, stored_document, vector_store, owner
    ):
        document = stored_document([TEXT_PAGE, TEXT_PAGE, TEXT_PAGE])

        pipeline.ingest(db_session, document.id)

        row_ids = {row.pinecone_id for row in db_session.query(DocumentChunk).all()}
        assert row_ids == set(vector_store.namespaces[namespace_for(str(owner.id))])

    def test_embedding_calls_are_batched(self, pipeline, db_session, stored_document, embedder):
        document = stored_document([TEXT_PAGE] * 4)

        pipeline.ingest(db_session, document.id)

        assert max(embedder.batch_sizes) <= 2

    def test_an_ingested_document_can_be_retrieved_by_its_own_words(
        self, pipeline, db_session, stored_document, vector_store, embedder, owner
    ):
        """Phase 2 exit criterion: spot-check retrieval against the upserted vectors."""
        document = stored_document([TEXT_PAGE, "Unrelated content about shipping logistics only."])

        pipeline.ingest(db_session, document.id)

        query_vector = embedder.embed(["quarterly revenue figure"])[0]
        matches = vector_store.query(query_vector, top_k=1, namespace=namespace_for(str(owner.id)))
        assert matches[0].metadata["page"] == 1


class TestOcr:
    def test_a_scanned_page_is_sent_to_ocr(self, pipeline, db_session, stored_document, ocr):
        ocr.page_text = {2: "Scanned page text recovered by optical character recognition."}
        document = stored_document([TEXT_PAGE, ""])

        pipeline.ingest(db_session, document.id)

        assert ocr.requested_pages == [2]

    def test_ocr_text_is_chunked_like_any_other_page(
        self, pipeline, db_session, stored_document, ocr
    ):
        ocr.page_text = {1: "Scanned page text recovered by optical character recognition."}
        document = stored_document([""])

        pipeline.ingest(db_session, document.id)

        chunk = db_session.query(DocumentChunk).one()
        assert "optical character recognition" in chunk.text
        assert chunk.page == 1

    def test_a_page_with_a_text_layer_is_not_sent_to_ocr(
        self, pipeline, db_session, stored_document, ocr
    ):
        document = stored_document([TEXT_PAGE])

        pipeline.ingest(db_session, document.id)

        assert ocr.requested_pages == []

    def test_a_page_ocr_cannot_read_is_skipped_rather_than_failing_the_document(
        self, pipeline, db_session, stored_document, ocr
    ):
        ocr.page_text = {}
        document = stored_document([TEXT_PAGE, ""])

        pipeline.ingest(db_session, document.id)

        db_session.refresh(document)
        assert document.status == "ready"
        assert {row.page for row in db_session.query(DocumentChunk).all()} == {1}


class TestFailurePaths:
    def test_an_unreadable_pdf_marks_the_document_failed_with_a_reason(
        self, pipeline, db_session, owner, blob_store
    ):
        document = Document(owner_id=owner.id, filename="broken.pdf", s3_key="k")
        db_session.add(document)
        db_session.commit()
        blob_store.put("k", b"not a pdf", "application/pdf")

        pipeline.ingest(db_session, document.id)

        db_session.refresh(document)
        assert document.status == "failed"
        assert document.error

    def test_a_missing_blob_marks_the_document_failed(self, pipeline, db_session, owner):
        document = Document(owner_id=owner.id, filename="gone.pdf", s3_key="absent")
        db_session.add(document)
        db_session.commit()

        pipeline.ingest(db_session, document.id)

        db_session.refresh(document)
        assert document.status == "failed"

    def test_a_failed_document_leaves_no_half_written_chunks(
        self, pipeline, db_session, owner, blob_store, embedder
    ):
        def explode(texts):
            raise RuntimeError("embedding provider is down")

        embedder.embed = explode
        document = Document(owner_id=owner.id, filename="x.pdf", s3_key="k")
        db_session.add(document)
        db_session.commit()
        blob_store.put("k", build_pdf([TEXT_PAGE]), "application/pdf")

        pipeline.ingest(db_session, document.id)

        db_session.refresh(document)
        assert document.status == "failed"
        assert db_session.query(DocumentChunk).count() == 0

    def test_a_pdf_with_no_extractable_text_anywhere_is_marked_failed(
        self, pipeline, db_session, stored_document
    ):
        document = stored_document([""])

        pipeline.ingest(db_session, document.id)

        db_session.refresh(document)
        assert document.status == "failed"
        assert "no text" in document.error.lower()

    def test_ingesting_an_unknown_document_id_raises(self, pipeline, db_session):
        import uuid

        with pytest.raises(LookupError):
            pipeline.ingest(db_session, uuid.uuid4())


class TestReingestion:
    def test_reingesting_replaces_the_previous_chunks_rather_than_duplicating(
        self, pipeline, db_session, stored_document
    ):
        document = stored_document([TEXT_PAGE])
        pipeline.ingest(db_session, document.id)
        first_count = db_session.query(DocumentChunk).count()

        pipeline.ingest(db_session, document.id)

        assert db_session.query(DocumentChunk).count() == first_count


class TestRemoval:
    def test_removing_a_document_deletes_its_vectors_and_blob(
        self, pipeline, db_session, stored_document, vector_store, blob_store, owner
    ):
        document = stored_document([TEXT_PAGE])
        pipeline.ingest(db_session, document.id)
        key = document.s3_key

        pipeline.remove(db_session, document)

        assert vector_store.namespaces.get(namespace_for(str(owner.id)), {}) == {}
        assert key not in blob_store.objects
        assert db_session.query(DocumentChunk).count() == 0
        assert db_session.query(Document).count() == 0
