"""Pydantic request/response models.

Field-shape validation only (types, bounds, single-field requirements).
Anything needing more than one field or the database lives in
app/services/camera_service.py.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import CameraStatus, ChangeType, UserRole

SERIAL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")
# Deliberately permissive: field contacts have +91 numbers, spaces and dashes.
PHONE_RE = re.compile(r"^[+0-9][0-9 \-()]{6,31}$")
# A shape check, not an RFC 5322 parser. `email-validator` rejects RFC 6761
# reserved TLDs such as `.test`, which is exactly where demo accounts belong.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

Latitude = Annotated[float, Field(ge=-90, le=90, description="Decimal degrees")]
Longitude = Annotated[float, Field(ge=-180, le=180, description="Decimal degrees")]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address.")
        return v


class UserOut(ORMModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    range_id: int | None
    range_name: str | None = None


class LoginResponse(BaseModel):
    user: UserOut
    # For scripted clients (curl, tests); browsers use the cookie instead.
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime


# --------------------------------------------------------------------------
# Reserve hierarchy
# --------------------------------------------------------------------------
class BeatOut(ORMModel):
    id: int
    name: str
    range_id: int


class RangeOut(ORMModel):
    id: int
    name: str
    beats: list[BeatOut] = []


# --------------------------------------------------------------------------
# Cameras
# --------------------------------------------------------------------------
class CameraBase(BaseModel):
    site_name: str | None = Field(default=None, max_length=200)
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    contact_name: str | None = Field(default=None, max_length=160)
    contact_phone: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("site_name", "contact_name", "notes", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @field_validator("contact_phone")
    @classmethod
    def _check_phone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if not PHONE_RE.match(v):
            raise ValueError("Enter a valid phone number, e.g. +91 98765 43210")
        return v


class CameraCreate(CameraBase):
    serial_number: str = Field(min_length=3, max_length=64)
    model: str | None = Field(default=None, max_length=120)
    # Omit to let the server infer it: no range -> in stock, range -> allocated.
    status: CameraStatus | None = None
    range_id: int | None = None
    beat_id: int | None = None

    @field_validator("serial_number")
    @classmethod
    def _check_serial(cls, v: str) -> str:
        # Upper-cased so "cam-001" and "CAM-001" are one camera, not two.
        v = v.strip().upper()
        if not SERIAL_RE.match(v):
            raise ValueError(
                "Serial number must be 3-64 characters: letters, digits, hyphen or underscore."
            )
        return v


class CameraUpdate(CameraBase):
    """Deployment detail and status changes.

    Only keys present in the request body are applied, so a partial update
    cannot blank fields it never mentioned.
    """

    model: str | None = Field(default=None, max_length=120)
    status: CameraStatus | None = None
    beat_id: int | None = None


class CameraTransfer(BaseModel):
    """Allocate a camera to a range/beat, or move it to a different one."""

    range_id: int | None = Field(default=None, description="null returns the camera to stock")
    beat_id: int | None = None
    note: str | None = Field(default=None, max_length=500)


class CameraOut(ORMModel):
    id: int
    serial_number: str
    model: str | None
    status: CameraStatus
    range_id: int | None
    range_name: str | None = None
    beat_id: int | None
    beat_name: str | None = None
    site_name: str | None
    latitude: float | None
    longitude: float | None
    contact_name: str | None
    contact_phone: str | None
    notes: str | None
    allocated_at: datetime | None
    deployed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CameraListResponse(BaseModel):
    items: list[CameraOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class HistoryOut(ORMModel):
    id: int
    camera_id: int
    camera_serial: str | None = None
    change_type: ChangeType
    changed_at: datetime
    changed_by_user_id: int | None
    changed_by_name: str | None = None
    changed_by_email: str | None = None
    from_range_id: int | None
    to_range_id: int | None
    from_range_name: str | None = None
    to_range_name: str | None = None
    from_beat_id: int | None
    to_beat_id: int | None
    from_beat_name: str | None = None
    to_beat_name: str | None = None
    from_site_name: str | None
    to_site_name: str | None
    from_status: CameraStatus | None
    to_status: CameraStatus | None
    from_latitude: float | None
    to_latitude: float | None
    from_longitude: float | None
    to_longitude: float | None
    from_contact_name: str | None
    to_contact_name: str | None
    from_contact_phone: str | None
    to_contact_phone: str | None
    note: str | None


class CameraDetail(CameraOut):
    history: list[HistoryOut] = []


# --------------------------------------------------------------------------
# CSV import
# --------------------------------------------------------------------------
class ImportSkipped(BaseModel):
    serial_number: str
    reason: str


class ImportRowError(BaseModel):
    row: int
    serial_number: str
    message: str


class ImportResult(BaseModel):
    """Per-row outcome, so one bad row does not hide the rest."""

    total_rows: int
    created_count: int
    skipped_count: int
    error_count: int
    created: list[str]
    skipped: list[ImportSkipped]
    errors: list[ImportRowError]


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
class RangeBreakdown(BaseModel):
    range_id: int
    range_name: str
    total: int
    allocated: int
    deployed: int


class SummaryOut(BaseModel):
    total: int
    in_stock: int
    allocated: int
    deployed: int
    by_range: list[RangeBreakdown]
