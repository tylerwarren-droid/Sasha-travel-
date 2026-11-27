# AgAPI v1 · Part 3: conformance vectors

*EU 201 Part 3 · 8 Oct 2026 · **v1.0 FINAL (frozen 8 Oct 2026, EU 205)**.*

**What this part is:** data files that **both runtimes must pass**. A runtime is conformant when it reproduces every
`expect` exactly.

**Where they come from:**
- generated from a small, dependency-free **reference** (`vectors/reference/agapi_ref.py` +
  `vectors/reference/generate.py`), which isn't a product implementation;
- **checked across runtimes:** AD's own `lib/agapi/portable/canonical.js` (Node), via
  `vectors/reference/check_canonical_js.mjs`.

## 1. The files

| File | What it pins | Cases |
|---|---|---|
| `vectors/canonical.json` | Part 1 §4.1: input → canonical bytes → sha256; refusals | 10 accepted + 5 refused |
| `vectors/explicit-yes.json` + `vectors/approval-language.json` | Part 1 AP6: said → explicit yes (EN, ES); v1.0 adds the question/request vetoes; 1.0.1 the apostrophe cases; 1.1 `act_kind` (cancel) + the "what's" fix | 53 |
| `vectors/approval.json` | Part 1 AP1–AP9: the act-time decision, **in the normative check order** | 17 |
| `vectors/idempotency.json` | Part 1 §7: request sequences → status, replay, upstream calls, charge; v1.0 adds I-12 (scope includes the operation) | 12 |
| `vectors/outage.json` | Part 1 §5.1: per-source upstream results → an error or coverage | 7 |
| `vectors/untrusted.json` + `vectors/untrusted-patterns.json` | Part 2 §3: fetched text → cleaned text + `instruction_like` / `truncated`; 1.1 adds U-9/U-10 | 10 |
| `vectors/evidence.json` | Part 2 §4: `body_sha256` valid / tampered | 2 |
| `vectors/webhook-signature.json` | Part 4 W3: HMAC header, tamper, staleness | 3 |

## 2. Run results (8 Oct 2026, re-run for v1.0 in EU 205)

