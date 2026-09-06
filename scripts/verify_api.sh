#!/usr/bin/env bash
#
# Reproducible API checks for the TerraEdge camera inventory.
#
# Every request below goes straight to the API with a bearer token - no
# browser, no UI. That is the point: the brief asks for proof that permissions
# are enforced in the backend, and that hiding an action in the interface is
# not what protects the data.
#
# Usage:
#   ./scripts/verify_api.sh                       # against http://127.0.0.1:8000
#   API=https://your-api.onrender.com ./scripts/verify_api.sh
#
# Requires: curl, jq. Expects the database to be seeded (python -m app.seed).
#
# NOTE: this script WRITES. It registers a handful of cameras prefixed `ZZ-` so
# they are obviously synthetic and sort below the seeded inventory. Run with
# CLEAN=1 to reseed the database afterwards and leave no trace:
#   CLEAN=1 ./scripts/verify_api.sh
#
# The password defaults below are the documented LOCAL demo values (see the
# README). Against a deployed instance, pass the real ones:
#   API=... ADMIN_PASSWORD=... RANGE_PASSWORD=... ./scripts/verify_api.sh

set -uo pipefail

API="${API:-http://127.0.0.1:8000}"

# A free-tier instance sleeps and cold-starts, so a single bare curl can fail
# outright and cascade into every later check. Retry transient failures and
# allow a generous first-byte window.
CURL=(curl -s --connect-timeout 15 --max-time 90 --retry 3 --retry-delay 2 --retry-all-errors)
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@similipal.test}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-demo-admin-123}"
RANGE_EMAIL="${RANGE_EMAIL:-chahala@similipal.test}"
RANGE_PASSWORD="${RANGE_PASSWORD:-demo-chahala-123}"

PASS=0
FAIL=0

green() { printf '\033[32m%s\033[0m' "$1"; }
red()   { printf '\033[31m%s\033[0m' "$1"; }
bold()  { printf '\033[1m%s\033[0m\n' "$1"; }

# check <description> <expected> <actual>
check() {
  local description="$1" expected="$2" actual="$3"
  if [[ "$actual" == "$expected" ]]; then
    printf '  %s %s (%s)\n' "$(green PASS)" "$description" "$actual"
    PASS=$((PASS + 1))
  else
    printf '  %s %s (expected %s, got %s)\n' "$(red FAIL)" "$description" "$expected" "$actual"
    FAIL=$((FAIL + 1))
  fi
}

# NOTE: always call these on a single line with the JSON payload already in a
# variable. A backslash line-continuation inside "$( ... )" mangles the
# argument and silently sends a different request.
#
# status <method> <path> <token> [json] -> HTTP status code
status() {
  local method="$1" path="$2" token="$3" payload="${4:-}"
  if [[ -n "$payload" ]]; then
    "${CURL[@]}" -o /dev/null -w '%{http_code}' -X "$method" "$API$path" -H "Authorization: Bearer $token" -H 'Content-Type: application/json' -d "$payload"
  else
    "${CURL[@]}" -o /dev/null -w '%{http_code}' -X "$method" "$API$path" -H "Authorization: Bearer $token"
  fi
}

# body <method> <path> <token> [json] -> response body
body() {
  local method="$1" path="$2" token="$3" payload="${4:-}"
  if [[ -n "$payload" ]]; then
    "${CURL[@]}" -X "$method" "$API$path" -H "Authorization: Bearer $token" -H 'Content-Type: application/json' -d "$payload"
  else
    "${CURL[@]}" -X "$method" "$API$path" -H "Authorization: Bearer $token"
  fi
}

login() {
  "${CURL[@]}" -X POST "$API/api/auth/login" -H 'Content-Type: application/json' -d "{\"email\":\"$1\",\"password\":\"$2\"}" | jq -r '.access_token // empty'
}

# Distinct prefixes: a substring search for one must not match the others.
STAMP=$(date +%s)
SERIAL="ZZ-VERIFY-$STAMP"
SERIAL_EXTRA="ZZ-EXTRA-$STAMP"
SERIAL_CSRF="ZZ-CSRFOK-$STAMP"

