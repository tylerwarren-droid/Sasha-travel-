#!/usr/bin/env bash
# CR 57 · THE AGAPI SANDBOX, END TO END — 10 partner calls with curl (+ the end user's two taps on their approval page).
# Starts the sandbox on a throwaway database, mints a test key, runs, prints each answer, stops. Test mode only, 0 live calls.
#   bash agapi_service/walkthrough.sh                     (from the repo root)
#   BASE=https://<preview> KEY=agk_test_… bash agapi_service/walkthrough.sh    (against a running sandbox instead)
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-backend/venv/bin/python}"; [ -x "$PY" ] || PY=python3
J() { "$PY" -c "import sys,json; d=json.load(sys.stdin); print(eval(sys.argv[1], {'d': d}))" "$1"; }
DAY="$("$PY" -c 'import datetime; print((datetime.date.today()+datetime.timedelta(days=35)).isoformat())')"

if [ -z "${BASE:-}" ]; then
  export AGAPI_DB="$(mktemp -d)/walkthrough.db" AGAPI_PUBLIC_URL="http://127.0.0.1:8787"
  BASE="$AGAPI_PUBLIC_URL"
  KEY="$("$PY" -m agapi_service.keys "Walkthrough Partner" | tail -1)"
  "$PY" -m uvicorn agapi_service.app:app --port 8787 --log-level warning >/tmp/agapi_walkthrough.log 2>&1 &
  SERVER=$!; trap 'kill $SERVER 2>/dev/null || true' EXIT
  for _ in $(seq 1 40); do curl -sf "$BASE/docs" >/dev/null && break; sleep 0.25; done
fi
H=(-H "Authorization: Bearer $KEY" -H "Content-Type: application/json")
post() { curl -s "${H[@]}" -H "Idempotency-Key: $(uuidgen 2>/dev/null || "$PY" -c 'import uuid;print(uuid.uuid4())')" -X POST "$BASE$1" -d "$2"; }
step() { printf '\n\033[1m%s\033[0m\n' "$1"; }

step "1 · find — flights Madrid → London on $DAY"
R=$(post /v1/find "{\"kind\":\"flights\",\"origin\":\"Madrid\",\"destination\":\"London\",\"date\":\"$DAY\",\"adults\":1}")
echo "$R" | J "[(r['title'], r['departs'][11:16], r['price']) for r in d['results'][:3]]"
OFFER=$(echo "$R" | J "d['results'][0]['offer_id']")

step "2 · hold — the read-back (nothing is sent)"
R=$(post /v1/holds "{\"offer_id\":\"$OFFER\"}")
echo "$R" | J "d['read_back']['lines']"; HOLD=$(echo "$R" | J "d['id']"); echo "read_back_sha256: $(echo "$R" | J "d['read_back_sha256']")"

step "3 · request_approval — 'Tap to approve' for the end user's phone (sandbox: a page, no SMS)"
R=$(post /v1/approvals "{\"hold_id\":\"$HOLD\",\"end_user\":{\"phone\":\"+34 600 000 012\"}}")
APR=$(echo "$R" | J "d['id']"); URL=$(echo "$R" | J "d['approve_url']"); echo "$R" | J "(d['status'], d['end_user'], d['expires_at'])"; echo "approve_url: $URL"

step "4 · book BEFORE the end user approved → refused"
post /v1/bookings "{\"hold_id\":\"$HOLD\",\"approval_id\":\"$APR\"}" | J "d['error']"

step "   (end user) opens the page and types a question — never a yes"
curl -s "$URL" >/dev/null
curl -s -X POST "$URL" --data-urlencode "decision=said" --data-urlencode "said=Yes — what are my cancellation terms?" | grep -o "That isn[^.]*\." || true
step "   (end user) taps Approve"
curl -s -X POST "$URL" -d "decision=approve" | grep -o "Approved[^<]*" || true

step "5 · book — with the end user's approval"
R=$(post /v1/bookings "{\"hold_id\":\"$HOLD\",\"approval_id\":\"$APR\"}")
echo "$R" | J "(d['status'], d['provider'], d['provider_ref'], d['payment'])"; BK=$(echo "$R" | J "d['id']")

step "6 · status"
curl -s "${H[@]}" "$BASE/v1/bookings/$BK" | J "(d['id'], d['status'])"

step "7 · proof — hash-chained events"
curl -s "${H[@]}" "$BASE/v1/bookings/$BK/proof" | J "([(e['seq'], e['type'], e['sha256'][:12]) for e in d['events']], 'chain_valid', d['chain_valid'])"

step "8 · hold the cancellation (its own read-back)"
R=$(post /v1/holds "{\"cancel_booking_id\":\"$BK\"}"); CH=$(echo "$R" | J "d['id']"); echo "$R" | J "d['read_back']['lines']"

step "9 · request_approval for the cancellation"
R=$(post /v1/approvals "{\"hold_id\":\"$CH\",\"end_user\":{\"phone\":\"+34 600 000 012\"}}"); CA=$(echo "$R" | J "d['id']"); CURL=$(echo "$R" | J "d['approve_url']")
step "   (end user) opens it and taps Approve"
curl -s "$CURL" >/dev/null; curl -s -X POST "$CURL" -d "decision=approve" | grep -o "Approved[^<]*" || true

step "10 · cancel — with that approval"
post "/v1/bookings/$BK/cancel" "{\"hold_id\":\"$CH\",\"approval_id\":\"$CA\"}" | J "(d['id'], d['status'])"

step "and: an outage is an outage (simulated Duffel down) — never 'no flights'"
curl -s "${H[@]}" -H "Idempotency-Key: outage-demo-$$" -H "AgAPI-Sandbox-Simulate: duffel_down" -X POST "$BASE/v1/find" \
  -d "{\"kind\":\"flights\",\"origin\":\"Madrid\",\"destination\":\"London\",\"date\":\"$DAY\"}" | J "d['error']"
step "usage today"
curl -s "${H[@]}" "$BASE/v1/usage" | J "d"
