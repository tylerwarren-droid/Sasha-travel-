# AgAPI v1 · Part 1: the core contract

*EU 201 Part 1 · 8 Oct 2026 · **v1.0 FINAL (frozen 8 Oct 2026, EU 205)**. Additive-only from here (§3). Language-neutral: TypeScript (AD) and Python (Sasha, the CR sandbox)
implement it; neither is the reference. The machine-readable parts are in `schemas/` and `error-codes.json`; where
they and this text disagree, **the schema wins** and the text is a bug.*

**Read with:**
- `docs/ad/agapi-convergence.md` (EU 200; the design this implements);
- `docs/ad/checks-api-v1.md` (AD's domain contract, which becomes the `checks.*` operations);
- `backend/agapi/v0.py` (Sasha v0, which v1 supersedes).

**Contents:**
1. Envelope
2. Identifiers
3. Versioning
4. Canonical JSON and hashes
5. The error-code registry
6. Read-back and Approval
7. Idempotency

The status table is at the end.

---

## 1. The envelope

### 1.1 Request
**Transport-neutral form:**

```jsonc
{
  "agapi": "1.0",                         // the contract version the caller speaks (§3)
  "operation": "travel.book",             // <domain>.<verb>, from the operation table (Part 2)
  "request_id": "req_01J…",               // optional; the server assigns one if absent and always echoes it
  "idempotency_key": "…",                 // REQUIRED on every Austen operation (§7); optional elsewhere
  "approval_id": "apv_01J…",              // REQUIRED on every Austen operation that acts (§6)
  "input": { … }                          // the operation's input; additionalProperties: false
}
```

**Over HTTP:**
- `POST /v1/{operation}`, body = `input`.
- `agapi`, `request_id`, `idempotency_key` and `approval_id` travel as the headers `AgAPI-Version`, `AgAPI-Request-Id`,
  `Idempotency-Key` and `AgAPI-Approval-Id`.
- **The account, principal and mode are never in the request.** They come from authentication (Part 4: the API key
  ⇒ account + mode).

### 1.2 Response
Always this shape, **including errors**, with every HTTP status (§5.2):

```jsonc
// success
{ "agapi": "1.0", "request_id": "req_01J…", "ok": true, "result": { … },
  "replayed": true,                       // present only on an idempotent replay (§7)
  "evidence_id": "evd_01J…",              // present when the operation produced Pacioli evidence (Part 2)
  "trace": { "operation": "travel.book", "agent": "austen", "ms": 412, "upstream": [ { "service": "duffel", "ms": 380, "ok": true } ], "cost_units": 5 } }

// error
{ "agapi": "1.0", "request_id": "req_01J…", "ok": false,
  "error": { "code": "upstream_unreachable", "message": "…", "retryable": true, "retry_after_s": 30,
             "details": { "service": "google_places" } } }
```

**Rules:**
- **E1. `call()` never throws** (in-process) **and never returns a non-envelope body** (HTTP). A runtime failure is
  `internal`, or `outcome_unknown` (§5).
- **E2. `message`** is one sentence a person can read. It never contains a secret, a stack trace or an upstream body.
- **E3. `details`** is machine-readable and code-specific (`error-codes.json` → `details_schema`).
- **E4. Unknown response fields** must be ignored by callers. Unknown **request** fields are refused (`invalid_input`).

## 2. Identifiers

- **Form:** every id is `<prefix>_<ULID>` (26 Crockford base32 characters, time-sortable, opaque).
- **Rules:** callers must not parse beyond the prefix, and ids are never reused.

| Prefix | Object |
|---|---|
| `req_` | one inbound request |
| `int_` | an Intent (what an Austen act will do) |
| `rb_` | a ReadBack (what the end user is shown) |
| `apv_` | an Approval |
| `hold_` | a hold or quote |
| `act_` | a completed act (a booking, a submission, a cancellation) |
| `evd_` | Pacioli evidence |
| `acct_` | a customer account |
| `usr_` | an end user (the customer's user) |
| `key_` | an API key (Part 4) |
| `whk_` | a webhook delivery (Part 4) |
| `whe_` | a webhook endpoint (Part 4 `webhooks.register`, v1.0) |
| `rpl_` | a reply to a message Sasha/AgAPI sent (v1.1, `messages.replies`) |

## 3. Versioning

- **The contract version is `MAJOR.MINOR`** (`agapi` / `AgAPI-Version`). The server answers in the version requested
  if it supports it, else `version_unsupported`.
- **A minor version is additive only:** new operations, new optional input fields, new response fields, **new error
  codes** (callers treat an unknown code by its `retryable` flag and HTTP status). **Never** in a minor version:
  removing or renaming anything, changing a type, making an optional input required, or changing a code's meaning.
- **A major version** may break. v1 and v2 run side by side until every caller has moved.
- **Drafts:** `1.0-draft.1`–`draft.4` were mutable. **`1.0` was frozen on 8 Oct 2026 (EU 205)**, after CR's sandbox
  passed every vector (CR 59). Changes from here are 1.x additions only; the changelog is in `README.md`.

## 4. Canonical JSON and hashes

Every hash in AgAPI is `sha256(canonical(value))`, as lowercase hex, prefixed in fields as `sha256:<64 hex>`.

### 4.1 `canonical(value)`: RFC 8785 (JCS), restricted
- **Objects:**
  - keys sorted by UTF-16 code units;
  - no whitespace;
  - **keys must be ASCII `[a-z0-9_]`**. This makes UTF-16 order = code-point order = byte order, so Python's
    `sort_keys` and JavaScript's `.sort()` agree.
- **Arrays:** order preserved.
- **Strings:**
  - valid Unicode only (**a lone surrogate is refused**);
  - escaped as JSON does minimally (`\"`, `\\`, `\b \f \n \r \t`, other U+0000–U+001F as `\u00XX`);
  - **everything else is emitted raw as UTF-8** (Python: `ensure_ascii=False`).
- **Numbers:** **integer-valued only, |n| ≤ 2^53 − 1.** An integer-valued number written with a fraction or exponent (`1.0`, `1e3`, `-0.0`) is **normalised to the integer** (`1`, `1000`, `0`), because a JavaScript runtime can't tell `1.0` from `1` after parsing. **A number with a fractional part is refused** in hashed values (Part 3 vectors C-7, C-R1). Money is
  `{ "amount_minor": 12345, "currency": "EUR" }`; scores and ratios are strings (`"0.91"`) or integers per mille.
  ⚠ Why: the float formatting of Python's `repr` and ES `Number.prototype.toString` differ on some values. Forbidding
  floats is cheaper than proving equality.
- **`true` / `false` / `null`** as literals. **Absent ≠ null:** an optional field that's absent is omitted, never
  serialised as `null`, and a field set to null stays `null`.
- **Refused (an error, never coerced):** NaN/Infinity, floats, dates as objects (use RFC 3339 UTC strings with `Z`),
  bytes, non-plain objects, `undefined`.
- **Reference implementations:** AD `lib/agapi/portable/canonical.js` (already JCS-compatible for plain data; add the
  float and key-charset refusals); Python
  `json.dumps(v, sort_keys=True, separators=(",",":"), ensure_ascii=False)` **after** a validator applies the same
  refusals.
- **Part 3 vectors prove byte equality.**

### 4.2 Named hashes

| Field | = `sha256(canonical(…))` of |
|---|---|
| `payload_sha256` | the exact **upstream payload** the act will send (the offer ids, the travellers, the amounts in minor units, the venue form fields), as the product's adapter builds it |
| `read_back_sha256` | `{ "account": …, "intent_id": …, "operation": …, "lines": [...], "payload_sha256": … }`: the words shown, bound to the payload |
| `request_sha256` | `{ "operation": …, "input": … }`, for idempotency (§7) |
| `input_digest` | the Pacioli evidence input (Part 2) |

## 5. The error-code registry

**`error-codes.json` is normative.** Each entry has: `code`, `http`, `category`, `retryable`, `store_for_replay`,
`meaning`, `details_schema`. The summary:

| Category | Codes (HTTP) |
|---|---|
| request | `invalid_request` (400) · `invalid_input` (422) · `unknown_operation` (404) · `version_unsupported` (400) · `not_found` (404) |
| auth | `unauthenticated` (401) · `forbidden` (403) · `mode_not_available` (403) |
| limits | `rate_limited` (429, retryable) · `budget_exhausted` (402) |
| idempotency | `idempotency_key_required` (400) · `idempotency_in_flight` (409, retryable) · `idempotency_conflict` (409) · `already_completed` (409) |
| approval | `approval_required` (409) · `approval_not_found` (404) · `approval_same_turn` (409) · `approval_expired` (409) · `approval_void` (409) · `approval_consumed` (409) · `approval_untrusted_origin` (403) · `no_explicit_yes` (422) |
| upstream | `upstream_unreachable` (503, retryable) · `upstream_timeout` (504, retryable) · `upstream_rate_limited` (503, retryable) · `upstream_failed` (502, retryable) · `upstream_refused` (422) |
| outcome | **`outcome_unknown` (502)** |
| internal | `internal` (500, retryable) |

### 5.1 ⛔ Outage ≠ "no results" (the rule both runtimes must enforce)
- **R1. An empty result is a claim.** A `find` result's `items: []` is valid **only if every source queried
  answered**.
- **R2. Coverage on every multi-source result:** `coverage: { complete: bool, answered: [...], unavailable: [ {
  source, code } ] }`.
  - **All sources failed** → **an error** (`upstream_unreachable` / `upstream_timeout` / `upstream_failed`), never
    `ok:true` with no items.
  - **Some failed** → `ok:true`, `coverage.complete: false`, with the failures listed. The caller must say the result
    is partial.
- **R3. No silent substitution.** If an adapter widens or changes the question (another date, another currency, a
  nearby city), the result **must** carry `substituted: [ { field, asked, used, reason } ]`. Sasha's ±2-day search and
  non-EUR fallback (EU 200 R3) become visible this way.
- **R4. A status read is never empty on failure.** `status` with an unreadable upstream returns `upstream_*`, never
  an empty list (EU 200 R2).
- **R5. `outcome_unknown`:** an act whose upstream call may have taken effect but whose answer was lost (a timeout
  after sending, a dropped connection after payment) returns **`outcome_unknown`**, never `internal` and never
  `upstream_failed`.
  - `details.act_id` names what to check.
  - The caller **must call `status`** before retrying.
  - **"Nothing was changed by this call" may be said only by `internal`, and only when it's true.**

### 5.2 HTTP status vs `ok`
- `ok:true` → 200, or 201 when a new act/object was created.
- `ok:false` → the code's status.
- A replay returns the **stored** status and body (§7).

## 6. ReadBack and Approval

### 6.1 The flow (Austen)
1. `hold` / `request_approval` (Part 2) creates an **Intent** (`int_`) and a **ReadBack** (`rb_`): the exact lines the
   end user will be shown, `payload_sha256`, `read_back_sha256`.
2. AgAPI **presents** the read-back to **the end user on their own device**: a signed single-use link (SMS / WhatsApp /
   email), the customer's app via the SDK, or Sasha's own voice/chat surface. Presentation is an **event** with a time
   and a turn: `presented_at`, `presented_turn_id`.
3. The end user says or taps **yes in a later turn**. The approval surface (not the customer's server) creates the
   **Approval** (`apv_`).
4. The customer calls the act (`book` / `complete` / `cancel`) with `approval_id`. AgAPI **re-derives**
   `payload_sha256` and `read_back_sha256` from the current state and checks every rule in §6.3. Then it acts once.

### 6.2 Objects
- **Schemas:** `schemas/read_back.schema.json`, `schemas/approval.schema.json`.
- **Approval:**
  ```jsonc
  { "approval_id": "apv_…", "read_back_id": "rb_…", "intent_id": "int_…", "account": "acct_…",
    "read_back_sha256": "sha256:…", "payload_sha256": "sha256:…",
    "method": "tap" | "voice" | "signature",
    "said": "Yes, book it.",               // voice: the person's own words, verbatim (required for voice)
    "approved_by": "usr_…",                 // the END USER (verified by the channel), never the API principal
    "approved_at": "2026-10-08T14:07:31Z", "approved_turn_id": "trn_…",
    "device": { "channel": "link" | "sdk" | "sasha_voice" | "sasha_chat", "attestation": "…" },
    "expires_at": "2026-10-08T14:22:31Z",
    "irreversible": true,
    "state": "valid" | "consumed" | "expired" | "void",
    "consumed_by_request_id": null, "void_reason": null }
  ```

### 6.3 The rules (each has a code and a Part 3 vector)

| # | Rule | On breach |
|---|---|---|
| **AP1** | **Bound to hashes.** At act time, the re-derived `payload_sha256` **and** `read_back_sha256` must equal the Approval's | `approval_void`, `void_reason: payload_changed \| read_back_changed` |
| **AP2** | **Void, never corrected.** Any change of price, availability, travellers, fields, wording or intent voids the Approval permanently. A new read-back and a new yes are required | `approval_void` (`intent_changed` \| `superseded`) |
| **AP3** | **Never the same turn.** `approved_turn_id ≠ presented_turn_id`, **and** `approved_at > presented_at`. For a link or SDK, the approval must be a separate user action **after** the presentation event was recorded (a page view, then a tap) | `approval_same_turn` |
| **AP4** | **Expiry.** A ReadBack can be approved until `presented_at + 30 min` (`read_back.expires_at`). An Approval must be consumed by `approved_at + 15 min` (`approval.expires_at`). Products may shorten these, never lengthen them. **Irreversible acts: both at most 15 min** | `approval_expired` |
| **AP5** | **On the end user's own device.** An Approval is created only by the approval surface, authenticated by the **single-use approval token** delivered to the end user's channel, or by Sasha's authenticated user session. **An API key can never create or forge an Approval.** `device.channel` is required; `device.attestation` is required for the SDK | `approval_untrusted_origin` |
| **AP6** | **An explicit yes.** For `method: voice`, `said` must pass the registry's explicit-yes rule: an affirmative phrase, and **no** negation or hesitation token anywhere ("no", "not", "don't", "wait", "hold on", "later", "maybe", "cancel", "stop", in the user's language). The rule is versioned in `approval-language.json` (Part 3). It's evaluated **server-side**, never by a model | `no_explicit_yes` |
| **AP7** | **Single use.** One Approval authorises exactly one act request (the same `idempotency_key` may replay it, §7). After use, `state: consumed` | `approval_consumed` |
| **AP8** | **Irreversible acts aren't batched.** An Approval with `irreversible: true` covers exactly one act. A plan approval may cover several **reversible** holds only | `approval_void` (`irreversible_batch`) |
| **AP9** | **Who.** `approved_by` must be the end user the read-back was presented to (`read_back.presented_to`) | `approval_untrusted_origin` |
| **AP10** | **Missing.** An Austen act without `approval_id` | `approval_required`, with `details.read_back` (the lines to show) |

### 6.4 What each runtime already has
- **Sasha:** AP3 (`read_back_first`), AP6 (`explicit_yes`), the AP1 read-back half (`BB.pay` recompute), a 30-min reuse.
- **AD:** the AP1 payload/capture half, AP2 (`readyToSubmit` voids), AP5 (`originates.js`), AP8 (`assisted.ts`).
- **Missing in both:** AP4 as specified (AD's Austen has no expiry), AP7 as an explicit state, AP9.

## 7. Idempotency

| Rule | |
|---|---|
| **I1. Required** on every Austen operation (`hold`, `book`/`complete`, `cancel`, `request_approval`); optional on reads | missing → `idempotency_key_required` |
| **I2. The key:** client-chosen, `^[A-Za-z0-9_-]{16,128}$` | |
| **I3. Scope:** stored as **(account, operation, idempotency_key)**. Keys never cross accounts; the same key on two **operations** is two keys (vector I-12); the same key on the same operation with a different input is a conflict (I4, vector I-2). **The intent is not part of the scope:** one act per intent is I11's job. *(v1.0, CR 59 finding 2: draft.3 said "intent_id-or-operation", which contradicted I-2; CR's sandbox scopes per account + operation + key, and that wins.)* | |
| **I4. The request hash:** `request_sha256` is stored with the key. The same key + a different hash | `idempotency_conflict` |
| **I5. Durable:** the store survives restarts and is shared by every worker (**not** in-process memory; EU 200 R4) | |
| **I6. Order:** **authenticate → resolve the account → validate → claim the key → act → store.** Never claim or replay before authentication (EU 196 G2) | |
| **I7. What's stored for replay:** `ok:true` results and **non-retryable** refusals of the act itself (`upstream_refused`, `approval_void`, `approval_expired`, `approval_consumed`, `no_explicit_yes`, `already_completed`, `invalid_input`). **Never stored:** auth errors, `rate_limited`, `budget_exhausted`, `idempotency_in_flight`, `upstream_unreachable` / `timeout` / `rate_limited` / `failed`, `internal`. These **release** the key so a retry acts | |
| **I8. `outcome_unknown`** keeps the key **in flight**. A retry with the same key → `idempotency_in_flight` until `status` resolves the act, then replays the resolved outcome | |
| **I9. Replay:** the same HTTP status and the same `result` as the first time, `replayed: true`, header `AgAPI-Replayed: true`. **No side effect, no metering charge** | |
| **I10. Retention:** **24 h** for API customers. (AD's in-app 5-minute intent buckets are a product-side key derivation, not a server rule.) | |
| **I11. One act per intent:** an Austen act on an intent whose prior act is CONFIRMED | `already_completed`, `details.act_id` |
| **I12. In flight:** the same key while the first is running | `idempotency_in_flight`, `retry_after_s` |

---

## Status of Part 1 (v1.0 FINAL)

| Item | Status |
|---|---|
| Envelope, ids, versioning (§1–3) | **frozen** (+ `whe_`) |
| Canonical JSON (§4): JCS, integers only, ASCII keys | **frozen**; byte-equality proven Python ↔ Node, and by CR's sandbox |
| The error registry (§5, `error-codes.json`, 36 codes) | **frozen**; new codes are additive |
| Approval (§6): AP1–AP10 | **frozen**. Read-back approvable **30 min** after presentation; approval usable **15 min** (Tyler). A typed yes in Sasha's own session counts as `tap`-equivalent, with AP3 and AP6 applied; partners' end users must tap (Tyler) |
| Idempotency (§7) | **frozen**; I3 settled as (account, operation, key) |

**Additive, later (1.x):** the SDK device-attestation format; `cost_units` values (Part 4); more AP6 languages.
