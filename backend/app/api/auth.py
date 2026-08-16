"""Signup / login / identity. Own auth with JWT + bcrypt (plan.md Phase 1 decision)."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import UNAUTHORIZED, CurrentUser, DbSession
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

_PASSWORD_MIN_LENGTH = get_settings().password_min_length


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=1024)


class UserPublic(BaseModel):
    """Deliberately excludes `password_hash` — never serialise the User model directly."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/signup", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def signup(credentials: Credentials, db: DbSession) -> User:
    user = User(email=credentials.email.lower(), password_hash=hash_password(credentials.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from None

    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(credentials: Credentials, db: DbSession) -> TokenResponse:
    user = db.execute(
        select(User).where(User.email == credentials.email.lower())
    ).scalar_one_or_none()

    # Hash even when the user is unknown, so timing does not leak account existence.
    known_hash = user.password_hash if user else hash_password("nonexistent-user-placeholder")
    if not verify_password(credentials.password, known_hash) or user is None:
        raise UNAUTHORIZED

    return TokenResponse(access_token=create_access_token(subject=user.email))


@router.get("/me", response_model=UserPublic)
def read_current_user(current_user: CurrentUser) -> User:
    return current_user
