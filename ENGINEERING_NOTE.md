# Engineering note

Camera Inventory & Deployment Platform — Similipal Tiger Reserve
Sandipan Paul · September 2026

## The problem

~500 cameras move from the reserve → ranges → beats. In a spreadsheet, one cell
overwrite silently destroys the previous deployment, so a camera's images can no
longer be tied to a location. The design is organised around preventing that.

## Architecture

```
┌────────── one origin, one container ──────────┐
│ React + TS (Vite)      FastAPI                │      PostgreSQL
│   TanStack Query ────►   routers/  (HTTP only)│ ───►   ranges → beats
│   React Router           services/ (all rules)│        users
│   Tailwind               models/   (schema)   │        cameras
│   httpOnly cookie        Alembic   (migrations)│       assignment_history
└───────────────────────────────────────────────┘
```

- **Routers** parse and serialise — no rules.
- **`services/camera_service.py`** holds every permission and validation
  decision. One file, no way around it.
- **`models.py`** repeats the important invariants as database constraints.

The key opinion: **the same rule is enforced twice on purpose.** The service
layer returns a helpful message; the constraint makes the bad state
unrepresentable. `tests/test_persistence.py` bypasses the service layer and
asserts the database still refuses.

## Data model

Five tables ([`docs/schema.png`](docs/schema.png)). The reserve is a seeded
constant, not a table.

**Core decision:** `cameras` holds *where a camera is now*;
`assignment_history` is append-only rows with `from_*`/`to_*` pairs, actor and
timestamp.

| Alternative | Why not |
|---|---|
| Overwrite on change | Loses history — the spreadsheet's exact failure |
| Event log only | Every list/filter/search becomes a fold over history |
| **Current state + append-only history** ✅ | Reads stay one indexed scan; history never rewritten |

Both are written in one transaction from one function (`add_history`), and
history is never updated or deleted. Explicit `from_`/`to_` columns (not a JSON
diff) keep the timeline renderable without replaying the table.

**Enforced by the database:**

| Rule | How |
|---|---|
| One identity per camera | `UNIQUE` on `serial_number`, upper-cased on write |
| Beat must belong to the selected range | Composite FK `(beat_id, range_id) → beats(id, range_id)` |
| Range without a beat allowed | Composite FK not applied when `beat_id` is `NULL` |
| Valid, paired coordinates | `CHECK` on ±90/±180 and `(lat IS NULL) = (lon IS NULL)` |
| Deployed ⇒ range, beat, site, coordinates, contact | One `CHECK` on `status` |
| Range user has a range; admin never does | `CHECK` on `users` |

The composite FK is the piece I'm happiest with: "the beat must belong to the
range" is usually an app-layer check that quietly rots; `UNIQUE (id, range_id)`
on `beats` lets Postgres enforce it for free.

Status is `VARCHAR` + `CHECK`, not a native `ENUM`, so values stay readable in
SQL and adding one is an ordinary migration.

## Access rules

| | Reserve admin | Range user |
|---|---|---|
| See cameras | All, incl. unallocated stock | Only their range |
| Register | Yes | No |
| Edit deployment detail / move between beats | Yes | Within their range |
| Move between ranges, return to stock | Yes | **No** |
| Dashboard totals | Whole reserve | Their range |

One function, `scope_to_user()`, appends `WHERE range_id = :user_range`. Every
read path uses it, applied **last** — after user filters — so no query parameter
can widen visibility. Writes go through `get_camera_for_user()`.

Out-of-scope access returns **404, not 403**: a 403 would confirm a serial
exists in another range. Where the camera is visible but the action isn't
allowed, it's a 403 with a reason. `scripts/verify_api.sh` proves this with
curl, no browser involved.

## Security

- **Passwords** — Argon2id: memory-hard, per-hash salt and parameters,
  transparent re-hash on login.
- **Sessions** — Signed JWT, 12 h, **httpOnly** cookie so XSS can't read it. The
  token's role/range claims are **never trusted**; the user row is re-read every
  request, so revoking an account takes effect immediately. Logout increments a
  `token_version` on the account and every request compares it, so signing out
  invalidates tokens already issued — not just the cookie. That costs nothing
  extra, because the user row was already being loaded.
- **CSRF** — Double-submit token, as **middleware not a decorator**, so routes
  added later are protected by default.
- **Secrets** — All environment variables; only `.env.example` is committed. In
  production the app refuses to boot on a placeholder `JWT_SECRET`, with
  `COOKIE_SECURE=false`, or with wildcard CORS.
- **Other** — One identical message for unknown email and wrong password. SPA
  fallback checks resolved paths stay inside the build directory.

