"""Cron entry point: `python -m app.ingestion.cli`.

Scheduling itself is left to the deploy environment — a host crontab line or a scheduled
container run, not a `docker-compose.yml` service (plan.md Phase 2b backlog). Example
crontab entry, every 10 minutes:

    */10 * * * * cd /path/to/backend && .venv/bin/python -m app.ingestion.cli \
        >> /var/log/chatagent-ingest.log 2>&1
"""

import logging

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.ingestion.deps import get_blob_store, get_embedder, get_ocr_service, get_vector_store
from app.ingestion.folder_watcher import sync_folder
from app.ingestion.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    folders = [p.strip() for p in get_settings().ingestion_folder_paths.split(",") if p.strip()]
    if not folders:
        logger.warning("INGESTION_FOLDER_PATHS is empty — nothing to scan")
        return

    pipeline = IngestionPipeline(
        blob_store=get_blob_store(),
        ocr=get_ocr_service(),
        embedder=get_embedder(),
        vector_store=get_vector_store(),
    )

    db = get_session_factory()()
    try:
        report = sync_folder(db, pipeline, folders)
        logger.info(
            "folder sync done: %d created, %d updated, %d unchanged, %d failed",
            len(report.created),
            len(report.updated),
            report.unchanged,
            len(report.failed),
        )
        for source_path, error in report.failed:
            logger.error("could not read %s: %s", source_path, error)
    finally:
        db.close()


if __name__ == "__main__":
    main()