bold "TerraEdge API verification against $API"
echo

# ---------------------------------------------------------------------------
bold "1. Authentication"
# Wake a sleeping instance before timing anything.
"${CURL[@]}" -o /dev/null "$API/api/health" || true

check "unauthenticated read is rejected" 401 "$("${CURL[@]}" -o /dev/null -w '%{http_code}' "$API/api/cameras")"
check "forged token is rejected" 401 "$("${CURL[@]}" -o /dev/null -w '%{http_code}' "$API/api/cameras" -H 'Authorization: Bearer not-a-real-token')"

WRONG_LOGIN='{"email":"'"$ADMIN_EMAIL"'","password":"wrong-password"}'
check "wrong password is rejected" 401 "$("${CURL[@]}" -o /dev/null -w '%{http_code}' -X POST "$API/api/auth/login" -H 'Content-Type: application/json' -d "$WRONG_LOGIN")"

ADMIN_TOKEN=$(login "$ADMIN_EMAIL" "$ADMIN_PASSWORD")
RANGE_TOKEN=$(login "$RANGE_EMAIL" "$RANGE_PASSWORD")
if [[ -z "$ADMIN_TOKEN" || -z "$RANGE_TOKEN" ]]; then
  echo "$(red 'Could not sign in.') Is the API running and the database seeded?"
  exit 1
fi
check "admin can sign in" 200 "$(status GET /api/auth/me "$ADMIN_TOKEN")"
check "range user can sign in" 200 "$(status GET /api/auth/me "$RANGE_TOKEN")"
echo

# ---------------------------------------------------------------------------
bold "2. Reserve hierarchy"
RANGES=$(body GET /api/ranges "$ADMIN_TOKEN")
CHAHALA_ID=$(echo "$RANGES" | jq -r '.[] | select(.name=="Chahala Range") | .id')
NAWANA_ID=$(echo "$RANGES" | jq -r '.[] | select(.name=="Nawana Range") | .id')
BAKUA_ID=$(echo "$RANGES" | jq -r '.[] | select(.name=="Chahala Range") | .beats[0].id')
JORANDA_ID=$(echo "$RANGES" | jq -r '.[] | select(.name=="Nawana Range") | .beats[1].id')
echo "  Chahala=$CHAHALA_ID (beat $BAKUA_ID)   Nawana=$NAWANA_ID (beat $JORANDA_ID)"
echo

# ---------------------------------------------------------------------------
bold "3. Registration and unique serial numbers"
CREATED=$(body POST /api/cameras "$ADMIN_TOKEN" "{\"serial_number\":\"$SERIAL\"}")
CAMERA_ID=$(echo "$CREATED" | jq -r '.id')

check "admin registers a camera" 201 "$(status POST /api/cameras "$ADMIN_TOKEN" "{\"serial_number\":\"$SERIAL_EXTRA\"}")"
check "duplicate serial is rejected" 409 "$(status POST /api/cameras "$ADMIN_TOKEN" "{\"serial_number\":\"$SERIAL\"}")"

LOWER=$(echo "$SERIAL" | tr '[:upper:]' '[:lower:]')
check "the same serial in lower case is rejected" 409 "$(status POST /api/cameras "$ADMIN_TOKEN" "{\"serial_number\":\"$LOWER\"}")"
check "range user cannot register a camera" 403 "$(status POST /api/cameras "$RANGE_TOKEN" '{"serial_number":"TE-SHOULD-NOT-EXIST"}')"
echo

# ---------------------------------------------------------------------------
bold "4. Validation"
MISMATCHED_BEAT="{\"range_id\":$CHAHALA_ID,\"beat_id\":$JORANDA_ID}"
check "beat from another range is rejected" 422 "$(status POST "/api/cameras/$CAMERA_ID/transfer" "$ADMIN_TOKEN" "$MISMATCHED_BEAT")"

RANGE_ONLY="{\"range_id\":$CHAHALA_ID}"
check "allocation to a range without a beat is allowed" 200 "$(status POST "/api/cameras/$CAMERA_ID/transfer" "$ADMIN_TOKEN" "$RANGE_ONLY")"

