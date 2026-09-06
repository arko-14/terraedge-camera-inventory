"""Regression tests for defects found during a review pass.

Each of these was reproduced before it was fixed.
"""

from __future__ import annotations

import app.main as main_module
from tests.conftest import register


# ---------------------------------------------------------------------------
# The health check must fail when it is failing
# ---------------------------------------------------------------------------
def test_health_reports_503_when_the_database_is_unreachable(client, monkeypatch):
    """A platform health check reads the status code, not the body.

    Answering 200 while degraded keeps a broken instance in the load balancer.
    """
    from sqlalchemy import create_engine

    unreachable = create_engine("postgresql+psycopg://nobody:nobody@127.0.0.1:1/none")
    monkeypatch.setattr(main_module, "engine", unreachable)

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_health_reports_200_when_the_database_is_reachable(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


# ---------------------------------------------------------------------------
# Security headers come from the app that serves the page
# ---------------------------------------------------------------------------
def test_security_headers_are_present(client):
    """Set here, not in vercel.json, because this process serves the web app."""
    headers = client.get("/api/health").headers

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_csp_allows_the_map_tiles_and_nothing_else(client):
    csp = client.get("/api/health").headers["Content-Security-Policy"]

    assert "https://*.tile.openstreetmap.org" in csp  # Leaflet tiles
    assert "script-src 'self'" in csp
    assert "default-src 'self'" in csp


def test_hsts_is_sent_only_when_cookies_are_secure(client, monkeypatch):
    """HSTS over plain HTTP is meaningless, and pins a scheme the app is not on."""
    from app.config import settings

    # Test settings run with COOKIE_SECURE=false, i.e. plain HTTP.
    assert "Strict-Transport-Security" not in client.get("/api/health").headers

    monkeypatch.setattr(settings, "cookie_secure", True)
    headers = client.get("/api/health").headers
    assert headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


# ---------------------------------------------------------------------------
# LIKE metacharacters are data, not syntax
# ---------------------------------------------------------------------------
def test_percent_in_search_matches_nothing_instead_of_everything(admin, reserve):
    """An unescaped '%' would match every row and force a full scan."""
    register(admin, "TE-AAA-001")
    register(admin, "TE-BBB-002")

    assert admin.get("/api/cameras?search=%25").json()["total"] == 0
    assert admin.get("/api/cameras?search=_").json()["total"] == 0


def test_search_still_works_normally(admin, reserve):
    register(admin, "TE-AAA-001")
    register(admin, "TE-BBB-002")

    assert admin.get("/api/cameras?search=TE-AAA").json()["total"] == 1
    assert admin.get("/api/cameras?search=te-aaa").json()["total"] == 1
    assert admin.get("/api/cameras?search=TE-").json()["total"] == 2


def test_a_literal_percent_in_a_site_name_is_searchable(admin, reserve):
    camera = register(admin, "TE-CAM-090", range_id=reserve["chahala"])
    admin.patch(f"/api/cameras/{camera['id']}", json={"site_name": "Ridge 50% Slope"})

    assert admin.get("/api/cameras?search=50%25").json()["total"] == 1


# ---------------------------------------------------------------------------
# deployed_at must not outlive the deployment
# ---------------------------------------------------------------------------
def test_deployed_at_is_cleared_when_a_camera_leaves_the_field(admin, reserve):
    camera = register(admin, "TE-CAM-091", range_id=reserve["chahala"], beat_id=reserve["bakua"])
    admin.patch(
        f"/api/cameras/{camera['id']}",
        json={
            "status": "deployed",
            "site_name": "Bakua Nala Crossing",
            "latitude": 21.9042,
            "longitude": 86.3611,
            "contact_name": "Ranjan Mahanta",
            "contact_phone": "+91 98110 20034",
        },
    )
    assert admin.get(f"/api/cameras/{camera['id']}").json()["deployed_at"] is not None

    admin.patch(f"/api/cameras/{camera['id']}", json={"status": "allocated"})

    body = admin.get(f"/api/cameras/{camera['id']}").json()
    assert body["status"] == "allocated"
    assert body["deployed_at"] is None, "an allocated camera still claimed a deployment date"


def test_deployed_at_survives_an_unrelated_edit(admin, reserve):
    camera = register(admin, "TE-CAM-092", range_id=reserve["chahala"], beat_id=reserve["bakua"])
    admin.patch(
        f"/api/cameras/{camera['id']}",
        json={
            "status": "deployed",
            "site_name": "Bakua Nala Crossing",
            "latitude": 21.9042,
            "longitude": 86.3611,
            "contact_name": "Ranjan Mahanta",
            "contact_phone": "+91 98110 20034",
        },
    )
    admin.patch(f"/api/cameras/{camera['id']}", json={"notes": "Lens cleaned"})

    assert admin.get(f"/api/cameras/{camera['id']}").json()["deployed_at"] is not None


# ---------------------------------------------------------------------------
# An oversized upload is refused before it is buffered
# ---------------------------------------------------------------------------
def test_oversized_csv_is_rejected(admin, reserve):
    from app.services.csv_service import MAX_UPLOAD_BYTES

    payload = "serial_number\n" + "".join(f"TE-BIG-{n:06d}\n" for n in range(200_000))
    assert len(payload) > MAX_UPLOAD_BYTES

    response = admin.post(
        "/api/cameras/import",
        files={"file": ("huge.csv", payload.encode(), "text/csv")},
    )

    assert response.status_code == 413
    assert "larger than" in response.json()["detail"]


def test_a_normal_sized_csv_is_still_accepted(admin, reserve):
    response = admin.post(
        "/api/cameras/import",
        files={"file": ("ok.csv", b"serial_number\nTE-SMALL-001\n", "text/csv")},
    )

    assert response.status_code == 200
    assert response.json()["created_count"] == 1
