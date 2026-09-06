"""Camera business rules: scoping, validation, state transitions, history.

Every decision about who may do what, and what a valid camera looks like, lives
here rather than in the routers - so the rules are readable in one place and
cannot be bypassed by calling a different endpoint.

Two invariants hold for every mutation:

1. Current state and history are written in the same transaction.
2. A camera keeps one identity for life. Transfers update columns and append
   history; nothing here ever inserts a second row for the same serial.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AssignmentHistory,
    Beat,
    Camera,
    CameraStatus,
    ChangeType,
    Range,
    User,
)
from app.schemas import CameraCreate, CameraTransfer, CameraUpdate

# Fields whose before/after values are recorded on every history row. Add a
# name here and it is captured automatically.
TRACKED_FIELDS = (
    "range_id",
    "beat_id",
    "site_name",
    "status",
    "latitude",
    "longitude",
    "contact_name",
    "contact_phone",
)

DEPLOYMENT_REQUIRED = {
    "range_id": "a range",
    "beat_id": "a beat",
    "site_name": "a site name",
    "latitude": "a latitude",
    "longitude": "a longitude",
    "contact_name": "a responsible contact name",
    "contact_phone": "a responsible contact phone number",
}


def invalid(detail: str) -> HTTPException:
    return HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail=detail)


def not_found() -> HTTPException:
    """Identical whether the camera does not exist or is simply out of scope.

    A range user must not be able to probe for serial numbers in other ranges.
    """
    return HTTPException(
        status_code=http_status.HTTP_404_NOT_FOUND,
        detail="Camera not found, or not in a range you have access to.",
    )


# ---------------------------------------------------------------------------
# Scoping
# ---------------------------------------------------------------------------
def scope_to_user(stmt: Select, user: User) -> Select:
    """Restrict a camera query to what `user` may see.

    An admin sees everything. A range user sees only cameras in their range,
    which excludes unallocated stock - stock belongs to the reserve.
    """
    if user.is_admin:
        return stmt
    return stmt.where(Camera.range_id == user.range_id)


def get_camera_for_user(db: Session, user: User, camera_id: int) -> Camera:
    camera = db.scalars(scope_to_user(select(Camera).where(Camera.id == camera_id), user)).first()
    if camera is None:
        raise not_found()
    return camera


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def load_range(db: Session, range_id: int) -> Range:
    rng = db.get(Range, range_id)
    if rng is None:
        raise invalid(f"Range {range_id} does not exist.")
    return rng


def check_beat_belongs_to_range(db: Session, range_id: int | None, beat_id: int | None) -> None:
    if beat_id is None:
        return
    if range_id is None:
        raise invalid("Select a range before selecting a beat.")

    beat = db.get(Beat, beat_id)
    if beat is None:
        raise invalid(f"Beat {beat_id} does not exist.")
    if beat.range_id != range_id:
        owning = db.get(Range, beat.range_id)
        target = db.get(Range, range_id)
        raise invalid(
            f"Beat '{beat.name}' belongs to range '{owning.name if owning else beat.range_id}', "
            f"not '{target.name if target else range_id}'."
        )


def check_camera_state(values: dict[str, Any]) -> None:
    """Whole-camera rules that no single field can check alone."""
    new_status = values["status"]

    if (values.get("latitude") is None) != (values.get("longitude") is None):
        raise invalid(
            "Latitude and longitude must be provided together - a half-known position is not usable."
        )

    if new_status == CameraStatus.IN_STOCK:
        if values.get("range_id") is not None or values.get("beat_id") is not None:
            raise invalid(
                "A camera in stock cannot hold a range or beat. Return it to stock via a transfer instead."
            )
    elif new_status == CameraStatus.ALLOCATED:
        if values.get("range_id") is None:
            raise invalid("An allocated camera must have a range.")
    elif new_status == CameraStatus.DEPLOYED:
        missing = [label for field, label in DEPLOYMENT_REQUIRED.items() if values.get(field) is None]
        if missing:
            raise invalid(
                "Before a camera can be marked deployed it needs " + ", ".join(missing) + "."
            )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------
def snapshot(camera: Camera) -> dict[str, Any]:
    return {field: getattr(camera, field) for field in TRACKED_FIELDS}


def add_history(
    db: Session,
    camera: Camera,
    actor: User,
    change_type: ChangeType,
    before: dict[str, Any],
    after: dict[str, Any],
    note: str | None = None,
) -> None:
    db.add(
        AssignmentHistory(
            camera=camera,
            changed_by_user_id=actor.id,
            changed_at=datetime.now(UTC),
            change_type=change_type,
            note=note,
            **{f"from_{field}": before.get(field) for field in TRACKED_FIELDS},
            **{f"to_{field}": after.get(field) for field in TRACKED_FIELDS},
        )
    )


def has_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return any(before.get(f) != after.get(f) for f in TRACKED_FIELDS)


def commit(db: Session, serial: str) -> None:
    """Commit, turning constraint violations into clean errors.

    The service layer already checks these rules; the database checks them
    again as a backstop. If the backstop fires, the client still gets a
    sensible message instead of a 500.
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        message = str(getattr(exc, "orig", exc)).lower()
        if "serial" in message or "unique" in message:
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail=f"Serial number {serial} is already registered.",
            ) from exc
        if "beat_within_range" in message:
            raise invalid("The selected beat does not belong to the selected range.") from exc
        raise invalid(
            "That change would leave the camera in an inconsistent state and was rejected."
        ) from exc


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def register_camera(db: Session, actor: User, payload: CameraCreate) -> Camera:
    """Register a new camera. Reserve administrators only."""
    serial = payload.serial_number  # trimmed and upper-cased by the schema

    if db.scalars(select(Camera).where(Camera.serial_number == serial)).first() is not None:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"Serial number {serial} is already registered.",
        )

    if payload.range_id is not None:
        load_range(db, payload.range_id)
    check_beat_belongs_to_range(db, payload.range_id, payload.beat_id)

    new_status = payload.status or (
        CameraStatus.IN_STOCK if payload.range_id is None else CameraStatus.ALLOCATED
    )

    values = {
        "serial_number": serial,
        "model": payload.model,
        "status": new_status,
        "range_id": payload.range_id,
        "beat_id": payload.beat_id,
        "site_name": payload.site_name,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "contact_name": payload.contact_name,
        "contact_phone": payload.contact_phone,
        "notes": payload.notes,
    }
    check_camera_state(values)

    now = datetime.now(UTC)
    camera = Camera(
        **values,
        created_by_user_id=actor.id,
        allocated_at=now if new_status != CameraStatus.IN_STOCK else None,
        deployed_at=now if new_status == CameraStatus.DEPLOYED else None,
    )
    db.add(camera)

    add_history(
        db, camera, actor, ChangeType.REGISTERED, dict.fromkeys(TRACKED_FIELDS), snapshot(camera)
    )

    commit(db, serial)
    db.refresh(camera)
    return camera


