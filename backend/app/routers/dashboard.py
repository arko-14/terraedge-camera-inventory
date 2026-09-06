"""Dashboard totals and recent-activity feed, scoped by `scope_to_user`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import joinedload

from app.deps import CurrentUser, DbSession
from app.models import AssignmentHistory, Beat, Camera, CameraStatus, Range
from app.schemas import HistoryOut, RangeBreakdown, SummaryOut
from app.serializers import history_out, name_lookups
from app.services.camera_service import scope_to_user

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/stats/summary", response_model=SummaryOut)
def summary(user: CurrentUser, db: DbSession) -> SummaryOut:
    counts_stmt = scope_to_user(
        select(Camera.status, func.count(Camera.id)).group_by(Camera.status), user
    )
    counts = {row[0]: row[1] for row in db.execute(counts_stmt).all()}

    # CASE aggregation keeps this to one query and works on both engines.
    by_range_stmt = scope_to_user(
        select(
            Range.id.label("range_id"),
            Range.name.label("range_name"),
            func.count(Camera.id).label("total"),
            func.sum(case((Camera.status == CameraStatus.ALLOCATED, 1), else_=0)).label("allocated"),
            func.sum(case((Camera.status == CameraStatus.DEPLOYED, 1), else_=0)).label("deployed"),
        )
        .join(Camera, Camera.range_id == Range.id)
        .group_by(Range.id, Range.name)
        .order_by(Range.name),
        user,
    )

    by_range = [
        RangeBreakdown(
            range_id=row.range_id,
            range_name=row.range_name,
            total=row.total or 0,
            allocated=int(row.allocated or 0),
            deployed=int(row.deployed or 0),
        )
        for row in db.execute(by_range_stmt).all()
    ]

    return SummaryOut(
        total=sum(counts.values()),
        in_stock=counts.get(CameraStatus.IN_STOCK, 0),
        allocated=counts.get(CameraStatus.ALLOCATED, 0),
        deployed=counts.get(CameraStatus.DEPLOYED, 0),
        by_range=by_range,
    )


@router.get("/activity", response_model=list[HistoryOut])
def recent_activity(
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 15,
) -> list[HistoryOut]:
    entries = list(
        db.scalars(
            select(AssignmentHistory)
            .options(joinedload(AssignmentHistory.camera))
            .where(AssignmentHistory.camera_id.in_(scope_to_user(select(Camera.id), user)))
            .order_by(AssignmentHistory.changed_at.desc(), AssignmentHistory.id.desc())
            .limit(limit)
        )
    )
    range_names, beat_names = name_lookups(
        list(db.scalars(select(Range))), list(db.scalars(select(Beat)))
    )
    return [history_out(e, range_names, beat_names) for e in entries]
