# AgAPI v1 · Part 4: the API product surface (the private sandbox)

*EU 201 Part 4 · 8 Oct 2026 · **v1.0 FINAL (frozen 8 Oct 2026, EU 205)**.*

**The normative files:**
- `schemas/product/product.schema.json` (API key, end user, usage, webhook event, the sandbox operations);
- `operations.json` (+7 product operations: `users.register`, `users.verify_destination`, `usage.get`,
  `webhooks.register`, `webhooks.revoke`, `sandbox.simulate_approval`, `sandbox.messages`);
- `schemas/approval.schema.json` (+ the `sandbox_simulated` channel);
- `vectors/evidence.json`, `vectors/webhook-signature.json`.

**Checks:**
- 8 schemas valid against the 2020-12 meta-schema; every operation reference and error code resolves.
- **The webhook HMAC vector is identical in Python and Node.**

## 1. Customers and API keys

| Rule | |
|---|---|
| **K1. The model** | an **account** (`acct_`) per customer; **API keys** (`key_`) belong to an account and carry its **mode**: `agp_test_…` or `agp_live_…` (32 base62 after the prefix) |
| **K2. Secrets** | the full key is **shown once** at creation and stored **only as HMAC-SHA256(server pepper, key)**. Logs and dashboards show `prefix` (the first 6 characters) only. A key never goes in a URL |
| **K3. Auth** | `Authorization: Bearer agp_…`. The key resolves the **account** and the **mode**. Neither is ever taken from the request (Part 1 §1.1). Revoked or unknown → `unauthenticated` |
| **K4. Scopes** | `scopes: ["travel.*", "trip.complete", …]`. Calling outside them → `forbidden` |
| **K5. Rotation** | up to **2 active keys** per account per mode, so a customer can rotate without downtime; revocation is immediate |
| **K6. Issuing (private sandbox)** | keys are **issued by Kanoe by hand** to named partners; no self-serve signup in the private phase |
| **K7. What a key can never do** | create or forge an **Approval** (Part 1 AP5). The approval surface (§3) is a separate, key-less endpoint |

## 2. End users
- **Registering:** `users.register` (idempotent) registers the customer's end user with an `external_ref` and
  destinations (SMS, WhatsApp, email).
- **Verified destinations only:** AgAPI **verifies possession** of each destination by a one-time code before presenting
  an approval there (`verified: true`). An approval link is only ever sent to a verified destination.
- **Two ways to verify (v1.0, CR 59 finding 5):** the key-less code page (the default), **or**
  `users.verify_destination {end_user_id, channel, value, code}` → `end_user`, where the partner's own app relays the
  6-digit code AgAPI sent. 10-minute codes, 5 attempts per code; `destination_code_invalid` (422, attempts left in
  `details`) / `destination_code_expired` (409). **The code is always generated and sent by AgAPI**; a partner can
  relay it, never choose it, so a key alone still can't mark a destination verified.
- **SDK devices:** an Ed25519 key pair is generated **on the device**; only the public key is registered.
- **Minimal data:** AgAPI stores no end-user profile beyond what approvals need.

## 3. The approval surface (key-less)

### 3.1 The link channels (SMS / WhatsApp / email)
- `approvals.request` sends a **single-use, 15-minute** link: `https://approve.agapi…/a/{token}`. The token is opaque,
  ≥ 128 bits, stored hashed, and bound to `read_back_id` + `presented_to` + the destination.
- **`GET` the link:**
  - renders the read-back lines **exactly** (the `read_back_sha256` lines);
  - **records the presentation event** (`presented_at`, `presented_turn_id`);
  - never approves.
- **`POST` (the "Yes, go ahead" button)** creates the Approval (`method: tap`, `device.channel: link`):
  - a **separate action** after the GET (AP3);
  - with a CSRF token issued by the GET;
  - the token is consumed.
- **The button only.** A link preview or unfurler (the GET) can never approve.

### 3.2 The SDK
The customer's app shows the read-back with the SDK component. The device **signs**
`{approval_id, read_back_sha256, payload_sha256, approved_at}` with its registered key, giving `device.attestation`
(AP5).

### 3.3 Sasha (first party)
Its authenticated user session plus the turn ids (`sasha_voice` / `sasha_chat`). AP3 and AP6 are applied to `said`.

## 4. Webhooks

| Rule | |
|---|---|
| **W0. Endpoints (v1.0, CR 59 finding 5)** | `webhooks.register {url, events?}` → `{endpoint_id (whe_), url, secret (whsec_, **shown once**), created_at, events}`; `webhooks.revoke {endpoint_id}`. **https only**; the URL is refused after DNS resolution if it points at a loopback, private (RFC 1918 / RFC 4193), link-local or cloud-metadata address, **re-checked at each delivery** (DNS rebinding) → `webhook_url_refused`. **At most 2 active endpoints per account and mode**, which is how a secret is rotated (register the new, move, revoke the old) → `webhook_limit_reached`. The secret is stored as an HMAC, like keys (K2) |
| **W1. Events** | `approval.presented` · `approval.given` · `approval.expired` · `approval.void` · `act.confirmed` (booked) · `act.awaiting_payment` · `act.refused` · `act.failed` · `act.unknown` · `act.cancelled` |
| **W2. Payload** (`webhook_event`) | `{webhook_id, event, created_at, account, mode, data}`. **`data` holds ids and states only** (`intent_id`, `act_id`, `approval_id`, `evidence_id`, `outcome_kind`, `reference`, `void_reason`). **No personal data, no upstream text**: the customer fetches details with its key. The schema refuses extra fields |
| **W3. Signature** | the header `AgAPI-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(endpoint secret, "<t>.<raw body>")>`. Receivers **must**: compute over the **raw** body; compare in constant time; **reject if `t` is more than 5 minutes old** (vector W-3). The endpoint secret `whsec_…` is shown once; two secrets may be active during rotation |
| **W4. Delivery** | **at least once**; deduplicate on `webhook_id`; **no ordering guarantee** (use `created_at` and `acts.status` for truth); retries with exponential back-off for 24 h, then marked failed and visible in the dashboard |
| **W5. Source of truth** | a webhook is a **notification**, not proof. "Booked" is stated only from `acts.status` / the Evidence (`CONFIRMED`) |
| **W6. Mode** | test keys receive test events only, flagged `mode: test` |

