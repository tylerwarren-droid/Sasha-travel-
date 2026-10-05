# Sasha 154: build times

*5 Oct 2026. Commit af1d53c (configuration only).*

## 1. Measured: Railway's own build logs, timestamped

| Builds | Build time |
|---|---|
| 10:03–11:28 (with `playwright` already installed since 10:52) | **0m53s – 1m27s** |
| 14:35, 16:02, 16:07 | 2m42s, 4m14s, 3m02s |
| **15:38 (f2b3861), the "25 minutes"** | **20m45s** |
| **After the fix (af1d53c)** | **2m37s** (live 4.1 min after the push) |

**Inside the 20-minute build:**
- ≈ 620 s passed **before any build step ran**: Railway's own preparation stalled (`prepare-driver`, `load build definition`
  and `load .dockerignore`, with gaps of 125 s and 192 s).
- Then it rebuilt from a **cold cache**:
  - the Nix setup ran again;
  - pip re-downloaded every package;
  - the image export took 98 s.
- A second build was queued behind it, which is the ~25 minutes seen from outside.

**Not the cause: no local browser is installed anywhere.**
- No `playwright install`, Chromium or system-package step appears in any build. The hand-over drives Browserbase's
  remote browser, and `playwright` is only the pip client library (with its small driver).
- Builds stayed at ~1 min for the 36 minutes after it was added (10:52 → 11:28).
- **Nothing to drop. Nothing removed.**

## 2. Fixed (configuration only; CR's code untouched)

**What was wrong:** the backend service had **no watch patterns**, so every push rebuilt it. That included every
docs-only and frontend-only commit: ≈ 30 builds today, mostly for nothing that changed the backend. They queue behind each
other, and each deploy also **ends any live hand-over in flight** (CR 23's finding).

**What changed:** `backend/railway.json` now has `"watchPatterns": ["/backend/**"]`, confirmed in the live deploy's
manifest.
- Backend changes build exactly as before.
- Docs and frontend pushes no longer touch Railway; Vercel still deploys the frontend.

## 3. Verified after the deploy

- **Build:** 2m37s, live 4.1 min after the push.
- **Docs-only push** (this report): no Railway build. The result is in the readout.
- **Live hand-over: could NOT be opened, for a reason outside the build.**
  - Browserbase answers **HTTP 402**: the project has used its **60 browser-minutes** (the free plan's allowance), during
    today's rehearsals.
  - **Founder action:** Browserbase dashboard → Billing → choose a paid plan (the Developer plan is enough for the demo).
    Then I re-run one test-venue session end to end.
- **The voice page's camera was not touched.**
