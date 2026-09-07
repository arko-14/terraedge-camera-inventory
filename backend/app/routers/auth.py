"""Sign in, sign out, and "who am I"."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.config import settings
from app.deps import CurrentUser, DbSession, get_optional_user
from app.models import User
from app.schemas import LoginRequest, LoginResponse, UserOut
from app.security import (
    create_access_token,
    generate_csrf_token,
    hash_password,
    verify_password,
)
from app.serializers import user_out

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookies(response: Response, token: str, csrf_token: str) -> None:
    max_age = settings.access_token_expire_minutes * 60
    common = {
        "max_age": max_age,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "path": "/",
    }
    # httpOnly: unreadable from JavaScript, so XSS cannot steal the session.
    response.set_cookie(settings.session_cookie_name, token, httponly=True, **common)
    # Readable by design - the frontend echoes it back in X-CSRF-Token.
    response.set_cookie(settings.csrf_cookie_name, csrf_token, httponly=False, **common)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response, db: DbSession) -> LoginResponse:
    email = payload.email.strip().lower()
    user = db.scalars(select(User).where(User.email == email)).first()

    password_ok = False
    if user is not None:
        password_ok, needs_rehash = verify_password(payload.password, user.password_hash)
        if password_ok and needs_rehash:
            user.password_hash = hash_password(payload.password)
            db.commit()

    # One message for both cases, so accounts cannot be enumerated.
    if user is None or not password_ok or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    token, expires_at = create_access_token(
        user.id, user.role.value, user.range_id, user.token_version
    )
    csrf_token = generate_csrf_token()
    _set_session_cookies(response, token, csrf_token)

    return LoginResponse(user=user_out(user), access_token=token, expires_at=expires_at)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession) -> Response:
    """Sign out, and invalidate every token already issued to this account.

    Clearing the cookie ends a browser session, but a token that had been
    copied out would otherwise stay valid until it expired. Bumping the
    account's token version revokes those too.

    The trade-off is that logout is account-wide, not per-device: signing out
    on one device signs out everywhere. For this application that is the safer
    default; per-device sessions would need a session table.
    """
    user = get_optional_user(request, db)
    if user is not None:
        user.token_version += 1
        db.commit()

    for name in (settings.session_cookie_name, settings.csrf_cookie_name):
        response.delete_cookie(
            name,
            path="/",
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,
        )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return user_out(user)
