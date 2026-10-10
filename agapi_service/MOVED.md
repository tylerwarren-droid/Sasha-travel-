# This service now lives in `tylerwarren-droid/agapi`

**Frozen at CR 77 (`12f5610`, 10 Oct 2026). Kept for history. Do not change it.**

AgAPI was extracted into its own private repository on 10 Oct 2026 (US 123–126), with its
history: `git filter-repo` carried every commit that touched `agapi_service/` and
`tools/yes_one/`, so the new repo's log is this one's, not a snapshot of it.

| | |
|---|---|
| **New home** | `tylerwarren-droid/agapi` — `main`, released as `v1.3.0` |
| **Frozen at** | `12f5610` — CR 77's final commit on `cr/agapi-api` |
| **Serving from the new repo** | `agapi-sandbox` and `agapi-live` (Railway), since 10 Oct 2026 |
| **The spec** | `spec/` in the new repo — EU's path, and EU's alone |

## What to do instead of editing this copy

- **A change to the service or its spec:** open it against `tylerwarren-droid/agapi`. Six checks
  run on every push there — the tests on SQLite and on Postgres, the 109-case `yes_one`
  conformance set, an additive-only contract diff, the vendored-copy hashes, and an image build
  that re-runs the tests.
- **A change to the provider clients** (`backend/booking_signer`, `backend/app`, `backend/agapi`):
  **make it here, on Sasha's own branches, as always.** The new repo carries a *pinned, hashed
  copy* of those files (160 of them, `providers/vendored/MANIFEST.json`). It is refreshed with
  `node scripts/vendor-providers.mjs .` over there — never by editing a vendored file, which the
  check would catch anyway.

## Why the branch is still here

Deliberately. The extraction kept these commits, and this is the original they came from — the
record of where the code was written. **Do not delete the branch, and do not delete
`agapi_service/`.** Add never remove.

Replacing the vendored copy with HTTPS calls to Sasha — the way the venue ladder already works —
is a separate decision, recorded in AD's `docs/agapi/platform/PLATFORM-V1.md` and deferred to
US 135.
