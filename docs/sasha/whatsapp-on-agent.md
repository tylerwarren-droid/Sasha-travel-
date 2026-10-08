# WhatsApp on the /next agent: the cutover (design only)

*Sasha 212 H, 8 Oct 2026. A design: nothing here is built. The architecture as it stands today is
`docs/sasha/whatsapp-architecture.md` (EU 186). This document says what changes, what's retired, how it's gated, and how
it's rolled back.*

---

## 1. The idea in five lines

1. **The same agent.** A WhatsApp message is one turn of the /next agent (`app.agent.sasha.turn`) with the same AgAPI
   tools, guards and persona. The older engine behind WhatsApp (`wa_brain.web_turn` → `conductor`) is retired.
2. **Same front door.** The webhook, identity, de-duplication (034), the per-number lock, voice notes, STOP/START and the
   strict spaces stay exactly as they are. The agent sits where the engine sat.
3. **The phone is the human step,** as it already is: Tap to pay (Apple Pay), Tap to finish (a CAPTCHA), a platform's
   page, and a drafted message to send.
4. **The same rules.** The yes is a later turn than the read-back; booked only from Pacioli; one total; no internals; no
   test disclaimers (the TEST tag stays on the checkout and the cards).
5. **Twilio today, Meta's Cloud API as an option.** One sender interface, two adapters, so the switch is a configuration
   change rather than a rewrite.

---

## 2. The turn, before and after

```
 Twilio webhook → inbound_phone.sms → guest_whatsapp.dispatch → _turn (lock) → turn():
   1 voice note → Deepgram                                        (kept)
   2 STOP / START                                                 (kept)
   3 SPACES → products.whatsapp.product_turn (strict)             (kept; CampusMe becomes an agent skill later — CR 54)
   4 _answer_pending  (buttons, picks, the guided trip's state)   → RETIRED for agent accounts
   5 _new_request     (HELP, flights, hotels, venues, ladder…)    → RETIRED for agent accounts (HELP and "reset" kept)
   6 wa_brain.web_turn → conductor                                → REPLACED by wa_agent.turn → app.agent.sasha.turn
```

**`wa_agent.turn(ch, text)`** is new, about 200 lines:
- **History:** `guest_wa_state.history` (the last 20 turns, as `{role, content}`), the same shape /next sends.
- **Session id:** `wa-<hash16>` of the number, so openers and acknowledgements are tracked per conversation.
- **Its events, as WhatsApp messages:**

| Agent event | On WhatsApp |
|---|---|
| `say` / `text` | One message per step: the display text (digits kept; nothing is spoken). Split at sentences under 1,600 characters. |
| `filler` | Not sent: a chat has no silence to fill. Optional: a typing indicator on the Meta adapter. |
| `render flights` (the proposal's cards) | One message per leg: up to 5 numbered options, the chosen one marked "✓ in your trip", with reply buttons "1"…"5". A tap becomes the card's own pick words ("the Iberia flight out at 08:30"), so the agent swaps it. |
| `render total` | One line: "about €X all in · flights quoted, hotels estimated · TEST". |
| `render venues` | The existing photo cards (`_photos_within`, at most 3) with "Choose" buttons. A tap becomes "<venue name>, please". |
| `render read_back` / `hold_*` awaiting a yes | The summary plus quick replies [Yes] [Not yet]. A tap is the next turn's words ("Yes"), so the "later turn" rule holds by construction. |
| `trip_changed` / Pacioli | The itinerary link (`/next?tab=trip`) when something lands. |
| Live events (212 A: booked / failed) | Already told on WhatsApp by `paid_watch._tell`. Unified: the same `words_for` text, within the 24-hour window or as the `booked` template outside it. |

**Approval:** a typed "yes" or a [Yes] tap is passed as the real words of that turn (`approval.said`). `explicit_yes`
and the `read_back_first` rule apply unchanged.

**Media in:** a photo goes to the agent as a note ("📷 a photo"), as today's engine does. Documents for the spaces stay
in the spaces.

---

## 3. What's retired (kept dormant until the rollback window closes, then deleted)

- `wa_brain.web_turn` and the WhatsApp path into `conductor.conduct`.
- The `_new_request` handlers the agent's tools now cover:
  - flights and hotels → `propose_trip`, `search_flights`, `choose_offer`, `search_stays`, `swap_stay`;
  - venues and the ladder → `search_venues`, `read_booking_route`, `hold_venue`, `book_venue`;
  - cancel → `cancel_venue`;
  - receipts and itinerary → `get_status`, `get_trip`;
  - the combo spa demo.
- **Kept:** HELP, "reset the demo", STOP/START, LINK, invitations, forwarded confirmations (evidence), and the captcha
  test.
- `_answer_pending` kinds that belong to the retired handlers: `pick`, `ladder`, `confirm`, `plan_link`, `link`, the
  guided trip's numbered flights, and `so:` / `amb:`.
- `guest_whatsapp._prepare_or_ask`, `_approve` and `_send_link`: the agent reaches the same routes through
  `agapi/venues.py`. They stay as long as the web's ChatBooking card uses them; they are not WhatsApp-specific.

---

## 4. Transport: one sender, two adapters

```
class Transport:            # guest_whatsapp.Sender today, generalised
    send_text(to, from_, text)
    send_buttons(to, from_, text, buttons[≤3])         # quick replies
    send_list(to, from_, text, rows[≤10])              # a flight list beyond 3 options
    send_media(to, from_, image_url, caption, buttons)
    send_template(to, from_, name, lang, variables)     # outside the 24-hour window
    parse_inbound(request) → {sid, from, to, body, button_payload, media[]}
    verify(request) → bool
```

| | Twilio (today) | Meta Cloud API (the option being prototyped) |
|---|---|---|
| Webhook | `POST /api/booking/twilio/sms`, HMAC-SHA1 `X-Twilio-Signature` | `POST /api/booking/meta/whatsapp`, `X-Hub-Signature-256` (app secret); `GET` verify-token handshake |
| Message id (de-dup, 034) | `MessageSid` (`SM…`/`MM…`) | `wamid.…` — **`guest_inbound_sids.message_sid`'s check constraint must widen**: a migration, drafted for the founder |
| Buttons | Twilio Content (one-off) quick replies | interactive `button` (3) and `list` (10 rows) — native |
| Templates | Content templates mapped to Meta's | Meta templates directly (`tap_to_pay`, `tap_to_finish`, `booked`) |
| Media | URLs | URLs, or uploaded media ids |
| Typing | none | `typing_indicator` on read |
| Sender | +44 7915 914215 via Twilio | the same number, migrated to a Meta-hosted phone_number_id (one-way; Twilio no longer receives) |

**Switch:** `SASHA_WA_TRANSPORT=twilio|meta`. Both webhooks can be live at once during the move; the de-dup table keeps
one turn per message whichever route it came in on.

---

## 5. Gate

A new gate step, **WHATSAPP-AGENT**: the voice-loop's 15 conversations replayed through the WhatsApp path, in-process,
with the captured sender (no live messages).

1. Each scripted line goes in as a signed Twilio payload: `dispatch` → `_turn` → `wa_agent.turn`.
2. Button taps are replayed as `button_payload`s.
3. Checks:
   - the same as /next's: no process talk, no test disclaimers, one total, the proposal offered, flights in it, the
     payment link once and only after the yes;
   - plus WhatsApp's own:
     - every message under 1,600 characters;
     - at most 3 buttons a message;
     - a tap maps to the right tool (`choose_offer`, `hold_venue`, `book`);
     - no message outside the 24-hour window without a template;
     - no turn runs twice for one message id;
     - a turn's messages leave in order, spaced (the 3.1 s rule).
4. The venue suite's routes through WhatsApp: a platform page, Tap to finish, an email, an Instagram/WhatsApp draft (never
   "booked").
