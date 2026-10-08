# Sasha on WhatsApp: the architecture as it is (for the CTO)

*EU 186, 8 Oct 2026. Read-only, from `origin/main` at `41d924e` (7 Oct 18:05) and this week's mailbox readouts
(#472–#490). It **supersedes** `S-71-whatsapp-via-twilio.md` and `S-75-whatsapp-interface.md`, which are out of
date (§6).*

**Paths** are under `backend/` unless shown in full.

**Marks:**
- ✅ live and covered by a test or a readout;
- ◐ live but partly covered or unverified;
- ○ not built.

---

## The 5-minute summary

1. **One Twilio WhatsApp number per environment**, +44 7915 914215 "KANOE" (the Twilio sandbox +1 415 523 8886 is
   the fallback).
   - It posts to **one webhook**, `POST /api/booking/twilio/sms` (`inbound_phone.sms`), with a signature check.
   - A message **to** a guest number (env `SASHA_GUEST_WHATSAPP_TO`) goes to `guest_whatsapp.dispatch`. **Anything
     else is treated as a venue** (logged, never answered).
2. **The phone number is the account.**
   - A number is bound to an account by `LINK ######` from the laptop. An unknown number gets an automatic private
     guest account (Sasha 153), with no proactive messages until consent.
3. **Every message runs one ordered pipeline** (`guest_whatsapp.turn`), under a per-number lock:
   1. voice notes → Deepgram;
   2. STOP / START;
   3. **the spaces** (Sasha, CampusMe, RelocateMe, EspañaMe; strict since Sasha 194, entered and left only by their
      word or button);
   4. Sasha's open questions and buttons;
   5. a fixed list of request handlers;
   6. the **web conversation engine** (`wa_brain.web_turn` → `conductor.conduct`).
4. **Bookings go through the AgAPI roles.**
   - **The guided trip (flights + stays) uses the trip basket:** Magellan suggests, Sherlock re-checks, Austen holds
     after the yes, Pacioli alone writes "booked".
   - **Venues use the ladder:** form, platform page, email, or call, after one bound yes.
   - **Duffel webhooks feed Pacioli.**
5. **The person's own steps happen on the phone:**
   - "Tap to pay" (Stripe TEST checkout, Apple Pay);
   - "tap to finish" (our hand-over page with any CAPTCHA, ticked by the person);
   - platform pages opened on the phone.
   - Signatures happen on paper: the PDFs are printed from the laptop.
6. **The platform** (project.kanoe.ai) shows the same account: journey tabs, Requests, Receipts. *"show me my trips"*
   on WhatsApp gives the same groups. The laptop hands off to the phone with one message.
7. **What isn't true yet:**
   - WhatsApp is **not** on the new `/next` agent; it still runs the older engine.
   - Meta business verification and the templates' approval are pending ◐.
   - **Payment-result and Duffel-change messages are probably never delivered**, because `last_to` isn't saved (R1).
   - There's no inbound de-duplication (R2).
   - The per-number lock holds only within one worker (R3).
   - The spaces have **no WhatsApp tests** (14 skipped, R4).
   - There's no staging environment (R6).

---

## 1. The picture

```
 Guest's phone (WhatsApp)                                                       Guest's laptop (project.kanoe.ai)
        │  text · voice note · photo · button tap                                  ▲ journey tabs · Requests · Receipts
        ▼                                                                          │ (plan_store.view + journeys)
 Twilio WhatsApp sender  +44 7915 914215 "KANOE"   (sandbox +1 415 523 8886 = fallback)
        │  POST /api/booking/twilio/sms   (HMAC-SHA1, TWILIO_AUTH_TOKEN)
        ▼
 inbound_phone.sms ──► To ∉ guest numbers ──► VENUE path: booking_inbound (dedupe on MessageSid), written.file → evidence
        │ To ∈ SASHA_GUEST_WHATSAPP_TO
        ▼
 guest_whatsapp.dispatch ── unknown number ─► LINK ###### · invitation · auto guest account (Sasha 153) · ONBOARD
        │ known number → account
        ▼
 guest_whatsapp._turn  (per-number asyncio lock)  → turn():
   1 voice note ─► Deepgram (nova-3 multi → nova-2 en) "🎙 I heard: …"
   2 STOP/START · reminders
   3 SPACES ─► products.whatsapp.product_turn  [sasha | campus | relocate | españa | AD]  (strict: own word/button only)
   4 _answer_pending  (open question / buttons: pick:, yes:, so:, amb:, …)
   5 _new_request: HELP · "reset the demo" · cancel · receipts · forwarded confirmation · itinerary · flights · hotels ·
                   combo/spa · reorder · invites · captcha test · start another · find venues · ladder …
   6 wa_brain.web_turn ─► app.services.conductor.conduct()   (the web's conversation engine; session wa-<hash16>)
        │
        ▼   AgAPI roles (code)
   MAGELLAN  search & suggest   (Duffel offers, plan stays, Google Places venues)  basket.suggest / sync_stays
   SHERLOCK  re-check           (offer live? price? the venue's route)            basket.refresh · venue_read
   AUSTEN    act after the yes  (choose · hold · Stripe checkout · Duffel order · ladder send)   basket.choose/hold · ladder
   PACIOLI   proof & truth      (booked/failed/cancelled + status line; Duffel webhooks)  basket.booked/… · duffel_webhook
        │
        ▼
 Replies: deliver() (24-h window; opted-out refused)  ── text · media cards (≤3 + late photos) · quick-reply buttons
          (Twilio Content, one-off) · Meta templates outside the window (tap_to_pay, tap_to_finish; en/es)
        │
        ▼
 PHONE-ONLY HUMAN STEPS:  Apple Pay on Stripe TEST checkout · "tap to finish" (CAPTCHA ticked by the person) ·
                          platform page (TheFork/CoverManager…) booked in the person's own browser · paper signatures
```

---

## 2. Each part

| Part | What it does | File · function | Reads / writes | Tests |
|---|---|---|---|---|
| **Webhook** | receives every SMS and WhatsApp message; checks the Twilio signature; separates guests from venues | `inbound_phone.py:sms():228`, `_verified():75`, `signature_ok():49`, `_channel_and_number():59` | `booking_inbound` (venue path, deduped) | `test_inbound_phone.py`, `test_guest_whatsapp_s75.py` (signature) ✅ |
| **Dispatch** | guest vs venue; unknown numbers (LINK, invitation, auto guest, ONBOARD) | `guest_whatsapp.dispatch():482`, `guest_numbers():125` | `guest_channels`, `guest_link_codes` | `test_guest_whatsapp_s75.py`, `test_auto_guests_s153.py` ✅ |
| **Turn + lock** | one turn per number at a time; runs in the background, returns empty TwiML | `_turn():560` (`_TURN_LOCKS`), `turn():628` | `guest_wa_state` (history 20, pending, last_inbound_at, link_tries) | ◐ (lock: single worker only) |
| **Voice notes** | the audio from Twilio (retried; without creds on 404) → Deepgram → text | `voice_text():572` | — | `test_guest_whatsapp_s75.py` ✅ |
| **Spaces** | Sasha / CampusMe / RelocateMe / EspañaMe / AD; strict (`SASHA_SPACES` ≠ `loose`); entry `_CAMPUS`, `_RELOC`, `_HEALTH`, `_DILIGENCE`, button prefixes, typo matching; exit `_EXIT` (exit / **sasha** / back / quit / salir); label *"You're in CampusMe — say 'sasha' for travel"* (founder only) | `products/whatsapp.py:product_turn`, `:30–40`, `:103`, `_key:193`; `switching.label_space():45` | `product_cases` (`kind=conversation`, key `acct:<account>`), mirrored in `guest_wa_state.pending` | **gate SPACES runs on the web only; 14 WhatsApp tests skipped since Sasha 194** ◐ |
| **Open questions** | buttons and answers: picks, yes/no, start-over, ambiguity, the guided trip's numbered flights | `_answer_pending():1786` | `guest_wa_state.pending` | `test_flight_pick_s182.py`, `test_guest_whatsapp_s75.py` ✅ |
| **Request handlers** | HELP, reset, cancel, receipts, forwarded confirmations, itinerary, flights, hotels, spa, invites, captcha test, start another, venue search and ladder | `_new_request():862` | `trip_items`, `booking_*` | partly ◐ |
| **Conversation engine** | everything else, plus the guided trip (plan → flights → basket → "book it") | `wa_brain.web_turn():513` → `conductor.conduct` | `trips` (plans), `trip_basket_items`, chat session cards | `test_wa_brain_s167.py`; gate BASKET (R5 via `web_turn`) ✅ |
| **Trip basket** (AgAPI) | suggested → chosen → pending_payment → booked/failed/cancelled; roles in code | `basket.py` (`suggest:121`, `refresh:159`, `choose:179`, `hold:215`, `booked:275`, `failed:280`, `cancelled:284`, `event:288`, `status_line:240`); `basket_book.pay():185`, `book_paid():208` | `trip_basket_items`, `basket_events`, `saved_passengers`, `trip_items` | gate BASKET 55+/55 ✅ |
| **Duffel webhooks** → Pacioli | signed events; cancellation or schedule change → the row + tell the guest | `duffel_webhook.py:webhook():127`, `handle():93` | `basket_events`, `trip_basket_items`, `trip_items` | gate `webhook_cases` ✅ (the WhatsApp message itself not tested, R1) |
| **Venue ladder** | the route (form, platform page, email, call), one bound yes, send | `ladder_of():2404`, `decision_of():2448`, `_prepare_or_ask():2527`, `_approve():2753`; `decide.py`, `yes.py` | `booking_forms`, `booking_emails`, `booking_links`, `booking_calls`, `trip_items` | gate REST/ladder ✅ |
| **Evidence (venues)** | forwarded confirmations, venue SMS, Gmail | `_forwarded_confirmation():1413` → `written.file():108`; `watch_gmail_confirmation:3078`; `mailbox.py` | `booking_inbound`, `booking_attempts`, `trip_items` | `test_written_s118.py` ✅ |
| **Outbound** | text, media, buttons; 3.1 s gap per number; 24-hour window; templates outside it | `Sender:303`, `quick_reply():314`, `deliver():393`, `_tell():2966`, `TEMPLATES:2959`, `sender_for():114` | — | `test_s159.py` (but it fakes `get_state`, R1) ◐ |
| **Tap messages** | Tap to pay (Stripe checkout links only), tap to finish (our hand-over), platform page + Gmail watch | `tap_to_pay():2887`, `tap_to_finish():2935`, `tap_platform():2908` | in-memory `_TAPPED` | ◐ |
| **Identity** | number hash = channel; LINK codes (10 min, 5 tries/h); auto guests; founder detection | `wa_key()`, `/whatsapp/link` (`:3396–3445`), `guest_accounts.create_guest`, `identity.founder_account():106` | `guest_channels`, `guest_link_codes` | ✅ |
| **Platform bridge** | the same account's journeys on the laptop; *"show me my trips"*; laptop → phone hand-off | `plan_store.view`, `journeys.py`; `itinerary_q.TRIPS:177`, `trips_text():260`; `handoff_phone.send()` | `trips`, `trip_items`, `trip_basket_items` | `test_bridge_s165.py`; gate TABS ✅ |
| **Reset** | "reset the demo" (any account, its own TEST data; Reset/Keep buttons); per-space "start over" | `wa_brain.start_reset():713`, `reset_demo():623`; `products.whatsapp.reset_modes():79`, `start_over():93` | cancels TEST `trip_items`, plans, saved searches, unpaid links, `saved_passengers`; drops `acct:`/`web:` conversations; keeps files and real bookings | `test_restart_cr39.py`; gate ✅ |

---

## 3. The routes

### 3.1 Venue booking on WhatsApp
- **The ladder on WhatsApp (built):** form → the platform's own page (one message, booked in the person's own browser;
  Gmail confirms automatically) → email → call (only within 48 h or when asked). Each runs after **one bound yes**
  (hash + 15 min).
