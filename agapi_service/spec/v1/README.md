# AgAPI v1: the contract

**One language-neutral contract, two runtimes now, one service later** (EU 200, adopted).

**Who uses it:** CR builds the sandbox service against it, part by part. AD (TypeScript) and Sasha (Python) implement it.

## ⛔ v1.0 FINAL: frozen 8 Oct 2026 (EU 205)
From here, **1.x is additive only** (Part 1 §3): new operations, optional fields, error codes and vector cases. An
existing `expect`, field, type or code meaning never changes. Anything else is v2.

| Part | File(s) | Status |
|---|---|---|
| 1 · Core: envelope, ids, versioning, canonical JSON, the error registry, ReadBack/Approval, idempotency | `01-core.md`, `error-codes.json` (36 codes), `schemas/{common,request,response,error,read_back,approval}.schema.json` | **1.0 frozen** |
| 2 · Tools (11 operations) + untrusted-data marking + the evidence shape | `02-tools.md`, `operations.json`, `schemas/tools/tools.schema.json` | **1.0 frozen** |
| 3 · Conformance vectors (9 files, 102 cases) + `approval-language.json` + **Sasha's conformance list (§5)** | `03-conformance.md`, `vectors/*.json`, `vectors/reference/*` | **1.0 frozen** |
| 4 · The API product surface (7 product operations: keys, end users, webhooks, metering, sandbox) | `04-product.md`, `schemas/product/product.schema.json` | **1.0 frozen** |

`operations.json`: **18 operations**, version `1.0`.

## Changelog
| Version | EU | What changed |
|---|---|---|
| draft.1 | 201 P1 | the core: envelope, ids, versioning, canonical JSON (JCS restricted), the error registry, ReadBack/Approval AP1–AP10, idempotency I1–I12 |
| draft.2 | 201 P2 | the 10 tool operations as JSON Schema; untrusted-data marking; the evidence shape; 3 domain codes |
| draft.3 | 201 P3 | the conformance vectors (canonical, explicit-yes, approval, idempotency, outage, untrusted); the number-normalisation clarification in Part 1 |
| draft.4 | 201 P4 | the product surface: keys, end users, the key-less approval surface, webhooks + HMAC, test/live, metering; `users.register`, `usage.get`, `sandbox.simulate_approval`, `sandbox.messages`; evidence and webhook vectors |
| **1.0** | **205** | **CR 59's five findings (tab_messages #565), all built and passing on CR's sandbox before the freeze:** (1) AP6: **a question or a request for options vetoes a yes**: `questions_and_requests` (EN 21, ES 18) in `approval-language.json`; em/en dashes stripped in normalisation; +12 explicit-yes vectors (38). (2) **Idempotency I3 settled as (account, operation, key)**; draft.3's "intent_id-or-operation" contradicted vector I-2 and lost; +vector I-12. (3) **`approvals.status`** (Pacioli, read). (4) **`acts.status` items carry `evidence_id`, required when `CONFIRMED`**. (5) **`webhooks.register` / `webhooks.revoke`** (new id prefix `whe_`) and **`users.verify_destination`**; +4 codes: `destination_code_invalid`, `destination_code_expired`, `webhook_url_refused`, `webhook_limit_reached`. Tyler's decisions recorded: expiries 30/15 min; a typed yes in Sasha's own session = tap; `payment_link` only; no real venue sends in test; "vale" = yes; Duffel/Stripe test as upstreams. Every file's version set to `1.0` |
| **1.0.1** (erratum) | **209** | **CR 61 (#573):** AP6 normalisation turned apostrophes into spaces, so "don't" became "don t" and matched no negation: **"Yes, don't book it" counted as a yes**, and "OK, let's do it" as not a yes. Fix: apostrophes (`'` `‘` `’`) are **deleted before** the punctuation-to-space step (`agapi_ref.py` `_norm`). +4 explicit-yes vectors (42); no existing `expect` changed; `approval-language.json` unchanged (byte-identical). A bug fix to the reference, not a contract change |
| **1.1** (additive) | **211** | **Operations (+6, CR 60–62, shapes taken from the live sandbox):** `messages.send_email` and `messages.send_whatsapp` (act; message class; need the end user's Approval), `messages.replies` and `activity.list` (read), `calendar.add_event` (free; no Approval), `sandbox.simulate_reply` (test). Schemas: `schemas/ext/ext.schema.json`. New id `rpl_`; webhook event **`message.replied`** (`data.reply_id`). **AP6 act-aware (CR 61):** an optional `act_kind`; for `cancel`, the words in the new `approval-language-acts.json` stop vetoing, so "Yes, cancel it" approves a cancellation; every other veto still applies; without `act_kind` AP6 is unchanged. **AP6 apostrophes, second fix:** 1.0.1 let "what's" escape the question veto ("Yes, but what's the refund?" was a yes); vetoes now match in both apostrophe forms (deleted and split). **Untrusted (CR 62):** "ignore/disregard **your/my/these/those** previous …" is flagged. Vectors: explicit-yes **53** (+11), untrusted **10** (+2). `approval-language.json` is byte-identical to 1.0 |
| **1.2** (additive, core) | **213** | **The Keep (CR 63), read from the live sandbox:** `keep.put`, `keep.list` (masked only), `keep.use` (purpose `fill` → a fill token `kf_…` redeemed by code at the moment of use, never the value; `show` → a read-back-only item shown once on the person's own phone), `keep.delete` (one item, or everything **plus the person's wrapped key**, which shreds every value), `keep.activity`. **Tiers:** free (preference, loyalty, home address) · **yes** (passport, DNI/NIE, trusted traveller, visa/residence, insurance, health card: used only when the booking's own yes **names** it; a `keep.use` fill re-issues the hold's read-back with the line "I'll use your saved Passport ES ••••456 for this booking.") · read_back (booking refs, door/Wi-Fi codes, eSIM: shown, never filled) · **never** (card numbers, one-time/2FA codes; passwords not in v1). **Masks:** public words + `••••` + at most a third of the secret, never more than 4 characters. **Refusals:** `invalid_input` with `details.rule` ∈ never_card · never_2fa · not_in_v1 · **never_raw** (any purpose other than fill/show: raw, value, reveal, plaintext, export, …) · read_back_only · fill_only · checksum · expired · iso2 · enum · unknown_field · unknown_type · required · already_bound. A booking whose yes didn't name the item → `approval_void`, new `void_reason` **`keep_not_approved`**. No new error codes. `activity.list` kinds widened with keep_save/keep_use/keep_show/keep_delete (callers must tolerate unknown kinds). New ids `kpi_` (Keep item), `kf_` (fill token). Schemas `schemas/keep/keep.schema.json`; operations +5 (29); vectors `vectors/keep.json` = **CR's frozen keep-vectors.1, byte-identical (sha256 802401e4…)**, with EU's independent reference agreeing on 15 masks/tiers, 12 use gates and 2 use lines (the 14 refusals and 1 envelope vector are CR-run). **DIVE is not in 1.2**: it's a separate partner service (`docs/agapi/dive/`, extension 0.1) |

**Rules of this directory:**
- **The JSON files are normative.** The prose explains them; where they disagree, the JSON wins and the prose is the
  bug.
- **Every schema is JSON Schema 2020-12, validated** (`Draft202012Validator.check_schema`) before posting.
- **Additive-only after `1.0`** (Part 1 §3).
- **Docs only:** nothing here is built by this directory. US commits it.
