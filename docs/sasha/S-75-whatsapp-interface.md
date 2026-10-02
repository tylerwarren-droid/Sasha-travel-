# S-75 · Sasha on WhatsApp for guests: build-ready

*EU session, 2 Oct 2026 (EU 113). Written for the Sasha tab, which owns this repo's git. **Read-only**: Sasha's code was
read at `7c58986`, and the external sources (Meta, Twilio) at source today. Nothing was run, sent or changed.*

**What this is:** a guest uses Sasha **entirely through WhatsApp**. The request comes in, ranked venue cards go out,
then one confirmation sentence, a yes by button or reply, progress, the result and receipt, and "cancel X" followed by
one yes and the cancellation. All of it runs on the same server routes the web chat already uses.

**What it isn't:** the existing WhatsApp work.
- **S-48, S-61 and S-71 are about venues.** That's Sasha messaging a restaurant (Mode A from the guest's own WhatsApp;
  Mode B from Sasha's number to opted-in venues), with replies landing on the reservation through
  `POST /api/booking/twilio/sms`.
- **S-75 is the guest's side.** It's new, and it **must not break the venue side.** Venue messages are never answered
  automatically (`inbound_phone.py:225`, `return _twiml()   # never an automatic reply`).

---

## 0. ⛔ THE GATE: Meta's AI policy (read this before building anything)

**At source, 2 Oct 2026:** *Meta Terms for WhatsApp Business Platform*
(`facebook.com/legal/Meta-Terms-for-WhatsApp-Business-Platform`, page "last updated September 23, 2026").
- **Prohibited:** *"Providers and developers of artificial intelligence or machine learning technologies… are strictly
  prohibited from accessing or using the WhatsApp Business Platform"*, where such technology is **the primary
  functionality being offered, as determined by Meta.**
- **Permitted:** a business using AI that is **incidental or ancillary** to its own operations, and a business retaining
  an AI provider as a solution provider.
- **The data rule:** you *"may not directly or indirectly allow WhatsApp Business Platform Data… to be used to create,
  develop, train, or improve any machine learning or artificial intelligence systems"*. It survives termination.

**Already on record in this repo:**
- `docs/sasha/S-48-whatsapp-rung.md:28–34` read the same policy (in force 15 Jan 2026): general-purpose AI assistants
  are permitted only *"where Meta is legally required to permit this use case"*, while purpose-specific automation
  such as booking is allowed.
- It concluded: **"Sasha must not be offered to guests as a general assistant on WhatsApp… Counsel should confirm."**

**What that means for S-75 (the shape we build):**
1. **Sasha on WhatsApp is Kanoe's booking service for Kanoe's own customers.** It isn't "an AI you can chat with". The
   WhatsApp entry point answers **only** booking, change, cancellation, receipt and itinerary requests.
2. **Anything else gets one fixed sentence, not a model answer.** That covers general questions, essays, advice and
   chit-chat: *"On WhatsApp I can book, change or cancel things for you, and send your receipts. For anything else,
   open Sasha at {web link}."*
   - This is enforced **in code before the model is called** (§3, step 4). A prompt instruction alone isn't enough.
3. **No WhatsApp message content is used to train or improve any model.** That's already true (we call Anthropic's API
   and train nothing). §9 records it, and it's added to the privacy notice.
4. **⚠ Whether this shape is "ancillary" is Meta's determination, not ours.**
   - **Founder decision F-1:** get counsel's read (S-48 already asked for it) **before the production sender carries
     guests.**
   - The sandbox phase (§2) is internal testing only and doesn't need it.
   - I'm not claiming compliance. I'm recording the shape most likely to be compliant, and that Meta decides.

---

## 1. Architecture: one webhook, two audiences, the same booking routes

**One number, two audiences.** Sasha's own number **+447915914215** (S-70; in code at
`backend/tests/test_call_script_sasha88.py:98`, `SASHA_PHONE_NUMBER`) will receive **venue** replies (S-71) and
**guest** messages. The dispatch is by **who sent it**, decided before anything else:

