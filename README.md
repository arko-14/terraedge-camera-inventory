# Camera Inventory & Deployment Platform

A centralised web application for tracking the ~500 camera traps supplied to
**Similipal Tiger Reserve**: where each camera is, who is responsible for it,
and whether it is in stock, allocated or deployed — replacing the Google Sheets
and paper registers currently in use.

Built as a take-home engineering assignment. **All camera, contact and location
data in this repository is fictional.**

- **Engineering note** (architecture, data model, trade-offs, limitations):
  [`ENGINEERING_NOTE.md`](ENGINEERING_NOTE.md)
- **Demo walkthrough** (the exact journey to record or present):
  [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md)

---

## What it does

| Requirement | Where it lives |
|---|---|
| Sign in / sign out with individual credentials | `backend/app/routers/auth.py`, `frontend/src/pages/LoginPage.tsx` |
| Register a camera and allocate it to a range, then a beat | `POST /api/cameras`, `POST /api/cameras/{id}/transfer` |
| Record deployment: site, coordinates, responsible contact, status | `PATCH /api/cameras/{id}` |
| Search by serial; filter by range, beat and status; detail view | `GET /api/cameras`, `frontend/src/pages/CamerasPage.tsx` |
| Totals for inventory, allocated and deployed | `GET /api/stats/summary` |
| Movement tracking with full previous assignments, actor and timestamp | `assignment_history` table, `GET /api/cameras/{id}/history` |
| Two access levels, enforced in the backend | `backend/app/services/camera_service.py` |
| *(optional extension)* CSV export and bulk import | `backend/app/services/csv_service.py` |

---

## Stack

| Layer | Choice |
|---|---|
| Frontend | React 19 + TypeScript, Vite, Tailwind CSS 4, TanStack Query, React Router |
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2, Alembic |
| Database | PostgreSQL 16 (SQLite for the test-suite) |
| Auth | Argon2id password hashing, signed JWT in an httpOnly cookie, double-submit CSRF |

Reasoning for each choice is in the [engineering note](ENGINEERING_NOTE.md).

---

## Running it locally

**Prerequisites:** Python 3.11+, Node 20+, and Docker (for Postgres). If you
would rather point at an existing Postgres, just set `DATABASE_URL` and skip
step 1.

### 1. Database

```bash
docker compose up -d db
```

### 2. Backend — http://127.0.0.1:8000

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then edit it, see "Configuration" below
alembic upgrade head               # create the schema
python -m app.seed                 # fictional demo data + demo accounts

uvicorn app.main:app --reload
```

`python -m app.seed` prints the demo account credentials. Interactive API docs
are at http://127.0.0.1:8000/docs.

### 3. Frontend — http://127.0.0.1:5173

```bash
cd frontend
npm install
npm run dev
```

In development Vite proxies `/api` to the backend, so the app and API share an
origin and no CORS configuration is needed.

---

## Demo accounts

Created by `python -m app.seed`.

| Email | Role | Sees |
|---|---|---|
| `admin@similipal.test` | Reserve administrator | Every camera; can register, allocate and transfer |
| `chahala@similipal.test` | Range user | Chahala Range only |
| `nawana@similipal.test` | Range user | Nawana Range only |

**Every account has its own password** — the seed script refuses to run if two
are the same, so one leaked credential cannot open another officer's account.
They come from `SEED_ADMIN_PASSWORD`, `SEED_CHAHALA_PASSWORD` and
`SEED_NAWANA_PASSWORD`. **If those are unset the seed generates a strong random
password per account and prints it once**, rather than baking a weak default
into the repository.

For a throwaway local database you can set them to `demo-admin-123`,
`demo-chahala-123` and `demo-nawana-123` — the values `DEMO_SCRIPT.md` and
`scripts/verify_api.sh` assume by default, so the walkthrough stays
copy-pasteable. **These are local-only.** The hosted demo uses different
passwords, supplied privately.

Seeded inventory: 2 ranges, 2 beats each, 24 cameras — 6 in stock, 8 allocated,
10 deployed.

---

## Configuration

Every setting is an environment variable; no secret is committed. See
[`backend/.env.example`](backend/.env.example) and
[`frontend/.env.example`](frontend/.env.example).

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (`postgres://` URLs are rewritten to the psycopg driver automatically) |
| `JWT_SECRET` | Signing key for session tokens. Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Session lifetime (default 720 = 12 h) |
| `COOKIE_SECURE` / `COOKIE_SAMESITE` | `false`/`lax` for local; `true`/`none` for a split deployment |
| `CORS_ORIGINS` | Exact frontend origins allowed to call the API with credentials |
| `SEED_*_PASSWORD` | One per demo account; must all differ |
| `VITE_API_BASE_URL` | *(frontend)* Empty locally; the API origin in production |

In `ENVIRONMENT=production` the app **refuses to start** with a placeholder
`JWT_SECRET`, with `COOKIE_SECURE=false`, or with wildcard CORS origins.

---

## Tests and checks

### Backend test-suite — 82 tests

```bash
cd backend && pytest -q
```

Runs against a throwaway SQLite file: no Docker, no Postgres, no network. It
covers duplicate serial numbers, invalid range/beat combinations, coordinate
bounds and pairing, deployment completeness, unauthorised access across ranges,
CSRF, persistence across connections, and assignment history.

