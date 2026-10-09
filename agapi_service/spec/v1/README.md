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

**Rules of this directory:**
- **The JSON files are normative.** The prose explains them; where they disagree, the JSON wins and the prose is the
  bug.
- **Every schema is JSON Schema 2020-12, validated** (`Draft202012Validator.check_schema`) before posting.
- **Additive-only after `1.0`** (Part 1 §3).
- **Docs only:** nothing here is built by this directory. US commits it.