```
inbound whatsapp:+X  →  signature_ok (inbound_phone.py:49–56)  →
   1. X is a LINKED GUEST (guest_channels, §4)          → guest pipeline (§3) — replies allowed
   2. X matches a VENUE call (STORE.call_for_number, :212) → venue path, unchanged — NEVER an auto-reply
   3. X is neither, and the body is a link code "LINK 1234" → linking (§4)
   4. X is neither                                        → one fixed onboarding sentence (§4), nothing stored but the hash
```

- **Guest first, then venue**, because a guest who is also a venue owner is still a guest when they write to us. A
  linked guest's number is never matched to a venue call.
- **Where:** `backend/booking_signer/inbound_phone.py:203–225` (`sms()`). Today it reads the channel
  (`_channel_and_number`, `:59–62`), matches a venue call and stores the message.
  - The change: right after `_verified` (`:205–207`), when `channel == "whatsapp"`, call
    `guest_whatsapp.dispatch(p)` (a new module, `backend/booking_signer/guest_whatsapp.py`).
  - If it returns a reply, respond with that TwiML. Otherwise fall through to the existing venue code, **byte for
    byte**.
- **A separate route is not used.** Twilio sends both audiences to the number's one webhook. Splitting by URL would
  need two numbers.

**The booking engine is not duplicated.** Every step calls the routes the web chat already calls, **server-side, in
process** (no HTTP to ourselves):
- discovery `V.find_venues` (`venue_read.py:577`) and `rank()` (`ranking.py:57`);
- the hand-off `booking_handoff` (`handoff.py:206`);
- the draft `booking_turn`;
- the call prepare/place in `call_routes.py`;
- forms, links and email in `ladder_routes.py` / `form_rung.py`;
- cancellation in `cancel_routes.py:170/185`;
- receipts via `guest_receipt.py`.

**⚠ Three things live only in the web frontend today and must move to the server first,** or WhatsApp would get a
second copy that drifts:

| Thing | Today | Moves to |
|---|---|---|
| The confirmation sentence | `frontend/app/components/ChatBookingCall.tsx:172` `` `Book ${venue} for ${d.count}…, under ${surname}?` `` (and the cancel one, `ChatCancel.tsx:121`) | `backend/booking_signer/sentences.py` `confirm_sentence(draft)` / `cancel_sentence(rc)`. The web reads it from the prepare response, so one owner |
| "Sasha's pick" | `ChatBooking.tsx:209–210`, `idx === 0 && state.phase === 'found' && !grey` | `ranking.py`: `rank()` marks `pick: true` on the first sellable result, and both channels read the field |
| What counts as a typed "yes" | `frontend/lib/chat-booking-bus.ts:21` `YES = /^\s*(yes|yeah|yep|go ahead|ok(ay)?|s[ií]|vale|claro|sim|oui|ja|confirm(ed)?)\b/i` | `backend/booking_signer/yes.py`, the same regex, exported. The web keeps its copy, and a test asserts the two are identical strings |

---

## 2. The two phases

**Phase 1: Twilio WhatsApp Sandbox.** Internal only, no Meta verification. Read at `twilio.com/docs/whatsapp/sandbox`,
2 Oct:
- Users join by sending `join <code>` to **+1 415 523 8886**, and *"You can only message end users who have joined your
  Sandbox."*
- *"The Sandbox session expires three days after joining."*
- *"The Sandbox number can only send one message every three seconds."*
- *"You can't use custom message templates with the Sandbox"*. Only three stock templates exist, so **receipts outside
  24 hours can't be tested here**. Inside the window they can.
- It uses the same webhook configured in the Sandbox settings. **Interactive content inside the window isn't documented
  for the sandbox.** Step 3 of §10 tests it and records the result.

**Phase 2: the production sender on +447915914215.**
- It follows S-71's two founder sittings: Twilio self sign-up, the "Sasha by Kanoe" display name, and Meta business
  verification with the AEAT certificate.
- Then gate F-1 (counsel).
- Then the utility templates (§6) are submitted through Twilio's Content Template Builder (*"WhatsApp reviews most
  templates… within minutes"*; *"Once you submit a template, it cannot be edited"*).
- **The number must be in a Twilio Messaging Service with Advanced Opt-Out** (§7).

---

