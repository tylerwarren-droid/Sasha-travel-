# Sasha 229 · S1's legacy Stripe path — on TEST for the beta (open item)

**What changed (10 Oct 2026):** `backend/app/api/payments.py` (the legacy "pay with a different card" → Stripe Checkout path on
/next: `create_checkout`, `verify`, `webhook`) now reads `SASHA_LEGACY_STRIPE_MODE`:

| value | secret key | webhook secret |
|---|---|---|
| `test` (default; also unset or anything else) | `STRIPE_TEST_SECRET_KEY` (the one S2's Pay here uses; refused unless `sk_test_`) | `STRIPE_TEST_WEBHOOK_SECRET`, else `STRIPE_WEBHOOK_SECRET` |
| `live` | `STRIPE_SECRET_KEY` | `STRIPE_WEBHOOK_SECRET` |

Nothing else changed: no button, label or UI. No key was overwritten or deleted.

## Open item — before real payments

Before this path takes a live card it needs the proper fix, not a key switch:

1. **The server sets the amount from the booking.** Today the itinerary path charges the stored itinerary's `total_usd`, an
   *estimate* built by the planner. It is not the re-checked basket total that S1's agent path reads back (`hold_booking`). The
   no-id legacy branch still charges whatever amount the browser sends.
2. **The yes rule.** This path charges on a tap ("Pay securely") with no read-back the person heard and no explicit yes bound to
   it, unlike `book()` (read-back sha256 → yes in a later turn → claim → pay).
3. **Return URLs.** `STRIPE_SUCCESS_URL` / `STRIPE_CANCEL_URL` are unset on Railway, so Checkout returns to the code default
   (`http://localhost:3000/vietnam…`). The webhook still records the payment; the person just lands on a dead page.
4. **The live key.** When the beta began, `STRIPE_SECRET_KEY` was **not set** on Railway, so `live` mode would answer 501 until
   it is.

Until then: `SASHA_LEGACY_STRIPE_MODE=test` on Railway.
