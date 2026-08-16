"""Phase 1 initial schema: users, chat sessions/messages, documents, document chunks.

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("session_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("tool_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.CheckConstraint("role IN ('user', 'assistant', 'tool')", name="ck_chat_messages_role"),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        # Phase 2b: set only for documents the folder-sync cron ingested (absolute path
        # on the watched filesystem) — lets a re-scan tell "unchanged" apart from
        # "new"/"modified" without re-reading and re-embedding every file every run.
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("source_mtime", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'failed')", name="ck_documents_status"
        ),
        sa.UniqueConstraint("source_path", name="uq_documents_source_path"),
    )
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("pinecone_id", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("pinecone_id", name="uq_document_chunks_pinecone_id"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])


def downgrade() -> None:
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("users")
