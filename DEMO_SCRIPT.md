# Demo walkthrough

A 5–6 minute run through the main user journey, in the order the brief's
"suggested demonstration" asks for. Works for a recording or a live demo.

**Before you start**

```bash
docker compose up -d db
cd backend && source .venv/bin/activate && python -m app.seed --reset && uvicorn app.main:app
cd frontend && npm run dev
```

If demoing the hosted version, **load the app once a minute beforehand** — a
free Render service sleeps after 15 minutes idle and takes ~50 s to wake.

Have two browsers (or one normal + one private window) open so you can be signed
in as the administrator and a range user at the same time, and a terminal ready
for step 6.

---

## 1. Sign in · 20 s

Sign in as `admin@similipal.test`.

> "Individual credentials, seeded demo accounts. The session is a signed token
> in an httpOnly cookie, so page JavaScript can't read it."

**Dashboard:** 24 cameras — 6 in stock, 8 allocated, 10 deployed, broken down by
range, with a recent-movement feed.

---

## 2. Register a camera · 40 s

**Register** → serial `TE-CAM-025`, model `PantheraCam S3`, leave the range as
*Keep in stock*.

> "Cameras arrive at the reserve before anyone decides where they go, so stock
> is a first-class state."

Now try to register `te-cam-025` again — **rejected**, and note the lower case:

> "Serial numbers are normalised and unique, so one physical camera can only
> ever have one record."

---

## 3. Allocate it · 40 s

Open `TE-CAM-025` → **Allocate** → *Chahala Range*, leave the beat as
*Not decided yet* → confirm.

> "The brief asks for range allocation before the beat is known, so beat is
> optional here. But a beat can never belong to a different range — that's a
> composite foreign key in the database, not just a form check."

Optionally show the rejection: pick *Chahala Range* with a Nawana beat via the
API in step 6.

---

## 4. Record a deployment · 60 s

**Record deployment** → beat *Bakua Beat*, site `Bakua Fire Line South`,
coordinates `21.9101`, `86.3702`, contact `Ranjan Mahanta`, `+91 98110 20034`.

First tick **Mark as deployed** *without* filling the coordinates and save:

> "It won't let me. A camera can't be 'deployed' without a location and someone
> responsible for it — that's a check constraint in Postgres, so it holds even
> if a request bypasses the application."

Now fill everything in and save. Status turns **Deployed**.

---

## 5. Find it, then move it · 90 s

**Cameras** → search `TE-CAM-025`; also filter by range *Chahala* + status
*Deployed*.

Open it → **Transfer** → *Nawana Range* / *Joranda Beat*, reason
"Moved for the winter census".

Point at the **assignment history**:

> "Four entries. The transfer records where it came from — Chahala, Bakua Beat,
> Bakua Fire Line South, and the coordinates — who moved it, and when. The
> earlier deployment entry is untouched. History is append-only; nothing is
> ever overwritten, which is exactly what a spreadsheet gets wrong."

> "Note the camera is now 'allocated', not 'deployed'. The old site described
> where it used to be, so a move ends the deployment and it gets redeployed at
> the new location as a separate step."

---

## 6. Access control — the part that matters · 90 s

**In the second browser,** sign in as `chahala@similipal.test`.

- Dashboard shows **only Chahala** cameras — no stock, no Nawana.
- Search for `TE-CAM-025` (now in Nawana) → **nothing**.
- Open one of their own cameras → they *can* edit deployment details.
- Try **Transfer** → only Chahala is selectable.

Then, in the terminal — this is the bit the brief specifically asks for:

```bash
# Sign in as the Chahala range user and get a token
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"chahala@similipal.test","password":"demo-chahala-123"}' | jq -r .access_token)

# Ask directly for a Nawana camera by id — no UI involved
curl -s http://127.0.0.1:8000/api/cameras/10 -H "Authorization: Bearer $TOKEN" | jq
# {"detail": "Camera not found, or not in a range you have access to."}

# Try to modify it
curl -s -X PATCH http://127.0.0.1:8000/api/cameras/10 \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"site_name":"Hijacked"}' | jq
# 404 again
```

> "It's a 404 rather than a 403 on purpose — a 403 would confirm that serial
> exists in another range. The scoping is one function applied to every query
> after any user filters, so no combination of parameters widens it. Hiding the
> button was never the protection."

---

## 7. Off the spreadsheets · 45 s

On the Cameras page, **Export CSV** — point out it exports the *current filter*,
and that a range user's export contains only their range.

Then **Import** (admin only) → download the template, or upload a small file
with one good row and one bad one:

```csv
serial_number,model,range,beat
TE-CAM-100,PantheraCam S3,Chahala Range,Bakua Beat
TE-CAM-101,PantheraCam S3,Chahala Range,Joranda Beat
```

> "The second row names a beat from the other range, so it's rejected — but the
> first still imports. A 300-row spreadsheet with two bad rows imports 298 and
> tells you which two, by their spreadsheet row number. And re-uploading a
> corrected file skips what's already registered rather than duplicating it."

That is the optional extension I chose, because their data is in Google Sheets
today.

---

## 8. The checks · 45 s

```bash
cd backend && pytest -q          # 105 passed
./scripts/verify_api.sh          # 53 checks passed, 0 failed
```

> "The test-suite runs on SQLite so it needs no Docker or network, and the shell
> script drives the running API with curl — duplicate serials, bad range/beat
> combinations, unauthorised access, persistence and history."

---

## 9. Close · 20 s

> "It's a small, reliable implementation of the core workflow, plus CSV as the
> one extension. The engineering note has the trade-offs, what I assumed, what's
> missing, and what I'd change first — offline capture for beats with no signal,
> and rate limiting on login."

---

## Reset afterwards

```bash
cd backend && python -m app.seed --reset
```

## If something goes wrong mid-demo

| Symptom | Cause | Say / do |
|---|---|---|
| First request hangs ~50 s | Render free tier waking | Say so and keep talking; it's a known free-tier trade-off |
| "Could not reach the server" | Backend not running | `uvicorn app.main:app` |
| Login fails locally | Database not seeded | `python -m app.seed --reset` |
| Frontend 404 on refresh in prod | SPA rewrite | Already handled by `frontend/vercel.json` |
