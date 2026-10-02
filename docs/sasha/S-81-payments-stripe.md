# S-81 · Payments: "Pay the €20 deposit to X?", one amount, one yes

> ✅ **Founder default (EU 120): Tier 0 only this week.** Tiers 1 and 2 wait for counsel (S-1, S-2). §8's steps 1–2 are this week's build; steps 3–5 are parked.

*EU session, 2 Oct 2026 (EU 119), spec ahead of the Sasha tab. Code at **`22ccc0e`**. Stripe was read at source today
(`docs.stripe.com`). Nothing built.*

## 0. What Stripe offers, at source (2 Oct 2026)

| Product | What it does | Fit for Sasha | Availability (verbatim) |
|---|---|---|---|
| **Link Agent Wallet** (`docs.stripe.com/agentic-commerce/agents/link-agent-wallet`) | *"Creates a spend request for a specific purchase. The customer approves it, and Link returns a **one-time-use payment credential** your agent uses to pay."* It can *"transact anywhere on the internet"* | **The ideal shape:** per-amount approval in the payer's own wallet, a one-time card, **nothing stored by us** | *"Agent payments: **US and Canadian consumers**… Your own business can be outside these countries as can the sellers your customers buy from."* → **US and Canadian guests in Spain or Portugal: yes. EU guests: no** |
| **Issuing** (`docs.stripe.com/issuing`) | Kanoe creates virtual cards with **spending controls** (`spending_limits` with `interval: per_authorization`, `allowed_categories`, `allowed_merchant_countries`) and **real-time authorisations** | Kanoe pays the venue with a **single-purpose Kanoe card**, capped to the approved amount, the venue's category and ES/PT | *"Commercial issuing is available in the United States, United Kingdom, and **European Economic Area**… Consumer issuing is available in the US."* → **Kanoe (Spain) can issue business cards to itself.** €0.10 per virtual card (`issuing/cards/virtual`). Defaults: 500 USD/day per card unless set; 10,000 USD per authorisation |
| **Agentic commerce: Agents** (`docs.stripe.com/agentic-commerce`) | Embed seller catalogues and checkout in an agent; Shared Payment Tokens to sellers **on Stripe** | not for venues that aren't on Stripe | *"This feature is in **private preview**. Join the waitlist"* |
| **Checkout / PaymentIntents** (in use: `app/api/payments.py:182, :261`, `stripe==9.9.0`) | charges the guest **to Kanoe** | the guest pays Kanoe; Kanoe then pays the venue (tier 2) | live |

**PCI, at source** (`issuing/cards/virtual`):
- *"If you're generating virtual cards for your own use, you're not required to attain PCI-DSS compliance for Issuing
  activity. If you're generating virtual cards for use by your users, you might be considered a Service Provider."*
- *"we recommend limiting retrieval of virtual card information to the Dashboard or Issuing Elements. If you use the API
  to retrieve card information… store it in a password manager or otherwise encrypt it."*

## 1. Facts from the code

- **Every booking today refuses money:**
  - `reservation.py:34` `CONSTRAINTS = {"no_deposit": True, "no_card": True}`;
  - `calls.py:392` *"Never accept a deposit, fee, minimum spend, cancellation charge or card (you have none)."*;
  - `calls.py:431`;
  - `calls.py:615–622`, the `_MONEY` regex, means a "yes" that mentions money reads as `unclear`;
  - `calls.py:831` *"I never pay a deposit for you."*
