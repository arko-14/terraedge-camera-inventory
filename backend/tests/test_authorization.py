"""Authorisation, enforced in the backend.

Every request here is made directly to the API with a bearer token - no
browser, no UI. That is the point: hiding a button is not access control, so
these tests exercise the same path a reviewer would use with curl.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models import Camera
from tests.conftest import register


# ---------------------------------------------------------------------------
# Range isolation: reads
# ---------------------------------------------------------------------------
def test_range_user_list_shows_only_their_own_range(admin, chahala_user, reserve):
    register(admin, "TE-CHA-001", range_id=reserve["chahala"], beat_id=reserve["bakua"])
    register(admin, "TE-CHA-002", range_id=reserve["chahala"])
    register(admin, "TE-NAW-001", range_id=reserve["nawana"], beat_id=reserve["joranda"])
    register(admin, "TE-STOCK-001")

    response = chahala_user.get("/api/cameras")

    assert response.status_code == 200
    serials = {c["serial_number"] for c in response.json()["items"]}
    assert serials == {"TE-CHA-001", "TE-CHA-002"}
    # Unallocated stock belongs to the reserve, not to any single range.
    assert "TE-STOCK-001" not in serials
    assert response.json()["total"] == 2


def test_admin_sees_every_camera(admin, reserve):
    register(admin, "TE-CHA-001", range_id=reserve["chahala"])
    register(admin, "TE-NAW-001", range_id=reserve["nawana"])
    register(admin, "TE-STOCK-001")

    response = admin.get("/api/cameras")
    assert response.json()["total"] == 3


def test_range_user_cannot_read_another_ranges_camera(admin, chahala_user, reserve):
    other = register(admin, "TE-NAW-001", range_id=reserve["nawana"], beat_id=reserve["joranda"])

    detail = chahala_user.get(f"/api/cameras/{other['id']}")
    history = chahala_user.get(f"/api/cameras/{other['id']}/history")

    assert detail.status_code == 404
    assert history.status_code == 404
    # 404 rather than 403: a range user must not be able to confirm that a
    # camera id exists in another range.
    assert "not found" in detail.json()["detail"].lower()


def test_filtering_by_another_range_cannot_widen_visibility(admin, chahala_user, reserve):
    register(admin, "TE-NAW-001", range_id=reserve["nawana"])

    response = chahala_user.get(f"/api/cameras?range_id={reserve['nawana']}")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_search_cannot_reach_across_ranges(admin, chahala_user, reserve):
    register(admin, "TE-NAW-001", range_id=reserve["nawana"])

    response = chahala_user.get("/api/cameras?search=TE-NAW-001")
    assert response.json()["total"] == 0


def test_range_user_summary_counts_only_their_range(admin, chahala_user, reserve):
    register(admin, "TE-CHA-001", range_id=reserve["chahala"])
    register(admin, "TE-NAW-001", range_id=reserve["nawana"])
    register(admin, "TE-STOCK-001")

    response = chahala_user.get("/api/stats/summary")

    assert response.json()["total"] == 1
    assert response.json()["in_stock"] == 0
    assert [r["range_name"] for r in response.json()["by_range"]] == ["Chahala Range"]


def test_range_user_is_only_shown_their_own_range_and_beats(chahala_user, reserve):
    """The reference list is scoped too, or the UI offers filters that can only
    return nothing and names ranges the user cannot act on."""
    ranges = chahala_user.get("/api/ranges").json()

    assert [r["name"] for r in ranges] == ["Chahala Range"]
    beat_names = {b["name"] for r in ranges for b in r["beats"]}
    assert beat_names == {"Bakua Beat", "Jenabil Beat"}
    assert "Joranda Beat" not in beat_names


def test_admin_is_shown_every_range(admin, reserve):
    ranges = admin.get("/api/ranges").json()

    assert [r["name"] for r in ranges] == ["Chahala Range", "Nawana Range"]
    assert sum(len(r["beats"]) for r in ranges) == 4


def test_activity_feed_is_scoped_to_the_users_range(admin, chahala_user, reserve):
    register(admin, "TE-NAW-001", range_id=reserve["nawana"])
    register(admin, "TE-CHA-001", range_id=reserve["chahala"])

    response = chahala_user.get("/api/activity")

    assert response.status_code == 200
    assert all(entry["to_range_id"] == reserve["chahala"] for entry in response.json())


# ---------------------------------------------------------------------------
# Range isolation: writes
# ---------------------------------------------------------------------------
def test_range_user_cannot_modify_another_ranges_camera(admin, chahala_user, reserve, db):
    other = register(admin, "TE-NAW-001", range_id=reserve["nawana"], beat_id=reserve["joranda"])

    response = chahala_user.patch(
        f"/api/cameras/{other['id']}", json={"site_name": "Hijacked Site"}
    )

    assert response.status_code == 404
    stored = db.scalars(select(Camera).where(Camera.id == other["id"])).one()
    assert stored.site_name is None


def test_range_user_cannot_transfer_a_camera_into_their_own_range(admin, chahala_user, reserve, db):
    """The classic escalation attempt: pull another range's camera to yourself."""
    other = register(admin, "TE-NAW-001", range_id=reserve["nawana"], beat_id=reserve["joranda"])

    response = chahala_user.post(
        f"/api/cameras/{other['id']}/transfer",
        json={"range_id": reserve["chahala"], "beat_id": reserve["bakua"]},
    )

    assert response.status_code == 404
    stored = db.scalars(select(Camera).where(Camera.id == other["id"])).one()
    assert stored.range_id == reserve["nawana"]


