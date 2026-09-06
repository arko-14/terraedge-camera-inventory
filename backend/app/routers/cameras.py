"""Camera inventory endpoints.

Thin on purpose: parse, call the service layer, serialise. Permission and
validation decisions live in app/services/camera_service.py.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import AdminUser, CurrentUser, DbSession
from app.models import AssignmentHistory, Beat, Camera, CameraStatus, Range
from app.schemas import (
    CameraCreate,
    CameraDetail,
    CameraListResponse,
    CameraOut,
    CameraTransfer,
    CameraUpdate,
    HistoryOut,
    ImportResult,
)
from app.serializers import camera_detail, camera_out, history_out, name_lookups
from app.services import camera_service, csv_service

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


def load_name_lookups(db: Session) -> tuple[dict[int, str], dict[int, str]]:
    # A few dozen rows; loading them once beats joining history four times.
    return name_lookups(list(db.scalars(select(Range))), list(db.scalars(select(Beat))))


@router.get("", response_model=CameraListResponse)
def list_cameras(
    user: CurrentUser,
    db: DbSession,
    search: Annotated[str | None, Query(max_length=100, description="Serial, site or contact")] = None,
    range_id: int | None = None,
    beat_id: int | None = None,
    camera_status: Annotated[CameraStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> CameraListResponse:
    camera_service.check_filters_exist(db, range_id, beat_id)
    stmt = camera_service.build_camera_query(user, search, range_id, beat_id, camera_status)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Camera.serial_number).offset((page - 1) * page_size).limit(page_size)
    ).unique()

    return CameraListResponse(
        items=[camera_out(c) for c in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, -(-total // page_size)),
    )


@router.post("", response_model=CameraOut, status_code=status.HTTP_201_CREATED)
def register_camera(payload: CameraCreate, admin: AdminUser, db: DbSession) -> CameraOut:
    """Register a camera. Reserve administrators only - stock belongs to the reserve."""
    camera = camera_service.register_camera(db, admin, payload)
    return camera_out(camera)


# --------------------------------------------------------------------------
# CSV import / export
#
# Declared before the /{camera_id} routes so these literal paths win.
# --------------------------------------------------------------------------
@router.get("/export", response_class=PlainTextResponse)
def export_cameras(
    user: CurrentUser,
    db: DbSession,
    search: Annotated[str | None, Query(max_length=100)] = None,
    range_id: int | None = None,
    beat_id: int | None = None,
    camera_status: Annotated[CameraStatus | None, Query(alias="status")] = None,
) -> PlainTextResponse:
    """Export the current view as CSV.

    Built on the same scoped query as the list endpoint, so a range user's
    export contains their range and nothing else.
    """
    camera_service.check_filters_exist(db, range_id, beat_id)
    stmt = camera_service.build_camera_query(user, search, range_id, beat_id, camera_status)
    cameras = list(db.scalars(stmt.order_by(Camera.serial_number)).unique())

    return PlainTextResponse(
        content=csv_service.export_cameras(cameras),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="camera-inventory.csv"'},
    )


@router.get("/import/template", response_class=PlainTextResponse)
def import_template(admin: AdminUser) -> PlainTextResponse:
    """A blank CSV with the expected headers and one example row."""
    return PlainTextResponse(
        content=csv_service.import_template(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="camera-import-template.csv"'},
    )


@router.post("/import", response_model=ImportResult)
async def import_cameras(admin: AdminUser, db: DbSession, file: UploadFile = File(...)) -> ImportResult:
    """Bulk-register cameras from a CSV file. Reserve administrators only.

    Valid rows are imported even when others fail, so one bad row in a long
    spreadsheet does not reject the whole file.
    """
    raw = await file.read()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The file must be UTF-8 encoded text. Re-save it as CSV UTF-8.",
        ) from exc

    return ImportResult(**csv_service.import_cameras(db, admin, content))


@router.get("/{camera_id}", response_model=CameraDetail)
def get_camera(camera_id: int, user: CurrentUser, db: DbSession) -> CameraDetail:
    camera = camera_service.get_camera_for_user(db, user, camera_id)
    history = list(
        db.scalars(
            select(AssignmentHistory)
            .where(AssignmentHistory.camera_id == camera.id)
            .order_by(AssignmentHistory.changed_at.desc(), AssignmentHistory.id.desc())
        )
    )
    range_names, beat_names = load_name_lookups(db)
    return camera_detail(camera, history, range_names, beat_names)


@router.patch("/{camera_id}", response_model=CameraOut)
def update_camera(
    camera_id: int, payload: CameraUpdate, user: CurrentUser, db: DbSession
) -> CameraOut:
    """Update deployment detail or status for a camera inside your scope."""
    camera = camera_service.get_camera_for_user(db, user, camera_id)
    camera = camera_service.update_camera(db, user, camera, payload)
    return camera_out(camera)


@router.post("/{camera_id}/transfer", response_model=CameraOut)
def transfer_camera(
    camera_id: int, payload: CameraTransfer, user: CurrentUser, db: DbSession
) -> CameraOut:
    """Allocate a camera, move it between beats/ranges, or return it to stock.

    A range user may only reassign within their own range; crossing a range
    boundary requires a reserve administrator.
    """
    camera = camera_service.get_camera_for_user(db, user, camera_id)
    camera = camera_service.transfer_camera(db, user, camera, payload)
    return camera_out(camera)


@router.get("/{camera_id}/history", response_model=list[HistoryOut])
def camera_history(camera_id: int, user: CurrentUser, db: DbSession) -> list[HistoryOut]:
    camera = camera_service.get_camera_for_user(db, user, camera_id)
    entries = list(
        db.scalars(
            select(AssignmentHistory)
            .where(AssignmentHistory.camera_id == camera.id)
            .order_by(AssignmentHistory.changed_at.desc(), AssignmentHistory.id.desc())
        )
    )
    range_names, beat_names = load_name_lookups(db)
    return [history_out(e, range_names, beat_names) for e in entries]