- **Stripe today** (`app/api/payments.py`):
  - Checkout `mode="payment"` (`:261`) for itinerary totals and offer cards;
  - the webhook `checkout.session.completed` → `_confirm_paid_session` (`:340, :380–392`);
  - env `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, …;
  - **no saved PaymentMethods, no Issuing, no refunds code.**
- **The "saved card" is a mock:** `app/services/conductor.py:643` `SAVED_CARD_LAST4 = os.getenv("SASHA_SAVED_CARD_LAST4",
  "1003")`. ⚠ **It must not survive this ticket**: a mock card shown as real is rule 4.
- **No browser executor exists** (S-78 §0). A card can't be typed into a venue's web form by Sasha today.

---

## 2. Rules (all enforced in code)

1. **One amount, one yes.** The read-back names the **amount, currency, payee, what it's for, and whether it's
   refundable and until when**, as the venue stated it: *"Pay the €20 deposit to Casa Lucio, refundable until 24 h
   before, for Thursday 21:00 for 2?"* The yes is hash-bound like every other (`call_routes.py:497–503`). **Any change
   to the amount means a new yes.**
2. **Never a card number on a phone call.** Bland records and transcribes calls (`calls.py`, `anthropic_reader`
   `:685–689`). A card read aloud would sit in a third party's transcript and in our records. **A phone-only deposit is
   always the guest's to pay** (tier 0).
3. **We never store a card number** (S-78 §8). Card data stays with Stripe; we hold PaymentIntent, PaymentMethod and
   Issuing card **ids** only.
4. **Who paid is recorded and shown:** `payer` = `guest_direct` | `guest_link_wallet` | `kanoe_issuing` (BACKLOG item 1's
   "who pressed it", for money).
5. **No surcharge in phase 1.** The guest pays the venue's amount, and Kanoe's fee (if any) is separate and shown. ⚖
   Counsel: whether passing through a deposit is regulated (§6).

---

## 3. Three tiers (built in this order)

### Tier 0: the guest pays the venue directly (all guests; build first; no money touches Kanoe)

When a venue asks for a deposit (phone, email or form), Sasha **stops**, as today, and reads the requirement back:
*"Casa Lucio needs a €20 deposit, refundable until 24 h before. They'll send a payment link to you. Shall I ask them
to? (You pay them directly; I never see your card.)"*
- Yes → Sasha asks the venue to send its **own payment link** to the guest (by email or text to the guest's contact in
  `guest_contacts`), or relays the venue's link if it's already given.
- The guest pays on the venue's page.
- Sasha records `deposit_requested` and, when the venue confirms, `confirmed` with `payer='guest_direct'`.
- **Code:**
  - `calls.py:392/431` change from "never accept" to *"If they need a deposit or card, don't agree to anything: ask how
    they take it (a payment link is best), and say the guest will pay them directly."*;
  - `_MONEY` (`:615–622`) stays (a money mention is never a yes);
  - `reservation.py:34` `no_card: True` **stays** (Sasha never gives a card), and `no_deposit` becomes
    `"deposit": "guest_pays_venue"`.

### Tier 1: Link Agent Wallet (US and Canadian guests only; needs a browser executor for web forms)

- The guest connects Link (OAuth at `login.link.com`; the token is a vault item `kind 'oauth'`, `provider 'link.com'`,
  as S-79 does).
- Per deposit: the per-amount read-back + yes → **a spend request** for exactly that amount and payee → the guest
  approves **in Link's own prompt** (a second, Stripe-side approval) → a one-time credential.
- The **browser executor** (not built; S-78 step 9's separate ticket) types it into the venue's own payment form, inside
  `vault.use_connection`-style scoping, and **drops it immediately**.
- **Never on the phone rung** (rule 2).
- `payer='guest_link_wallet'`.
- **Blocked until the browser executor exists.** Specced so the schema and consent are ready.

### Tier 2: Kanoe pays with a single-use Issuing card (EU guests; needs counsel + Stripe approval)

1. The per-amount read-back + yes.
2. **Charge the guest to Kanoe first:** a `PaymentIntent` for exactly the amount, `description="Deposit to {venue} for
   {booking}"`, metadata `{trip_item_id, payment_request_id}`.
   - First time: Stripe Checkout or a Payment Element with `setup_future_usage='off_session'` to save the guest's
     PaymentMethod (a `pm_…` id only).
   - Later: `off_session` charges, **still one yes per amount**.
