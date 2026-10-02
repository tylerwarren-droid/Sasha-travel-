# S-82 · Gmail, read-only: booking confirmations, cancellations and bills found in the guest's inbox

> ✅ **Founder defaults (EU 120):** M-1 = `gmail.readonly`, read narrowly as §2. M-2 = **"beta, by invitation"** (testing mode, no CASA yet). M-3 = **rules first**; the model only per §1 M-3.

*EU session, 2 Oct 2026 (EU 119), spec ahead of the Sasha tab. Code at **`22ccc0e`**. Google read at source today.
Nothing built.*

## 0. Facts

**Google, at source:**
- **Scopes** (`developers.google.com/workspace/gmail/api/auth/scopes`): `gmail.readonly` (*"View your email messages
  and settings"*) and `gmail.metadata` (*"View your email message metadata such as labels and headers, but not the email
  body"*) are **restricted**.
- **The rule:** *"If you store restricted scope data on servers (or transmit), then you must go through a security
  assessment."*
- **Testing** (Google Cloud console help, via search):
  - up to **100 test users**;
  - **authorisations and refresh tokens expire 7 days** after consent;
  - the "unverified app" warning shows.
- **Production** (Google's restricted-scope verification pages, via search):
  - restricted-scope verification plus a **CASA security assessment** by a Google-approved assessor (the App Defense
    Alliance);
  - it is **repeated every 12 months**;
  - *"2–3 weeks for tier-2… 4–6 weeks for tier-3"*;
  - assessor fees *"ranging from $500 to $4,500 USD"*.

**Sasha at `22ccc0e`:**
- **No Gmail code, and no Google client library.**
- **The vault is built** (S-78). `kind 'oauth'` is refused by `vault/api.py:89–90` until S-79's callback creates it.
- **Reusable parsers:**
  - `followup.py:330` `reply_reading(text, o) -> {result: confirmed|proposed|declined|none, why, quote}`;
  - `followup.py:320` `own_words` (strips quoted text);
  - `cancel_routes.py:52` `cancel_reading(text)`;
  - `form_rung.py:316` `_REF` (localizador|referencia|reference|booking number|confirmation code|nº de reserva);
  - `heard.py:136` `asked_from`, `:186` `mismatches`.
- **Reservations to attach to:** `trip_items` (`provider_name`, `date_time`, `booking_reference`, `status`), read
  through `GET /api/booking/reservations` (`routes.py:484`, `store.py:375`).
- **Sasha's own inbound email** (venue replies to `act-…@booking.kanoe.ai`) is a **separate** path:
  `ladder_routes.py:355` → match → `followup.on_reply` (`followup.py:354`). S-82 doesn't change it.

---

## 1. Decisions

- **M-1, scope: `gmail.readonly`.** `gmail.metadata` would only show headers (from, subject, date), which is enough to
  **find** a confirmation but not to read its reference or time. Proposed: `gmail.readonly`, **read narrowly** (§2).
- **M-2, the security assessment.** Testing mode is fine for the founder plus ≤100 pilot users, with weekly
  re-consent. **Production needs CASA** (annual, $500–$4,500, weeks). Decide before promising Gmail to hotel pilots: the
  pilot pack should say "Gmail reading in beta, by invitation".
- **M-3, the model.** Rules-based parsing first. The model (Anthropic, US) reads an email body **only** when the rules
  can't, and only for a message already matched to a booking. ⚖ Google's **Limited Use** requirements (API Services
  User Data Policy) must be met: data used only for the user-facing feature, no training, no human reading without
  consent, no transfer except as needed for the feature. Counsel confirms that a model processor is within "as
  necessary to provide the feature", and the privacy notice names it.

---

## 2. Reading narrowly (minimisation by design)

- **Never list the whole inbox.** Each sync runs **one Gmail search** (`users.messages.list?q=`), built from:
  - **the last 90 days** (`newer_than:90d`);
  - **senders tied to the guest's bookings:** each `trip_items.provider_email`, the venue domains Sasha knows, and the
    platform domains (`thefork`, `eltenedor`, `fresha`, `covermanager`, `zenchef`, `opentable`, `booking.com`, …);
  - **OR** subject keywords: `(reserva OR booking OR reservation OR confirmación OR confirmation OR cancelación OR
    cancellation OR factura OR invoice OR receipt OR recibo)`.
- **Fetch only those messages** (`format=full` for a match, else nothing).
- **Store only:**
  - the Gmail message id;
  - a sha256 of the body;
  - **the extracted facts** (kind, venue, date and time, party, reference, amount, currency, cancellation flag);
  - the link to the `trip_item`.
- **No body is stored.** The guest opens the original in Gmail through a deep link.
- **A bill or receipt PDF** is attached (stored) **only** after the guest's yes for that one item (§4), and then it goes
  into the booking's record under S-53 retention.

---

## 3. Data (migration `025_mailbox.sql`, DRAFT, not applied; it depends on 021 and 022)

```sql
-- Preview: expect NULL
select to_regclass('public.mailbox_finds');
create table public.mailbox_links (
  account_id uuid primary key references auth.users(id) on delete cascade,
  vault_item_id uuid not null references public.vault_items(id) on delete cascade,   -- oauth, provider google.com, purpose gmail_read
  consent_at timestamptz not null, consent_wording_version text not null, consent_text_sha256 text not null,
  last_sync_at timestamptz, history_id text, needs_reconnect_at timestamptz
);
create table public.mailbox_finds (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references auth.users(id) on delete cascade,
  gmail_message_id text not null, body_sha256 text not null,
  kind text not null check (kind in ('confirmation','cancellation','change','bill','receipt','other')),
  facts jsonb not null,               -- {venue, at, party, reference, amount_minor, currency, cancellable_until} — extracted, never the body
  parsed_by text not null check (parsed_by in ('rules','model')),
  trip_item_id uuid references public.trip_items(id) on delete set null,
  match_basis text check (match_basis in ('reference','venue_and_time','sasha_ref')),
  offered_action text, action_status text not null default 'none' check (action_status in ('none','offered','accepted','declined','done')),
  found_at timestamptz not null default now(),
  unique (account_id, gmail_message_id)
);
alter table public.mailbox_links enable row level security;   -- backend only
alter table public.mailbox_finds enable row level security;
```

---

## 4. Matching and actions (after the guest's yes)

**Matching, in order:**
1. **A reference:** `facts.reference` equals `trip_items.booking_reference`.
2. **Sasha's own K-reference** in the body (as `inbound_phone.match_written`, `:314`).
3. **The venue and time:** a normalised `provider_name` matches, and `date_time` is within ±90 min.

No match → a **"found outside Sasha"** item (a booking the guest made themselves).

**What's offered** (one sentence, one yes each, never automatic):

| Find | Offer | On yes |
|---|---|---|
| a confirmation of a Sasha booking whose `trip_item` is `requested` / `unclear` | *"Casa Lucio's email confirms Thursday 21:00 for 2 (ref ABC123). Mark it confirmed?"* | `status='confirmed'`, `booking_reference` set. This is a **status write, so S-79's trigger updates the calendar** |
| a cancellation of a Sasha booking | *"Casa Lucio's email says your Thursday booking is cancelled. Update it?"* | `status='cancelled'` |
| a booking made outside Sasha | *"Your inbox has a booking at Zalacaín, Friday 14:00. Add it to your itinerary?"* | a new `trip_item` with `status='guest_booked'`, `payer`/presser `guest`; S-79 adds it to the calendar |
| a bill or invoice tied to a booking | *"There's a €48 receipt from Zalacaín for Friday. Attach it to the booking?"* | the PDF stored with the booking |
| a deposit request | *"Casa Lucio asks for a €20 deposit by link. Open it?"* | S-81 tier 0 (the guest pays on the venue's page) |

**"Confirmed" from an email follows the product's rule:** the venue's own words, read back, with the guest's yes
recorded (`approval.how = 'chat'`, `said` = the guest's words).

---

## 5. Code (new `backend/booking_signer/mailbox.py` + routes)

1. **OAuth:** reuse S-79's `/api/booking/google/connect` with an **incremental** scope request
   (`include_granted_scopes=true`, adding `gmail.readonly`) and its **own consent text**: *"Sasha will look in your
   Gmail only for emails about bookings, cancellations and bills from the last 90 days, keep only the details she needs
   (venue, date, reference, amount), and never store your emails. You can disconnect at any time."*
   - The vault item's `allowed_purposes` gains `gmail_read`; `vault.use_connection(…, purpose='gmail_read')`.
2. **Sync:**
   - `mailbox.sync(account)` runs on connect, then every 6 h, and on demand ("check my email");
   - it uses Gmail `history.list` from `history_id` after the first run (incremental);
   - `invalid_grant` → `needs_reconnect_at` + one message (as S-79 §6).
3. **Parse:** `mailbox.read(msg) -> (kind, facts, parsed_by)`:
   - rules first: `_REF`, `reply_reading`, `cancel_reading`, a date/time parser (**new**, with ES/EN/PT month words);
   - the amount regex `(€|EUR)\s?\d+[.,]?\d*`;
   - the **model only** if the rules give `none` **and** the message already matched a venue (M-3);
   - the **vault guard runs on extracted text** (`vault/guard.py:51` Luhn): a card number in an email is never
     extracted or stored.
4. **Offer:** findings produce chat or WhatsApp offers (S-75 `deliver`, inside the window or a utility template).
   Accept or decline routes are bound to the `mailbox_finds.id` plus a hash of the offer sentence.
5. **Disconnect:** revoke at Google, crypto-shred the vault item, **delete `mailbox_finds`** for the account (facts are
   kept only on `trip_items` the guest accepted).

---

## 6. Tests

1. `test_query_narrow`: the built Gmail `q` always has `newer_than:90d` and only booking senders or keywords. **No code
   path calls `messages.list` without `q`.**
2. `test_no_body_stored`: after a sync over fixtures, no `mailbox_finds` column contains body text (assert ≤ the facts
   keys; body_sha256 only).
3. `test_parsers`: Spanish and English confirmation, cancellation and invoice fixtures (TheFork, CoverManager, a
   restaurant's own email, a Fresha receipt) → the right kind and facts. A PAN in a fixture → never in the facts.
4. `test_match`: a reference match beats venue and time; ±90 min; no match → "found outside Sasha".
5. `test_offer_needs_yes`: no status changes without the accept route; accept with a stale offer hash → refused.
6. `test_model_gate`: the model is called only for a matched message the rules couldn't read (mock counts calls).
7. **Live** (the founder's Gmail, testing mode): book something by email, see the confirmation found and offered,
   accept it, and check the calendar updates (S-79). Disconnect → the finds are deleted, the token revoked.

## 7. Build order

021 + 022 + 025 applied → S-79's OAuth (shared) → §5.1–5.3 (tests 1–3, 6) → matching and offers (tests 4–5) → live
(test 7). **Production only after M-2** (CASA).

## Founder decisions

- **M-1:** `gmail.readonly` vs metadata only.
- **M-2:** when to start CASA, if Gmail is to leave testing.
- **M-3:** model parsing allowed for unmatched-by-rules messages (and counsel's Limited Use view).

---

## Built, Sasha 109–110 (2 Oct 2026): §5.1–5.5 in code, testing mode

- **`booking_signer/mailbox.py`:**
  - the one narrow search (`newer_than:90d` plus booking senders or booking words, always);
  - rules-first parsing (ES/EN/PT dates, the `_REF` reference, amounts, the K-reference);
  - the vault guard on what is extracted;
  - matching by reference, then K-reference, then venue ±90 min;
  - one-sentence offers stored with their hash (`offered_sentence`, one column added to 025), applied only on the yes
    (the status write, so S-79's trigger updates the calendar);
  - the 6-hourly sync (`SASHA_MAILBOX_LOOP`, only once Google is configured);
  - disconnect: revoke at Google, shred the vault item, delete the finds.
- **The connection is its own vault item** (purpose `gmail_read`), made through S-79's shared callback (state
  `product: gmail`), so Calendar and Gmail disconnect independently.
- **The model (M-3) is gated off** (`SASHA_MAILBOX_MODEL` unset): rules only until counsel's Limited Use view.
- **Not built yet:**
  - bill attachments (the PDF needs the guest's yes and a store);
  - the deposit-request offer (S-81 tier 0 takes over);
  - `history.list` incremental sync (each run is the narrow search).
- **Migration 025** is drafted. **Web:** the "Gmail (read-only, beta)" block. Tests: `tests/test_mailbox_s82.py`, 1–6.
