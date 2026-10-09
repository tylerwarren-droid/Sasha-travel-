# CR 61 · Sasha's AgAPI v1.0 conformance — the merge note

**Branch:** `cr/sasha-conformance`, from main `513d6cd`. It touches `backend/agapi` only, plus one runner script and one test file. The agent loop, `sasha/mobile` and main are untouched.

## Run it

```
cd backend && AGAPI_V1_DIR="$HOME/Developer/Applied Diligence/docs/agapi/v1" python -m scripts.agapi_v1_conformance
```

The runner:
- loads EU's frozen vector files where they live, never a copy;
- prints `<file> <passed>/<total>` and the sha256 of every file;
- exits 1 on any failure (checked against a tampered copy).

## Before / after (EU 03-conformance.md §5)

| File | Before (main `513d6cd`) | After |
|---|---|---|
| `canonical.json` | 12/15. Sasha's only canonical was the booking helper's (`booking_signer.canonical`, a different contract). | **15/15** (`agapi/v1.canonical`) |
| `explicit-yes.json` | 31/38. All 7 failures were Spanish ("Sí, adelante.", "vale"…). | **38/38** (`agapi/v0.explicit_yes`, on EU's lists) |
| `approval.json` | 0/17: no act-time Approval decision | **17/17** (`agapi/v1.decide`) |
| `outage.json` | 0/7: no outage classification | **7/7** (`agapi/v1.classify`) |
| pinned `approval-language.json` == EU's file | — | **✓** (sha256 `b4992034…`) |

## What changes in Sasha's behaviour when merged

**`agapi/v0.explicit_yes` (live: book, book_venue, cancel_venue)** now reads EU's frozen lists:
- **English and Spanish.** "Sí, adelante", "vale" and "de acuerdo" are now a yes, and "sí, pero luego" is not.
- **Questions and requests** veto, from EU's `questions_and_requests`.
- **Kept from Sasha 215, on purpose:**
  - "yes, cancel it" confirms a cancellation, and `yes_to_book` still refuses it;
  - Sasha's extra affirmatives ("book the whole trip", "send me their page");
  - Sasha's extra vetoes (refund, cost, price, fees, details, first…).

  None of these contradicts a v1.0 vector; they're reported to EU as proposed additions.
- **Apostrophe errata.** EU's frozen normalisation turns `'` into a space, so in EU's own reference **"Yes, don't book it" is a yes** and "OK, let's do it" isn't. Sasha deletes apostrophes instead, so "dont" and "lets" match EU's own lists. All 38 vectors still pass, and the fix is reported to EU.

**`agapi/v1.py` (new):** canonical, decide and classify are the v1.0 rules. Nothing calls `decide` or `classify` in a live path yet. Wiring `classify` into venue and stay search (CR 56 #4: an outage read as "no hotels") is the next ticket.

## Tests

- `tests/test_agapi_v1_sasha.py`: apostrophes, Spanish, Sasha's additions, the pinned file, and the runner itself (skipped where EU's files aren't on disk).
- Full suite: 1606 run, 0 failures.