**Observability** — one structured line per request with a correlation id,
method, path, status, duration, the authenticated user id and the forwarded
client ip. The id is returned in an `X-Request-ID` header and included in error
bodies, so a reported failure maps to a log line. Deliberately no emails,
tokens or request bodies in the logs. Successful health checks are not logged,
so a platform probe every few seconds cannot bury real traffic.

## Technology choices

- **FastAPI + SQLAlchemy 2 + Alembic** — validation and OpenAPI docs for free;
  DI puts `CurrentUser`/`AdminUser` in the route signature, so the permission
  requirement is visible rather than buried.
- **PostgreSQL** — the integrity rules above are the reason.
- **React + Vite + Tailwind** — TanStack Query supplies the loading/error states
  the brief asks for; one place for desktop-table and mobile-card layouts.
- **SQLite for tests** — `pytest` needs no Docker or network. Safe only because
  the schema is portable; I verified the same migrations and every constraint
  against real Postgres 16. `PRAGMA foreign_keys=ON` is set on connect and a
  test asserts it, or the composite-FK tests would pass vacuously.
- **One Docker image** — the built React app is served by FastAPI, so app and
  API share an origin: no CORS, `SameSite=Lax`, one free instance to wake. Built
  it split (Vercel + Render) first; moved once same-origin proved simpler *and*
  safer. The split path still works and is documented.

## Optional extensions

Both built only after the core workflow was complete and tested.

**CSV import/export** — chosen first because it addresses the actual starting
point: the records are in spreadsheets today. Export reuses the same scoped
query as the list endpoint, so it inherits range isolation rather than
re-implementing it. Import is row-by-row rather than transactional: a file with
two bad rows imports the rest and reports those two against their spreadsheet
row numbers, and existing serials are skipped rather than duplicated, so
re-uploading a corrected file is safe. Each row goes through the same
`register_camera` call as the API, so imported cameras get identical validation
and a real history entry.

**Deployment map** — deployed cameras on an OpenStreetMap layer, scoped per
role, fitted to the markers. It reuses the camera list endpoint, so a range
user's map shows their range and nothing else. Vector markers rather than pin
icons, so there are no image assets to break under a bundler.

## Assumptions

1. One reserve, modelled as a constant.
2. **A transfer ends the deployment** — site, coordinates and contact described
   where it *used to be*, so they're cleared and preserved in history; the camera
   returns to `allocated`. Carrying them across would record a camera as deployed
   at a site in a beat it no longer belongs to.
3. Contacts are data, not accounts — no login needed.
4. Ranges and beats are seeded reference data (admin screen optional in the brief).
5. Returning to stock is a transfer, not a status edit, so it's one event.
6. Unallocated stock is invisible to range users — stock belongs to the reserve.
7. Serial numbers are case-insensitive.

## Known limitations

- No password reset, invite flow or admin user screen; accounts are seeded.
- No refresh tokens; a 12 h session simply expires. Logout is account-wide
  rather than per-device — per-device sessions would need a session table.
- No rate limiting on login.
- Coordinates validated for range, not plausibility — nothing checks a point
  falls inside Similipal or the named beat.
- Offset pagination; history isn't paginated at all.
- No offline support — the remaining optional extension, and the one that
  matters most operationally.
- The map shows current positions only, not historical tracks.
- CSV import is capped at 1000 rows and 2 MB per file, with no dry-run preview.
- Tests run on SQLite while production is Postgres (mitigated above).

## What I'd change before real deployment

1. Run the test-suite against Postgres in CI.
2. Rate-limit authentication per IP and account, with lockout and backoff.
3. Ship logs to a searchable service and add error reporting. The structured
   per-request logging and correlation ids are already in place; what is missing
   is somewhere to search them and alerting when they go wrong.
4. Admin screens for ranges, beats and accounts.
5. **Offline capture** — beats have no connectivity: queued writes on the device,
   synced later, serial number as the idempotency key. The change that would most
   affect the data model, and part of why history is append-only.
6. Soft delete for decommissioned cameras.

## Time spent

Roughly 12 hours: data modelling 2 h, backend 4 h, frontend 3.5 h, tests and
verification script 1.5 h, docs and deployment 1 h.

## Use of AI tools

I used **Claude (Anthropic)** as a coding assistant throughout — scaffolding,
drafting the service and UI layers, and drafting this note.

The design decisions are mine and are the ones I'd defend: the current-state +
append-only history split, the composite FK for range/beat integrity, scoping in
one query-level function applied last, 404 rather than 403 for out-of-scope
cameras, and treating a transfer as something that ends a deployment.

Verified rather than assumed: dependency versions pinned from a real resolved
install; migrations applied to Postgres 16 with each constraint driven to
failure; `email-validator` dropped after it rejected the RFC 6761 `.test` domain
the demo accounts use; and the first `verify_api.sh` run's four failures traced
to a bash quoting bug in the script, not the application — confirmed by
reproducing the requests by hand first.
