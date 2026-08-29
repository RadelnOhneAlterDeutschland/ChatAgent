"""In-process polling scheduler for folder-sync ingestion (plan.md Phase 8).

Resolves Phase 2b's open "cron scheduling mechanism" decision: the backend polls its own
watched folders on a background thread, so no OS-level cron/Task Scheduler entry is
needed on any platform. `app/ingestion/cli.py` still exists for anyone who wants a manual
or externally-scheduled trigger instead — this doesn't replace it.

`poll_forever` is the pure loop, independent of real threading/sleeping, so it can be
unit-tested without a real clock. `IngestionScheduler` is the thin threading wrapper
around it; `build_folder_sync_fn` wires the real ingestion adapters, the same
construction `app/ingestion/cli.py` uses for a manual run.
"""

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


def poll_forever(
    sync_fn: Callable[[], None], wait: Callable[[float], bool], interval_seconds: float
) -> None:
    """Calls `sync_fn` immediately, then again every `interval_seconds`, until `wait`
    reports a stop was requested. `wait` follows `threading.Event.wait`'s contract (blocks
    up to `interval_seconds`, returns `True` if the event fired) — production passes the
    real thing; tests pass a fake that returns instantly, so this loop never sleeps under
    test."""
    while True:
        try:
            sync_fn()
        except Exception:  # noqa: BLE001 - one bad tick must not kill the poller
            logger.exception("scheduled folder sync failed")
        if wait(interval_seconds):
            return


class IngestionScheduler:
    """Runs `poll_forever` on a background daemon thread. Started/stopped from the FastAPI
    lifespan (`app/main.py`)."""

    def __init__(self, sync_fn: Callable[[], None], interval_seconds: float) -> None:
        self._sync_fn = sync_fn
        self._interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=poll_forever,
            args=(self._sync_fn, self._stop_event.wait, self._interval_seconds),
            daemon=True,
            name="ingestion-scheduler",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None


def build_folder_sync_fn(folder_paths: list[str]) -> Callable[[], None]:
    """Wires the real ingestion adapters and a fresh DB session per tick — the same
    construction `app/ingestion/cli.py` uses for a manual run."""
    from app.db.session import get_session_factory
    from app.ingestion.deps import get_blob_store, get_embedder, get_ocr_service, get_vector_store
    from app.ingestion.folder_watcher import sync_folder
    from app.ingestion.pipeline import IngestionPipeline

    pipeline = IngestionPipeline(
        blob_store=get_blob_store(),
        ocr=get_ocr_service(),
        embedder=get_embedder(),
        vector_store=get_vector_store(),
    )
    session_factory = get_session_factory()

    def sync_fn() -> None:
        db = session_factory()
        try:
            report = sync_folder(db, pipeline, folder_paths)
            logger.info(
                "scheduled folder sync: %d created, %d updated, %d unchanged, %d failed",
                len(report.created),
                len(report.updated),
                report.unchanged,
                len(report.failed),
            )
            for source_path, error in report.failed:
                logger.error("could not read %s: %s", source_path, error)
        finally:
            db.close()

    return sync_fn
