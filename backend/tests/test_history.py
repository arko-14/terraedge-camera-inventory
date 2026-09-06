"""Movement tracking: current state stays correct, previous assignments survive."""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import AssignmentHistory, Camera
from tests.conftest import register


def deploy(api, camera_id, site, lat, lon, contact="Ranjan Mahanta", phone="+91 98110 20034"):
    response = api.patch(
        f"/api/cameras/{camera_id}",
        json={
            "status": "deployed",
            "site_name": site,
            "latitude": lat,
            "longitude": lon,
            "contact_name": contact,
            "contact_phone": phone,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_registration_creates_the_first_history_entry(admin, reserve):
    camera = register(admin, "TE-CAM-001", range_id=reserve["chahala"], beat_id=reserve["bakua"])

    history = admin.get(f"/api/cameras/{camera['id']}/history").json()

    assert len(history) == 1
    assert history[0]["change_type"] == "registered"
    assert history[0]["from_status"] is None
    assert history[0]["to_status"] == "allocated"
    assert history[0]["to_range_name"] == "Chahala Range"


def test_transfer_preserves_the_previous_deployment(admin, reserve, db):
    camera = register(admin, "TE-CAM-002", range_id=reserve["chahala"], beat_id=reserve["bakua"])
    deploy(admin, camera["id"], "Bakua Nala Crossing", 21.9042, 86.3611)

    moved = admin.post(
        f"/api/cameras/{camera['id']}/transfer",
        json={
            "range_id": reserve["nawana"],
            "beat_id": reserve["joranda"],
            "note": "Moved for the winter census",
        },
    )
    assert moved.status_code == 200

    history = admin.get(f"/api/cameras/{camera['id']}/history").json()
    transfer = next(h for h in history if h["change_type"] == "transferred")

    # The earlier deployment is still fully readable in the history.
    assert transfer["from_range_name"] == "Chahala Range"
    assert transfer["from_beat_name"] == "Bakua Beat"
    assert transfer["from_site_name"] == "Bakua Nala Crossing"
    assert transfer["from_latitude"] is not None
    assert transfer["from_status"] == "deployed"
    assert transfer["to_range_name"] == "Nawana Range"
    assert transfer["to_beat_name"] == "Joranda Beat"
    assert transfer["note"] == "Moved for the winter census"

    # ...and the deployment record that came before it was not rewritten.
    deployment = next(h for h in history if h["change_type"] == "deployed")
    assert deployment["to_site_name"] == "Bakua Nala Crossing"


def test_transfer_never_creates_a_second_camera(admin, reserve, db):
    camera = register(admin, "TE-CAM-003", range_id=reserve["chahala"], beat_id=reserve["bakua"])
    deploy(admin, camera["id"], "Bakua Nala Crossing", 21.9042, 86.3611)

    for target_range, target_beat in [
        (reserve["nawana"], reserve["joranda"]),
        (reserve["chahala"], reserve["jenabil"]),
        (reserve["nawana"], reserve["barehipani"]),
    ]:
        response = admin.post(
            f"/api/cameras/{camera['id']}/transfer",
            json={"range_id": target_range, "beat_id": target_beat},
        )
        assert response.status_code == 200

    assert db.scalar(select(func.count(Camera.id))) == 1
    stored = db.scalars(select(Camera).where(Camera.serial_number == "TE-CAM-003")).one()
    assert stored.id == camera["id"]  # same identity throughout


def test_current_state_reflects_the_latest_move_only(admin, reserve):
    camera = register(admin, "TE-CAM-004", range_id=reserve["chahala"], beat_id=reserve["bakua"])
    deploy(admin, camera["id"], "Bakua Nala Crossing", 21.9042, 86.3611)

    admin.post(
        f"/api/cameras/{camera['id']}/transfer",
        json={"range_id": reserve["nawana"], "beat_id": reserve["joranda"]},
    )

    current = admin.get(f"/api/cameras/{camera['id']}").json()

    assert current["range_name"] == "Nawana Range"
    assert current["beat_name"] == "Joranda Beat"
    # A move ends the previous deployment: the camera awaits redeployment at
    # its new location, and the old site is not carried across.
    assert current["status"] == "allocated"
    assert current["site_name"] is None
    assert current["latitude"] is None
    assert len(current["history"]) == 3


def test_history_records_who_made_each_change_and_when(admin, chahala_user, reserve):
    camera = register(admin, "TE-CAM-005", range_id=reserve["chahala"], beat_id=reserve["bakua"])
    deploy(chahala_user, camera["id"], "Bakua Nala Crossing", 21.9042, 86.3611)

    history = admin.get(f"/api/cameras/{camera['id']}/history").json()

    registered = next(h for h in history if h["change_type"] == "registered")
    deployed = next(h for h in history if h["change_type"] == "deployed")

    assert registered["changed_by_email"] == "admin@similipal.test"
    assert deployed["changed_by_email"] == "chahala@similipal.test"
    assert deployed["changed_at"] is not None
    assert deployed["changed_at"] >= registered["changed_at"]


def test_history_is_append_only_across_a_full_lifecycle(admin, reserve, db):
    camera = register(admin, "TE-CAM-006")

    admin.post(
        f"/api/cameras/{camera['id']}/transfer",
        json={"range_id": reserve["chahala"], "beat_id": reserve["bakua"]},
    )
    deploy(admin, camera["id"], "Bakua Nala Crossing", 21.9042, 86.3611)
    admin.post(
        f"/api/cameras/{camera['id']}/transfer",
        json={"range_id": reserve["nawana"], "beat_id": reserve["joranda"]},
    )
    deploy(admin, camera["id"], "Joranda Falls Viewpoint", 21.8123, 86.3055)
    admin.post(f"/api/cameras/{camera['id']}/transfer", json={"range_id": None})

    rows = db.scalars(
        select(AssignmentHistory)
        .where(AssignmentHistory.camera_id == camera["id"])
        .order_by(AssignmentHistory.id)
    ).all()

    assert [r.change_type.value for r in rows] == [
        "registered",
        "allocated",
        "deployed",
        "transferred",
        "deployed",
        "returned_to_stock",
    ]
    # Every recorded step still names both its ends.
    assert rows[2].to_site_name == "Bakua Nala Crossing"
    assert rows[4].to_site_name == "Joranda Falls Viewpoint"
    assert rows[5].from_range_id == reserve["nawana"]
    assert rows[5].to_range_id is None


def test_returning_to_stock_clears_the_assignment_but_not_the_record(admin, reserve):
    camera = register(admin, "TE-CAM-007", range_id=reserve["chahala"], beat_id=reserve["bakua"])
    deploy(admin, camera["id"], "Bakua Nala Crossing", 21.9042, 86.3611)

    response = admin.post(f"/api/cameras/{camera['id']}/transfer", json={"range_id": None})

    assert response.status_code == 200
    assert response.json()["status"] == "in_stock"
    assert response.json()["range_id"] is None

    history = admin.get(f"/api/cameras/{camera['id']}/history").json()
    returned = next(h for h in history if h["change_type"] == "returned_to_stock")
    assert returned["from_site_name"] == "Bakua Nala Crossing"


def test_a_no_op_transfer_does_not_add_noise_to_the_history(admin, reserve):
    camera = register(admin, "TE-CAM-008", range_id=reserve["chahala"], beat_id=reserve["bakua"])

    admin.post(
        f"/api/cameras/{camera['id']}/transfer",
        json={"range_id": reserve["chahala"], "beat_id": reserve["bakua"]},
    )

    history = admin.get(f"/api/cameras/{camera['id']}/history").json()
    assert len(history) == 1