check "out-of-bounds latitude is rejected" 422 "$(status PATCH "/api/cameras/$CAMERA_ID" "$ADMIN_TOKEN" '{"latitude":120,"longitude":86.3}')"
check "latitude without longitude is rejected" 422 "$(status PATCH "/api/cameras/$CAMERA_ID" "$ADMIN_TOKEN" '{"latitude":21.9}')"
check "deploying without full detail is rejected" 422 "$(status PATCH "/api/cameras/$CAMERA_ID" "$ADMIN_TOKEN" '{"status":"deployed"}')"
check "invalid phone number is rejected" 422 "$(status PATCH "/api/cameras/$CAMERA_ID" "$ADMIN_TOKEN" '{"contact_phone":"not a phone"}')"
echo

# ---------------------------------------------------------------------------
bold "5. Deployment and search"
SET_BEAT="{\"beat_id\":$BAKUA_ID}"
body PATCH "/api/cameras/$CAMERA_ID" "$ADMIN_TOKEN" "$SET_BEAT" > /dev/null

DEPLOY='{"status":"deployed","site_name":"Verification Ridge","latitude":21.9042,"longitude":86.3611,"contact_name":"Ranjan Mahanta","contact_phone":"+91 98110 20034"}'
check "camera is deployed with full detail" 200 "$(status PATCH "/api/cameras/$CAMERA_ID" "$ADMIN_TOKEN" "$DEPLOY")"

check "camera is findable by serial number" 1 "$(body GET "/api/cameras?search=$SERIAL" "$ADMIN_TOKEN" | jq -r '.total')"
check "camera is findable by site name" 1 "$(body GET "/api/cameras?search=Verification%20Ridge" "$ADMIN_TOKEN" | jq -r '.total')"
check "status is now deployed" "deployed" "$(body GET "/api/cameras/$CAMERA_ID" "$ADMIN_TOKEN" | jq -r '.status')"
echo

# ---------------------------------------------------------------------------
bold "6. Transfer preserves history"
TRANSFER="{\"range_id\":$NAWANA_ID,\"beat_id\":$JORANDA_ID,\"note\":\"Verification transfer\"}"
body POST "/api/cameras/$CAMERA_ID/transfer" "$ADMIN_TOKEN" "$TRANSFER" > /dev/null

DETAIL=$(body GET "/api/cameras/$CAMERA_ID" "$ADMIN_TOKEN")
check "current range is now Nawana" "Nawana Range" "$(echo "$DETAIL" | jq -r '.range_name')"
check "current beat is now Joranda" "Joranda Beat" "$(echo "$DETAIL" | jq -r '.beat_name')"

HISTORY=$(body GET "/api/cameras/$CAMERA_ID/history" "$ADMIN_TOKEN")
TRANSFER_ROW=$(echo "$HISTORY" | jq -c '[.[] | select(.change_type=="transferred")][0]')
check "previous deployment site is retained" "Verification Ridge" "$(echo "$TRANSFER_ROW" | jq -r '.from_site_name')"
check "previous range is retained" "Chahala Range" "$(echo "$TRANSFER_ROW" | jq -r '.from_range_name')"
check "previous coordinates are retained" "21.9042" "$(echo "$TRANSFER_ROW" | jq -r '.from_latitude')"
check "history records who made the change" "$ADMIN_EMAIL" "$(echo "$TRANSFER_ROW" | jq -r '.changed_by_email')"
check "history records the stated reason" "Verification transfer" "$(echo "$TRANSFER_ROW" | jq -r '.note')"
check "history records when" "true" "$(echo "$TRANSFER_ROW" | jq -r '.changed_at != null')"
check "the earlier deployment entry still exists" "Verification Ridge" "$(echo "$HISTORY" | jq -r '[.[] | select(.change_type=="deployed")][0].to_site_name')"
check "transfer did not duplicate the camera" 1 "$(body GET "/api/cameras?search=$SERIAL" "$ADMIN_TOKEN" | jq -r '.total')"
echo