## 3. The flow in WhatsApp, step by step

*Content types, read at `twilio.com/docs/content/content-types-overview`, 2 Oct:*
- `twilio/text`, `twilio/media`, `twilio/quick-reply` and `twilio/list-picker` can reply inside the 24-hour window
  without approval.
- `twilio/card` / `whatsapp/card`: *"Approval might be required to reply to inbound messages based on buttons types
  present"*.
- `twilio/carousel`: *"Approval required"*.
- **Button titles are max 25 characters** on WhatsApp.

| # | The guest | Sasha sends | Server, existing code |
|---|---|---|---|
| 1 | *"Dinner for 2 tomorrow at 9 near Retiro"* | (nothing yet) | `guest_whatsapp.dispatch` → the **scope gate** (step 4 below) → `conduct()` (`app/services/conductor.py:1783`), whose first moves are `booking_handoff` (`:1817–1818`) and `booking_turn` (`:1822–1823`). The turn is saved like the web chat's (`chat_store.save_turn`, `app/api/conductor.py:~131`), with `channel: "whatsapp"` |
| 2 | — | **Up to 3 venue cards**, each a `twilio/media` message: the photo from the venue's own site (`style.py:130`, `page["image"]`, the og:image, *"never a Google one"* `:104–106`), and as the body, `{name} · {rating_words} · {distance_words}`, prefixed **"Sasha's pick ·"** on the `pick` card. Then **one `twilio/quick-reply`**: "Which one?", with up to 3 buttons titled by venue name (≤25 chars, truncated with "…") and `ButtonPayload = "pick:<draft_id>:<venue_idx>"` | `find_venues` → `rank()` (§1 move 2). `rating_words` `ranking.py:21`, `distance_words` `venue_read.py:541` (*"never 'nearby'"*). ⚠ **Not `twilio/card` or `carousel`:** those may need template approval even in-session, and `media` + `quick-reply` is known to work in-session. A **4th or later** option goes in a `twilio/list-picker` ("More places") |
| 3 | taps a venue (or types its name or number) | **One confirmation sentence**, `confirm_sentence(draft)` (§1), as a `twilio/quick-reply` with two buttons, **"Yes, book it"** / "No". `ButtonPayload = "yes:<call_id>:<read_back_sha256[0:16]>"` | the existing prepare route for that venue's rung (call / form / email / link). It returns `read_back_sha256`. The read-back lines are sent **as text before** the buttons when a rung has them, so the guest sees what they're approving |
| 4 | taps **Yes**, or types "yes" / "vale" / "sí" | — | **The yes is bound to THIS card.** A button's payload names the call and the hash prefix. A typed yes binds to the **latest pending confirmation in this conversation only, within `APPROVAL_WINDOW` (15 min, `call_routes.py:48`)**, via `yes.py`; older ones are void. The approval is `{how: "whatsapp_button" or "whatsapp_text", said: <the button text or the typed words>}`. `call_routes.py:503` **widens** `("button","voice","chat")` to add `"whatsapp_button"`, `"whatsapp_text"`, and the same `said` requirement for text. The full hash must still match (`:497–499`); the payload's 16-char prefix is only for lookup |
| 5 | — | **Progress**, as text, sent when the state **changes** (`placing → ringing → answered → confirmed/failed`): *"Calling {venue} now."* / *"They've answered. Asking for 9pm."* | today the web **polls** `GET /calls/{id}` every 10 s (`ChatBookingCall.tsx:129–132`), and there is no server push. **New:** `guest_whatsapp.notify(call_id, state)` is called from the places the call row's status is written (the Bland webhook handling in `calls.py`, and the form/email/link rungs' status updates). That's a push, sent only if the guest's channel is WhatsApp. Never more than one message per state |
| 6 | — | **The result and receipt**, plain text: the venue's own words where they exist, the reference, and *"Who pressed it: {guest / Sasha by phone / Sasha by email}"* (BACKLOG item 1). Inside 24 h: `twilio/text`. **Outside 24 h:** the utility template `sasha_booking_receipt` (§6) | `guest_receipt.send_after_call` (`:110`) / `send_for_route` (`:188`) gain a `channel` argument. WhatsApp **in addition to** email (the email stays the record) |
| 7 | *"cancel the Retiro dinner"* | the cancellation sentence `cancel_sentence(rc)` + quick-reply **"Yes, cancel"** / "No", with `ButtonPayload = "cancel:<trip_item_id>:<sha16>"` | `booking_handoff` returns `booking_cancel` (`cancel_request`, `handoff.py:196`) → `GET /reservations/{id}/cancel` (`cancel_routes.py:170`) for the route and read-back |
| 8 | taps **Yes, cancel** | *"Cancelling with {venue} now."* then, **only once the venue's own words say so**, *"{venue} has cancelled your booking."* plus the receipt | `POST …/cancel` (`cancel_routes.py:185`), hash-checked (`:198`); `send_after_cancel` (`guest_receipt.py:146`); *"'Reservation cancelled' ONLY once the venue's own words say so"* (`cancel_routes.py:1–16`) |