| File | Covers |
|---|---|
| `tests/test_auth.py` | Sign-in, password hashing, account enumeration, token tampering, CSRF |
| `tests/test_validation.py` | Unique serials, range/beat coherence, coordinates, status rules |
| `tests/test_authorization.py` | Range isolation on every read and write path |
| `tests/test_history.py` | Movement tracking, append-only history, no duplicate identities |
| `tests/test_persistence.py` | Data survives restarts; constraints hold when the service layer is bypassed |
| `tests/test_csv.py` | CSV export scoping and filters; per-row import outcomes; round-trip |

### End-to-end API checks — 53 assertions

```bash
./scripts/verify_api.sh                          # local
API=https://your-api.onrender.com ./scripts/verify_api.sh
```

Drives the **running API directly with curl** — no browser involved — which is
how the brief asks for authorisation to be demonstrated. Requires `jq` and a
seeded database.

### Linting

```bash
cd backend && ruff check app tests     # config in pyproject.toml
cd frontend && npx oxlint src && npx tsc -b
```

---

## CSV import and export

The one optional extension I built, because the reserve's records live in
spreadsheets today.

- **Export** — `GET /api/cameras/export` returns the *current view* as CSV: it
  reuses the same scoped, filtered query as the list endpoint, so a range user's
  export contains their range and nothing else.
- **Import** — `POST /api/cameras/import` (administrators only) bulk-registers
  from CSV. Only `serial_number` is required; range and beat are matched by
  name. Each row goes through the same service call the API uses, so imported
  cameras get identical validation and a real history entry.
- **Row-by-row, not all-or-nothing.** A 300-row file with two bad rows imports
  298 and reports the two, with the spreadsheet's own row numbers. Serials that
  already exist are *skipped*, not duplicated, so re-uploading a corrected file
  is safe.
- A template with the expected headers is at `GET /api/cameras/import/template`.

---

## Deploying

Both options below use free tiers and need no payment details.

### Recommended: one Render service + Neon Postgres

The [`Dockerfile`](Dockerfile) builds the React app and serves it from the
FastAPI process, so **the web app and the API share a single origin**. That is
not just convenience:

- no CORS configuration at all;
- the session cookie stays `SameSite=Lax` instead of the `SameSite=None` a split
  deployment forces;
- one free instance to wake instead of two.

**1. Database — Neon.** Create a project and copy the connection string.
Render's own free Postgres expires after 30 days, which is why the database
lives on Neon.

**2. App — Render.** Create a **Blueprint** from this repository; it reads
[`render.yaml`](render.yaml). Then set in the dashboard:

| Variable | Value |
|---|---|
| `DATABASE_URL` | your Neon connection string |
| `SEED_ADMIN_PASSWORD`, `SEED_CHAHALA_PASSWORD`, `SEED_NAWANA_PASSWORD` | one per demo account, to share privately with reviewers |

`JWT_SECRET` is generated by Render. Migrations run on every deploy. Seed once
from the Render shell:

```bash
python -m app.seed
```

Verify the deployment end to end:

```bash
API=https://your-app.onrender.com ADMIN_PASSWORD=... RANGE_PASSWORD=... ./scripts/verify_api.sh
```

You can run the exact production image locally first:

```bash
docker build -t terraedge .
docker run --rm -p 8080:8080 -e PORT=8080 \
  -e DATABASE_URL="postgresql+psycopg://terraedge:terraedge@host.docker.internal:5432/terraedge" \
  -e JWT_SECRET="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  terraedge
```

### Alternative: split deployment (Vercel + Render)

Still supported. Host `frontend/` on Vercel with **Root Directory** `frontend`
and `VITE_API_BASE_URL=https://your-api.onrender.com`
([`frontend/vercel.json`](frontend/vercel.json) handles client-side routing),
and run the API separately without `STATIC_DIR`. The API then needs
`CORS_ORIGINS` set to the exact Vercel origin, plus `COOKIE_SAMESITE=none` and
`COOKIE_SECURE=true` — which is what the CSRF double-submit token exists to
cover.

> **Free-tier caveat:** a Render free service sleeps after 15 minutes idle, so
> the first request can take ~50 seconds while it wakes. Load the app once
> before a live demo. The frontend shows a clear "could not reach the server"
> message rather than hanging silently.

---

## Repository layout

```
backend/
  app/
    config.py               settings + production safety checks
    database.py             engine, session, SQLite FK enforcement
    models.py               ORM models and database-level constraints
    schemas.py              request/response validation
    security.py             Argon2 hashing, JWT, CSRF tokens
    deps.py                 authentication and role dependencies
    serializers.py          ORM -> API response shapes
    services/
      camera_service.py     all business rules: scoping, validation, history
    routers/                auth, cameras, ranges, dashboard
    seed.py                 fictional demo data
  alembic/versions/         database migrations
  tests/                    66 tests
frontend/
  src/
    lib/                    API client, types, formatting, hooks
    auth/                   session context
    components/             layout and UI primitives
    pages/                  login, dashboard, cameras, detail, register
scripts/verify_api.sh       44 direct-API assertions
docs/schema.png             entity-relationship diagram
```
