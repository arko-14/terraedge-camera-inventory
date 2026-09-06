"""Data integrity: unique serials, range/beat coherence, coordinates, status rules."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models import Camera
from tests.conftest import register


# ---------------------------------------------------------------------------
# Serial numbers: one stable identity per physical camera
# ---------------------------------------------------------------------------
def test_duplicate_serial_number_is_rejected(admin, db):
    register(admin, "TE-CAM-001")

    duplicate = admin.post("/api/cameras", json={"serial_number": "TE-CAM-001"})

    assert duplicate.status_code == 409
    assert "already registered" in duplicate.json()["detail"]
    assert db.scalar(select(func.count(Camera.id))) == 1


def test_duplicate_serial_is_caught_regardless_of_case_or_padding(admin, db):
    register(admin, "TE-CAM-002")

    for variant in ["te-cam-002", "  TE-CAM-002  ", "Te-Cam-002"]:
        response = admin.post("/api/cameras", json={"serial_number": variant})
        assert response.status_code == 409, f"{variant!r} created a second identity"

    assert db.scalar(select(func.count(Camera.id))) == 1


def test_serial_number_is_normalised_to_upper_case(admin):
    camera = register(admin, "te-cam-003")
    assert camera["serial_number"] == "TE-CAM-003"


@pytest.mark.parametrize("bad_serial", ["", "ab", "has spaces", "bad/slash", "x" * 65])
def test_malformed_serial_numbers_are_rejected(admin, bad_serial):
    response = admin.post("/api/cameras", json={"serial_number": bad_serial})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Range / beat coherence
# ---------------------------------------------------------------------------
def test_beat_from_another_range_is_rejected(admin, reserve):
    response = admin.post(
        "/api/cameras",
        json={
            "serial_number": "TE-CAM-010",
            "range_id": reserve["chahala"],
            "beat_id": reserve["joranda"],  # belongs to Nawana
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "Joranda Beat" in detail and "Nawana Range" in detail


def test_beat_without_a_range_is_rejected(admin, reserve):
    response = admin.post(
        "/api/cameras", json={"serial_number": "TE-CAM-011", "beat_id": reserve["bakua"]}
    )
    assert response.status_code == 422
    assert "Select a range" in response.json()["detail"]


def test_transfer_to_a_mismatched_beat_is_rejected(admin, reserve):
    camera = register(admin, "TE-CAM-012", range_id=reserve["chahala"])

    response = admin.post(
        f"/api/cameras/{camera['id']}/transfer",
        json={"range_id": reserve["chahala"], "beat_id": reserve["barehipani"]},
    )
    assert response.status_code == 422


def test_range_allocation_without_a_beat_is_allowed(admin, reserve):
    """The brief explicitly requires allocating a range before the beat is known."""
    camera = register(admin, "TE-CAM-013", range_id=reserve["chahala"])

    assert camera["status"] == "allocated"
    assert camera["range_id"] == reserve["chahala"]
    assert camera["beat_id"] is None


def test_nonexistent_range_is_rejected(admin):
    response = admin.post("/api/cameras", json={"serial_number": "TE-CAM-014", "range_id": 9999})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Filters that name something that does not exist
# ---------------------------------------------------------------------------
def test_filtering_by_a_nonexistent_range_is_an_error_not_an_empty_list(admin, reserve):
    """A stale client must be told its filter is wrong, not shown 'no results'."""
    register(admin, "TE-CAM-050", range_id=reserve["chahala"])

    response = admin.get("/api/cameras?range_id=9999")

    assert response.status_code == 422
    assert "Range 9999 does not exist" in response.json()["detail"]


def test_filtering_by_a_nonexistent_beat_is_an_error(admin, reserve):
    response = admin.get("/api/cameras?beat_id=9999")

    assert response.status_code == 422
    assert "Beat 9999 does not exist" in response.json()["detail"]


def test_exporting_with_a_nonexistent_filter_is_an_error(admin, reserve):
    assert admin.get("/api/cameras/export?range_id=9999").status_code == 422


def test_filtering_by_a_real_range_returns_its_cameras(admin, reserve):
    register(admin, "TE-CHA-001", range_id=reserve["chahala"])
    register(admin, "TE-NAW-001", range_id=reserve["nawana"])

    response = admin.get(f"/api/cameras?range_id={reserve['chahala']}")

    assert response.status_code == 200
    assert [c["serial_number"] for c in response.json()["items"]] == ["TE-CHA-001"]


# ---------------------------------------------------------------------------
# Coordinates
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "latitude,longitude",
    [(91, 86.3), (-91, 86.3), (21.9, 181), (21.9, -181), (200, 200)],
)
def test_out_of_bounds_coordinates_are_rejected(admin, reserve, latitude, longitude):
    camera = register(admin, "TE-CAM-020", range_id=reserve["chahala"], beat_id=reserve["bakua"])

    response = admin.patch(
        f"/api/cameras/{camera['id']}", json={"latitude": latitude, "longitude": longitude}
    )
    assert response.status_code == 422


def test_latitude_without_longitude_is_rejected(admin, reserve):
    camera = register(admin, "TE-CAM-021", range_id=reserve["chahala"], beat_id=reserve["bakua"])

    response = admin.patch(f"/api/cameras/{camera['id']}", json={"latitude": 21.9042})

    assert response.status_code == 422
    assert "together" in response.json()["detail"]


def test_valid_coordinates_are_accepted_and_persisted(admin, reserve):
    camera = register(admin, "TE-CAM-022", range_id=reserve["chahala"], beat_id=reserve["bakua"])

    response = admin.patch(
        f"/api/cameras/{camera['id']}", json={"latitude": 21.9042, "longitude": 86.3611}
    )

    assert response.status_code == 200
    assert response.json()["latitude"] == pytest.approx(21.9042)
    assert response.json()["longitude"] == pytest.approx(86.3611)


# ---------------------------------------------------------------------------
# Status rules
# ---------------------------------------------------------------------------
def test_camera_cannot_be_deployed_without_full_deployment_detail(admin, reserve):
    camera = register(admin, "TE-CAM-030", range_id=reserve["chahala"], beat_id=reserve["bakua"])

    response = admin.patch(f"/api/cameras/{camera['id']}", json={"status": "deployed"})

    assert response.status_code == 422
    detail = response.json()["detail"]
    for expected in ["site name", "latitude", "longitude", "contact"]:
        assert expected in detail


def test_camera_cannot_be_deployed_without_a_beat(admin, reserve):
    camera = register(admin, "TE-CAM-031", range_id=reserve["chahala"])

    response = admin.patch(
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

    assert response.status_code == 422
    assert "a beat" in response.json()["detail"]


def test_full_deployment_succeeds_and_records_the_date(admin, reserve):
    camera = register(admin, "TE-CAM-032", range_id=reserve["chahala"], beat_id=reserve["bakua"])

    response = admin.patch(
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
    body = response.json()
    assert body["status"] == "deployed"
    assert body["deployed_at"] is not None
    assert body["site_name"] == "Bakua Nala Crossing"


def test_an_invalid_phone_number_is_rejected(admin, reserve):
    camera = register(admin, "TE-CAM-033", range_id=reserve["chahala"], beat_id=reserve["bakua"])

    response = admin.patch(f"/api/cameras/{camera['id']}", json={"contact_phone": "not a phone"})
    assert response.status_code == 422


def test_a_partial_update_does_not_blank_untouched_fields(admin, reserve):
    camera = register(
        admin,
        "TE-CAM-034",
        range_id=reserve["chahala"],
        beat_id=reserve["bakua"],
        site_name="Bakua Nala Crossing",
        contact_name="Ranjan Mahanta",
        contact_phone="+91 98110 20034",
    )

    response = admin.patch(f"/api/cameras/{camera['id']}", json={"notes": "Battery replaced"})

    assert response.status_code == 200
    body = response.json()
    assert body["notes"] == "Battery replaced"
    assert body["site_name"] == "Bakua Nala Crossing"
    assert body["contact_name"] == "Ranjan Mahanta"


def test_status_cannot_be_set_to_in_stock_directly(admin, reserve):
    """Returning to stock is a transfer, so that the move is recorded as one event."""
    camera = register(admin, "TE-CAM-035", range_id=reserve["chahala"])

    response = admin.patch(f"/api/cameras/{camera['id']}", json={"status": "in_stock"})

    assert response.status_code == 422
    assert "transfer" in response.json()["detail"].lower()
