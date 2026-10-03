# Sasha 131: the escalation policy, loyalty numbers, one-touch deposits

*3 Oct 2026. Commits: 1be4d13, 58097e5, b9223d1, plus this report's commit.*

**Before this pass:**
- Migration 030 was applied by chat (verified in `pg_constraint`).
- `SASHA_NO_REPLY_CALL=1` was set on Railway (CLI, read back).

## 1. The founder's escalation policy (`decide.py`)

| The booking | Route |
|---|---|
| Own form | Fill it after the yes |
| Otherwise | **One-tap on the guest's phone** (the default). Calls are no longer the default for an open venue. |
| One-tap not pressed within **`SASHA_TAP_WINDOW_MIN`** (30) | The **email** is offered on WhatsApp |
| No venue reply within **`SASHA_EMAIL_REPLY_HOURS`** (24) | The **call** is offered (when they're open by their hours, or in the daytime when the hours aren't known) |
| **Urgent**: within **`SASHA_URGENT_HOURS`** (24) | **Call + email at once.** Both are read back, on **one** yes. |
| No page, no form | Email (then the call after 24 h); a phone only → call |
| The guest's override | Any route that exists: "call them", "email them", "call and email them", "send me the link" |

**How each escalation step works**
- Each step is a **question on WhatsApp** ("Not booked on X's page yet … Shall I email them instead?"). Its yes leads
  to that route's **own** read-back and yes.
- **Nothing is sent or dialled without a yes to its exact words.** This is a deliberate choice: the founder's policy
  says "→ EMAIL", and I kept a yes per outward contact, as every other route has.
  - **If he wants it fully automatic,** the first yes would have to cover the later email's exact words. That is
    possible, but the guest would approve an email before it exists. His call.

**Switches**
- The email-after-24-h call offer is **ON**.
- The tap-window email offer waits for **migration 031** (`backend/booking_signer/sql/031_tap_expired.sql`, for chat).
  After it, set `SASHA_TAP_ESCALATION=1`. Until then it is neither offered nor promised.

**Cost and outcome per booking.** Ops page → *Cost per confirmed booking*.
- **Calls** are costed at **Bland's own price** per call (USD).
- **Email, one-tap and form** are costed at rate settings: `SASHA_COST_EMAIL_EUR`, `SASHA_COST_WHATSAPP_EUR`,
  `SASHA_COST_FORM_EUR`. `SASHA_USD_EUR` converts Bland's USD.
- An unset rate is **unknown, never €0**. With any unknown cost, the total and the cost per confirmed booking are not
  stated; the known part is.
- **Live today:** 24 bookings, 2 confirmed. **No rates are set yet**, so the cost per confirmed booking can't be stated.
  **The founder sets the four rates.**

**Tests:** `test_decide_s130` (23), `test_route_costs_s131` (4).

## 2. Calls never read out the K-reference

- The call script no longer says it. The read-back now says: "I'll ask for their booking reference; it goes on your
  receipt with ours, K-…, which I only ever give in writing."
- Freeing that space lets the call's written-confirmation ask include Sasha's **email** as well as her number again.
- **Tests:** the golden examples and 3 tests were updated to the new wording.
- **Live check:** a built call brief contains no K-reference.

## 3. Loyalty numbers in the Keep (the vault)

**Saved in the founder's vault** (fictional numbers):

| Site | Programme | Number |
|---|---|---|
| iberia.com | Iberia Plus | IBP-FICT-0001 |
| marriott.com | Marriott Bonvoy | MBV-FICT-0002 |
| club.kanoe.ai | Kanoe Test Club (ours) | KTC-FICT-0003 |

**Matching** uses a fixed list, never a guess:
- Iberia Plus → flights;
- Marriott Bonvoy → Marriott-family hotels only;
- the test club → our test venue and demo spa.

Sasha books restaurants and a spa today, so **only the test club matches anything yet.**

**How it's used**
- The read-back names it: "I'll use your saved Kanoe Test Club number (fictional) from your vault."
- The yes covers it. The number is **opened only at the send**, once, and logged (`loyalty_number`).
- It is written into the form's comments box. It is scrubbed from their echoed page and **never said on a call**.

**Live, on the founder's account:** test venue booked (TV-1F8577-30, since reset); vault log shows `loyalty_number`,
done, 12:31:50 UTC.

**Found on the way (a real defect)**
- The vault names a site by its **address**, so the night-before steps "site 'Kanoe Demo Market' / 'Kanoe Demo Spa'"
  would have been **refused**. Neither login had ever been saved; the rehearsals used an in-memory vault.
- They are now **demo-market.kanoe.ai** and **demo-spa.kanoe.ai**; the old names still match. The run of show is
  updated.
- A misplaced comment had also deleted the demo shop's and demo spa's second read-back line. It's restored and tested.

## 4. Deposits: one touch

- **Any venue:** the deposit is paid on the venue's **own** page in one touch (Apple Pay or the phone's saved card).
  Sasha never sees a card.
- **Our test venue:** its deposit is a **Stripe TEST-mode Payment Link**, labelled "TEST payment — nothing is charged".
  - A live key (`sk_live_…`) is refused, always.
  - "Paid" means Stripe's own completed test checkout, never assumed.
  - Founder ops: `/ops/test-deposit/link`, `/status`.
  - On WhatsApp, after a test-venue booking: `SASHA_TEST_VENUE_DEPOSIT=1`.
  - Tests: 3.
- **⛔ Not rehearsed on his iPhone yet: there is no Stripe key on Railway.** The founder sets
  **`STRIPE_TEST_SECRET_KEY`** (an `sk_test_…` key from Stripe's dashboard in TEST mode) himself, plus
  `SASHA_TEST_VENUE_DEPOSIT=1`. Then I make the link, send him ONE WhatsApp, he pays with Apple Pay, and his phone
  should say "✅ Deposit paid … TEST payment".

## 5. The site

- It stays held until the founder's signed-out walk.
- CR 8's link is ready to go out with it: `/officer/vxgS8Ol0xgzR8D-kNaIk3Q`, "For administrations: the case officer's
  queue (click-through) →".

## 6. Akaneya

- Pilar Akaneya is **dropped** from the demo. The run of show marks it, and §2.2's request is not to be sent.
- It still appears among real search cards. **Don't pick it on stage.**

## For the founder / chat

1. **Chat:** apply migration 031, then `SASHA_TAP_ESCALATION=1`.
2. **Founder:** set `STRIPE_TEST_SECRET_KEY` (sk_test_…) and `SASHA_TEST_VENUE_DEPOSIT=1`, then tell this tab to run
   the iPhone rehearsal.
3. **Founder:** set the cost rates, or say they stay unknown:
   - `SASHA_COST_EMAIL_EUR`
   - `SASHA_COST_WHATSAPP_EUR`
   - `SASHA_COST_FORM_EUR`
   - `SASHA_USD_EUR`
4. **Founder:** save the demo logins as **demo-market.kanoe.ai** / **demo-spa.kanoe.ai** (ops page buttons give the
   passwords).
5. **Decide:** keep a yes per escalation step (as built), or make the first yes cover the later steps.
