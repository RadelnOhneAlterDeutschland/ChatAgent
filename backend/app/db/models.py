"""SQLAlchemy models — see implementation.md §3.

Portable across Postgres (prod) and SQLite (tests): UUID via `sa.Uuid`, JSONB via a
`JSON` variant. Business SQL tables live in a separate schema/connection so the
agent's read-only role can never reach `users` or `chat_*`.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JsonColumn = JSON().with_variant(JSONB(), "postgresql")

MESSAGE_ROLES = ("user", "assistant", "tool")
DOCUMENT_STATUSES = ("pending", "processing", "ready", "failed")


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class ChatSession(Base):
    """A conversation. Retained indefinitely; deleted only by its owner (plan.md Phase 1)."""

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()

    user: Mapped[User] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'tool')", name="ck_chat_messages_role"),
    )

    id: Mapped[uuid.UUID] = _pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    # Which tools ran and what they cited — audit trail and citation source.
    tool_calls: Mapped[list | dict | None] = mapped_column(JsonColumn)
    created_at: Mapped[datetime] = _created_at()

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'failed')",
            name="ck_documents_status",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = _created_at()
    # Phase 2b: set only for documents the folder-sync cron ingested (absolute path on
    # the watched filesystem), so a re-scan can tell "already ingested, unchanged" apart
    # from "new" or "modified" by comparing source_mtime. Null for anything else.
    source_path: Mapped[str | None] = mapped_column(Text, unique=True)
    source_mtime: Mapped[float | None] = mapped_column(Float)

    owner: Mapped[User] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    """Maps a Pinecone vector id back to its document, page, and source text."""

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = _pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pinecone_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    document: Mapped[Document] = relationship(back_populates="chunks")
