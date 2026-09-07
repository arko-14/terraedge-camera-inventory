"""Authentication: sign-in, session handling, and CSRF protection."""

from __future__ import annotations

from app.config import settings
from tests.conftest import ADMIN_EMAIL, CHAHALA_EMAIL, PASSWORD


def test_login_returns_user_and_sets_httponly_session_cookie(client, reserve):
    response = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == ADMIN_EMAIL
    assert body["user"]["role"] == "reserve_admin"
    assert body["user"]["range_id"] is None

    session_cookie = response.headers.get_list("set-cookie")
    session_header = next(c for c in session_cookie if c.startswith(settings.session_cookie_name))
    # The session token must be unreadable from page JavaScript.
    assert "HttpOnly" in session_header
    # The CSRF token must be readable, since the frontend has to echo it back.
    csrf_header = next(c for c in session_cookie if c.startswith(settings.csrf_cookie_name))
    assert "HttpOnly" not in csrf_header


def test_password_is_never_returned_or_stored_in_plaintext(client, reserve, db):
    from sqlalchemy import select

    from app.models import User

    response = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    assert PASSWORD not in response.text
    assert "password" not in response.json()["user"]

    stored = db.scalars(select(User).where(User.email == ADMIN_EMAIL)).one()
    assert stored.password_hash != PASSWORD
    assert stored.password_hash.startswith("$argon2id$")


def test_wrong_password_and_unknown_email_are_indistinguishable(client, reserve):
    wrong_password = client.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": "not-the-password"}
    )
    unknown_email = client.post(
        "/api/auth/login", json={"email": "nobody@similipal.test", "password": PASSWORD}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    # Identical message, so the endpoint cannot be used to enumerate accounts.
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


def test_protected_endpoints_reject_anonymous_requests(client, reserve):
    for method, url in [
        ("get", "/api/cameras"),
        ("get", "/api/stats/summary"),
        ("get", "/api/activity"),
        ("get", "/api/ranges"),
        ("get", "/api/auth/me"),
    ]:
        assert getattr(client, method)(url).status_code == 401, f"{url} was not protected"

    for method, url in [("post", "/api/cameras"), ("patch", "/api/cameras/1")]:
        response = getattr(client, method)(url, json={"serial_number": "TE-X-001"})
        assert response.status_code == 401, f"{method.upper()} {url} was not protected"


def test_tampered_and_malformed_tokens_are_rejected(client, reserve):
    good = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    token = good.json()["access_token"]
    client.cookies.clear()

    tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")
    for bad_token in [tampered, "not-a-jwt", ""]:
        response = client.get("/api/cameras", headers={"Authorization": f"Bearer {bad_token}"})
        assert response.status_code == 401


def test_me_reports_the_range_scope_of_a_range_user(client, reserve):
    login = client.post("/api/auth/login", json={"email": CHAHALA_EMAIL, "password": PASSWORD})
    token = login.json()["access_token"]

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["role"] == "range_user"
    assert response.json()["range_id"] == reserve["chahala"]
    assert response.json()["range_name"] == "Chahala Range"


def test_cookie_session_write_requires_a_csrf_token(client, reserve):
    """A cookie-authenticated write must carry the double-submit CSRF header."""
    client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    csrf_token = client.cookies.get(settings.csrf_cookie_name)
    assert csrf_token

    # Cookie is sent automatically by the client, but no CSRF header: rejected.
    forged = client.post("/api/cameras", json={"serial_number": "TE-CSRF-001"})
    assert forged.status_code == 403
    assert "csrf" in forged.json()["detail"].lower()

    # A wrong header value is rejected too.
    wrong = client.post(
        "/api/cameras",
        json={"serial_number": "TE-CSRF-001"},
        headers={"X-CSRF-Token": "some-other-value"},
    )
    assert wrong.status_code == 403

    # The matching header succeeds.
    allowed = client.post(
        "/api/cameras",
        json={"serial_number": "TE-CSRF-001"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert allowed.status_code == 201


def test_logout_clears_the_session(client, reserve):
    client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    csrf_token = client.cookies.get(settings.csrf_cookie_name)

    assert client.get("/api/auth/me").status_code == 200

    logout = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert logout.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


# ---------------------------------------------------------------------------
# Logout revokes tokens, not just cookies
# ---------------------------------------------------------------------------
def test_logout_invalidates_a_bearer_token(client, reserve):
    """A stateless token would otherwise stay valid until it expired.

    Logout bumps the account's token version, and every request compares the
    version in the token against the user row it already loads.
    """
    login = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    token = login.json()["access_token"]
    csrf = client.cookies.get(settings.csrf_cookie_name)

    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401, "the bearer token outlived logout"


def test_logout_invalidates_the_cookie_session_too(client, reserve):
    client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    csrf = client.cookies.get(settings.csrf_cookie_name)

    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})

    assert client.get("/api/auth/me").status_code == 401


def test_a_token_issued_after_logout_still_works(client, reserve):
    """Revocation must not lock the account out of signing back in."""
    first = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    client.post("/api/auth/logout", headers={"X-CSRF-Token": client.cookies.get(settings.csrf_cookie_name)})

    second = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    fresh = second.json()["access_token"]

    assert fresh != first.json()["access_token"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200


def test_logout_does_not_sign_out_other_accounts(client, reserve):
    """Revocation is scoped to the account, not global."""
    admin_login = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    admin_token = admin_login.json()["access_token"]

    client.cookies.clear()
    range_login = client.post("/api/auth/login", json={"email": CHAHALA_EMAIL, "password": PASSWORD})
    range_token = range_login.json()["access_token"]

    client.post("/api/auth/logout", headers={"X-CSRF-Token": client.cookies.get(settings.csrf_cookie_name)})
    client.cookies.clear()

    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {range_token}"}).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 200


def test_logout_without_a_session_still_succeeds(client, reserve):
    """An expired or absent session must still clear cookies, not 401."""
    assert client.post("/api/auth/logout").status_code == 204
