# Sasha 330 · "give me a button": the cancel read-back's Yes / No

Tyler, 3 Nov 16:38: "give me a button".

The cancel read-back ("Cancel Taberna Sandbox, Fri 20 Nov 22:00, 2 people, ref SBX-ABC123?") was said and drawn with no buttons: on
/s2 `RENDER["cancel_venue"]` is `"trip"`, so `render()` returned nothing for it; on WhatsApp no read-back event reached `wa_agent`, so
no reply buttons either. He had to type "yes, cancel it".

## Root test (written before the code)

### THE ONE PLACE a read-back gets its buttons

**`app/agent/sasha.py` `yes_buttons(tool, res)`** builds `{ask, choices, read_back_id}` for every read-back that needs a yes. Every
render of such a read-back takes its buttons from it, and from nowhere else:

| read-back | tool (render) | choices | where the yes goes |
|---|---|---|---|
| **book** (a venue) | `hold_venue` / `book_venue`, `awaiting_yes` | the tool's own (`voice.KANOE_CHOICES` "Yes, send it" · `booking_decide.CALL_CHOICES` / `OK_CHOICES` · the platform question's `pick:<option>`) | `card_tap` → `venues.answer_card` (unchanged) |
| **pay** (the trip) | `hold_booking` | `voice.PAY_CHOICES`: "Yes, book it" / "No" as `say:<words>` | the tap sends those words as the person's message → the model → `book(approval.said)` (unchanged) |
| **cancel** (a venue booking) | `cancel_venue`, `awaiting_yes` | `voice.CANCEL_CHOICES`: "Yes, cancel it" (`cancel`) / "No, keep it" (`keep`) | `card_tap` → `venues.cancel_card` → `_cancel_act` (the existing path) |

- **/s2** draws every one of them with the SAME component, `CallCard` (`frontend/app/s2/S2App.tsx`): `CardView` picks it when the
  read-back has `choices` and a `read_back_id`. No second card, no second button set. `cancel` joins the gold YES set.
- **WhatsApp** draws the SAME `choices` as reply buttons (`booking_signer/wa_agent.py` `_buttons`): `cancel` / `keep` →
  `card:<read_back_id>:<route>`, which goes to the SAME `card_tap`; `say:<words>` stays `say:<words>` (typed words, as WhatsApp's list
  rows already do). The older booking buttons (`send` / `call` / `page`) keep WhatsApp's typed "Yes" / "No" (`yn:`), as before.

### THE ONE CLAIM: a tap counts once, only for its read-back

`card_tap` sets `ctx.idem = "card_tap:<account>:<read_back_id>:<choice>"` and the act claims it durably (`agapi/v0.py claim`). That is
the claim the booking card already uses; the cancel's Yes and No use it too, from /s2 and from WhatsApp:
- **Yes, cancel it** → `venues.cancel_card` → `_cancel_act(said="Yes, cancel it")`: the held `_CANCEL` read-back (its `read_back_id`
  must match the card's), its rules unchanged — an explicit yes (`yes_to_cancel`) in a LATER turn than the read-back
  (`held["at"] < ctx.started`), the ONE-YES gate (CR 76: `yes_gate.heard` → `check` at the claim, on S2 and WhatsApp), then
  `VS.cancel_submit` (`venue.cancel_booking` with the in-app tap / their verified WhatsApp).
- **No, keep it** → the held cancel dropped (and its one-yes read-back), nothing sent: "Kept — nothing changed."
- **A second tap on the same card** (either button, either surface) → nothing is sent and AgAPI is not called; one short line:
  "That card's already answered." (the read-back is gone, or the claim is already taken).
- **Typed** "yes, cancel it" / "no" still work exactly as before (the model, `cancel_venue` with `approval.said`).

### Which read-backs need a yes — honestly

- **book** (venue): its own choices already; unchanged, now built in the one place. A venue read-back with NO card of its own (the
  plain "Shall I send this to …?" read-back, typed yes until now) gets the pay read-back's typed-word taps ("Yes, book it" / "No"),
  for the same reason: its yes is `book_venue`'s `yes_to_book` on their words. `_hold` now puts the card's id on it (`read_back_id`:
  AgAPI's, else the read-back's sha).
- **pay** (`hold_booking`): its yes MUST be the person's words to `book()` (`yes_to_book`, the CR 76 gate binds it to the read-back
  they heard). A tap cannot be that yes under today's rules, so its buttons are **typed-word taps** — the tap sends "Yes, book it" as
  their own message, exactly how WhatsApp's [Yes] has always worked (`yn:yes` → "Yes" in a later turn) and how /s2's one-question card
  (`KindAsk`) sends its taps. Nothing bypasses `book()`'s yes.
- **cancel** (`cancel_venue`): the tap IS the yes (as the booking card's), through the same claim.
- Not in scope (their own read-back cards, no buttons today, unchanged): `send_email`, `send_whatsapp`, `hotel_request`, and s2_manage's
  `running_late` / `change_booking` / `cancel_booking`.

### Second copies: PATCH

**No second button set.** The one test (`tests/test_s330.py` `TheOnePlace`) enumerates book / pay / cancel and checks each render's
buttons are `yes_buttons`' output, that `render()` builds `choices` nowhere else, and that S2App has one `CallCard`.

**PATCH (pre-existing, not new): WhatsApp's literal `[Yes] [No]` (`yn:yes` / `yn:no`) for the venue booking read-backs** whose
choices are `send` / `call` / `page`. Those are a second drawing of the booking's yes on WhatsApp (typed "Yes" into a later turn, claimed
once by the act's own read-back-bound claim — `v0._act_bound_to` + the one-yes gate — not by `card_tap`). Moving them onto `card_tap`
changes how a WhatsApp booking is approved (`answer_card` on WhatsApp's verified number), which is outside this ticket.