**Step 0, the scope gate,** in `guest_whatsapp.py`, **before** `conduct()`:
- `booking_handoff(message, history)` is not None → booking/cancel path;
- or the message matches the receipt/itinerary/help intents (a small keyword set: "receipt", "my bookings",
  "itinerary", "help");
- **otherwise** the one fixed out-of-scope sentence (§0.2). **The model is never called** for it.
- This is what keeps WhatsApp-Sasha a booking service rather than a general assistant.

**Refusals** use the existing guest-words refusals (Sasha 96, `88059ae`): never a rule code or a setting's name.

---

## 4. Account linking by phone (the same reservations and itinerary)

**What exists:**
- `guest_contacts` (`backend/booking_signer/sql/015_guest_contacts.sql:10–17`): `account_id` → `auth.users`,
  `mobile_e164`, consent fields. **Not applied.**
- Its consent wording covers **only** giving the number to venues (`contacts.py:27`, *"Sasha will give your name and
  mobile to the places you ask her to book — and to nobody else."*).
- Reservations hang off `trips.owner_id` (`backend/migrations/001_initial_schema.sql:112–114`) and the booking tables'
  `account_id`.

**New migration `020_guest_channels.sql`** (for the founder's go, like 015 to 019; **draft only, not applied**):
```sql
-- Preview: expect 0 rows
select to_regclass('public.guest_channels');
create table public.guest_channels (
  account_id uuid not null references auth.users(id) on delete cascade,
  channel text not null check (channel in ('whatsapp')),
  wa_id_sha256 text not null,            -- sha256 of the E.164 number, as booking_inbound.from_key does (016:9–22)
  number_e164 text not null,             -- needed to SEND; never logged
  linked_at timestamptz not null default now(),
  consent_at timestamptz not null,
  consent_wording_version text not null,
  consent_text_sha256 text not null,
  opted_out_at timestamptz,              -- STOP (§7); a row with this set is never messaged
  primary key (channel, wa_id_sha256)
);
create unique index guest_channels_one_per_account on public.guest_channels (account_id, channel) where opted_out_at is null;
alter table public.guest_channels enable row level security;  -- backend only, no policies (as 015:3)
create table public.guest_link_codes (
  code text primary key, account_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(), used_at timestamptz
);
alter table public.guest_link_codes enable row level security;
```

**Linking flow (it proves possession of both the account and the WhatsApp number, with no SMS cost):**
1. **On the web** (signed in, S-62), Settings → "Use Sasha on WhatsApp":
   - the guest ticks the **new consent v2**: *"Sasha by Kanoe will message you on WhatsApp about the bookings you ask
     for: confirmations, progress and receipts. Reply STOP at any time to stop."* This meets Meta's opt-in rule
     (*"clearly state that a person is opting in… [and] the business's name"*, read at
     `developers.facebook.com/docs/whatsapp/overview/getting-opt-in`);
   - the server mints a 6-digit code in `guest_link_codes` (10-minute life, one use);
   - the page shows a **`wa.me/447915914215?text=LINK%20123456`** button, so the guest's own WhatsApp opens with the
     message ready, and they press send.
2. **Inbound** `LINK 123456` from `whatsapp:+X`: the code is valid, unused and not expired, so insert `guest_channels
   (account_id, 'whatsapp', sha256(X), X, consent…)`, mark the code used, and reply *"Linked. You can book with me here
   now."*
   - A wrong or expired code: *"That code didn't work. Get a new one at {link}."*
   - Rate-limit by `wa_id_sha256`: 5 tries an hour.
3. **Unknown sender, no code** (case 4 in §1): one fixed reply, *"Hi, I'm Sasha by Kanoe. To book on WhatsApp, link
   your account first: {link}."* We store nothing but the hash and timestamp (for rate limiting).
   - **Phone-first sign-up** (no web account) is **phase 3**, founder decision F-2. It needs Supabase phone auth or a
     WhatsApp-only account type.
4. **Unlink** on the web: delete the row, then a final *"Unlinked."*. On deletion of the account, cascade.

From then on, a linked number **is** the account: `chat_account` (`app/services/chat_account.py:19`) gets a sibling
`whatsapp_account(wa_id)` returning the same `account_id`. So reservations, the itinerary and `/reservations` are
shared with the web automatically.

---

## 5. Voice notes (later, phase 3)

- Inbound audio arrives as `MediaUrl0` with `MediaContentType0` `audio/ogg` (Twilio webhook docs).
- The plan: transcribe, then run as text through §3.
- **A voice note can never be the yes on its own:** the confirmation step always sends the quick-reply. A voice yes is
  accepted only as `how: "voice"` with the transcript as `said` (the rule already at `call_routes.py:503`), bound to
  the latest pending card, as in step 4.
- The media is fetched with Twilio Basic auth and **deleted** from our side after transcription (retention, S-53).
- Out of scope until F-3 (which transcription provider, and its DPA).

---

## 6. The 24-hour window and the templates

- *"Customer service windows are valid for 24 hours after the most recently received message, during which you can
  communicate with customers using free-form messages… To send a message outside the customer service window, you
  must use a pre-approved message template."* (`twilio.com/docs/whatsapp/api`, 2 Oct.)
- **`guest_whatsapp.send(account, kind, payload)`** decides by `last_inbound_at` (from `booking_inbound` for that
  hash): inside 24 h, free-form; outside, the matching **utility** template. With no template for that kind, nothing
  goes to WhatsApp and the email still does.

**Templates to submit** (all **utility**, never marketing; drafted with disclosure first, as S-49):

| Name | Text | When |
|---|---|---|
| `sasha_booking_result` | *"Sasha by Kanoe: {{1}} is booked for {{2}}. Reference {{3}}. Reply CANCEL to cancel, STOP to stop messages."* | a venue confirms after the window has closed (a callback hours later) |
| `sasha_cancel_result` | *"Sasha by Kanoe: your booking at {{1}} for {{2}} is cancelled, in the venue's words: {{3}}."* | the same, for a cancellation |
| `sasha_venue_replied` | *"Sasha by Kanoe: {{1}} replied about your booking for {{2}}. Open WhatsApp to read it."* | a venue's message arrives after the window has closed |

**Costs** (S-71's figures, read at source 1 Oct, saved raw in `docs/sasha/replies/`):
- Inside the window, every message is **free from Meta** plus Twilio's **$0.005** per message, in or out.
- A utility template **outside** the window: **Spain €0.0166**, **UK €0.0182**, plus $0.005.
- **A typical booking:** the guest's request, 3 cards, 1 quick-reply, the sentence, the yes, 2 or 3 progress messages,
  the receipt. That's about 10 in-session messages, so **≈ $0.05**, plus at most one template (≈ 2 cents) if the result
  lands after 24 h.
- The sandbox is free.

---

## 7. STOP and opt-out

- **Twilio, at source** (help.twilio.com, Advanced Opt-Out): *"If you are not using Advanced Opt-Out, Twilio's default,
  account-wide keyword-based opt-out handling system does not apply to WhatsApp senders."* With a Messaging Service and
  Advanced Opt-Out configured, STOP/START/HELP apply to WhatsApp senders too.
- So: **put +447915914215's WhatsApp sender in a Messaging Service with Advanced Opt-Out** (a founder console step,
  F-4), with STOP, PARAR, BAJA and ARRÊT added, and START to resume.
- **Our side, too,** because Twilio can't tell us about blocks (WhatsApp *"does not offer a way to be notified when a
  user has blocked your sender"*):
  - inbound `STOP` (or the extra keywords) from a linked guest sets `guest_channels.opted_out_at = now()`;
  - every send checks it first, and an opted-out guest gets **nothing** on WhatsApp (email receipts continue);
  - `START` clears it.
- **Venue STOP is separate and unchanged:** `stop.py`, venues are never contacted again.
- Guest STOP doesn't cancel bookings in progress. It only silences WhatsApp, and says so once: *"OK, no more WhatsApp
  messages. Your receipts still come by email."*

---

## 8. What is never done

- **No first contact to a guest who hasn't linked**, and no message to a number we only hold for venues.
  (`guest_contacts` is consent v1, *give to venues*. It's not consent to message the guest.)
- **No reply to a venue**, ever, from this path. The venue branch stays `return _twiml()` (`inbound_phone.py:225`).
- **No booking without the bound yes** (§3 step 4). The existing hash check stays the single gate.
- **No marketing templates.**
- **No model call for out-of-scope messages** (§3 step 0).
- **No WhatsApp data used to train anything** (§0, §9).

---

## 9. Privacy and GDPR

- **S-51 privacy notice** (`frontend/app/sasha-privacy/page.tsx`): add **Meta (WhatsApp) and Twilio as processors for
  guest messaging.** S-51 says Meta is *"named as a future processor"* and that Sasha-sent WhatsApp is *"not built"*,
  so both lines change when this ships.
- Add: *"WhatsApp messages are used only to carry out your bookings; they are never used to train any AI model."*
- **Retention:** `booking_inbound` bodies follow S-53's periods (`retention.py`).
- **Deletion:** account deletion cascades `guest_channels`, and S-78 (Vault) §9 adds a single "delete
  everything" endpoint that covers this too.

---

## 10. Build steps, in order (each ends with its tests green)

1. **Move the three frontend-only rules to the server** (§1 table): `sentences.py`, `pick` in `rank()`, and `yes.py`.
   The web reads the server's sentence and pick.
   - *Tests:* `confirm_sentence` equals the old frontend output for 5 fixtures; the `YES` regex string is identical in
     `yes.py` and `chat-booking-bus.ts`; `rank()` marks exactly one `pick`.
2. **`call_routes.py:503` accepts `whatsapp_button` / `whatsapp_text`**, with `said` required for text.
   - *Test:* the 422 for an empty `said`, and acceptance with it.
3. **The sandbox, read-only spike.** Point the Sandbox's inbound URL at a **new** dev route that only logs, to record
   whether `twilio/quick-reply` and `twilio/media` deliver in the sandbox and what the inbound `ButtonPayload` looks
   like. Write the result into this doc (§2).
4. **`guest_whatsapp.py`**: `dispatch` (§1 order), the scope gate (§3 step 0), `send` (§6 window logic), and `notify`
   (§3 step 5). It's wired at `inbound_phone.py` after `:205–207`.
   - *Tests:*
     - a venue's WhatsApp message produces **no** reply and the old storage, byte for byte;
     - an unlinked sender gets the one onboarding sentence;
     - a linked guest's "write me a poem" gets the out-of-scope sentence, and the model is **not** called (mocked);
     - "dinner for 2…" reaches `conduct()`.
5. **Migration 020** (founder's go) + **linking** (§4): mint code → inbound `LINK` → row.
   - *Tests:* the code works once, expires after 10 min, is rate-limited, and is bound to the right account.
6. **The card flow** (§3 steps 2–4), in-session only.
   - *Tests:*
     - 3 media cards + 1 quick-reply for 3 results, and a list-picker for more than 3;
     - button titles ≤ 25 characters;
     - a typed "vale" binds only to the latest pending card within 15 min;
     - a stale button payload (an old hash) is refused with the guest-words refusal.
7. **Progress push + receipts by channel** (§3 steps 5–6): `notify` at each status write, and `guest_receipt` gains
   `channel`.
   - *Tests:* one message per state change, never two; the email receipt is still sent.
8. **Cancel by WhatsApp** (§3 steps 7–8).
   - *Test:* "cancelled" is only sent after the venue's words (a fixture with no venue confirmation → *"Cancelling…"*
     only).
9. **STOP / START** (§7) on our side.
   - *Test:* an opted-out guest's send is a no-op that logs a reason; START resumes.
10. **Live, sandbox**, the founder's phone only: book a real form-rung venue (S-73 candidates) end to end, then cancel
    it. Record what's seen.
11. **Production** (after S-71's sittings, F-1 counsel and F-4 opt-out): submit the 3 utility templates, switch the
    sender, and link the founder's account first.
12. **Phase 3** (later): voice notes (F-3), phone-first sign-up (F-2).

## Founder decisions

- **F-1:** counsel on Meta's AI policy for this shape (§0). **Required before production carries guests.** Status (EU
  114): **still open.** **The sandbox build (§10 steps 1–10) proceeds internally**; steps 11–12 wait for F-1.
- **F-2:** phone-first sign-up without a web account (phase 3), or not.
- **F-3:** voice notes: the transcription provider and its DPA.
- **F-4:** the Messaging Service with Advanced Opt-Out on the production sender (a console step).
- **Numbering:** this is S-75 as instructed.

---

## Built, Sasha 102 (2 Oct 2026): steps 1–9 in code, sandbox only

- **Steps 1–2 (`bce9aa6`):**
  - `sentences.py` holds the confirmation and cancel sentences; the prepare and cancel-plan responses carry them, and
    the web shows the server's words.
  - `rank()` marks the pick per ordering (`pick`, `picks`), never a greyed place.
  - `yes.py` holds the yes pattern (identical to `chat-booking-bus.ts`; a test compares them) and the one approval rule.
    `whatsapp_button` and `whatsapp_text` are accepted at calls, forms, emails and cancels; typed ones need their words.
- **Steps 4–9 (`guest_whatsapp.py`):** dispatch, the scope gate, cards, the bound yes, progress, the result, cancel,
  and STOP/START. Plus migration **020** (draft, for chat to apply) and the web's "Use Sasha on WhatsApp" block on the
  booking page.
- **Where the build differs from the text above, and why:**
  1. **The model is never called on WhatsApp**, not even after the scope gate. The booking hand-off and drafts are
     deterministic, so the whole turn runs without `conduct()`. That's stricter than §3 step 0, and safer under §0.
  2. **The card photos** come from the venue's own og:image read directly (`style.page_text`: robots first). They don't
     come through `/venues/style`, which is a model call.
  3. **Guests are served only on the numbers in `SASHA_GUEST_WHATSAPP_TO`** (the sandbox's, +14155238886). On every
     other number, including Sasha's own +44 where venues write, the venue path runs byte for byte. On a guest number,
     a sender matching a venue call still takes the venue path.
  4. **Progress and the result** come from an in-process watcher started at the yes. It polls the call every 10 s for
     up to 8 minutes (the web chat's cadence) and sends one message per state change. It isn't a push from the
     status-write sites.
     - A server restart mid-call loses those WhatsApp messages, but **not** the email receipt, which is unchanged
       (`guest_receipt`).
     - A written cancellation is watched for 30 minutes; "cancelled" is said only once the reservation reads cancelled.
  5. **The rung order on WhatsApp** is the approved form, then the platform's slot link (the guest presses; they reply
     BOOKED), then a call. The web chat offers no form.
  6. **Migration 020 adds a third table, `guest_wa_state`**, keyed by the number's hash: the last 20 lines, the one
     pending question, the 24-hour window and the link tries.
     - An unlinked sender leaves only their hash and timestamps.
     - A password typed on WhatsApp is never written (S-78 guard).
  7. **One WhatsApp per account** (a plain unique index). Re-linking replaces the old number.
- **Not yet done:**
  - **step 3:** the sandbox's inbound URL is set in Twilio's console, and the founder sends the sandbox's
    `join <words>` from his phone;
  - **step 10:** the live sandbox run.
  - Until 020 is applied, a message on the sandbox number is logged and not answered, and venues are unaffected.
