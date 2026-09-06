"""CSV export and bulk import.

Import is row-by-row rather than all-or-nothing: a 300-row spreadsheet with two
bad rows should import 298 and report the two. Each row goes through the same
`register_camera` call the API uses, so it gets the same validation and the
same history entry as a camera added by hand.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Beat, Camera, Range, User
from app.schemas import CameraCreate
from app.services import camera_service

EXPORT_COLUMNS = [
    "serial_number",
    "model",
    "status",
    "range",
    "beat",
    "site_name",
    "latitude",
    "longitude",
    "contact_name",
    "contact_phone",
    "allocated_at",
    "deployed_at",
    "notes",
]

# Only the serial number is required; everything else may be blank.
IMPORT_COLUMNS = [
    "serial_number",
    "model",
    "range",
    "beat",
    "site_name",
    "latitude",
    "longitude",
    "contact_name",
    "contact_phone",
    "notes",
]

MAX_IMPORT_ROWS = 1000
# 1000 rows of this shape is well under 200 KB; the cap exists so a large
# upload is refused before it is read into memory, not after.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


def export_cameras(cameras: list[Camera]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for camera in cameras:
        writer.writerow(
            {
                "serial_number": camera.serial_number,
                "model": camera.model or "",
                "status": camera.status.value,
                "range": camera.range.name if camera.range else "",
                "beat": camera.beat.name if camera.beat else "",
                "site_name": camera.site_name or "",
                "latitude": camera.latitude if camera.latitude is not None else "",
                "longitude": camera.longitude if camera.longitude is not None else "",
                "contact_name": camera.contact_name or "",
                "contact_phone": camera.contact_phone or "",
                "allocated_at": camera.allocated_at.isoformat() if camera.allocated_at else "",
                "deployed_at": camera.deployed_at.isoformat() if camera.deployed_at else "",
                "notes": camera.notes or "",
            }
        )
    return output.getvalue()


def import_template() -> str:
    """A header row plus one worked example, so the expected shape is obvious."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerow(
        {
            "serial_number": "TE-CAM-101",
            "model": "PantheraCam S3",
            "range": "Chahala Range",
            "beat": "Bakua Beat",
            "site_name": "Bakua Nala Crossing",
            "latitude": "21.904200",
            "longitude": "86.361100",
            "contact_name": "Ranjan Mahanta",
            "contact_phone": "+91 98110 20034",
            "notes": "",
        }
    )
    return output.getvalue()


def _clean(row: dict[str, Any], key: str) -> str | None:
    value = (row.get(key) or "").strip()
    return value or None


def _parse_coordinate(raw: str | None, label: str) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{label} '{raw}' is not a number.") from exc


def import_cameras(db: Session, actor: User, content: str) -> dict[str, Any]:
    """Register every valid row; report the rest.

    Returns a summary the UI renders directly: how many were created, how many
    were skipped as already-present, and one message per failed row.
    """
    try:
        text = content.lstrip("﻿")  # Excel writes a BOM
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except csv.Error as exc:
        raise HTTPException(
            status_code=422, detail=f"Could not read the CSV file: {exc}"
        ) from exc

    if reader.fieldnames is None or "serial_number" not in [
        (f or "").strip().lower() for f in reader.fieldnames
    ]:
        raise HTTPException(
            status_code=422,
            detail=(
                "The file needs a 'serial_number' column. "
                "Download the template for the expected format."
            ),
        )

    if len(rows) > MAX_IMPORT_ROWS:
        raise HTTPException(
            status_code=422,
            detail=f"That file has {len(rows)} rows; the limit is {MAX_IMPORT_ROWS} per import.",
        )

    # Names are matched case-insensitively so a spreadsheet typed by hand still
    # lines up with the seeded hierarchy.
    ranges = {r.name.strip().lower(): r for r in db.scalars(select(Range))}
    beats: dict[tuple[int, str], Beat] = {
        (b.range_id, b.name.strip().lower()): b for b in db.scalars(select(Beat))
    }

    created: list[str] = []
    skipped: list[dict[str, str]] = []
    errors: list[dict[str, Any]] = []

    for index, raw_row in enumerate(rows, start=2):  # row 1 is the header
        row = {(k or "").strip().lower(): v for k, v in raw_row.items()}
        serial = _clean(row, "serial_number")

        if serial is None:
            errors.append({"row": index, "serial_number": "", "message": "Serial number is missing."})
            continue

        try:
            range_name = _clean(row, "range")
            beat_name = _clean(row, "beat")

            range_obj = None
            if range_name is not None:
                range_obj = ranges.get(range_name.lower())
                if range_obj is None:
                    raise ValueError(f"Range '{range_name}' does not exist.")

            beat_obj = None
            if beat_name is not None:
                if range_obj is None:
                    raise ValueError("A beat was given without a range.")
                beat_obj = beats.get((range_obj.id, beat_name.lower()))
                if beat_obj is None:
                    raise ValueError(f"Beat '{beat_name}' is not in range '{range_obj.name}'.")

            payload = CameraCreate(
                serial_number=serial,
                model=_clean(row, "model"),
                range_id=range_obj.id if range_obj else None,
                beat_id=beat_obj.id if beat_obj else None,
                site_name=_clean(row, "site_name"),
                latitude=_parse_coordinate(_clean(row, "latitude"), "Latitude"),
                longitude=_parse_coordinate(_clean(row, "longitude"), "Longitude"),
                contact_name=_clean(row, "contact_name"),
                contact_phone=_clean(row, "contact_phone"),
                notes=_clean(row, "notes"),
            )
            camera = camera_service.register_camera(db, actor, payload)
            created.append(camera.serial_number)

        except HTTPException as exc:
            # A duplicate serial is an expected outcome when re-importing a
            # spreadsheet, so it is reported separately from a real error.
            if exc.status_code == 409:
                skipped.append({"serial_number": serial.upper(), "reason": "Already registered."})
            else:
                errors.append({"row": index, "serial_number": serial, "message": str(exc.detail)})
        except ValidationError as exc:
            message = exc.errors()[0]["msg"].removeprefix("Value error, ")
            errors.append({"row": index, "serial_number": serial, "message": message})
        except ValueError as exc:
            errors.append({"row": index, "serial_number": serial, "message": str(exc)})

    return {
        "total_rows": len(rows),
        "created_count": len(created),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }
