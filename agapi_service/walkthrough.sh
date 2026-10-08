#!/usr/bin/env bash
# CR 58 · THE AGAPI v1 SANDBOX, END TO END (Part 4 §7's walkthrough + the safety beats) — partner calls with curl, and the end
# user's own steps (enter the code, open the link, tap "Yes, go ahead", pay) on the key-less pages. Test mode only.
#   bash agapi_service/walkthrough.sh                                   (local: starts a throwaway sandbox, mints a key, stops)
#   BASE=https://… KEY=agp_test_… bash agapi_service/walkthrough.sh     (against a running sandbox — the key never printed)
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-backend/venv/bin/python}"; [ -x "$PY" ] || PY=python3
J() { "$PY" -c "import sys,json; d=json.load(sys.stdin); print(eval(sys.argv[1], {'d': d}))" "$1"; }
DAY="$("$PY" -c 'import datetime; print((datetime.date.today()+datetime.timedelta(days=35)).isoformat())')"
RUN="$("$PY" -c 'import secrets; print(secrets.token_hex(4))')"

if [ -z "${BASE:-}" ]; then
  export AGAPI_DB="$(mktemp -d)/walkthrough.db" AGAPI_PUBLIC_URL="http://127.0.0.1:8787"
  BASE="$AGAPI_PUBLIC_URL"
  KEY="$("$PY" -m agapi_service.admin key "Walkthrough Partner" | tail -1)"
  "$PY" -m uvicorn agapi_service.app:app --port 8787 --log-level warning >/tmp/agapi_walkthrough.log 2>&1 &
  SERVER=$!; trap 'kill $SERVER 2>/dev/null || true' EXIT
  for _ in $(seq 1 60); do curl -sf "$BASE/health" >/dev/null && break; sleep 0.25; done
fi
N=0
call() {  # call <operation> <json> [approval_id]  — Austen ops get a fresh Idempotency-Key
  N=$((N+1))
  local extra=(); [ -n "${3:-}" ] && extra=(-H "AgAPI-Approval-Id: $3")
  curl -s -X POST "$BASE/v1/$1" -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
       -H "Idempotency-Key: walk-$RUN-$RANDOM$RANDOM$RANDOM-x" ${extra[@]+"${extra[@]}"} -d "$2"
}
path() { echo "/${1#*://*/}"; }
step() { printf '\n\033[1m%s\033[0m\n' "$1"; }

step "1 · users.register — the end user, with a sandbox destination (+1 500 555 0xxx)"
R=$(call users.register "{\"external_ref\":\"walk-$RUN\",\"destinations\":[{\"channel\":\"sms\",\"value\":\"+15005550006\"}]}")
echo "$R" | J "(d['ok'], d['result']['end_user_id'], d['result']['destinations'])"; USR=$(echo "$R" | J "d['result']['end_user_id']")

step "2 · sandbox.messages — the verification code (captured, never sent)"
R=$(call sandbox.messages "{\"end_user_id\":\"$USR\"}"); MSG=$(echo "$R" | J "[m['body'] for m in d['result']['messages']][-1]"); echo "$MSG"
CODE=$(echo "$MSG" | sed -E 's/.*code is ([0-9]{6}).*/\1/'); VLINK=$(echo "$MSG" | grep -oE 'https?://[^ ]+/v/[^ ]+')
step "   (end user) enters the code"; curl -s -X POST "$BASE$(path "$VLINK")" -d "code=$CODE" | grep -o "Thank you[^<]*" || true

step "3 · travel.find_flights — Madrid → London, $DAY"
R=$(call travel.find_flights "{\"origin\":{\"query\":\"Madrid\"},\"destination\":{\"query\":\"London\"},\"date\":\"$DAY\",\"passengers\":1}")
echo "$R" | J "([(o['carrier']['name']['text'], o['flight_numbers'], o['departs'], o['price']) for o in d['result']['offers'][:3]], 'coverage', d['result']['coverage'])"
OFFER=$(echo "$R" | J "d['result']['offers'][0]['offer_ref']")

step "4 · trip.hold — the read-back (nothing is sent)"
R=$(call trip.hold "{\"end_user\":\"$USR\",\"items\":[{\"kind\":\"flight\",\"ref\":\"$OFFER\"}],\"travellers\":[{\"given_name\":\"Ana\",\"family_name\":\"Ejemplo\",\"born_on\":\"1990-01-01\",\"title\":\"ms\"}]}")
echo "$R" | J "d['result']['read_back']['lines']"; HOLD=$(echo "$R" | J "d['result']['hold_id']"); RB=$(echo "$R" | J "d['result']['read_back']['read_back_id']")
echo "read_back_sha256: $(echo "$R" | J "d['result']['read_back']['read_back_sha256']")"

