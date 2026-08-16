"""Shared request dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import InvalidTokenError, decode_access_token
from app.db.models import User
from app.db.session import get_db

# auto_error=False so a missing header yields our 401, not FastAPI's 403.
bearer_scheme = HTTPBearer(auto_error=False)

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def _resolve_user(token: str | None, db: Session) -> User:
    if not token:
        raise UNAUTHORIZED

    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        raise UNAUTHORIZED from None

    user = db.execute(select(User).where(User.email == payload.subject)).scalar_one_or_none()
    if user is None:
        raise UNAUTHORIZED

    return user


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    return _resolve_user(credentials.credentials if credentials else None, db)


def get_current_user_from_header_or_query(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[
        str | None,
        Query(description="Access token, for links a browser opens as a plain navigation."),
    ] = None,
) -> User:
    """Same as `get_current_user`, plus a `?token=` fallback for endpoints opened as a
    plain browser navigation (e.g. a citation link), which can't set an Authorization
    header. KNOWN SIMPLIFICATION (plan.md Phase 5 backlog): swap the one endpoint that
    uses this for presigned S3 URLs before production — a bearer token in a URL ends up
    in browser history and server logs."""
    return _resolve_user(credentials.credentials if credentials else token, db)


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentUserFlexible = Annotated[User, Depends(get_current_user_from_header_or_query)]
DbSession = Annotated[Session, Depends(get_db)]
