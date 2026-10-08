# AgAPI sandbox (CR 57 → CR 58: AgAPI v1)

A private, **test-mode-only** implementation of **AgAPI v1** (EU 201 Parts 1–4, `1.0-draft.4`). The normative files are vendored in `spec/v1/`, copied from the AD repo's `docs/agapi/v1`, with checksums in `SHA256SUMS`. **The JSON wins over the prose.**

It is a separate small service. It reuses Sasha's own search code (`backend/booking_signer`, plus `scripts/duffel_fake` and `places_fake` on recorded fixtures) but **not** the agent loop. It makes **0 live calls**: every outbound connection is refused except to a registered webhook endpoint.

## Run

```
python -m unittest agapi_service.tests.test_vectors agapi_service.tests.test_service   # from the repo root
bash agapi_service/walkthrough.sh                                                       # local end-to-end
python -m agapi_service.admin key "Partner name"                                        # a key, printed ONCE
python -m uvicorn agapi_service.app:app --port 8787
```

The generated docs are served at `/docs`, `/openapi.json` (OpenAPI 3.1), `/mcp.json` (an MCP manifest) and `/collection.http`.

## What's implemented

- **Envelope** (Part 1 §1). `POST /v1/{operation}`, body = the input. Headers: `AgAPI-Version`, `AgAPI-Request-Id`, `Idempotency-Key` and `AgAPI-Approval-Id`. Every response is `{agapi, request_id, ok, result|error, replayed?, evidence_id?, trace}`.
- **Ids:** `<prefix>_<ULID>`.
- **Errors:** the 32 registry codes, with HTTP status, retryable and store_for_replay taken from `error-codes.json`.
- **All 14 operations** in `operations.json`. Inputs are validated against EU's JSON Schemas (`additionalProperties: false`).
- **Canonical JSON and hashes** (§4), including the §4.1 refusals.
- **ReadBack and Approval** with AP1–AP10, checked in the normative order (`rules.decide`). There is **no approve operation**. An Approval comes only from:
  - the key-less approval link (`/a/{token}`): GET presents the read-back and never approves; POST "Yes, go ahead" approves, with the CSRF token from the GET; single use, 15 minutes;
  - or, in test mode only, `sandbox.simulate_approval` (channel `sandbox_simulated`, in a separate turn).
- **Expiry** (Tyler): a read-back is approvable for 30 minutes after it's presented (15 for irreversible acts, AP4), and an Approval is usable for 15 minutes.
- **Idempotency** (§7): durable; claim → act → store; transient failures release the key and the Approval; `outcome_unknown` keeps the key in flight until `acts.status` resolves it; 24-hour retention.
- **Outages are never "no results":** coverage on every find, and `upstream_*` errors. Magic refs: `off_test_sold_out`, `off_test_timeout_before`, `off_test_timeout_after`, `off_test_price_jump` and `src_test_down`.
- **`untrusted_text`** on every fetched string: cleaned, capped, and flagged `instruction_like`, never removed.
- **Evidence** with `body_sha256`, plus `evidence.verify`.
- **Keys** `agp_test_` + 32 base62: shown once, stored as HMAC(pepper), the prefix displayed, scopes, at most 2 active.
- **End users:** destinations verified by one-time code (`/v/{token}`); sandbox destinations only; every message captured (`sandbox.messages`).
- **Webhooks:** ids and states only, `AgAPI-Signature`, at-least-once delivery with back-off for 24 hours.
- **Metering:** `cost_units` per class, no charge for replays or outages; monthly budget (402) and per-minute rate limit (429); `RateLimit-*` and `AgAPI-Budget-Remaining` headers; `usage.get`.
- **Payments:** `payment_link` is the only sandbox payment method (Stripe test, simulated, on `/pay/{token}`). **No real venue is ever contacted in test mode.**

## Stricter than the spec (reported to EU)

- **The explicit yes:** a question word or a request for options vetoes it (`rules.QUESTION_VETO`). Under the v1 lists alone, "Yes — what are my cancellation terms?" is a yes. All 26 vectors pass with or without the veto.

## Deploy (Railway service `agapi-sandbox`, Tyler's approval)

- Built from `agapi_service/Dockerfile` with the repo root as context. **The build runs the vectors and the tests.**
- Variables:
  - `AGAPI_KEY_PEPPER`, generated on Railway and never printed;
  - `AGAPI_DB=/data/sandbox.db` (a Railway volume at `/data`);
  - `AGAPI_PUBLIC_URL` (the service's domain).
- **No Sasha keys.**
