# Camera Inventory & Deployment Platform

Tracks the ~500 camera traps supplied to **Similipal Tiger Reserve**: where each
camera is, who is responsible for it, and whether it is in stock, allocated or
deployed — replacing the spreadsheets and paper registers in use today.

**Live demo:** https://terraedge-3y8f.onrender.com

| Account | Email | Password | Sees |
|---|---|---|---|
| Reserve administrator | `admin@similipal.test` | `terraedge-admin-2026` | Everything |
| Range user | `chahala@similipal.test` | `terraedge-chahala-2026` | Chahala Range only |
| Range user | `nawana@similipal.test` | `terraedge-nawana-2026` | Nawana Range only |

> Free instance — the first request after ~15 minutes idle takes ~50 s to wake.
> All camera, contact and location data is fictional.

**[Engineering note](ENGINEERING_NOTE.md)** — architecture, data model, access
rules, trade-offs, assumptions, limitations.
**[Demo walkthrough](DEMO_SCRIPT.md)** — the journey to record or present.

---

## Stack

React 19 + TypeScript (Vite, Tailwind, TanStack Query) · FastAPI + SQLAlchemy 2
+ Alembic · PostgreSQL · Argon2id passwords, JWT in an httpOnly cookie,
double-submit CSRF.

One Docker image builds the frontend and serves it from FastAPI, so the app and
API share an origin.

## Running locally

Needs Python 3.11+, Node 20+, Docker.

```bash
docker compose up -d db                     # Postgres

cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                        # set JWT_SECRET and the SEED_* passwords
alembic upgrade head                        # create the schema
python -m app.seed                          # 2 ranges, 4 beats, 24 cameras, 3 accounts
uvicorn app.main:app --reload               # http://127.0.0.1:8000

cd ../frontend
npm install && npm run dev                  # http://127.0.0.1:5173
```

`python -m app.seed` prints the demo credentials. API docs at `/docs`.

## Tests and checks

```bash
cd backend && pytest -q            # 105 tests, SQLite - no Docker or network needed
./scripts/verify_api.sh            # 53 assertions against a running API, via curl
cd backend && ruff check app tests
cd frontend && npx oxlint src && npx tsc -b
```

`verify_api.sh` drives the **real API with curl, no browser** — which is how the
brief asks for authorisation to be demonstrated. Add `CLEAN=1` to reseed
afterwards, or point it at the deployment:

```bash
API=https://terraedge-3y8f.onrender.com ADMIN_PASSWORD=... RANGE_PASSWORD=... ./scripts/verify_api.sh
```

| Test file | Covers |
|---|---|
| `test_auth.py` | Sign-in, hashing, account enumeration, token tampering, CSRF |
| `test_validation.py` | Unique serials, range/beat coherence, coordinates, status rules |
| `test_authorization.py` | Range isolation on every read and write path |
| `test_history.py` | Movement tracking, append-only history, no duplicate identities |
| `test_persistence.py` | Survives restarts; constraints hold when the service layer is bypassed |
| `test_csv.py` | Export scoping and filters, per-row import outcomes, round-trip |

## Configuration

Every setting is an environment variable; only `.env.example` is committed. See
[`backend/.env.example`](backend/.env.example).

Under `ENVIRONMENT=production` the app **refuses to start** with a placeholder
`JWT_SECRET`, with `COOKIE_SECURE=false`, or with wildcard CORS origins.

Each demo account has its own password — the seed refuses to run if two match.
Leave the `SEED_*` variables blank and it generates strong ones, printed once.

## Optional extensions

Both built only after the core workflow was complete.

- **CSV export and bulk import** — export reuses the same scoped query as the
  list endpoint, so it inherits range isolation. Import is row-by-row: a file
  with two bad rows imports the rest and reports those two against their
  spreadsheet row numbers; existing serials are skipped, not duplicated. Sample
  files in [`samples/`](samples/).
- **Deployment map** — cameras in the field on an OpenStreetMap layer, scoped
  per role.

## Deploying

One Render service plus a Neon database, both free.

1. **Neon** — create a project, copy the connection string.
2. **Render** — New → Blueprint → this repo. It reads [`render.yaml`](render.yaml)
   and builds the Dockerfile. Set `DATABASE_URL` and the three `SEED_*`
   passwords; `JWT_SECRET` is generated. Migrations run on every deploy.
3. **Seed** — Render's shell is paid-only, so seed over the network:
   ```bash
   DATABASE_URL="<neon>" SEED_ADMIN_PASSWORD=... SEED_CHAHALA_PASSWORD=... \
   SEED_NAWANA_PASSWORD=... python -m app.seed
   ```

Use Neon rather than Render's free Postgres, which expires after 30 days.

A split deployment (frontend on Vercel, API on Render) also works — set
`VITE_API_BASE_URL`, `CORS_ORIGINS` and `COOKIE_SAMESITE=none`.

## Layout

```
backend/app/
  models.py                   schema and database-level constraints
  services/camera_service.py  all business rules: scoping, validation, history
  services/csv_service.py     export and bulk import
  routers/                    auth, cameras, ranges, dashboard
  config.py deps.py security.py schemas.py serializers.py
backend/alembic/versions/     migrations
backend/tests/                88 tests
frontend/src/                 pages, components, lib, auth
scripts/verify_api.sh         53 direct-API assertions
docs/schema.png               entity-relationship diagram
```