## 5. Test vs live

| | `agp_test_` (**the sandbox, now**) | `agp_live_` |
|---|---|---|
| Upstreams | Duffel **test**, Stripe **test**, **fixture** stays / venues / schools; **no real venue sends, ever** (EU 200 R13) | real |
| Money | Stripe test only | real |
| End users | sandbox destinations only (`+1 500 555 0xxx` numbers, `@example.test`); every message is **captured**, never sent, readable via `sandbox.messages` | verified real destinations |
| Approvals | the real approval surface **or** `sandbox.simulate_approval` (test only), which creates an Approval with `device.channel: sandbox_simulated` **after a simulated separate turn**. AP1–AP9 still apply. **A `sandbox_simulated` Approval is invalid in live** (`approval_untrusted_origin`) | the real surface only |
| Forcing outcomes | **magic refs:** `off_test_sold_out` → `upstream_refused` · `off_test_timeout_before` → `upstream_timeout` · `off_test_timeout_after` → `outcome_unknown` · `off_test_price_jump` → the next hold's price changes, so `approval_void: payload_changed` · `src_test_down` (any find) → `upstream_unreachable` for that source | none |
| Availability | issued to private partners | **`mode_not_available`** until Tyler opens live |

## 6. Metering and budgets

| Field / rule | |
|---|---|
| **M1.** Every response's `trace.cost_units`; every request writes a **`usage_record`**: `request_id`, `key_id`, `account`, `mode`, `operation`, `cost_class`, `cost_units`, `replayed`, `ok`, `error_code`, `at` | |
| **M2. Cost classes** (`operations.json` `cost_class`) | `free` 0 · `read` 0 · `search` 1 · `message` 1 · `act_prepare` 2 · `act` 5. **Placeholder units; prices are Tyler's** |
| **M3. No charge for** | replays (I9), errors in categories request/auth/limits/idempotency/internal, and `upstream_*` failures. **Charged:** ok results, and `upstream_refused` on act classes (the provider was reached and answered) |
| **M4. Budgets** | per key, per month (`budget.cost_units`); over budget → **402 `budget_exhausted`**; a webhook-free email to the account at 80% (private phase: by hand) |
| **M5. Rate limits** | per key per minute; **429 `rate_limited`** with `Retry-After`; headers `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset` on every response, plus `AgAPI-Budget-Remaining` |
| **M6.** `usage.get(from, to)` → totals by operation + the remaining budget | |
| **M7. Test-mode units** | metered and reported, **never billed** |

## 7. Docs for partners
- **Generated, never hand-written:**
  - **OpenAPI 3.1** from `operations.json` + the schemas (as `docs/ad/checks-api-v1.openapi.yaml` was built and
    linted);
  - an **MCP manifest** from the same table (`schema_for_model`: envelope fields hidden);
  - a **Postman/HTTP collection** of the sandbox flow.
- **The sandbox walkthrough** (the doc's first page):
  1. `travel.find_flights`
  2. `trip.hold` → a read-back
  3. `approvals.request` (channel `link_sms` to `+15005550006`)
  4. `sandbox.messages` (shows the link)
  5. `sandbox.simulate_approval("Yes, book it.")`
  6. `trip.complete` with the `approval_id`
  7. `acts.status` → `CONFIRMED`
  8. `evidence.get` + `evidence.verify`
  9. the `act.confirmed` webhook

## Status of Part 4 (v1.0 FINAL)

| Item | Status |
|---|---|
| Keys, scopes, rotation, auth (§1) | **frozen** |
| End users, verified destinations (code page or `users.verify_destination`), SDK devices (§2) | **frozen** (the SDK component is to be built) |
| The approval surface: link GET/POST semantics, SDK signing (§3) | **frozen** |
| Webhooks: endpoints (`webhooks.register` / `revoke`), events, payload, signature, delivery (§4) | **frozen**; the signature vector is proven in Python and Node |
| Test/live, magic refs, simulate (§5) | **frozen** for the sandbox |
| Metering fields and rules (§6) | **frozen** as fields; **the unit values are placeholders** (prices come later) |
| Evidence `body_sha256` vectors (EV-1 valid, EV-2 tampered) | **frozen** |

**Freeze conditions, met:** CR's sandbox passes every vector (CR 59, tab_messages #565); Tyler answered Parts 1–3.
**Sasha's conformance** is listed in `03-conformance.md` §5 and runs after the freeze; a failure there is Sasha's bug,
not a reason to change 1.0.

**Decided (Tyler):** Duffel **test** and Stripe **test** (Kanoe's accounts) are the sandbox upstreams.
**Later, by Tyler:** prices and the unit values; the first private partners and their budgets; when live mode opens
(a DPA and partner terms, real-destination verification, payment flows, AD's beta first).
