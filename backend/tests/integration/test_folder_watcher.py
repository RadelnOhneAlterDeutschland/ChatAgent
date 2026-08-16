"""Folder-scan cron ingestion (plan.md Phase 2b), wired to fakes — same pattern as
`test_ingestion_pipeline.py`, plus a real `tmp_path` standing in for the watched folder.
"""

import os

import fitz
import pytest

from app.db.models import Document, DocumentChunk
from app.ingestion.folder_watcher import discover_pdfs, sync_folder
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.system_owner import ensure_system_user
from tests.fakes import FakeBlobStore, FakeEmbedder, FakeOcrService, FakeVectorStore


def build_pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    if text:
        page.insert_text((72, 72), text, fontsize=11)
    return document.tobytes()


@pytest.fixture
def pipeline() -> IngestionPipeline:
    return IngestionPipeline(
        blob_store=FakeBlobStore(),
        ocr=FakeOcrService(),
        embedder=FakeEmbedder(dimension=64),
        vector_store=FakeVectorStore(),
        target_tokens=40,
        overlap_tokens=8,
    )


class TestDiscoverPdfs:
    def test_finds_a_pdf_in_the_folder(self, tmp_path) -> None:
        (tmp_path / "revenue.pdf").write_bytes(build_pdf("hello"))

        found = discover_pdfs([str(tmp_path)])

        assert [p.name for p in found] == ["revenue.pdf"]

    def test_finds_pdfs_in_nested_subfolders(self, tmp_path) -> None:
        nested = tmp_path / "2026" / "q1"
        nested.mkdir(parents=True)
        (nested / "report.pdf").write_bytes(build_pdf("hello"))

        found = discover_pdfs([str(tmp_path)])

        assert [p.name for p in found] == ["report.pdf"]

    def test_ignores_non_pdf_files(self, tmp_path) -> None:
        (tmp_path / "notes.txt").write_text("not a pdf")

        assert discover_pdfs([str(tmp_path)]) == []

    def test_extension_match_is_case_insensitive(self, tmp_path) -> None:
        (tmp_path / "REPORT.PDF").write_bytes(build_pdf("hello"))

        found = discover_pdfs([str(tmp_path)])

        assert [p.name for p in found] == ["REPORT.PDF"]

    def test_a_missing_folder_is_skipped_rather_than_raising(self, tmp_path) -> None:
        missing = tmp_path / "does-not-exist"

        assert discover_pdfs([str(missing)]) == []

    def test_searches_every_given_folder(self, tmp_path) -> None:
        first, second = tmp_path / "a", tmp_path / "b"
        first.mkdir()
        second.mkdir()
        (first / "one.pdf").write_bytes(build_pdf("hello"))
        (second / "two.pdf").write_bytes(build_pdf("hello"))

        found = discover_pdfs([str(first), str(second)])

        assert {p.name for p in found} == {"one.pdf", "two.pdf"}


class TestSyncFolder:
    def test_a_new_pdf_becomes_a_ready_document(self, db_session, pipeline, tmp_path) -> None:
        (tmp_path / "revenue.pdf").write_bytes(build_pdf("Quarterly revenue was strong."))

        report = sync_folder(db_session, pipeline, [str(tmp_path)])

        assert len(report.created) == 1
        document = db_session.query(Document).one()
        assert document.status == "ready"
        assert document.filename == "revenue.pdf"

    def test_the_document_is_owned_by_the_shared_system_user(
        self, db_session, pipeline, tmp_path
    ) -> None:
        (tmp_path / "revenue.pdf").write_bytes(build_pdf("hello"))

        sync_folder(db_session, pipeline, [str(tmp_path)])

        document = db_session.query(Document).one()
        system_user = ensure_system_user(db_session)
        assert document.owner_id == system_user.id

    def test_multiple_documents_share_one_owner(self, db_session, pipeline, tmp_path) -> None:
        (tmp_path / "a.pdf").write_bytes(build_pdf("hello a"))
        (tmp_path / "b.pdf").write_bytes(build_pdf("hello b"))

        sync_folder(db_session, pipeline, [str(tmp_path)])

        owners = {doc.owner_id for doc in db_session.query(Document).all()}
        assert len(owners) == 1

    def test_rescanning_an_unchanged_file_does_not_duplicate_it(
        self, db_session, pipeline, tmp_path
    ) -> None:
        (tmp_path / "revenue.pdf").write_bytes(build_pdf("hello"))
        sync_folder(db_session, pipeline, [str(tmp_path)])

        report = sync_folder(db_session, pipeline, [str(tmp_path)])

        assert report.unchanged == 1
        assert report.created == []
        assert db_session.query(Document).count() == 1

    def test_a_modified_file_is_reingested_not_duplicated(
        self, db_session, pipeline, tmp_path
    ) -> None:
        path = tmp_path / "revenue.pdf"
        path.write_bytes(build_pdf("Original content."))
        sync_folder(db_session, pipeline, [str(tmp_path)])

        path.write_bytes(build_pdf("Revised content about mergers."))
        os.utime(path, (path.stat().st_mtime + 10, path.stat().st_mtime + 10))

        report = sync_folder(db_session, pipeline, [str(tmp_path)])

        assert report.updated == [str(path.resolve())]
        assert db_session.query(Document).count() == 1
        chunk = db_session.query(DocumentChunk).one()
        assert "mergers" in chunk.text.lower()

    def test_an_unreadable_pdf_is_marked_failed_not_raised(
        self, db_session, pipeline, tmp_path
    ) -> None:
        (tmp_path / "corrupt.pdf").write_bytes(b"this is not a pdf at all")

        sync_folder(db_session, pipeline, [str(tmp_path)])

        document = db_session.query(Document).one()
        assert document.status == "failed"

    def test_no_folders_configured_finds_nothing_and_does_not_raise(
        self, db_session, pipeline
    ) -> None:
        report = sync_folder(db_session, pipeline, [])

        assert report.created == []
        assert db_session.query(Document).count() == 0

    def test_a_file_removed_between_discovery_and_read_is_reported_not_raised(
        self, db_session, pipeline, tmp_path, monkeypatch
    ) -> None:
        import pathlib

        path = tmp_path / "vanishes.pdf"
        path.write_bytes(build_pdf("hello"))
        path.unlink()  # discover_pdfs already ran conceptually; simulate the gap directly

        def stat_raises(self, *args, **kwargs):
            raise OSError("file vanished between discovery and read")

        monkeypatch.setattr(pathlib.Path, "stat", stat_raises)
        monkeypatch.setattr(
            "app.ingestion.folder_watcher.discover_pdfs", lambda folder_paths: [path]
        )

        report = sync_folder(db_session, pipeline, [str(tmp_path)])

        assert report.failed == [(str(path.resolve()), "file vanished between discovery and read")]
        assert db_session.query(Document).count() == 0
