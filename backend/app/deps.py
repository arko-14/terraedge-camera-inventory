"""Authentication and authorisation dependencies.

The JWT is only a claim of who you are. What you may do is always decided from
the live user row, which is re-read on every request.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User
from app.security import decode_access_token

NOT_AUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated.",
    headers={"WWW-Authenticate": "Bearer"},
)


def extract_token(request: Request) -> str | None:
    """The session token, from the Authorization header or the cookie.

    Bearer wins, so a scripted client behaves predictably even in a browser
    that also holds a session cookie.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token

    return request.cookies.get(settings.session_cookie_name)


def get_current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    token = extract_token(request)
    if not token:
        raise NOT_AUTHENTICATED

    payload = decode_access_token(token)
    if not payload:
        raise NOT_AUTHENTICATED

    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError) as exc:
        raise NOT_AUTHENTICATED from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise NOT_AUTHENTICATED

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]


def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires a reserve administrator account.",
        )
    return user


AdminUser = Annotated[User, Depends(require_admin)]