3. **On `payment_intent.succeeded`:** create an Issuing virtual card (cardholder: **Kanoe**, a company cardholder) with
   - `spending_controls.spending_limits=[{amount, interval:'per_authorization'}]`,
   - `allowed_categories=[eating_places_restaurants, …per activity]`,
   - `allowed_merchant_countries=['ES','PT']`,
   - and a **real-time authorisation webhook** that approves **only one** authorisation ≤ the amount, then
     **cancels the card**.
4. **The card reaches the venue only through the browser executor** typing it into the venue's own form (it doesn't
   exist yet). Card numbers are never emailed and never spoken (rule 2).
   - **So tier 2 also waits for the browser executor**, and for a venue whose form accepts a card.
5. **Refund:**
   - the venue refunds the deposit → an Issuing **refund transaction** on the card (`issuing/purchases/transactions`)
     → Kanoe refunds the guest's PaymentIntent (`stripe.Refund.create`) **for the same amount**, automatically, on that
     transaction webhook;
   - an unrefunded deposit after the venue's stated deadline → a Kanoe person checks it (logged, never silent).

---

## 4. Data (migration `024_payments.sql`, DRAFT, not applied)

```sql
-- Preview: expect NULL
select to_regclass('public.payment_requests');
create table public.payment_requests (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references auth.users(id) on delete cascade,
  trip_item_id uuid not null references public.trip_items(id) on delete cascade,
  payee text not null, purpose text not null,                     -- "deposit", "prepayment"
  amount_minor int not null check (amount_minor > 0), currency text not null check (currency ~ '^[A-Z]{3}$'),
  refundable_until timestamptz, venue_terms_quote text,           -- the venue's own words, verbatim
  approval jsonb,                                                 -- {by, how, said, at, read_back_sha256} — same shape as call_routes.py:533
  tier text not null check (tier in ('guest_direct','guest_link_wallet','kanoe_issuing')),
  stripe_payment_intent text, stripe_issuing_card text, link_spend_request text,   -- ids only, never card data
  status text not null default 'awaiting_approval' check (status in
    ('awaiting_approval','approved','link_sent','paid','refunded','refund_due','failed','cancelled')),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create unique index payment_requests_one_per_approval on public.payment_requests ((approval->>'read_back_sha256')) where approval is not null;
alter table public.payment_requests enable row level security;   -- backend only
```

---

## 5. Receipts

- **The guest's receipt** (`guest_receipt.send_for_route`, `:188`) gains a money line: *"Deposit €20 to Casa Lucio,
  paid by you directly / with your Link wallet / by Sasha with a single-use card charged to your card ending ••42.
  Refundable until {date}."*
- Stripe's own receipt email covers tier 2's charge (`receipt_email` on the PaymentIntent).
- A refund produces a receipt line and an email.

---

## 6. What Stripe and counsel require

