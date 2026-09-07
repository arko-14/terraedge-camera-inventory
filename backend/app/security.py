"""Password hashing, session tokens and CSRF tokens.

Passwords use Argon2id: memory-hard, with a random salt and the cost
parameters embedded in each hash, so `verify_password` can also report when a
stored hash should be upgraded.

Session tokens are signed JWTs delivered as httpOnly cookies. Authorisation
never trusts the role/range claims inside them - the user row is re-read on
every request (see app/deps.py), so revoking an account takes effect at once
rather than at token expiry.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import settings

hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> tuple[bool, bool]:
    """Return (password_is_correct, hash_should_be_upgraded)."""
    try:
        hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False, False
    return True, hasher.check_needs_rehash(password_hash)


def create_access_token(
    user_id: int, role: str, range_id: int | None, token_version: int
) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "range_id": range_id,
        "tv": token_version,
        "iat": datetime.now(UTC),
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), expires_at


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Return the payload, or None if invalid, expired or tampered with."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def constant_time_equals(a: str, b: str) -> bool:
    return secrets.compare_digest(a, b)
