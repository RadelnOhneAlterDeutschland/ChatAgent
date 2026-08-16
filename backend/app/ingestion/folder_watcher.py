"""Folder-scan cron ingestion trigger (plan.md Phase 2b).

Reuses `IngestionPipeline` exactly as the old web upload endpoint did — `blob_store.put`
then `pipeline.ingest` — only the trigger changed from an HTTP request to a directory
scan. `app/ingestion/cli.py` is what a cron entry actually calls; this module is the pure
sync logic, independent of how it's scheduled.

Deletion sync is explicitly NOT built (plan.md Phase 2b backlog): removing a file from a
watched folder does not remove its `Document`/vectors.
"""

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.system_owner import ensure_system_user

logger = logging.getLogger(__name__)


def discover_pdfs(folder_paths: list[str]) -> list[Path]:
    """Every `*.pdf` (case-insensitive) under each folder, recursively.

    A folder that doesn't exist is logged and skipped rather than raising — a watched
    folder can legitimately be briefly absent (e.g. a sync client not yet mounted).
    """
    found: list[Path] = []
    for raw in folder_paths:
        root = Path(raw)
        if not root.is_dir():
            logger.warning("ingestion folder does not exist, skipping: %s", root)
            continue
        found.extend(
            path for path in root.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf"
        )
    return found


@dataclass
class SyncReport:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)


def sync_folder(db: Session, pipeline: IngestionPipeline, folder_paths: list[str]) -> SyncReport:
    """New or modified (by mtime) files are (re-)ingested; unchanged files are skipped
    without touching Pinecone/S3 at all."""
    report = SyncReport()
    owner = ensure_system_user(db)

    for path in discover_pdfs(folder_paths):
        source_path = str(path.resolve())
        try:
            mtime = path.stat().st_mtime
            data = path.read_bytes()
        except OSError as exc:
            report.failed.append((source_path, str(exc)))
            continue

        existing = db.execute(
            select(Document).where(Document.source_path == source_path)
        ).scalar_one_or_none()

        if existing is not None and existing.source_mtime == mtime:
            report.unchanged += 1
            continue

        if existing is None:
            document = Document(
                owner_id=owner.id,
                filename=path.name,
                s3_key=f"shared/{uuid.uuid4()}.pdf",
                source_path=source_path,
                source_mtime=mtime,
                status="pending",
            )
            db.add(document)
            db.commit()
            report.created.append(source_path)
        else:
            document = existing
            document.source_mtime = mtime
            db.commit()
            report.updated.append(source_path)

        pipeline.blob_store.put(document.s3_key, data, "application/pdf")
        pipeline.ingest(db, document.id)  # never raises — a failure lands as status="failed"

        db.refresh(document)
        if document.status == "failed":
            logger.warning("ingestion failed for %s: %s", source_path, document.error)

    return report