def update_camera(db: Session, actor: User, camera: Camera, payload: CameraUpdate) -> Camera:
    """Update deployment detail and/or status.

    Only keys present in the request body are applied, so a partial update
    cannot blank a field it never mentioned.
    """
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return camera

    if changes.get("status") == CameraStatus.IN_STOCK:
        raise invalid(
            "Use a transfer to return a camera to stock, so the move is recorded as one event."
        )

    # A range user may set the beat, but only within their own range; the range
    # itself changes only via /transfer.
    if "beat_id" in changes:
        check_beat_belongs_to_range(db, camera.range_id, changes["beat_id"])

    before = snapshot(camera)
    proposed = {**before, **changes}
    proposed["status"] = changes.get("status", camera.status)
    check_camera_state(proposed)

    was_deployed = camera.status == CameraStatus.DEPLOYED
    for field, value in changes.items():
        setattr(camera, field, value)

    newly_deployed = camera.status == CameraStatus.DEPLOYED and not was_deployed
    if newly_deployed:
        camera.deployed_at = datetime.now(UTC)
    elif was_deployed and camera.status != CameraStatus.DEPLOYED:
        # Leaving the field clears the date, as a transfer already does.
        # Otherwise an allocated camera keeps claiming a deployment date.
        camera.deployed_at = None

    after = snapshot(camera)
    if has_changed(before, after) or "model" in changes or "notes" in changes:
        add_history(
            db,
            camera,
            actor,
            ChangeType.DEPLOYED if newly_deployed else ChangeType.DETAILS_UPDATED,
            before,
            after,
        )

    commit(db, camera.serial_number)
    db.refresh(camera)
    return camera


