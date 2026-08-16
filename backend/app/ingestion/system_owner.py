"""The shared corpus's one owner (plan.md Phase 2b).

Folder-ingested documents don't belong to any real signed-in user — every account reads
the same corpus. `ensure_system_user` get-or-creates a fixed, unusable-password `User` row
by `settings.system_owner_email` so the rest of the schema (`Document.owner_id`, Pinecone
namespace-per-owner) needs no special-casing for "no owner".
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import User


def ensure_system_user(db: Session) -> User:
    email = get_settings().system_owner_email

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is not None:
        return user

    # Random, never handed out — this account only ever exists to own documents, it
    # can't sign in (no endpoint issues it a token; signup would reject the email as
    # already-registered if it tried).
    user = User(email=email, password_hash=hash_password(uuid.uuid4().hex + "-not-a-login"))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Lost a race with another cron run / worker creating the same row concurrently.
        db.rollback()
        user = db.execute(select(User).where(User.email == email)).scalar_one()

    return user
