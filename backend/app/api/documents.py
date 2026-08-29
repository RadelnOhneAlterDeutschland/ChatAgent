"""List/download/delete/search the shared PDF corpus (implementation.md §6, §8).

Documents arrive via the folder-sync cron job (`app/ingestion/folder_watcher.py`,
plan.md Phase 2b), not a web upload — there is no `POST /documents/upload` here anymore.
Every endpoint below is scoped to the one shared system owner
(`app/ingestion/system_owner.py::ensure_system_user`), not `current_user.id` — `CurrentUser`
still gates "must be signed in", it just no longer scopes *which* documents are visible.

`/documents/search` is not in the original endpoint table — it is the interim surface
for Phase 2's exit criterion ("spot-check retrieval via direct similarity query"). Phase
4's `pdf_search` agent tool wraps `IngestionPipeline.search` directly rather than calling
this endpoint, but exposing it here lets the retrieval path be exercised over HTTP now
instead of only from internal tests.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.agent.deps import LLMProviderDep
from app.api.deps import CurrentUser, CurrentUserFlexible, DbSession
from app.db.models import Document
from app.ingestion.deps import FolderPathsDep, IntakeStoreDep, PipelineDep
from app.ingestion.intake import write_confirmed_intake
from app.ingestion.intake_classifier import IntakeClassificationError, suggest_placement
from app.ingestion.parser import UnreadablePdfError, parse_pdf
from app.ingestion.ports import BlobNotFoundError
from app.ingestion.system_owner import ensure_system_user
from app.ingestion.topic_tree import discover_topic_tree

router = APIRouter(prefix="/documents", tags=["documents"])

# Keeps the classification prompt small — a folder decision doesn't need the whole
# document, just enough to tell what it's about (plan.md Phase 8).
INTAKE_EXCERPT_CHAR_LIMIT = 6000


class DocumentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    status: str
    uploaded_at: datetime


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    document_id: str
    filename: str
    page: int
    text: str
    score: float


class TopicFolderPublic(BaseModel):
    name: str
    subfolders: list[str]


class IntakeSuggestion(BaseModel):
    intake_id: str
    filename: str
    suggested_topic: str
    suggested_subfolder: str | None
    rationale: str
    topics: list[TopicFolderPublic]


class IntakeConfirmRequest(BaseModel):
    intake_id: str
    topic: str
    subfolder: str | None = None


@router.get("", response_model=list[DocumentPublic])
def list_documents(current_user: CurrentUser, db: DbSession) -> list[Document]:
    owner = ensure_system_user(db)
    return list(
        db.execute(
            select(Document).where(Document.owner_id == owner.id).order_by(Document.uploaded_at)
        ).scalars()
    )


@router.get("/{document_id}/download")
def download_document(
    document_id: uuid.UUID,
    current_user: CurrentUserFlexible,
    db: DbSession,
    pipeline: PipelineDep,
) -> Response:
    """The target of a citation link (`frontend/src/lib/api.ts::downloadUrl`) — opened as
    a plain browser navigation, `#page=N` and all, so it takes `?token=` as well as a
    Bearer header (`CurrentUserFlexible`)."""
    owner = ensure_system_user(db)
    document = db.execute(
        select(Document).where(Document.id == document_id, Document.owner_id == owner.id)
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    try:
        data = pipeline.blob_store.get(document.s3_key)
    except BlobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        ) from None

    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{document.filename}"'},
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    pipeline: PipelineDep,
) -> None:
    """Any signed-in user can delete any shared document — there's no admin-only
    restriction yet (plan.md Phase 2b, tracked as open). A deleted file that's still
    present in the watched folder reappears on the next cron run (deletion sync isn't
    built either — same tracking entry)."""
    owner = ensure_system_user(db)
    document = db.execute(
        select(Document).where(Document.id == document_id, Document.owner_id == owner.id)
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    pipeline.remove(db, document)


@router.post("/search", response_model=list[SearchResult])
def search_documents(
    request: SearchRequest,
    current_user: CurrentUser,
    db: DbSession,
    pipeline: PipelineDep,
) -> list[dict]:
    owner = ensure_system_user(db)
    return pipeline.search(db, owner.id, request.query, top_k=request.top_k)


@router.post("/intake/suggest", response_model=IntakeSuggestion)
def suggest_intake_placement(
    current_user: CurrentUser,
    llm_provider: LLMProviderDep,
    intake_store: IntakeStoreDep,
    folder_paths: FolderPathsDep,
    file: Annotated[UploadFile, File()],
) -> IntakeSuggestion:
    """Smart intake, step 1 of 2 (plan.md Phase 8): parses the upload, asks the LLM which
    existing (or new) folder it belongs in, and stages the bytes — nothing is written to
    disk yet. `/intake/confirm` is what actually files it, only after the author agrees."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are supported",
        )

    data = file.file.read()
    topics = discover_topic_tree(folder_paths)
    if not topics:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No topic folders exist yet under the configured watch folder(s)",
        )

    try:
        pages = parse_pdf(data)
    except UnreadablePdfError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unreadable PDF: {exc}"
        ) from None

    excerpt = "\n".join(page.text for page in pages)[:INTAKE_EXCERPT_CHAR_LIMIT]

    try:
        suggestion = suggest_placement(llm_provider, topics, excerpt)
    except IntakeClassificationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from None

    intake = intake_store.add(
        filename=file.filename,
        data=data,
        suggested_topic=suggestion["topic"],
        suggested_subfolder=suggestion["subfolder"],
        rationale=suggestion["rationale"],
    )
    return IntakeSuggestion(
        intake_id=intake.id,
        filename=intake.filename,
        suggested_topic=intake.suggested_topic,
        suggested_subfolder=intake.suggested_subfolder,
        rationale=intake.rationale,
        topics=[TopicFolderPublic(name=t.name, subfolders=t.subfolders) for t in topics],
    )


@router.post("/intake/confirm", response_model=DocumentPublic)
def confirm_intake_placement(
    request: IntakeConfirmRequest,
    current_user: CurrentUser,
    db: DbSession,
    pipeline: PipelineDep,
    intake_store: IntakeStoreDep,
    folder_paths: FolderPathsDep,
) -> Document:
    """Smart intake, step 2 of 2: the author's chosen topic/subfolder — which may or may
    not match the suggestion — is what actually gets used. Writes the staged bytes to the
    real watched folder (so it joins the organized library like any manually-filed
    document) and ingests it immediately rather than waiting for the next scheduled poll.
    """
    intake = intake_store.pop(request.intake_id)
    if intake is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No pending document with that id"
        )
    if not folder_paths:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="No watch folder is configured"
        )

    # Multiple watch folders can be configured; a newly-filed document always goes under
    # the first one (plan.md Phase 8) — the common case is exactly one configured root.
    target_path = write_confirmed_intake(intake, folder_paths[0], request.topic, request.subfolder)

    owner = ensure_system_user(db)
    document = Document(
        owner_id=owner.id,
        filename=intake.filename,
        s3_key=f"shared/{uuid.uuid4()}.pdf",
        source_path=str(target_path.resolve()),
        source_mtime=target_path.stat().st_mtime,
        status="pending",
    )
    db.add(document)
    db.commit()

    pipeline.blob_store.put(document.s3_key, intake.data, "application/pdf")
    pipeline.ingest(db, document.id)
    db.refresh(document)
    return document
