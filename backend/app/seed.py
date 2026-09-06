"""Seed the reserve hierarchy, demo accounts and fictional camera inventory.

    python -m app.seed            # seed once; does nothing if data exists
    python -m app.seed --reset    # wipe camera/user/hierarchy data and reseed

All names, phone numbers and coordinates below are FICTIONAL demo data, as the
brief requires. Demo account passwords come from the environment
(SEED_ADMIN_PASSWORD, SEED_CHAHALA_PASSWORD, SEED_NAWANA_PASSWORD); if unset, a
strong random password is generated per account and printed once, so nothing
weak is baked into the repo and no two accounts share a credential.

Cameras are created by calling the same service layer the API uses, so the
seeded inventory carries a real assignment history rather than hand-written
rows - and seeding doubles as a smoke test of the write path.
"""

from __future__ import annotations

import argparse
import secrets
import sys

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import AssignmentHistory, Beat, Camera, CameraStatus, Range, User, UserRole
from app.schemas import CameraCreate, CameraUpdate
from app.security import hash_password
from app.services import camera_service

RESERVE_NAME = "Similipal Tiger Reserve"

RANGES: dict[str, list[str]] = {
    "Chahala Range": ["Bakua Beat", "Jenabil Beat"],
    "Nawana Range": ["Barehipani Beat", "Joranda Beat"],
}

# (serial, model, range, beat, site, lat, lon, contact name, contact phone)
# lat/lon sit inside the Similipal bounding box; every contact is invented.
DEPLOYED = [
    ("TE-CAM-015", "PantheraCam S3", "Chahala Range", "Bakua Beat", "Bakua Nala Crossing", 21.9042, 86.3611, "Ranjan Mahanta", "+91 98110 20034"),
    ("TE-CAM-016", "PantheraCam S3", "Chahala Range", "Bakua Beat", "Chahala Salt Lick", 21.8875, 86.3489, "Ranjan Mahanta", "+91 98110 20034"),
    ("TE-CAM-017", "PantheraCam S3", "Chahala Range", "Jenabil Beat", "Jenabil Ridge Track", 21.9310, 86.4102, "Sunita Hansda", "+91 98110 20035"),
    ("TE-CAM-018", "TrailWatch X1", "Chahala Range", "Jenabil Beat", "Jenabil Waterhole", 21.9265, 86.3998, "Sunita Hansda", "+91 98110 20035"),
    ("TE-CAM-019", "TrailWatch X1", "Nawana Range", "Barehipani Beat", "Barehipani Falls Approach", 21.8402, 86.2711, "Debasis Naik", "+91 98110 20036"),
    ("TE-CAM-020", "TrailWatch X1", "Nawana Range", "Barehipani Beat", "Upper Barehipani Path", 21.8477, 86.2803, "Debasis Naik", "+91 98110 20036"),
    ("TE-CAM-021", "PantheraCam S3", "Nawana Range", "Joranda Beat", "Joranda Falls Viewpoint", 21.8123, 86.3055, "Malati Soren", "+91 98110 20037"),
    ("TE-CAM-022", "PantheraCam S3", "Nawana Range", "Joranda Beat", "Joranda Grassland Edge", 21.8056, 86.2967, "Malati Soren", "+91 98110 20037"),
    ("TE-CAM-023", "TrailWatch X1", "Nawana Range", "Joranda Beat", "Nawana Valley Culvert", 21.7988, 86.3140, "Malati Soren", "+91 98110 20037"),
    ("TE-CAM-024", "PantheraCam S3", "Chahala Range", "Bakua Beat", "Bakua Fire Line North", 21.9101, 86.3702, "Ranjan Mahanta", "+91 98110 20034"),
]

# (serial, model, range, beat-or-None) - allocated but not yet in the field.
ALLOCATED = [
    ("TE-CAM-007", "PantheraCam S3", "Chahala Range", "Bakua Beat"),
    ("TE-CAM-008", "PantheraCam S3", "Chahala Range", "Jenabil Beat"),
    ("TE-CAM-009", "TrailWatch X1", "Chahala Range", None),
    ("TE-CAM-010", "TrailWatch X1", "Nawana Range", "Barehipani Beat"),
    ("TE-CAM-011", "PantheraCam S3", "Nawana Range", "Joranda Beat"),
    ("TE-CAM-012", "PantheraCam S3", "Nawana Range", None),
    ("TE-CAM-013", "TrailWatch X1", "Chahala Range", "Bakua Beat"),
    ("TE-CAM-014", "TrailWatch X1", "Nawana Range", "Barehipani Beat"),
]

IN_STOCK = [(f"TE-CAM-{n:03d}", "PantheraCam S3" if n % 2 else "TrailWatch X1") for n in range(1, 7)]


def resolve_password(env_value: str) -> tuple[str, bool]:
    """Return (password, was_generated). Never fall back to a hard-coded value."""
    if env_value:
        return env_value, False
    return secrets.token_urlsafe(12), True


