"""Password hashing and JWT issue/verify.

Passwords are SHA-256 pre-hashed before bcrypt. bcrypt silently ignores input past
72 bytes, so a long passphrase would otherwise collide with its own prefix.
"""

import base64
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings


class InvalidTokenError(Exception):
    """Token is absent, malformed, expired, or not signed by us."""


@dataclass(frozen=True)
class TokenPayload:
    subject: str
    expires_at: datetime


def _prepare(password: str) -> bytes:
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), password_hash.encode("utf-8"))
    except ValueError:
        # Stored hash is not a valid bcrypt hash — treat as a failed login, not a crash.
        return False


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    delta = expires_delta or timedelta(minutes=settings.jwt_expiry_minutes)
    issued_at = datetime.now(UTC)
    claims = {
        "sub": subject,
        "iat": issued_at,
        "exp": issued_at + delta,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    subject = claims.get("sub")
    if not subject:
        raise InvalidTokenError("token has no subject")

    return TokenPayload(subject=subject, expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC))
