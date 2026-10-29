# Sasha 306 — shorten or move a hotel stay by its own route, and a price before every change

The sandbox said v1.45.1 at the start, so CR 137 (v1.47.0, AgAPI main `462e4da`) wasn't live there yet. This is built against CR 137's code, read
read-only: `booking_kinds.py`, `venue_manage.bookings`, `answers_of`.

## Root test (written before code)

1. **The ONE truth.**
   - A hotel stay is AgAPI's stay record, read through `venue.bookings`: `stay {check_in, check_out, nights, arrival, room?}`, its
     `answers.change {state, asked, venue_words}`, and its open `change`.
   - A flight is its Duffel order, through `flight_manage.order_now` (Sasha 305).
2. **No second copy.**
   - Sasha computes no check-out. My trips shows the stay's `check_in`, `check_out` and `nights` as AgAPI's record has them.
   - The read-back's new check-out is AgAPI's own read-back line.
   - What the hotel said is `answers.change.venue_words`, quoted.
3. **Whole class.**
   - `s2_manage.booking_meant` stays the one resolver.
   - Sasha holds no list of what a stay can change. Today two lists do: `venue_submit.change_read_back(at, party, arrive)` and
     `change_submit`'s whitelist `("at", "party", "arrive")`, and either one would drop a stay's `nights`.
   - Both now pass on whatever was asked. AgAPI's `booking_kinds` accepts a field or refuses it by name, and its words are said.
   - The change tool's own argument names become AgAPI's (`nights`, `check_in`) — one translation table from the tool's words to AgAPI's,
     never a per-kind list.

## Item 2 — a price before every change, by code

Found on 305: once, "move it" was answered from the earlier turn, with no tool call and no price.

- A message that asks to change or cancel a booking makes the turn's first model step call the quote tool. This uses the model API's
  `tool_choice` set to that one tool: `change_booking`, `cancel_booking`, or `cancel_venue` for a table.
- The tool's read-back (Duffel's price or refund, or AgAPI's read-back) is then said by code (`voice.flight_line`, which now covers a stay too).
- A prompt rule alone could be ignored. This can't.
- His yes is never forced: "yes, make this change" names no booking, so the turn runs as before. The tools gate every act on a read-back
  said in an earlier turn.
