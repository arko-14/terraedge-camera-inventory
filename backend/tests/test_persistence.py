"""Persistence and database-level integrity.

The API tests elsewhere run through one process. These check the two things
that only the storage layer can guarantee: that data outlives the application,
and that the constraints hold even when the service layer is bypassed.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal, engine
from app.models import Camera, CameraStatus
from tests.conftest import register


def test_data_survives_a_new_connection_and_session(admin, reserve):
    """Writes are committed to storage, not held in the process."""
    camera = register(
        admin,
        "TE-CAM-100",
        range_id=reserve["chahala"],
        beat_id=reserve["bakua"],
        site_name="Bakua Nala Crossing",
        contact_name="Ranjan Mahanta",
        contact_phone="+91 98110 20034",
    )

    # A completely separate session, as a restarted process would open.
    engine.dispose()
    fresh = SessionLocal()
    try:
        stored = fresh.scalars(select(Camera).where(Camera.id == camera["id"])).one()
        assert stored.serial_number == "TE-CAM-100"
        assert stored.site_name == "Bakua Nala Crossing"
        assert stored.range_id == reserve["chahala"]
    finally:
        fresh.close()


def test_a_reloaded_app_still_serves_the_same_inventory(admin, client, reserve):
    register(admin, "TE-CAM-101", range_id=reserve["chahala"])
    engine.dispose()

    response = admin.get("/api/cameras")

    assert response.status_code == 200
    assert {c["serial_number"] for c in response.json()["items"]} == {"TE-CAM-101"}


# ---------------------------------------------------------------------------
# Constraints hold even if the service layer is bypassed
# ---------------------------------------------------------------------------
def test_database_rejects_a_duplicate_serial_number(admin, reserve, db):
    register(admin, "TE-CAM-102")

    db.add(Camera(serial_number="TE-CAM-102", status=CameraStatus.IN_STOCK))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_database_rejects_a_beat_outside_the_selected_range(reserve, db):
    """The composite foreign key is the last line of defence for this rule."""
    db.add(
        Camera(
            serial_number="TE-CAM-103",
            status=CameraStatus.ALLOCATED,
            range_id=reserve["chahala"],
            beat_id=reserve["joranda"],  # Nawana's beat
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_database_rejects_a_deployed_camera_with_no_location(reserve, db):
    db.add(
        Camera(
            serial_number="TE-CAM-104",
            status=CameraStatus.DEPLOYED,
            range_id=reserve["chahala"],
            beat_id=reserve["bakua"],
            site_name="Bakua Nala Crossing",
            latitude=None,
            longitude=None,
            contact_name="Ranjan Mahanta",
            contact_phone="+91 98110 20034",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_database_rejects_out_of_range_coordinates(reserve, db):
    db.add(
        Camera(
            serial_number="TE-CAM-105",
            status=CameraStatus.ALLOCATED,
            range_id=reserve["chahala"],
            latitude=120.0,
            longitude=86.0,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_database_rejects_a_range_user_without_a_range(db):
    from app.models import User, UserRole

    db.add(
        User(
            email="rogue@similipal.test",
            full_name="Rogue",
            password_hash="x",
            role=UserRole.RANGE_USER,
            range_id=None,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_foreign_key_enforcement_is_actually_switched_on(db):
    """Guards the test-suite itself: SQLite ignores foreign keys by default."""
    if engine.dialect.name != "sqlite":
        pytest.skip("PRAGMA check is SQLite-specific")
    assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1
