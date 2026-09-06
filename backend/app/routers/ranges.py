"""Reserve hierarchy: ranges and their beats (seeded reference data).

Scoped the same way cameras are: an administrator sees the whole reserve, a
range user sees only their own range and its beats. Anything else would list
ranges they can neither filter by nor transfer to.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import CurrentUser, DbSession
from app.models import Range
from app.schemas import RangeOut

router = APIRouter(prefix="/api/ranges", tags=["reference"])


@router.get("", response_model=list[RangeOut])
def list_ranges(user: CurrentUser, db: DbSession) -> list[Range]:
    stmt = select(Range).options(selectinload(Range.beats)).order_by(Range.name)
    if not user.is_admin:
        stmt = stmt.where(Range.id == user.range_id)
    return list(db.scalars(stmt).unique())