| Check | Result |
|---|---|
| **Canonical JSON, Python reference vs AD `canonical.js` (Node)** | **10/10 accepted cases byte-identical**, with identical sha256. C-1 (key order), C-3 (raw UTF-8: `Café Ñandú 東京 🚀`), C-4 (escapes), C-7 (`1.0`/`-0.0`/`1e3` normalised), C-10 (the read-back shape) included |
| Canonical refusals | **AD `canonical.js` accepts all 5 refusal cases today** (a fraction, a non-ASCII key, an uppercase key, a lone surrogate, an integer > 2^53−1). With the §4.1 checks added (as in `check_canonical_js.mjs`'s `strict`), all 5 are refused. ⚠ **A gap to fix in the AgAPI service and in Sasha.** AD's own file stays untouched until AD's beta ships (EU 200 §5) |
| Explicit yes, approval, outage, untrusted, evidence, webhook | **asserted against the reference** by `generate.py` (it stops on any mismatch): canonical 15 · yes 53 · approval 17 · outage 7 · untrusted 8 · evidence 2 · webhook 3, all pass. Webhook W-1/W-2 re-checked in Node: identical |
| Idempotency | a sequence spec (no single-function reference); I-1–I-11 were passed by CR's sandbox (CR 59); **I-12 is new in v1.0** and pins what CR already implements |
| **CR's sandbox** (`agapi-sandbox-production`, `cr/agapi-api` @ `b9fa892`) | **all EU vectors pass**, 41/41 tests (CR 59, #565). The 12 new yes vectors were CR's own EN/ES lists, so it passes them by construction; CR re-runs to confirm |

**Re-run:**
```
cd docs/agapi/v1/vectors
python3 -I reference/generate.py
node reference/check_canonical_js.mjs ../../../../lib/agapi/portable/canonical.js canonical.json
```

## 3. The normative decision order (approval)
When several rules fail, the **first** in this order is the answer, so both runtimes return the same code:

1. `approval_not_found` (the wrong account / none)
2. `approval_untrusted_origin` (the channel, the approver ≠ presented-to, SDK without attestation)
3. `approval_consumed`
4. `approval_same_turn` (never presented; the same turn; approved ≤ presented)
5. `no_explicit_yes` (`voice`, or a typed `said` in `sasha_chat`)
6. `approval_expired` (approved after `read_back.expires_at`, or now > `approval.expires_at`)
7. `approval_void: irreversible_batch`
8. `approval_void: intent_changed`
9. `approval_void: payload_changed`
10. `approval_void: read_back_changed`
11. `valid`

**Comparisons:** times are RFC 3339 UTC strings; a lexical comparison is valid because the format is fixed (`Z`,
seconds precision in the vectors).

## 4. Points the vectors settle
- **"Then book it." is an explicit yes:** "then" is a filler and "book it" is affirmative. That's Sasha's v0
  behaviour, kept.
- **"¿sí?" is a yes, but "sí, pero luego" isn't:** punctuation is stripped, and a negation anywhere vetoes.
- **"yeah no"** is not a yes.
- **v1.0 (CR 59 finding 1): a question or a request for options vetoes a yes.** "Yes — what are my cancellation
  terms?", "Sure, find me dinner options" and "Vale, búscame opciones" are **not** approvals: the user is still
  deciding. "Yes, book it." still is. The lists are `questions_and_requests` in `approval-language.json` (EN 21,
  ES 18), checked as whole words after normalisation, exactly like the negations. Normalisation also strips em and en
  dashes.
- **Outage ranking** when every source failed: `upstream_unreachable` > `upstream_timeout` > `upstream_rate_limited` >
  `upstream_failed`. `upstream_refused` only if **every** source refused.
- **O-7:** one source answered empty and one failed. That's a **partial** result with 0 items, **not** "no results".
- **U-3 / U-4:** bidi overrides and zero-width characters are removed (`CaféolleH`, `Barcelona`). U-1, U-5, U-6 and
  U-8 are flagged `instruction_like` and **kept** as text. U-7 is truncated at 2,000.

## 5. ⛔ What Sasha must pass (its conformance, after the freeze)

Sasha implements the approval half of the contract in its own runtime (Python). **Required before any Sasha act runs
through AgAPI 1.0 rules:**

| # | File | Cases | What Sasha's code must do |
|---|---|---|---|
| 1 | `canonical.json` | **15**: 10 byte-exact + 5 refusals | `canonical(value)` produces the exact bytes and sha256 for C-1–C-10, and **refuses** C-R1–C-R5 (a fraction, a non-ASCII key, an uppercase key, a lone surrogate, an integer > 2^53−1) |
| 2 | `explicit-yes.json` + `approval-language.json` | **53**, including the 12 v1.0 cases, the 4 apostrophe cases (1.0.1) and the 11 v1.1 cases (`act_kind`, "what's") | AP6 on `said`, EN and ES, loading the lists from `approval-language.json` (not a copy in code): negations **and** `questions_and_requests` veto; "vale" is a yes alone |
| 3 | `approval.json` | **17** | the act-time decision, returning the **first failing rule in the §3 order** |
| 4 | `outage.json` | **7** | an upstream failure is never "no results"; partial with 0 items (O-7) stays partial; the ranking in §4 |

**Recommended next (not blocking):** `untrusted.json` (8: Sasha fetches venue text) and `idempotency.json` (12: once
Sasha calls AgAPI with keys). `evidence`, `webhook-signature` and the product surface are the service's (CR's), not
Sasha's.

**How Sasha reports:** a runner that loads each file, prints `<file> <passed>/<total>`, and exits non-zero on any
failure; posted as a readout with the commit it ran on.

## Status of Part 3 (v1.0 FINAL)

| Item | Status |
|---|---|
| The vector formats and the nine files | **frozen**; new cases are additive and never change an existing `expect` |
| Canonical JSON byte equality across runtimes | **proven** (Python ↔ AD Node 10/10; CR's sandbox) |
| AD `canonical.js` refusal gap | **open, AD-side** (not a contract change): the service and Sasha must refuse; AD's file is fixed after its beta |
| The explicit-yes lists (EN, ES) incl. question/request vetoes | **frozen**; more languages are additive |
| The untrusted heuristic patterns | **frozen**; additive. **A heuristic, not a guarantee:** the real defence is the delimiting + never-execute rule in Part 2 §3 |

**Decided (Tyler):** "vale" (ES) counts as an explicit yes alone; any negation, question or request still vetoes it.
