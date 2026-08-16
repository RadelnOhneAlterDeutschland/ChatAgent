"""Phase 1 exit criterion: the schema is ready to receive chat history rows."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import ChatMessage, ChatSession, Document, DocumentChunk, User


@pytest.fixture
def user(db_session) -> User:
    user = User(email="ana@example.com", password_hash="x")
    db_session.add(user)
    db_session.commit()
    return user


class TestUsers:
    def test_a_user_gets_an_id_and_a_creation_timestamp(self, db_session, user: User) -> None:
        db_session.refresh(user)

        assert isinstance(user.id, uuid.UUID)
        assert user.created_at is not None

    def test_two_users_cannot_share_an_email(self, db_session, user: User) -> None:
        db_session.add(User(email="ana@example.com", password_hash="y"))

        with pytest.raises(IntegrityError):
            db_session.commit()


class TestChatHistory:
    def test_a_message_records_the_tool_calls_that_produced_it(self, db_session, user) -> None:
        session = ChatSession(user_id=user.id, title="Q1 revenue")
        db_session.add(session)
        db_session.flush()
        tool_calls = [
            {"tool": "pdf_search", "args": {"query": "revenue"}, "citations": ["a.pdf#3"]}
        ]
        db_session.add(
            ChatMessage(
                session_id=session.id,
                role="assistant",
                content="Revenue was 4.2M [a.pdf p.3]",
                tool_calls=tool_calls,
            )
        )
        db_session.commit()

        stored = db_session.query(ChatMessage).one()

        assert stored.tool_calls == tool_calls

    def test_a_message_role_outside_the_allowed_set_is_rejected(self, db_session, user) -> None:
        session = ChatSession(user_id=user.id)
        db_session.add(session)
        db_session.flush()
        db_session.add(ChatMessage(session_id=session.id, role="wizard", content="hi"))

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_deleting_a_session_deletes_its_messages(self, db_session, user) -> None:
        session = ChatSession(user_id=user.id)
        db_session.add(session)
        db_session.flush()
        db_session.add(ChatMessage(session_id=session.id, role="user", content="hi"))
        db_session.commit()

        db_session.delete(session)
        db_session.commit()

        assert db_session.query(ChatMessage).count() == 0


class TestDocuments:
    def test_a_document_starts_pending_and_maps_chunks_to_vector_ids(
        self, db_session, user
    ) -> None:
        document = Document(owner_id=user.id, filename="report.pdf", s3_key="u/1/report.pdf")
        db_session.add(document)
        db_session.flush()
        db_session.add(
            DocumentChunk(
                document_id=document.id,
                pinecone_id="report-p3-c0",
                page=3,
                chunk_index=0,
                text="Revenue was 4.2M",
            )
        )
        db_session.commit()

        assert document.status == "pending"
        assert db_session.query(DocumentChunk).one().pinecone_id == "report-p3-c0"

    def test_a_document_status_outside_the_allowed_set_is_rejected(self, db_session, user) -> None:
        db_session.add(Document(owner_id=user.id, filename="x.pdf", s3_key="k", status="haunted"))

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_deleting_a_document_deletes_its_chunks(self, db_session, user) -> None:
        document = Document(owner_id=user.id, filename="x.pdf", s3_key="k")
        db_session.add(document)
        db_session.flush()
        db_session.add(
            DocumentChunk(
                document_id=document.id, pinecone_id="v1", page=1, chunk_index=0, text="t"
            )
        )
        db_session.commit()

        db_session.delete(document)
        db_session.commit()

        assert db_session.query(DocumentChunk).count() == 0
