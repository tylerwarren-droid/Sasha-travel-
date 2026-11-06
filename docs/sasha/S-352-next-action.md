# Sasha 352 · every card shows its NEXT ACTION as a button, derived from the item's state; tapping = saying it

FROZEN BETA LIST: SME demo. This ticket follows the NO PATCHES rule.

## What was seen, and the cause

- **Tyler, S2, 6 Nov 10:45:** "YOUR TRIP · MAD → LHR · Iberia · €72.57 all in" offered only "See the whole trip". To book it, he had to know to type "book it".
  - **Cause:** each card drew its own buttons, and no card knew its item's state.
- **The 351 gate's VOICE LOOP 5:** "Book it." on a trip still being prepared went to the model. It tried `hold_booking` (no_trip), then `propose_trip` inside the booking turn.
  - **Cause:** the words and the action were not the same path. The model chose what "book it" meant.

## The one source

`backend/booking_signer/next_actions.py` is ONE table. An action's id maps to its button's label, the words it says, and the tool those words reach.

`for_trip(state)` gives a trip's buttons:

| State | Buttons |
|---|---|
| offers | Choose (the options card: a tap says the option) |
| prepared | See the trip |
| chosen | Book it · See the whole trip |
| held | Yes, book it |
| pending_payment | Pay |
| booked | Change · Cancel |

The state is the record's (`agapi.v0.trip_next`): the trip's basket rows, a read-back waiting for the yes, a trip being prepared, a search's offers. A pending payment or a booking always outranks an old read-back.

The group table:
- `for_group_row(row)`: planned → Book; needs vault → Invite; over limit → Book anyway; booked → Cancel.
- `for_group(rows)`: Book all, Invite everyone, The invoice.

Both are read from `groups.status_of`, the one classification.

## A tap IS the words, and the words are the action (one path)

- **On every surface, a button says its words.**
  - S2 and S1 send `say`.
  - WhatsApp's buttons are `say:` taps.
  - /group calls the same outcome (`group_outcome.run`) that the chat's tools call.
- **The turn routes the words to the action by code** (`next_actions.heard` → `agapi.v0.next_uses` → the turn's first step), the way Sasha 306 already routes change and cancel. "Book it" means the same whether it is typed, spoken or tapped:
  - **chosen:** `hold_booking`.
  - **held:** `book` with their own words (it IS their yes).
  - **prepared:** that trip's proposal from the prepared work (never a second plan), then `hold_booking`. Where they fly from is never assumed: without it, the conversation asks.
  - **offers or nothing:** the conversation, which asks which one.
- **The gate's judge:** a RE-plan needs a trip already on the record before the turn. A new line now fails any book-only turn whose hold found no trip ("didn't reach the trip").

## Surfaces

- **The ONE trip card** (`S2Cards.TripCard`, shared by S2 and S1 through SHARED_KINDS) shows `/api/booking/plan`'s `card.actions`.
- **The Booked card** carries Change and Cancel.
- **The master-list card** and **/group** (each row and the list) render the actions from the server. The page decides nothing about who gets which button.
- **WhatsApp:** the chosen-flight line, the master-list message and the "Picking up: …" hand-off carry the trip's next action as taps (three at most). The Trip tab, a view, is never a tap.

## Retired

- S2's own TripCard and its hard-wired "See the whole trip" button.
- /group's hand-built per-row buttons (passport → Invite, else Book; booked → Cancel).
- The fixed "Book all planned", "Invite everyone to the vault" and "The invoice" buttons. They come from the table now, so a button never shows without an action behind it.

## Not done here (said)

The yes to a read-back ("Yes." / "Yes, book it") still goes through the model to `book`, as before (the well-tested path). The table names it, and its button says those words.

## Tests

- `backend/tests/test_s352_next_action.py`: the table; the state; the words; the group rows; `next_uses`; a real turn where "Book it." runs `hold_booking` by code before any model step; WhatsApp taps.
- `frontend/scripts/next-action-352.test.mjs` (npm test): no surface hard-wires a trip or group button.

## Live proof (6 Nov, project.kanoe.ai, the test organiser, phone viewport, a fictional traveller; no card number entered)

**S2, Madrid → Paris, 25 Nov:**
1. After the pick turn (the model also read the trip back in it), the trip card showed [Yes, book it] · [See the whole trip].
2. A tap on [Yes, book it] brought up the Pay card (Stripe TEST embedded checkout), and the card then showed [Pay] · [See the whole trip].
3. An earlier run (Madrid → London) showed [Book it] · [See the whole trip] after the choice. The tap went straight to Pay, because a read-back had already run in the pick turn: the stale button the end-of-turn refresh now fixes.
4. Not done here: paying on Stripe TEST, after which the card shows [Change] · [Cancel]. That needs Stripe's test card typed on a production page, so it is left to Tyler.

**/group, Porto:**
- The list showed [Book all] · [Invite everyone to the vault].
- Ana, Luis and Marta (planned) each showed [Book]; Nuria Prieto (needs vault) showed [Invite].

**WhatsApp** (the production code against the organiser's live state; sent nothing):
- With the trip pending payment, the chosen-flight line and the "Picking up" hand-off carry [Pay] (`say:Pay here`).
- When chosen, the same line carries [Book it] (`say:Book it`).
- The organiser has no WhatsApp linked, so nothing was sent.

**VOICE LOOP 5:** in a209d897's gate it passed the suite (15/15), then the 6-run probe ("0 failure(s) in 6 run(s)"), so 7 of 7. In these runs the model proposed the trip at "From Madrid.", so "Book it." went to `hold_booking`. The prepared-trip branch (the 6 Nov failure) is held by the unit test.

**Found, not this class (said, not patched):**
- A pick on a slice whose earlier choice is pending payment fails in the store (AlreadyRecorded, `trip_basket_items_one_chosen_per_slice`). Sasha says "still waiting for payment", but no card is drawn.
- "Yes" with nothing waiting for a yes (a payment already pending) led the model to search again.
- frontend `presence-rule.test.mjs`: 273 and 281 fail on main as they do here (pre-existing).