def transfer_camera(db: Session, actor: User, camera: Camera, payload: CameraTransfer) -> Camera:
    """Allocate, move, or return a camera to stock.

    Moving a camera ends its current deployment: the site, coordinates and
    contact described where it used to be, so they are cleared here and
    preserved in history. The camera returns to `allocated` and is redeployed
    at its new location as a separate step.
    """
    target_range_id = payload.range_id
    target_beat_id = payload.beat_id

    # Range users may reassign between beats of their own range; anything that
    # crosses a range boundary is an administrator action.
    if not actor.is_admin and target_range_id != actor.range_id:
        raise forbidden(
            "Only a reserve administrator can move a camera to a different range "
            "or return it to stock."
        )

    if target_range_id is not None:
        load_range(db, target_range_id)
    check_beat_belongs_to_range(db, target_range_id, target_beat_id)

    if camera.range_id == target_range_id and camera.beat_id == target_beat_id:
        return camera

    before = snapshot(camera)
    now = datetime.now(UTC)

    if target_range_id is None:
        change_type = ChangeType.RETURNED_TO_STOCK
        camera.status = CameraStatus.IN_STOCK
        camera.allocated_at = None
    else:
        change_type = ChangeType.ALLOCATED if camera.range_id is None else ChangeType.TRANSFERRED
        camera.status = CameraStatus.ALLOCATED
        camera.allocated_at = now

    camera.deployed_at = None
    camera.range_id = target_range_id
    camera.beat_id = target_beat_id
    camera.site_name = None
    camera.latitude = None
    camera.longitude = None
    camera.contact_name = None
    camera.contact_phone = None

    check_camera_state(snapshot(camera))
    add_history(db, camera, actor, change_type, before, snapshot(camera), note=payload.note)

    commit(db, camera.serial_number)
    db.refresh(camera)
    return camera


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def check_filters_exist(db: Session, range_id: int | None, beat_id: int | None) -> None:
    """Reject filters that name a range or beat which does not exist.

    Without this, a stale client sending an id that has since been removed gets
    an empty list and no hint that its filter, rather than the inventory, is
    the problem. Existence only - a real range the caller cannot see still
    returns an empty list, which is what range isolation should look like.
    """
    if range_id is not None and db.get(Range, range_id) is None:
        raise invalid(f"Range {range_id} does not exist. Reload the page and try again.")
    if beat_id is not None and db.get(Beat, beat_id) is None:
        raise invalid(f"Beat {beat_id} does not exist. Reload the page and try again.")


def build_camera_query(
    user: User,
    search: str | None = None,
    range_id: int | None = None,
    beat_id: int | None = None,
    camera_status: CameraStatus | None = None,
) -> Select:
    stmt = select(Camera)

    if search:
        # Escape LIKE metacharacters, or a search for "%" matches every row and
        # forces a full scan. The backslash is escaped first, or it would
        # re-escape the escapes added below.
        needle = search.strip().lower()
        for char in ("\\", "%", "_"):
            needle = needle.replace(char, f"\\{char}")
        term = f"%{needle}%"
        stmt = stmt.where(
            or_(
                func.lower(Camera.serial_number).like(term, escape="\\"),
                func.lower(func.coalesce(Camera.site_name, "")).like(term, escape="\\"),
                func.lower(func.coalesce(Camera.contact_name, "")).like(term, escape="\\"),
            )
        )
    if range_id is not None:
        stmt = stmt.where(Camera.range_id == range_id)
    if beat_id is not None:
        stmt = stmt.where(Camera.beat_id == beat_id)
    if camera_status is not None:
        stmt = stmt.where(Camera.status == camera_status)

    # Scoping is applied last, so no combination of filters can widen what a
    # range user sees.
    return scope_to_user(stmt, user)