- **"Sasha writes, the guest sends via wa.me" (○ not on WhatsApp):**
  - The `whatsapp` rung exists in `ladder.py:102–105`, but `decide.Venue` has no WhatsApp field and `ladder_of`
    never offers it.
  - The wa.me link (a pre-written message to the venue's WhatsApp, which the person sends) exists **only on the web**
    (`frontend/app/components/ChatBooking.tsx:396–400`, a hard-coded Spanish message; `booking-helper/Ladder.tsx:358`
    with `lib/whatsapp-template.ts`).
  - **To build:**
    1. add the venue's WhatsApp to `decide.Venue`;
    2. offer the rung in `ladder_of`;
    3. send the person one message with the wa.me link.
- **Replies the person forwards** to Sasha → `written.file` (rules 1–4) → the item's evidence. **These go to
  `written.py`, not Pacioli.** Pacioli covers only the basket (flights and stays) today.

### 3.2 Templates and the 24-hour window
- **Inside 24 h of the person's last message:** free-form text, media and buttons.
- **Outside the window:** only a **Meta-approved template** (`_tell` with `template=`).
- **Templates in code (en/es by +34):**
  - `tap_to_pay`, `tap_to_finish` (used);
  - `booking_confirmed`, `booking_declined`, `booking_reminder` (defined, **unused**);
  - proactive messages use a separate env map, `SASHA_WA_TEMPLATES`.
- ◐ **Approval status isn't recorded in the repo.** Readouts #346/#349/#352 say 10 templates were submitted and
  pending, and Meta business verification is in review.
- Until approval, outside-window messages fall back to the sandbox, or aren't sent.

### 3.3 Identity
- **The phone number is the channel; the account is what it's linked to.**
  - **Linking:** the laptop shows a 6-digit `LINK ######` + a wa.me link (consent v3 hash, 10 min); the person sends
    it from their phone.
  - **Unknown numbers** get an automatic private guest account (consent `v0`, so no proactive messages).
  - **The founder** is `FOUNDER_ACCOUNT_ID`.
- **The "one-time link to the laptop"** is that LINK code. After that, web and WhatsApp share one account (`acct:` key
  for spaces; the same trips, basket and items).

### 3.4 Resets
- **"reset the demo"** (any account; its own data only): Reset / Keep buttons. It:
  - cancels TEST bookings, plans, saved searches and unpaid pay links;
  - clears session cards and saved passengers;
  - closes every space's conversation (web and WhatsApp);
  - leaves zero tabs (Sasha 181).
  - Real bookings, product files and the vault are kept.
- **Per space:** "start over" → *"Start <product> from the beginning? Your old file is kept, not deleted."* → yes
  drops the conversation, and the file stays.
- **CR 47-style archiving** of product files was a one-off data operation; it isn't in code.

---

## 4. Status, and the known risks

| Capability | Status |
|---|---|
| +44 sender, inbound/outbound, signature, LINK, auto guests, STOP | ✅ (#349) |
| Voice notes (Deepgram) | ✅ |
| Strict spaces (Sasha, CampusMe, RelocateMe, EspañaMe, AD) | ✅ live ◐ **no WhatsApp tests** (R4) |
| Guided trip on WhatsApp (numbered flights, basket, one total, Tap to pay) | ✅ via `web_turn` (gate BASKET R5/R6) |
| Real passengers asked once (`saved_passengers`) | ✅ (#482) |
| Duffel webhooks → Pacioli | ✅ the rows ◐ the WhatsApp message (R1) |
| Venue ladder (form, platform page + Gmail auto-confirm, email, call) | ✅ |
| **wa.me "Sasha writes, the guest sends"** | ○ on WhatsApp (web only) |
| Forwarded confirmations → evidence | ✅ via `written.py`; ○ not Pacioli |
| **WhatsApp on the `/next` agent** | ○ **not wired** (only the agent's `book` sends a Tap to pay WhatsApp) |
| Meta business verification; the 10 templates' approval | ◐ pending (#346, #349, #352), not recorded in the repo |
| Templates outside the window | ✅ tap_to_pay / tap_to_finish; ○ booking_* unused |
| Staging WhatsApp number / environment | ○ (production only) |

**Known risks (from the code at `41d924e`, not verified live):**

| # | Risk | Where | Effect | Fix |
|---|---|---|---|---|
| **R1** | **`last_to` is never saved** (`put_state` keeps only history / pending / last_inbound_at / link_tries; no column in `sql/020`) | `guest_whatsapp.py:192,280`; `paid_watch._tell():200` requires it | the **payment-result and Duffel cancellation / schedule-change WhatsApp messages are probably never sent**. `test_s159` fakes `get_state`, so it can't see this | persist `last_to` (a column, or inside `pending`); a gate case: paid → the message captured |
| **R2** | **No inbound de-duplication** for guests (`MessageSid` unchecked) | `dispatch`/`turn` | a Twilio retry runs the turn twice (two replies, possibly two actions) | store the `MessageSid`, unique, and skip repeats |
| **R3** | **The per-number lock is in-process** | `_TURN_LOCKS` | a second worker or replica = concurrent turns, last write wins | a Postgres advisory lock per account (`sasha-rebuild-plan.md` §2.2) |
| **R4** | **Spaces untested on WhatsApp** (gate SPACES runs on the web; 14 tests skipped since 194) | `tests/` (cr10, cr13, cr20, cr35) | a regression in strict spaces ships unseen | rewrite the 14 against strict spaces; SPACES through `GW.turn` in the gate |
| **R5** | **Two engines:** WhatsApp runs the regex pipeline + `conduct()`; `/next` is the agent | `wa_brain.web_turn` vs `app/agent/sasha.py` | different behaviour per channel; fixes land in one | wire WhatsApp to the agent behind a switch; one suite on both |
| **R6** | **No staging**; the gate runs on the production deploy (deterministic Duffel fixtures since #475) | `scripts/gate.py`, Railway `preDeployCommand` | a WhatsApp-only failure surfaces live | a staging Twilio number + environment |
| **R7** | **The template approval state is unknown** in code | `TEMPLATES`, `SASHA_WA_TEMPLATES` | outside-window messages may silently fail | record status per SID; alert on a template send error |
| **R8** | **In-memory `_TAPPED`** de-duplication of tap messages | `tap_*` | lost on deploy: a duplicate tap after a restart | persist |
| **R9** | **Buttons are one-off Content templates per question** | `quick_reply():314` | a Content API call on every question (latency, quota) | reuse a fixed set |

---

## 5. Tests and gate (today)

- **Units:** `test_guest_whatsapp_s75.py` (FakeSender; dispatch/turn, LINK, STOP, voice, signature), `test_s159.py`,
  `test_wa_brain_s167.py`, `test_auto_guests_s153.py`, `test_inbound_phone.py`, `test_written_s118.py`,
  `test_bridge_s165.py`, `test_restart_cr39.py`, `test_flight_pick_s182.py`, product turns
  (`test_relocation_m3_cr1.py`, `test_tarjeta_cr30.py`), and others.
- **Gate** (`scripts/gate.py`, Railway pre-deploy, Duffel replayed from fixtures):
  - flight W1–W4 (web) + V1 (voice via WhatsApp's flow);
  - core ITIN, REST, spa, GUIDED, TABS, SPACES (**web**);
  - BASKET (incl. R5 via `web_turn`, webhook cases);
  - agent.
- **Not covered:**
  - `dispatch → turn → deliver` end to end;
  - spaces on WhatsApp;
  - `last_to` and the payment-result message;
  - duplicate `MessageSid`;
  - more than one worker;
  - real template sends;
  - the webhook's WhatsApp message;
  - `tap_platform` → Gmail;
  - the agent on WhatsApp.

---

## 6. What's out of date in S-71 / S-75 (superseded by this document)

- **S-75** (and the `guest_whatsapp.py` docstring `:5–16`):
  - *"the model is never called"* → `wa_brain.web_turn` → `conduct()` (Sasha 167);
  - voice notes "phase 3" → Deepgram live (Sasha 165/173);
  - "link first, no first message" → automatic guest accounts (153);
  - templates outside the window → now sent for tap_to_pay / tap_to_finish (162);
  - button titles ≤ 25 → ≤ **20**;
  - `notify()` progress pushes → the `watch_*` tasks;
  - spaces and products absent → §2, §3.4.
- **S-71:** "Mode A (the guest sends from their own WhatsApp) until templates exist" → Mode A exists **only on the
  web** (wa.me link); the +44 business sender is in use (162/173); the guest pipeline it calls "later" is built.
