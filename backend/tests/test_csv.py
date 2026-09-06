"""CSV export and bulk import."""

from __future__ import annotations

import csv
import io

from tests.conftest import register


def upload(api, content: str, filename: str = "cameras.csv"):
    return api.post(
        "/api/cameras/import",
        files={"file": (filename, content.encode("utf-8"), "text/csv")},
    )


def rows(csv_text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(csv_text)))


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def test_export_returns_a_csv_attachment(admin, reserve):
    register(admin, "TE-CAM-001", range_id=reserve["chahala"], beat_id=reserve["bakua"])

    response = admin.get("/api/cameras/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert rows(response.text)[0]["serial_number"] == "TE-CAM-001"


def test_export_includes_readable_range_and_beat_names(admin, reserve):
    register(admin, "TE-CAM-002", range_id=reserve["chahala"], beat_id=reserve["bakua"])

    row = rows(admin.get("/api/cameras/export").text)[0]

    assert row["range"] == "Chahala Range"
    assert row["beat"] == "Bakua Beat"
    assert row["status"] == "allocated"


def test_export_honours_the_current_filters(admin, reserve):
    register(admin, "TE-CHA-001", range_id=reserve["chahala"])
    register(admin, "TE-NAW-001", range_id=reserve["nawana"])

    exported = rows(admin.get(f"/api/cameras/export?range_id={reserve['chahala']}").text)

    assert [r["serial_number"] for r in exported] == ["TE-CHA-001"]


def test_export_is_scoped_to_the_users_range(admin, chahala_user, reserve):
    """The new endpoint inherits scoping from the shared query builder."""
    register(admin, "TE-CHA-001", range_id=reserve["chahala"])
    register(admin, "TE-NAW-001", range_id=reserve["nawana"])
    register(admin, "TE-STOCK-001")

    exported = rows(chahala_user.get("/api/cameras/export").text)

    assert [r["serial_number"] for r in exported] == ["TE-CHA-001"]


def test_export_requires_authentication(client, reserve):
    assert client.get("/api/cameras/export").status_code == 401


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------
def test_import_creates_cameras(admin, reserve):
    content = (
        "serial_number,model,range,beat\n"
        "TE-IMP-001,PantheraCam S3,Chahala Range,Bakua Beat\n"
        "TE-IMP-002,TrailWatch X1,Nawana Range,\n"
        "TE-IMP-003,,,\n"
    )

    response = upload(admin, content)

    assert response.status_code == 200
    body = response.json()
    assert body["created_count"] == 3
    assert body["error_count"] == 0

    listed = admin.get("/api/cameras?search=TE-IMP").json()
    assert listed["total"] == 3

    imported = admin.get("/api/cameras?search=TE-IMP-001").json()["items"][0]
    assert imported["range_name"] == "Chahala Range"
    assert imported["beat_name"] == "Bakua Beat"
    assert imported["status"] == "allocated"
    # A camera with no range stays in stock.
    stock = admin.get("/api/cameras?search=TE-IMP-003").json()["items"][0]
    assert stock["status"] == "in_stock"


def test_import_records_history_for_each_camera(admin, reserve):
    upload(admin, "serial_number\nTE-IMP-010\n")

    camera = admin.get("/api/cameras?search=TE-IMP-010").json()["items"][0]
    history = admin.get(f"/api/cameras/{camera['id']}/history").json()

    assert len(history) == 1
    assert history[0]["change_type"] == "registered"
    assert history[0]["changed_by_email"] == "admin@similipal.test"


def test_import_skips_serials_that_already_exist(admin, reserve):
    register(admin, "TE-IMP-020")

    response = upload(admin, "serial_number\nTE-IMP-020\nTE-IMP-021\n")

    body = response.json()
    assert body["created_count"] == 1
    assert body["skipped_count"] == 1
    assert body["skipped"][0]["serial_number"] == "TE-IMP-020"
    assert body["error_count"] == 0


def test_one_bad_row_does_not_stop_the_rest(admin, reserve):
    content = (
        "serial_number,range,beat\n"
        "TE-IMP-030,Chahala Range,Bakua Beat\n"
        "TE-IMP-031,Chahala Range,Joranda Beat\n"   # beat is in the other range
        "TE-IMP-032,Nowhere Range,\n"               # range does not exist
        ",,\n"                                      # no serial number
        "TE-IMP-034,,\n"
    )

    body = upload(admin, content).json()

    assert body["created_count"] == 2
    assert body["error_count"] == 3
    messages = {e["message"] for e in body["errors"]}
    assert any("Joranda Beat" in m for m in messages)
    assert any("Nowhere Range" in m for m in messages)
    assert any("Serial number is missing" in m for m in messages)
    # Reported against the spreadsheet's own row numbers, header included.
    assert {e["row"] for e in body["errors"]} == {3, 4, 5}


def test_import_reports_invalid_coordinates_per_row(admin, reserve):
    content = (
        "serial_number,range,beat,site_name,latitude,longitude,contact_name,contact_phone\n"
        "TE-IMP-040,Chahala Range,Bakua Beat,Ridge,not-a-number,86.3,A,+91 98110 20034\n"
        "TE-IMP-041,Chahala Range,Bakua Beat,Ridge,120,86.3,A,+91 98110 20034\n"
    )

    body = upload(admin, content).json()

    assert body["created_count"] == 0
    assert body["error_count"] == 2
    assert any("not a number" in e["message"] for e in body["errors"])


def test_import_matches_range_and_beat_names_case_insensitively(admin, reserve):
    body = upload(admin, "serial_number,range,beat\nTE-IMP-050,chahala range,BAKUA BEAT\n").json()

    assert body["created_count"] == 1
    camera = admin.get("/api/cameras?search=TE-IMP-050").json()["items"][0]
    assert camera["beat_name"] == "Bakua Beat"


def test_import_handles_an_excel_byte_order_mark(admin, reserve):
    response = admin.post(
        "/api/cameras/import",
        files={"file": ("cameras.csv", "﻿serial_number\nTE-IMP-060\n".encode(), "text/csv")},
    )
    assert response.json()["created_count"] == 1


def test_import_rejects_a_file_without_a_serial_number_column(admin, reserve):
    response = upload(admin, "model,range\nPantheraCam S3,Chahala Range\n")

    assert response.status_code == 422
    assert "serial_number" in response.json()["detail"]


def test_range_user_cannot_import(chahala_user, reserve):
    response = upload(chahala_user, "serial_number\nTE-IMP-070\n")

    assert response.status_code == 403
    assert "administrator" in response.json()["detail"]


def test_import_template_is_downloadable_by_admin(admin, chahala_user):
    response = admin.get("/api/cameras/import/template")

    assert response.status_code == 200
    assert "serial_number" in response.text
    assert chahala_user.get("/api/cameras/import/template").status_code == 403


def test_exported_file_can_be_imported_into_an_empty_database(admin, reserve, db):
    """Round-trip: export, wipe, re-import, same inventory."""
    register(admin, "TE-RT-001", range_id=reserve["chahala"], beat_id=reserve["bakua"])
    register(admin, "TE-RT-002", range_id=reserve["nawana"])
    exported = admin.get("/api/cameras/export").text

    from sqlalchemy import delete

    from app.models import AssignmentHistory, Camera

    db.execute(delete(AssignmentHistory))
    db.execute(delete(Camera))
    db.commit()

    body = upload(admin, exported).json()

    assert body["created_count"] == 2
    assert body["error_count"] == 0
    restored = admin.get("/api/cameras").json()["items"]
    assert {c["serial_number"] for c in restored} == {"TE-RT-001", "TE-RT-002"}
    assert restored[0]["range_name"] == "Chahala Range"