- **Stripe:**
  - Issuing needs an **Issuing application in the Dashboard** (business verification, use-case review: "pay merchants
    for bookings our users approve, single-use cards capped per authorisation");
  - **Link Agent Wallet** needs no Stripe account for payments, but registering an OAuth client is recommended (*"gives
    your customers a better approval prompt"*);
  - **Agentic commerce Agents:** join the waitlist only if a seller-catalogue model is wanted later;
  - `stripe==9.9.0` (`requirements.txt`) predates recent Issuing fields. **Upgrade the SDK in its own commit, with
    tests.**
- **Counsel (⚖ S-1):** tier 2 means **Kanoe receives the guest's money and pays a venue with it.** Under PSD2 (Directive
  (EU) 2015/2366; in Spain, RDL 19/2018) that may be a **payment service (money remittance)** requiring a licence,
  unless an exclusion applies, such as the commercial-agent exclusion (Art. 3(b)) as narrowed by the EBA.
  **Tier 2 must not go live without counsel's written view.** Tier 0 doesn't touch money, and tier 1 is the payer's own
  wallet.
- **PCI (⚖ S-2):** Stripe says cards generated **for your own use** don't need PCI DSS for Issuing activity. But a
  server executor handling the PAN to type it into a form is card data on our systems. Confirm the scope with Stripe or
  a QSA before tier 2's executor exists.

---

## 7. Tests

1. `test_money_readback`: a deposit requirement → the read-back names the amount, currency, payee, purpose and
   refundability; a changed amount → a new hash, and the old yes is void.
2. `test_no_card_on_phone`: the call brief never contains a card or PAN field; the `_MONEY` reading still makes a
   money "yes" `unclear`.
3. `test_tier0_flow`: venue asks for a deposit → guest yes → venue asked for a link → `payer='guest_direct'` recorded;
   receipt line present.
4. `test_issuing_controls` (tier 2, Stripe mocked):
   - the card is created with `per_authorization` = the amount, the allowed categories and `['ES','PT']`;
   - the auth webhook approves the first authorisation ≤ amount and declines a second;
   - the card is cancelled after the first.
5. `test_refund_mirror`: an Issuing refund transaction → `Refund.create` on the guest's PaymentIntent for the same
   amount, once (idempotent).
6. `test_no_pan_stored`: grep the schema and the code. No column or log line can hold a card number; the vault's Luhn
   guard (`vault/guard.py:51`) runs on payment_request text fields.
7. `test_saved_card_mock_gone`: `SASHA_SAVED_CARD_LAST4` and `saved_card_payload` are removed (`conductor.py:643–664`),
   or gated so they never render to a guest.

## 8. Build order

1. **Remove or gate the saved-card mock** (rule 4) and **tier 0** (no money touches us). Migration 024. Tests 1, 2, 3,
   7.
2. Receipts with the money line (§5).
3. **Stripe Issuing application** (the founder, in the Dashboard) and **counsel S-1/S-2**, in parallel.
4. Tier 2 behind a flag, only after the written view and the browser executor (tests 4–6).
5. Tier 1 for US and Canadian guests, after the browser executor.

## Founder decisions

- **P-1:** Kanoe's fee on deposits, if any.
- **P-2:** apply for Issuing now (it takes Stripe's review time) or after counsel.
- **P-3:** which tier the pilot hotels' guests get (default: tier 0 only).

---

## Built, Sasha 109–110 (2 Oct 2026): step 1, the mock removed and tier 0

- **The mock card is gone (test 7).**
  - `SAVED_CARD_LAST4`, the "ending 1003" question and the branch that said a payment was done (with none made) are
    removed from `app/services/conductor.py`.
  - "Book it" now opens the real payment: one offer → `await_payment_item` (the payment popup); the whole trip →
    `await_payment` (Stripe Checkout). Sasha says nothing is charged or booked until the payment goes through.
  - `POST /api/payments/reserve` refuses `payment_method: saved_card`.
  - The You tab no longer shows "card ending …".
- **Tier 0:**
  - **The call's rule (`calls.DEPOSIT_RULE`):** agree to no deposit and give no card; ask how they take it (a payment
    link to the guest is best); say the guest pays them directly; get the amount. `_MONEY` still makes a money "yes"
    unclear.
  - **After the call (`payments_t0.after_call`, from `call_routes._follow_up`):** a payment request, once per booking.
    It carries the venue's own words, the amount if they said one, and a three-line read-back with its hash. On
    WhatsApp, ONE sentence and Yes/No. **No confirmation call is placed for a deposit-unclear call.**
  - **On the yes (`POST /api/booking/payments/{id}/approve`, hash-bound):** the venue is asked, in writing, to send the
    guest its own payment link (a text to its published mobile when venue texts are on, else an email).
    `payer = guest_direct`.
- **`CONSTRAINTS` is unchanged** (`no_deposit: true, no_card: true`). Stored reservation objects and their hashes
  depend on its keys; tier 0 is expressed by the call rule and the payment request instead.
- **Migration 024** is drafted, with two additions: the stored read-back, and one open request per booking and purpose.
- **Not built (parked by EU 120):** tiers 1 and 2, the receipt's money line in the email (§5; WhatsApp says it), and the
  Stripe SDK upgrade.