5. The spaces' 123 WhatsApp tests keep running unchanged: the spaces come before the agent.

The Meta adapter gets its own offline suite: signature, verify handshake, `wamid` de-dup, interactive payload parsing,
template sends.

---

## 6. Rollout

1. **Flag per account:** `SASHA_WA_ENGINE=classic|agent`, plus `SASHA_WA_AGENT_ACCOUNTS` (an allowlist).
2. **Order:**
   1. the founder's account;
   2. scratch guests in the gate;
   3. the allowlist (the pilot);
   4. everyone.
3. **Optional shadow week:** the agent runs beside the classic engine for allowlisted accounts and sends nothing; the two
   replies are logged side by side for review.
4. Each step is a separate ticket, and each one ships only behind a passing gate.

## 7. Rollback

- **Instant:** remove the account from `SASHA_WA_AGENT_ACCOUNTS`, or set `SASHA_WA_ENGINE=classic` (a Railway variable;
  the service restarts in about a minute).
- **State stays compatible:** both engines read and write `guest_wa_state.history` as `{role, content}`. On a switch the
  open `pending` is cleared, so no half-finished button from one engine reaches the other.
- **Bookings are unaffected:** both engines book through the same routes, and Pacioli's rows are the same rows.
- **Transport rollback:** `SASHA_WA_TRANSPORT=twilio`. Only possible while the number is still on Twilio: once it's
  migrated to Meta, a move back is a re-registration (days). So the transport moves last, after the engine has been
  stable on Twilio.

## 8. Risks and how each is met

| Risk | Met by |
|---|---|
| Agent turns take 5–30 s; WhatsApp feels silent | a typing indicator (Meta); one short "on it" text only past 8 s (as the voice "nearly there") |
| Long replies | sentence-split under 1,600 characters; the persona's "a sentence or two" |
| A tap and a typed reply race | the per-number lock (kept) |
| The 24-hour window for unprompted news (booked, a Duffel change) | the `booked` and `tap_to_pay` templates (Meta approval pending today) |
| Cost per message (an agent turn is dearer than a handler) | measured in shadow week; prompt caching is already on |
| The spaces and the agent fighting over a message | strict spaces run first and keep it; the agent never sees a space's message |

## 9. Tickets (proposed)

1. `wa_agent.turn` + the event → message mapping, behind the flag (founder only), with the WHATSAPP-AGENT gate step.
2. Retire the covered handlers for agent accounts; HELP and "reset" kept.
3. Shadow week for the allowlist; the cost and latency readout.
4. The transport interface; Twilio moved behind it, no behaviour change.
5. The Meta adapter + its offline suite; the `guest_inbound_sids` constraint migration (drafted for the founder).
6. Number migration to Meta, after the engine has been stable on Twilio for a week.
