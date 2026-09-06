"""Turn ORM rows into API response models."""

from __future__ import annotations

from app.models import AssignmentHistory, Beat, Camera, User
from app.schemas import CameraDetail, CameraOut, HistoryOut, UserOut


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        range_id=user.range_id,
        range_name=user.range.name if user.range else None,
    )


def camera_out(camera: Camera) -> CameraOut:
    return CameraOut(
        id=camera.id,
        serial_number=camera.serial_number,
        model=camera.model,
        status=camera.status,
        range_id=camera.range_id,
        range_name=camera.range.name if camera.range else None,
        beat_id=camera.beat_id,
        beat_name=camera.beat.name if camera.beat else None,
        site_name=camera.site_name,
        latitude=camera.latitude,
        longitude=camera.longitude,
        contact_name=camera.contact_name,
        contact_phone=camera.contact_phone,
        notes=camera.notes,
        allocated_at=camera.allocated_at,
        deployed_at=camera.deployed_at,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
    )


def history_out(
    entry: AssignmentHistory,
    range_names: dict[int, str],
    beat_names: dict[int, str],
) -> HistoryOut:
    """Names come from pre-fetched lookups, to avoid N+1 queries."""
    return HistoryOut(
        id=entry.id,
        camera_id=entry.camera_id,
        camera_serial=entry.camera.serial_number if entry.camera else None,
        change_type=entry.change_type,
        changed_at=entry.changed_at,
        changed_by_user_id=entry.changed_by_user_id,
        changed_by_name=entry.changed_by.full_name if entry.changed_by else None,
        changed_by_email=entry.changed_by.email if entry.changed_by else None,
        from_range_id=entry.from_range_id,
        to_range_id=entry.to_range_id,
        from_range_name=range_names.get(entry.from_range_id) if entry.from_range_id else None,
        to_range_name=range_names.get(entry.to_range_id) if entry.to_range_id else None,
        from_beat_id=entry.from_beat_id,
        to_beat_id=entry.to_beat_id,
        from_beat_name=beat_names.get(entry.from_beat_id) if entry.from_beat_id else None,
        to_beat_name=beat_names.get(entry.to_beat_id) if entry.to_beat_id else None,
        from_site_name=entry.from_site_name,
        to_site_name=entry.to_site_name,
        from_status=entry.from_status,
        to_status=entry.to_status,
        from_latitude=entry.from_latitude,
        to_latitude=entry.to_latitude,
        from_longitude=entry.from_longitude,
        to_longitude=entry.to_longitude,
        from_contact_name=entry.from_contact_name,
        to_contact_name=entry.to_contact_name,
        from_contact_phone=entry.from_contact_phone,
        to_contact_phone=entry.to_contact_phone,
        note=entry.note,
    )


def camera_detail(
    camera: Camera,
    history: list[AssignmentHistory],
    range_names: dict[int, str],
    beat_names: dict[int, str],
) -> CameraDetail:
    return CameraDetail(
        **camera_out(camera).model_dump(),
        history=[history_out(h, range_names, beat_names) for h in history],
    )


def name_lookups(ranges: list, beats: list[Beat]) -> tuple[dict[int, str], dict[int, str]]:
    return ({r.id: r.name for r in ranges}, {b.id: b.name for b in beats})
