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

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, CurrentUserFlexible, DbSession
from app.db.models import Document
from app.ingestion.deps import PipelineDep
from app.ingestion.ports import BlobNotFoundError
from app.ingestion.system_owner import ensure_system_user

router = APIRouter(prefix="/documents", tags=["documents"])


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