# ---------------------------------------------------------------------------
bold "7. Range isolation, enforced in the backend"
# The camera now sits in Nawana; the signed-in range user belongs to Chahala.
check "range user cannot read another range's camera" 404 "$(status GET "/api/cameras/$CAMERA_ID" "$RANGE_TOKEN")"
check "range user cannot read its history" 404 "$(status GET "/api/cameras/$CAMERA_ID/history" "$RANGE_TOKEN")"
check "range user cannot modify it" 404 "$(status PATCH "/api/cameras/$CAMERA_ID" "$RANGE_TOKEN" '{"site_name":"Hijacked"}')"

PULL="{\"range_id\":$CHAHALA_ID,\"beat_id\":$BAKUA_ID}"
check "range user cannot pull it into their own range" 404 "$(status POST "/api/cameras/$CAMERA_ID/transfer" "$RANGE_TOKEN" "$PULL")"

check "filtering by another range returns nothing" 0 "$(body GET "/api/cameras?range_id=$NAWANA_ID" "$RANGE_TOKEN" | jq -r '.total')"
check "searching for it returns nothing" 0 "$(body GET "/api/cameras?search=$SERIAL" "$RANGE_TOKEN" | jq -r '.total')"
check "every visible camera is in the user's own range" 0 "$(body GET "/api/cameras?page_size=100" "$RANGE_TOKEN" | jq -r '[.items[] | select(.range_name != "Chahala Range")] | length')"
check "totals are scoped to the user's range" 0 "$(body GET /api/stats/summary "$RANGE_TOKEN" | jq -r '.in_stock')"

# The boundary is a boundary, not a blanket denial: inside their own range the
# user can do real work.
OWN_ID=$(body GET "/api/cameras" "$RANGE_TOKEN" | jq -r '.items[0].id')
check "range user can read their own range's camera" 200 "$(status GET "/api/cameras/$OWN_ID" "$RANGE_TOKEN")"
check "range user can update it" 200 "$(status PATCH "/api/cameras/$OWN_ID" "$RANGE_TOKEN" '{"notes":"Checked during verification"}')"

PUSH="{\"range_id\":$NAWANA_ID,\"beat_id\":$JORANDA_ID}"
check "range user cannot push it to another range" 403 "$(status POST "/api/cameras/$OWN_ID/transfer" "$RANGE_TOKEN" "$PUSH")"
check "range user cannot return it to stock" 403 "$(status POST "/api/cameras/$OWN_ID/transfer" "$RANGE_TOKEN" '{"range_id":null}')"
echo

# ---------------------------------------------------------------------------
bold "8. CSRF protection on cookie sessions"
COOKIE_JAR=$(mktemp)
LOGIN_BODY='{"email":"'"$ADMIN_EMAIL"'","password":"'"$ADMIN_PASSWORD"'"}'
"${CURL[@]}" -c "$COOKIE_JAR" -X POST "$API/api/auth/login" -H 'Content-Type: application/json' -d "$LOGIN_BODY" > /dev/null

ATTACK='{"serial_number":"TE-CSRF-ATTACK"}'
check "cookie write without a CSRF header is rejected" 403 "$("${CURL[@]}" -o /dev/null -w '%{http_code}' -b "$COOKIE_JAR" -X POST "$API/api/cameras" -H 'Content-Type: application/json' -d "$ATTACK")"
check "cookie write with a wrong CSRF header is rejected" 403 "$("${CURL[@]}" -o /dev/null -w '%{http_code}' -b "$COOKIE_JAR" -X POST "$API/api/cameras" -H 'Content-Type: application/json' -H 'X-CSRF-Token: wrong-value' -d "$ATTACK")"

CSRF=$(grep terraedge_csrf "$COOKIE_JAR" | awk '{print $7}')
GOOD="{\"serial_number\":\"$SERIAL_CSRF\"}"
check "cookie write with a matching CSRF header succeeds" 201 "$("${CURL[@]}" -o /dev/null -w '%{http_code}' -b "$COOKIE_JAR" -X POST "$API/api/cameras" -H 'Content-Type: application/json' -H "X-CSRF-Token: $CSRF" -d "$GOOD")"
rm -f "$COOKIE_JAR"
echo