step "5 · trip.complete WITHOUT an Approval → approval_required (with the lines to show)"
call trip.complete "{\"hold_id\":\"$HOLD\"}" | J "(d['error']['code'], d['error']['details']['read_back_id'])"

step "6 · approvals.request — a 'Tap to approve' link by SMS (captured)"
call approvals.request "{\"read_back_id\":\"$RB\",\"channel\":\"link_sms\"}" | J "d['result']['presentation']"

step "7 · sandbox.messages — the approval link"
LINK=$(call sandbox.messages "{\"end_user_id\":\"$USR\"}" | J "[m['approval_link'] for m in d['result']['messages'] if m.get('approval_link')][-1]"); echo "$LINK"

step "   (end user) opens the link — the read-back is PRESENTED (a GET never approves)"
curl -s "$BASE$(path "$LINK")" | grep -oE "Approve this\?" | head -1
step "   a question is never a yes: sandbox.simulate_approval(\"Yes — what are my cancellation terms?\")"
call sandbox.simulate_approval "{\"read_back_id\":\"$RB\",\"said\":\"Yes — what are my cancellation terms?\"}" | J "d['error']['code']"
step "8 · sandbox.simulate_approval(\"Yes, book it.\") — stands in for the tap, in a separate turn (Part 4 §5)"
R=$(call sandbox.simulate_approval "{\"read_back_id\":\"$RB\",\"said\":\"Yes, book it.\"}"); echo "$R" | J "d.get('result') or d['error']"
APV=$(echo "$R" | J "d['result']['approval_id']")

step "9 · trip.complete — with the end user's Approval → AWAITING_PAYMENT (payment_link: the only sandbox method)"
R=$(call trip.complete "{\"hold_id\":\"$HOLD\",\"payment\":{\"method\":\"payment_link\"}}" "$APV")
echo "$R" | J "(d['ok'], d['result']['outcome']['kind'], d['result']['act_id'])"; ACT=$(echo "$R" | J "d['result']['act_id']")
EVD=$(echo "$R" | J "d['result']['evidence_id']"); PAY=$(echo "$R" | J "d['result']['outcome']['payment_url']")
step "   (end user) pays on the payment link (Stripe test, simulated)"; curl -s -X POST "$BASE$(path "$PAY")" | grep -oE "Booked[^<]*" | head -1

step "10 · acts.status → CONFIRMED (\"booked\" is said only from here)"
call acts.status "{\"act_id\":\"$ACT\"}" | J "d['result']['acts'][0]['outcome']"

step "11 · evidence.get + evidence.verify (the approval, its hashes and the person's own words)"
EV=$(call evidence.get "{\"evidence_id\":\"$EVD\"}"); echo "$EV" | J "(d['result']['outcome']['kind'], d['result']['approval'])"
BODY=$(echo "$EV" | "$PY" -c 'import sys,json; print(json.dumps({"evidence": json.load(sys.stdin)["result"]}))')
call evidence.verify "$BODY" | J "d['result']"

step "12 · trip.cancel — its own read-back (approval_required) → its own Approval → cancelled"
R=$(call trip.cancel "{\"act_id\":\"$ACT\"}"); echo "$R" | J "(d['error']['code'], d['error']['details']['read_back']['lines'])"
CRB=$(echo "$R" | J "d['error']['details']['read_back_id']")
CAPV=$(call sandbox.simulate_approval "{\"read_back_id\":\"$CRB\",\"said\":\"Yes, go ahead.\"}" | J "d['result']['approval_id']")
call trip.cancel "{\"act_id\":\"$ACT\"}" "$CAPV" | J "(d['result']['outcome']['kind'], d['result']['outcome']['reference'], d['result']['refund'])"

step "and: an outage is an outage (src_test_down) — never 'no results'"
call venues.find_venues "{\"what\":\"dinner\",\"where\":{\"query\":\"src_test_down\"}}" | J "d['error']"
step "usage.get"
call usage.get "{\"from\":\"2026-01-01T00:00:00Z\",\"to\":\"2099-01-01T00:00:00Z\"}" | J "(d['result']['total_cost_units'], d['result']['budget_remaining'])"
