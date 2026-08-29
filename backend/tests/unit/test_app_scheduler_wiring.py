"""Inner loop: `create_app`'s decision of whether to run the Phase 8 auto-ingestion
scheduler at all. `build_folder_sync_fn` is the architecture boundary (real adapters,
real DB) — stubbed out here rather than exercised."""

from app.core.config import Settings
from app.ingestion.scheduler import IngestionScheduler
from app.main import _build_scheduler


def _settings(**overrides) -> Settings:
    defaults = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "jwt_secret": "test-secret",
        "openai_api_key": "test-key",
        "pinecone_api_key": "test-key",
        "pinecone_index_name": "test-index",
        "s3_bucket_name": "test-bucket",
    }
    return Settings(**{**defaults, **overrides})


def test_no_scheduler_when_no_folder_is_configured() -> None:
    assert _build_scheduler(_settings(ingestion_folder_paths="")) is None


def test_a_scheduler_is_built_when_a_folder_is_configured(monkeypatch) -> None:
    monkeypatch.setattr("app.main.build_folder_sync_fn", lambda folders: lambda: None)

    scheduler = _build_scheduler(_settings(ingestion_folder_paths="/watched"))

    assert isinstance(scheduler, IngestionScheduler)


def test_the_poll_interval_comes_from_settings_in_seconds(monkeypatch) -> None:
    monkeypatch.setattr("app.main.build_folder_sync_fn", lambda folders: lambda: None)

    scheduler = _build_scheduler(
        _settings(ingestion_folder_paths="/watched", ingestion_poll_minutes=5)
    )

    assert scheduler._interval_seconds == 300


def test_multiple_comma_separated_folders_are_all_passed_through(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(
        "app.main.build_folder_sync_fn",
        lambda folders: seen.setdefault("folders", folders) or (lambda: None),
    )

    _build_scheduler(_settings(ingestion_folder_paths="/one, /two"))

    assert seen["folders"] == ["/one", "/two"]
