"""Application settings. Local: `.env`. Prod: AWS Secrets Manager injected as env vars."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    app_name: str = "chat-agent"
    app_version: str = "0.1.0"
    environment: str = "local"

    # App database: users, chat history, document metadata.
    database_url: str = Field(alias="DATABASE_URL")

    # Auth
    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = Field(default=30, alias="JWT_EXPIRY_MINUTES")
    password_min_length: int = 12

    # External services. Not used until Phase 2+, but fail fast at boot if absent.
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    openai_chat_model: str = Field(default="gpt-4o-mini", alias="OPENAI_CHAT_MODEL")
    pinecone_api_key: str = Field(alias="PINECONE_API_KEY")
    pinecone_index_name: str = Field(alias="PINECONE_INDEX_NAME")
    s3_bucket_name: str = Field(alias="S3_BUCKET_NAME")
    aws_region: str = Field(default="eu-west-1", alias="AWS_REGION")

    # v2 (plan.md Phase 3): read-only role against the business SQL schema.
    business_database_url: str | None = Field(default=None, alias="BUSINESS_DATABASE_URL")

    # Phase 2b: folder-sync cron ingestion, replacing per-user web upload.
    # Comma-separated absolute paths — e.g. a OneDrive-desktop-synced local folder.
    ingestion_folder_paths: str = Field(default="", alias="INGESTION_FOLDER_PATHS")
    # Not a real login — the single owner every folder-ingested document (and therefore
    # every user's pdf_search) is scoped to. Get-or-created by
    # app/ingestion/system_owner.py::ensure_system_user.
    system_owner_email: str = Field(
        default="shared-library@system.local", alias="SYSTEM_OWNER_EMAIL"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
