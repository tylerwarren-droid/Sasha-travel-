# AgAPI sandbox service (CR 57)

A private, **test-mode-only** AgAPI that a VC or a first partner can call:

**find → hold → request_approval → (the end user approves on their phone) → book → status → proof → cancel**

It is a separate small service. It reuses Sasha's engines from `backend/`:
- Duffel search and order: `booking_signer.travel`;
- venue and stay search: `booking_signer.venue_read`;
- canonical JSON: `booking_signer.canonical`.

It does **not** use the agent loop or any Sasha service.

**What stays out of the real world:**
- Searches answer from recorded fixtures: `backend/scripts/duffel_fake.py` (Duffel TEST, recorded 7 Oct 2026) and `places_fake.py` (fictional places).
- Payments are simulated (Stripe test, shown as `mode: "simulated"`).
- Venues are never contacted.
- **Every outbound connection is refused** in-process (`providers.block_network`), so there are 0 live calls.

## Run it locally

```
cd ~/Developer/Sasha-travel-cr52                     # the repo root (branch cr/agapi-api)
bash agapi_service/walkthrough.sh                     # starts it, mints a key, runs the 10 calls, stops
python -m unittest agapi_service.tests.test_sandbox   # 23 tests (+1 waiting for EU 201 Part 3)
```

To run it by hand:
- `python -m agapi_service.keys "Partner name"` prints a key once; it is stored hashed.
- `python -m uvicorn agapi_service.app:app --port 8787`
- The docs are at `http://127.0.0.1:8787/docs`.

## Endpoints (draft v1, tracking EU 201)

| | |
|---|---|
| `POST /v1/find` | flights · venues · stays → offers; fetched text as `{untrusted, text, source}` |
| `POST /v1/holds` | the read-back (lines + facts) and its `read_back_sha256`; nothing sent. Also `{cancel_booking_id}` |
| `POST /v1/approvals` | request_approval → an Approval + `approve_url` (sandbox: a page, no SMS) |
| `GET /v1/approvals/{id}` | pending · approved · declined · expired · void · consumed |
| `POST /v1/bookings` | book `{hold_id, approval_id}` |
| `POST /v1/bookings/{id}/cancel` | cancel `{hold_id, approval_id}` (the cancellation's own hold and approval) |
| `GET /v1/bookings/{id}` | status (written only from proof) |
| `GET /v1/bookings/{id}/proof` | the hash-chained events + `chain_valid` |
| `GET /v1/usage` | today's calls and finds against the key's budget |
| `POST /v1/sandbox/bookings/{id}/venue_reply` | simulate a venue's answer (untrusted data) |

## The rules (enforced in code, tested)

- **Keys:** `agk_test_<id>_<secret>`. Only an HMAC (with the server's pepper) is stored, and live keys are refused.
- **The Approval**, the draft of EU 200 §2, replaced by EU 201 Part 1 when it lands. Booking and cancelling need an Approval that:
  - was given **by the end user on their own device** (the approval page), never by an API key;
  - came **after the read-back was shown** (`presented_at` ≤ `decided_at`);
  - is for **exactly that read-back** (its sha256; a change voids it);
  - is **unexpired** (15 min) and **unused** (one approval = one action, consumed atomically).

  A typed answer counts only if it is a plain yes. **A question is never a yes:** "Yes — what are my cancellation terms?" is refused (CR 56).
- **Idempotency:** durable, per key. The same `Idempotency-Key` with the same body returns the first answer, even after a restart; a different body returns 409. An outage is never cached.
- **Outages:** `503 {type: "unavailable", code: "duffel_unreachable" | "places_unreachable", retryable: true}`, never "no results".
  - An outage while booking hands the approval back unused.
  - Simulate one with `AgAPI-Sandbox-Simulate: duffel_down | places_down`.
- **Metering:** per key, per UTC day (calls and finds). Over budget returns `429 daily_budget_reached`.
- **Proof:** Pacioli is the only writer of a booking's status. Each event's sha256 covers the previous one.

## Deploying (only on Tyler's word, as a NEW Railway service; never Sasha's)

- **Root:** the repo, so `backend/` is importable.
- **Start:** `python -m uvicorn agapi_service.app:app --host 0.0.0.0 --port $PORT`.
- **Requirements:** `backend/requirements.txt`; nothing else is needed.
- **Environment:**
  - `AGAPI_KEY_PEPPER` (required when deployed; the service refuses to start without it);
  - `AGAPI_PUBLIC_URL` (for the approval links);
  - `AGAPI_DB` (a path on a Railway volume; Postgres when it outgrows SQLite).
- **No** Sasha secrets: no Duffel, Places, Stripe or Anthropic keys are needed or used.

## Waiting on EU's spec (tab_messages "EU 201")

- **Part 1, the Approval object:** replace the draft fields and states in `core.py` with EU's exactly.
- **Part 2, the endpoints, the request and response schemas, and the error-code registry:** rename or reshape to match, and generate the docs from EU's schema.
- **Part 3, the conformance vectors:** canonical JSON → sha256, and approval valid / void / expired / same-turn. They go into `tests/test_sandbox.py · ConformanceVectors`, which is skipped until they're posted.
