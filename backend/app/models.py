"""ORM models.

`cameras` holds current state; `assignment_history` is an append-only record of
every change. Both are written in the same transaction, so "where is it now"
and "how did it get here" cannot disagree.

Invariants are enforced as database constraints as well as in the service
layer, so they hold even if the application is bypassed. See docs/schema.png.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    RESERVE_ADMIN = "reserve_admin"
    RANGE_USER = "range_user"


class CameraStatus(str, enum.Enum):
    IN_STOCK = "in_stock"
    ALLOCATED = "allocated"
    DEPLOYED = "deployed"


class ChangeType(str, enum.Enum):
    REGISTERED = "registered"
    ALLOCATED = "allocated"          # first time a range is attached
    TRANSFERRED = "transferred"      # range and/or beat changed afterwards
    DEPLOYED = "deployed"
    DETAILS_UPDATED = "details_updated"
    RETURNED_TO_STOCK = "returned_to_stock"


def enum_column(enum_cls, name: str) -> SAEnum:
    """Store enums as VARCHAR + CHECK rather than a native Postgres ENUM.

    Values stay readable in raw SQL, and adding one later is an ordinary
    migration instead of an ALTER TYPE.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        values_callable=lambda e: [m.value for m in e],
        length=32,
    )


class Range(Base):
    """A forest range. The reserve itself is a seeded constant, not a table."""

    __tablename__ = "ranges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    beats: Mapped[list[Beat]] = relationship(
        back_populates="range", order_by="Beat.name", cascade="all, delete-orphan"
    )


class Beat(Base):
    """A beat inside a range. Names are only unique within their range."""

    __tablename__ = "beats"
    __table_args__ = (
        UniqueConstraint("range_id", "name", name="uq_beats_range_name"),
        # Referenced by the composite foreign key on `cameras`, which is what
        # makes "the beat must belong to the range" a database guarantee.
        UniqueConstraint("id", "range_id", name="uq_beats_id_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    range_id: Mapped[int] = mapped_column(
        ForeignKey("ranges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    range: Mapped[Range] = relationship(back_populates="beats")


class User(Base):
    """Someone who can sign in.

    Field contacts are not users: a responsible contact is name/phone data on
    the camera, so recording one never requires creating an account.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(role = 'reserve_admin' AND range_id IS NULL) OR "
            "(role = 'range_user' AND range_id IS NOT NULL)",
            name="ck_users_role_range_consistency",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(enum_column(UserRole, "user_role"), nullable=False)
    range_id: Mapped[int | None] = mapped_column(
        ForeignKey("ranges.id", ondelete="RESTRICT"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    range: Mapped[Range | None] = relationship()

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.RESERVE_ADMIN


class Camera(Base):
    """Current state of one physical camera.

    `serial_number` is the stable identity: unique, upper-cased on write, and
    never changed. A transfer updates these columns and appends history; it
    never creates a second row.
    """

    __tablename__ = "cameras"
    __table_args__ = (
        # Not applied when beat_id is NULL, which is how "allocated to a range,
        # beat not yet decided" stays legal.
        ForeignKeyConstraint(
            ["beat_id", "range_id"],
            ["beats.id", "beats.range_id"],
            name="fk_cameras_beat_within_range",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_cameras_latitude_bounds",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_cameras_longitude_bounds",
        ),
        CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)",
            name="ck_cameras_coordinates_paired",
        ),
        # Stops a "deployed" camera with no location or nobody responsible.
        CheckConstraint(
            """
            (status = 'in_stock'  AND range_id IS NULL AND beat_id IS NULL)
         OR (status = 'allocated' AND range_id IS NOT NULL)
         OR (status = 'deployed'  AND range_id IS NOT NULL AND beat_id IS NOT NULL
             AND site_name IS NOT NULL AND latitude IS NOT NULL AND longitude IS NOT NULL
             AND contact_name IS NOT NULL AND contact_phone IS NOT NULL)
            """,
            name="ck_cameras_status_requirements",
        ),
        Index("ix_cameras_range_status", "range_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    serial_number: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)

    status: Mapped[CameraStatus] = mapped_column(
        enum_column(CameraStatus, "camera_status"),
        nullable=False,
        default=CameraStatus.IN_STOCK,
        index=True,
    )

    range_id: Mapped[int | None] = mapped_column(
        ForeignKey("ranges.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    beat_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    site_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6, asdecimal=False), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6, asdecimal=False), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    allocated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    range: Mapped[Range | None] = relationship(foreign_keys=[range_id], lazy="joined")
    # beat_id has no standalone foreign key (the composite constraint covers
    # it), so the join is spelled out and kept read-only.
    beat: Mapped[Beat | None] = relationship(
        primaryjoin="foreign(Camera.beat_id) == Beat.id", viewonly=True, lazy="joined"
    )
    history: Mapped[list[AssignmentHistory]] = relationship(
        back_populates="camera",
        order_by="AssignmentHistory.changed_at.desc(), AssignmentHistory.id.desc()",
        cascade="all, delete-orphan",
    )


class AssignmentHistory(Base):
    """Append-only record of every change to a camera.

    Rows are written, never updated or deleted, so a transfer preserves the
    earlier deployment instead of overwriting it. Storing before and after
    values explicitly means the timeline renders without replaying the table.
    """

    __tablename__ = "assignment_history"
    __table_args__ = (
        Index("ix_assignment_history_camera_changed", "camera_id", "changed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_id: Mapped[int] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SET NULL, so the trail survives if an account is removed.
    changed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    change_type: Mapped[ChangeType] = mapped_column(
        enum_column(ChangeType, "change_type"), nullable=False
    )

    from_range_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_range_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    from_beat_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_beat_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    from_site_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    to_site_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    from_status: Mapped[CameraStatus | None] = mapped_column(
        enum_column(CameraStatus, "camera_status"), nullable=True
    )
    to_status: Mapped[CameraStatus | None] = mapped_column(
        enum_column(CameraStatus, "camera_status"), nullable=True
    )
    from_latitude: Mapped[float | None] = mapped_column(Numeric(9, 6, asdecimal=False), nullable=True)
    to_latitude: Mapped[float | None] = mapped_column(Numeric(9, 6, asdecimal=False), nullable=True)
    from_longitude: Mapped[float | None] = mapped_column(Numeric(9, 6, asdecimal=False), nullable=True)
    to_longitude: Mapped[float | None] = mapped_column(Numeric(9, 6, asdecimal=False), nullable=True)
    from_contact_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    to_contact_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    from_contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    camera: Mapped[Camera] = relationship(back_populates="history")
    changed_by: Mapped[User | None] = relationship(lazy="joined")
