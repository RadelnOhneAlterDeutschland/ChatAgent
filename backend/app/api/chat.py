"""`POST /chat` and session listing (implementation.md §7, §8).

Non-streaming JSON response, not SSE as originally sketched — the orchestrator only ever
has a full turn (after any tool calls resolve) to hand back, so there is no incremental
token stream to forward yet. Revisit alongside Phase 5's frontend integration.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.agent.deps import LLMProviderDep
from app.agent.orchestrator import AgentOrchestrator
from app.agent.providers.base import Message
from app.agent.tools.pdf_search import make_pdf_search_tool
from app.api.deps import CurrentUser, DbSession
from app.db.models import ChatMessage, ChatSession
from app.ingestion.deps import PipelineDep
from app.ingestion.system_owner import ensure_system_user

router = APIRouter(prefix="/chat", tags=["chat"])

TITLE_MAX_LENGTH = 80


class ChatRequest(BaseModel):
    message: str
    session_id: uuid.UUID | None = None


class ChatResponse(BaseModel):
    session_id: uuid.UUID
    message: str
    citations: list[dict]


class ChatMessagePublic(BaseModel):
    role: str
    content: str | None
    created_at: datetime


class ChatSessionPublic(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime


class ChatSessionDetail(ChatSessionPublic):
    messages: list[ChatMessagePublic]


def _get_owned_session(
    db: DbSession, current_user: CurrentUser, session_id: uuid.UUID
) -> ChatSession:
    session = db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.user_id == current_user.id
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    return session


@router.post("", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    current_user: CurrentUser,
    db: DbSession,
    pipeline: PipelineDep,
    llm_provider: LLMProviderDep,
) -> ChatResponse:
    if request.session_id is None:
        session = ChatSession(user_id=current_user.id, title=request.message[:TITLE_MAX_LENGTH])
        db.add(session)
        db.commit()
    else:
        session = _get_owned_session(db, current_user, request.session_id)

    history = [
        Message(role=row.role, content=row.content)
        for row in db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at)
        ).scalars()
    ]

    # pdf_search reads the one shared corpus (plan.md Phase 2b), not current_user's own
    # documents — there's no such thing anymore.
    owner = ensure_system_user(db)
    tools = [make_pdf_search_tool(pipeline, db, owner.id)]
    orchestrator = AgentOrchestrator(llm_provider, tools=tools)
    result = orchestrator.run(history=history, user_message=request.message)

    db.add(ChatMessage(session_id=session.id, role="user", content=request.message))
    db.add(
        ChatMessage(
            session_id=session.id,
            role="assistant",
            content=result.content,
            tool_calls=result.citations or None,
        )
    )
    db.commit()

    return ChatResponse(session_id=session.id, message=result.content, citations=result.citations)


@router.get("/sessions", response_model=list[ChatSessionPublic])
def list_sessions(current_user: CurrentUser, db: DbSession) -> list[ChatSession]:
    return list(
        db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == current_user.id)
            .order_by(ChatSession.created_at)
        ).scalars()
    )


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_session(session_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> ChatSession:
    return _get_owned_session(db, current_user, session_id)
