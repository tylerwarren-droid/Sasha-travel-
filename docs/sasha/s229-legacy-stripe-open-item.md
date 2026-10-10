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

## Found while proving it live (10 Oct 2026)

- **The legacy pay button can't be reached any more.** /next runs the agent (`<SashaChat agent>`), so the conductor actions that
  open "Pay securely" (`await_payment`, `pay_new_card`) never fire there. `ItineraryDays` (whose "Book this trip" calls it) is
  not rendered anywhere. On /vietnam (still the conductor) a scratch guest's "Book the whole trip" → "A different card" never
  reached the card question, and no `itinerary_id` came back. Tried twice.
- **What was proved instead:** the button's endpoint, `POST /api/payments/create-checkout`, called as a signed-in scratch guest
  (its no-id branch, $1). It returned a `cs_test_` session, `livemode: false`, and Stripe's page showed Test mode
  (`s229-shots/stripe-checkout-test.png`). Before 229 this endpoint answered 501, because no `STRIPE_SECRET_KEY` was set.
- **The booking update** was proved with a SIMULATED `checkout.session.completed` signed with the TEST webhook secret. The live
  webhook accepted it, logged `PAID id=cs_test_…`, and marked the booking row paid (it reached the confirmation-email step;
  Resend rejected the `example.com` address, so nothing was sent). No card was typed: entering card numbers on the live site is
  outside what the Sasha tab does. **The 4242 leg is the founder's to run** on any account.