def test_range_user_cannot_push_their_camera_to_another_range(admin, chahala_user, reserve, db):
    camera = register(admin, "TE-CHA-001", range_id=reserve["chahala"], beat_id=reserve["bakua"])

    response = chahala_user.post(
        f"/api/cameras/{camera['id']}/transfer",
        json={"range_id": reserve["nawana"], "beat_id": reserve["joranda"]},
    )

    assert response.status_code == 403
    assert "administrator" in response.json()["detail"]
    stored = db.scalars(select(Camera).where(Camera.id == camera["id"])).one()
    assert stored.range_id == reserve["chahala"]


def test_range_user_cannot_return_a_camera_to_stock(admin, chahala_user, reserve):
    camera = register(admin, "TE-CHA-001", range_id=reserve["chahala"], beat_id=reserve["bakua"])

    response = chahala_user.post(f"/api/cameras/{camera['id']}/transfer", json={"range_id": None})

    assert response.status_code == 403


def test_range_user_cannot_register_a_camera(chahala_user):
    response = chahala_user.post("/api/cameras", json={"serial_number": "TE-NEW-001"})

    assert response.status_code == 403
    assert "administrator" in response.json()["detail"]


# ---------------------------------------------------------------------------
# What a range user *is* allowed to do
# ---------------------------------------------------------------------------
def test_range_user_can_update_and_deploy_within_their_range(admin, chahala_user, reserve):
    camera = register(admin, "TE-CHA-001", range_id=reserve["chahala"], beat_id=reserve["bakua"])

    response = chahala_user.patch(
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

    assert response.status_code == 200
    assert response.json()["status"] == "deployed"


def test_range_user_can_move_a_camera_between_beats_of_their_own_range(
    admin, chahala_user, reserve
):
    camera = register(admin, "TE-CHA-001", range_id=reserve["chahala"], beat_id=reserve["bakua"])

    response = chahala_user.post(
        f"/api/cameras/{camera['id']}/transfer",
        json={"range_id": reserve["chahala"], "beat_id": reserve["jenabil"]},
    )

    assert response.status_code == 200
    assert response.json()["beat_id"] == reserve["jenabil"]


def test_range_user_cannot_assign_a_beat_outside_their_range(admin, chahala_user, reserve):
    camera = register(admin, "TE-CHA-001", range_id=reserve["chahala"], beat_id=reserve["bakua"])

    response = chahala_user.patch(
        f"/api/cameras/{camera['id']}", json={"beat_id": reserve["joranda"]}
    )

    assert response.status_code == 422


def test_admin_can_allocate_stock_and_transfer_across_ranges(admin, reserve):
    camera = register(admin, "TE-STOCK-001")

    allocate = admin.post(
        f"/api/cameras/{camera['id']}/transfer",
        json={"range_id": reserve["chahala"], "beat_id": reserve["bakua"]},
    )
    assert allocate.status_code == 200
    assert allocate.json()["status"] == "allocated"

    move = admin.post(
        f"/api/cameras/{camera['id']}/transfer",
        json={"range_id": reserve["nawana"], "beat_id": reserve["joranda"]},
    )
    assert move.status_code == 200
    assert move.json()["range_id"] == reserve["nawana"]