# ---------------------------------------------------------------------------
bold "9. CSV export and import"
EXPORT=$("${CURL[@]}" "$API/api/cameras/export" -H "Authorization: Bearer $ADMIN_TOKEN")
check "export returns a CSV header row" "serial_number" "$(echo "$EXPORT" | head -1 | cut -d, -f1)"
check "export includes the verification camera" 1 "$(echo "$EXPORT" | grep -c "^$SERIAL,")"

RANGE_EXPORT=$("${CURL[@]}" "$API/api/cameras/export" -H "Authorization: Bearer $RANGE_TOKEN")
check "a range user's export excludes other ranges" 0 "$(echo "$RANGE_EXPORT" | grep -c ',Nawana Range,')"

IMPORT_CSV=$(printf 'serial_number,model,range,beat\nZZ-IMPORT-%s,PantheraCam S3,Chahala Range,Bakua Beat\nZZ-IMPBAD-%s,X,Chahala Range,Joranda Beat\n' "$STAMP" "$STAMP")
IMPORT_RESULT=$("${CURL[@]}" -X POST "$API/api/cameras/import" -H "Authorization: Bearer $ADMIN_TOKEN" -F "file=@-;filename=cameras.csv;type=text/csv" <<< "$IMPORT_CSV")
check "import registers the valid row" 1 "$(echo "$IMPORT_RESULT" | jq -r '.created_count')"
check "import reports the mismatched-beat row" 1 "$(echo "$IMPORT_RESULT" | jq -r '.error_count')"
check "the import error names the offending beat" "true" "$(echo "$IMPORT_RESULT" | jq -r '.errors[0].message | contains("Joranda Beat")')"

REIMPORT=$("${CURL[@]}" -X POST "$API/api/cameras/import" -H "Authorization: Bearer $ADMIN_TOKEN" -F "file=@-;filename=cameras.csv;type=text/csv" <<< "$IMPORT_CSV")
check "re-importing skips rather than duplicates" 1 "$(echo "$REIMPORT" | jq -r '.skipped_count')"
check "re-importing creates nothing" 0 "$(echo "$REIMPORT" | jq -r '.created_count')"

check "range user cannot import" 403 "$("${CURL[@]}" -o /dev/null -w '%{http_code}' -X POST "$API/api/cameras/import" -H "Authorization: Bearer $RANGE_TOKEN" -F "file=@-;filename=x.csv;type=text/csv" <<< 'serial_number
TE-NOPE-1')"
echo

# ---------------------------------------------------------------------------
bold "Summary"
if [[ $FAIL -eq 0 ]]; then
  printf '  %s checks passed, %s failed\n' "$(green "$PASS")" "$(green 0)"
else
  printf '  %s checks passed, %s failed\n' "$(green "$PASS")" "$(red "$FAIL")"
fi
echo

if [[ "${CLEAN:-0}" == "1" && "$API" != *"127.0.0.1"* && "$API" != *"localhost"* ]]; then
  # The seed script reads its own .env, which points at the local database -
  # running it here would wipe the wrong one and leave the remote untouched.
  echo "  CLEAN=1 ignored: it reseeds the LOCAL database, and this run targeted"
  echo "  $API. Reseed that deployment explicitly with its own DATABASE_URL."
elif [[ "${CLEAN:-0}" == "1" ]]; then
  echo "  Cleaning up: restoring the seeded database..."
  (cd "$(dirname "$0")/../backend" && ./.venv/bin/python -m app.seed --reset > /dev/null)
  echo "  Done - the inventory is back to its seeded 24 cameras."
else
  echo "  This run left synthetic ZZ-* cameras in the database."
  echo "  Remove them with:  cd backend && python -m app.seed --reset"
  echo "  Or re-run as:      CLEAN=1 ./scripts/verify_api.sh"
fi

[[ $FAIL -eq 0 ]]