def clear_all_data(db: Session) -> None:
    """Empty every table and restart the id sequences.

    Restarting matters: range and beat ids are used as filter values by the web
    app, so if a reseed handed out fresh ids an open browser tab would keep
    sending ids that no longer exist and every filter would quietly return
    nothing. Reseeding now always produces the same ids.
    """
    tables = ["assignment_history", "cameras", "users", "beats", "ranges"]

    if db.bind.dialect.name == "postgresql":
        db.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    else:
        for model in (AssignmentHistory, Camera, User, Beat, Range):
            db.execute(delete(model))
        # SQLite only keeps a sequence table when AUTOINCREMENT is used; the
        # reset is a no-op otherwise.
        if db.scalar(
            text("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
        ):
            db.execute(text("DELETE FROM sqlite_sequence"))

    db.commit()


def seed(reset: bool = False) -> None:
    db = SessionLocal()
    try:
        if reset:
            clear_all_data(db)
        elif db.scalar(select(Range).limit(1)) is not None:
            print("Database already contains data - nothing to do. Use --reset to reseed.")
            return

        # --- hierarchy -----------------------------------------------------
        ranges: dict[str, Range] = {}
        beats: dict[tuple[str, str], Beat] = {}
        for range_name, beat_names in RANGES.items():
            rng = Range(name=range_name)
            db.add(rng)
            ranges[range_name] = rng
            for beat_name in beat_names:
                beat = Beat(range=rng, name=beat_name)
                db.add(beat)
                beats[(range_name, beat_name)] = beat
        db.flush()

        # --- accounts ------------------------------------------------------
        # Every account gets its own password. Sharing one between the two
        # range officers would mean compromising either compromises both, and
        # "individual credentials" is a requirement, not a nicety.
        admin_pw, admin_generated = resolve_password(settings.seed_admin_password)
        chahala_pw, chahala_generated = resolve_password(settings.seed_chahala_password)
        nawana_pw, nawana_generated = resolve_password(settings.seed_nawana_password)
        generated = admin_generated or chahala_generated or nawana_generated

        admin = User(
            email="admin@similipal.test",
            full_name="Reserve Administrator",
            password_hash=hash_password(admin_pw),
            role=UserRole.RESERVE_ADMIN,
            range_id=None,
        )
        db.add(admin)
        accounts = [("admin@similipal.test", admin_pw, "Reserve administrator - all ranges")]

        for range_name, login, password in (
            ("Chahala Range", "chahala@similipal.test", chahala_pw),
            ("Nawana Range", "nawana@similipal.test", nawana_pw),
        ):
            db.add(
                User(
                    email=login,
                    full_name=f"{range_name.replace(' Range', '')} Range Officer",
                    password_hash=hash_password(password),
                    role=UserRole.RANGE_USER,
                    range_id=ranges[range_name].id,
                )
            )
            accounts.append((login, password, f"Range user - {range_name} only"))

        if len({password for _, password, _ in accounts}) != len(accounts):
            raise SystemExit(
                "Refusing to seed: two demo accounts were given the same password. "
                "Set a distinct SEED_*_PASSWORD for each, or leave them blank to generate."
            )

        db.commit()
        db.refresh(admin)

        # --- inventory, created through the real service layer -------------
        for serial, model in IN_STOCK:
            camera_service.register_camera(
                db, admin, CameraCreate(serial_number=serial, model=model)
            )

        for serial, model, range_name, beat_name in ALLOCATED:
            camera_service.register_camera(
                db,
                admin,
                CameraCreate(
                    serial_number=serial,
                    model=model,
                    range_id=ranges[range_name].id,
                    beat_id=beats[(range_name, beat_name)].id if beat_name else None,
                ),
            )

        for serial, model, range_name, beat_name, site, lat, lon, contact, phone in DEPLOYED:
            camera = camera_service.register_camera(
                db,
                admin,
                CameraCreate(
                    serial_number=serial,
                    model=model,
                    range_id=ranges[range_name].id,
                    beat_id=beats[(range_name, beat_name)].id,
                ),
            )
            # A second step, so each deployed camera has a real two-entry
            # history: registered/allocated, then deployed.
            camera_service.update_camera(
                db,
                admin,
                camera,
                CameraUpdate(
                    status=CameraStatus.DEPLOYED,
                    site_name=site,
                    latitude=lat,
                    longitude=lon,
                    contact_name=contact,
                    contact_phone=phone,
                ),
            )

        print(f"\nSeeded {RESERVE_NAME}: {len(RANGES)} ranges, "
              f"{sum(len(b) for b in RANGES.values())} beats, "
              f"{len(IN_STOCK) + len(ALLOCATED) + len(DEPLOYED)} cameras.\n")
        print("Demo accounts:")
        for email, password, description in accounts:
            print(f"  {email:<26} {password:<20} {description}")
        if generated:
            print(
                "\nPasswords not set in the environment were generated randomly and are\n"
                "shown only once. Set SEED_ADMIN_PASSWORD, SEED_CHAHALA_PASSWORD and\n"
                "SEED_NAWANA_PASSWORD in .env to choose your own."
            )
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the TerraEdge demo database.")
    parser.add_argument(
        "--reset", action="store_true", help="Delete existing data before seeding."
    )
    args = parser.parse_args()
    seed(reset=args.reset)
    return 0


if __name__ == "__main__":
    sys.exit(main())
