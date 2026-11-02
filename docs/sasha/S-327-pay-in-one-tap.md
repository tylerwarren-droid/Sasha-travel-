# Sasha 327 · Pay in one tap: wallets and a saved card (Stripe TEST)

## Root test

### 1. The one place money is taken

`booking_signer/test_deposit.py`:
- `checkout()`: a Stripe Checkout Session, hosted or embedded on the page.
- `intent_saved()` + `confirm_saved()`: the saved card's PaymentIntent.
- `legacy_session()`: the old S1 itinerary checkout. It used to be created inside `app/api/payments.py`; it is now created here, with
  its shape and keys unchanged.

The trip's one payment entry is `basket_book.pay`. What books after a payment is `paid_watch.settle`, the one entry for every
payment. It is reached through the Stripe webhook, the 15-second sweep, and `get_status`.

### 2. PATCH check

- **No second checkout.** No wallet-only page, no card store of our own.
- **Wallets come from Stripe Checkout itself.** Apple Pay, Google Pay and Link are shown first, as Stripe's express buttons, with the
  card form below them.
- **Stripe holds the card.** That means his Stripe customer plus its saved payment method.
- **What Sasha keeps:** the customer's id (`s2_memory` "stripe_customer"), a pointer only.
- **What Sasha says:** the card's brand and last four digits, as Stripe gives them. Sasha never sees, logs or stores a card number.

### 3. Can any booking path take money another way?

No. A test scans the backend: every Stripe money call (`/checkout/sessions`, `/payment_intents`, `/charges`, `*.create`) is in
`test_deposit.py` only, and no card or CVC field exists anywhere.

## How it works

**The Pay-now page**
- Wallets first, then the card form.
- "Save this card for next time" is ON by default in beta (every person while Stripe is in TEST; `SASHA_SAVE_CARD=off` turns it off).
- The page shows the wording at its pay button: "Your card is saved securely with Stripe for your next booking. Say "remove my saved
  card" any time to delete it."
- He can remove a saved card on the page itself (Stripe's `payment_method_remove`).

**Saved: "Yes, book it" in S2 or WhatsApp**
- The PaymentIntent is made and the payment record is written FIRST, so paid-never-booked stays impossible. Then the card is charged
  off-session.
- **Paid:** `paid_watch.settle` books it, and the outcome is said on his one channel (326).
- **His bank asks him to confirm (SCA / 3-D Secure):** ONE "Confirm with your bank" link (Stripe's own), on the channel he asked on.
  Paid after he confirms, through the `payment_intent.succeeded` webhook or the sweep.
- **Declined:** the payment is cancelled at Stripe and nothing stays held. He hears "Your saved card didn't go through (…), so nothing
  was charged" and gets the Pay-now page.

**Removing the card:** "Remove my saved card" (the `remove_saved_card` tool) detaches it at Stripe. His next booking shows the page
again.

**Apple Pay domains:** at start-up, Kanoe's pay domains (project, demo, investor .kanoe.ai) are registered with Stripe as payment
method domains, using the service's own TEST key. This is idempotent, and the log prints each domain's Apple Pay, Google Pay and Link
state.

Live stays OFF: every path refuses a live key.
