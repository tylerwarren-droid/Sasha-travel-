# Sasha 384 — CR 203's Sasha half: no table at the asked time → AgAPI's options as taps; one tap books it

Decision: KANOE_DECISIONS 13 Nov 2026 18:44 — "Sasha offers ranked alternatives as taps … One tap books it. A slot with no table is not a
refusal, so the venue's page is never handed over while options remain."

## What Sasha read from `venue.submit_booking` before
`status`, `say`, `act_id`, `venue`, `route`, `reference`, `ask` (a stop's question, CR 161), `instructed` (CR 196) — and `hand_over.link`,
drawn as the "Tap to finish" (`venues._platform_result` → `_link_out`). `alternatives` was never read.

## Now (backend/agapi/venues.py)
- `alternatives_of(r)` — AgAPI's `alternatives`, exactly as given (rank, kind, venue, date, time, reason, `book`); nothing re-ranked,
  added or filtered.
- `_platform_result` → `_alternatives`: AgAPI's sentence word for word ("… tap one and I'll book it"), its options as taps
  (`alt:<rank>`, titled "21:45 · Sat 14 Nov" / "<venue> · 21:00"); no page, no link, no "Tap to finish" while any option remains — the
  page only for a true refusal (no alternatives). The card is the platform question's card (CR 161): S2 and /next draw its choices,
  WhatsApp draws them as buttons (≤3) or a list, each `card:<id>:alt:<rank>` → the same `card_tap`.
- The tap IS the instruction (`answer_card` "alt:<rank>" → `alternative_answer`): `venue.prepare_booking` with the option's own `book`
  terms and the SAME person → `_act` (the tap's words, "Book <venue> on <date> at <time> for <n>", are the CR 196 mandate's instruction;
  its proof is the tap's door) → `venue.submit_booking` → "Booking now: …". AgAPI deciding that option another way → the whole path
  (`hold_venue`). Never a second card. Typed words naming exactly one option ("the 21:45") book it the same way (`book_venue`).

## Not Sasha's (said)
- The line for "no table in the asked SERVICE at all" ("… a restaurant nearby at <time>, or lunch there instead?") is AgAPI's sentence
  to write; AgAPI's CR 203 never offers lunch for a dinner ask, and Sasha adds no option of her own. The 18:48 decision isn't in
  KANOE_DECISIONS.md yet.
- In the sandbox, `venue.prepare_booking` doesn't prepare Kanoe's CoverManager stand-in from its alternative's `book` terms (route
  "none"), so a tapped option can't be booked there end to end (see the report).

## Tests
`backend/tests/test_s384_alternatives_as_taps.py` — AgAPI's sentence and options exactly; no link while options exist; one tap → prepare
with that option's terms for the same person → the mandate with the tap's words → booked; a nearby venue is its own booking; typed words
naming one; another card's tap books nothing; WhatsApp's rows are card taps with no link; the true refusal keeps the page; the ratchet.
ONE TRUTH T100.
