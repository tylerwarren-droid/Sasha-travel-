# Sasha 305 — change an existing trip: flight and hotel, end to end

## BUILT check (main 037862c, before any change)

| Booking | Act | Today | Where |
|---|---|---|---|
| Duffel flight | change date / time | **built**: Duffel's change offers for one leg, every time that day with its fare difference and penalty, read back, done on his yes in a later turn | `agapi/s2_manage.py:295-354` → `booking_signer/flight_manage.py:303` `change_quote`, `:367` `change_confirm` |
| | after the change | **half**: says "Changed — Duffel confirmed it. Booking reference X." It never says the new flight or what was charged, and nothing re-reads the order for My trips | `s2_manage.py:312-318` |
| Duffel flight | cancel | **built**: Duffel's own refund quote, read back, cancelled on his yes; the basket row is marked cancelled | `s2_manage.py:484-497` (quote), `:465-473` (yes) → `flight_manage.py:163` `cancel_quote`, `:209` `cancel_confirm` |
| Hotel | change dates / nights | **not built**: she says "I can't change the dates of your stay yet" | `s2_manage.py:291-294` |
| | on AgAPI | **not built**: `venue.change_booking` takes a new time (`at`) or `party` only — a stay's nights can't be asked for | agapi `agapi_service/venue_manage.py:269-294` (`_ask`) |
| Hotel | cancel | **Sasha's own TEST stay only**: the basket row is marked cancelled locally, no hotel is asked. A stay booked through AgAPI (CR 102) is never reached by it: `_item` only looks at basket stays | `s2_manage.py:498-506`, `:474-481`, `:234-240` |
| Restaurant / spa | change, running late | **built**: by the booking's own route through AgAPI (`venue.change_booking`), the venue's answer on the record (CR 132/134) | `s2_manage.py:289-290` → `:120` `_notice` → `:170` `_act_notice` |
| | cancel | **built**: `cancel_venue` | `agapi/venues.py` |
| My trips | one view | **built, but with copies**: AgAPI's acts read from `venue.bookings` (the truth); flights and Sasha's stays from the basket's **snapshot** (airline, flight numbers, departure, a copy taken at booking) | `agapi/itinerary.py:235-284`; flight rows `:256-262`, stays `:263-269` |

**The "7 Days in Rio" trip** (`e2de86ad…`) is on the shared **demo account** (`1111…`), not a scratch TEST guest:
- two Duffel TEST orders: out 15 Nov, `LY4XCR`; back 21 Nov, `YZVFI4`;
- one stay with `provider = plan`, `TEST-61094A`. That stay is Sasha's own placeholder: no hotel was asked, and it isn't on AgAPI.

So the proof books a fresh trip on a scratch TEST guest.

## Root test (written before code)

1. **The ONE truth per booking.**
   - A flight is the Duffel order, read live with `GET /air/orders/{id}`. The one reader is `flight_manage.order_now` (it grows out of `_order`, `flight_manage.py:145`).
   - A hotel, and any venue, is its booking record on AgAPI, read through `venue_submit.agapi_bookings` (`itinerary.py:181`, CR 132/134 fields: state, at, party, the stay's nights, the venue's words).
2. **No second copy.**
   - Today the itinerary's flight row is the basket's snapshot. After a change it would still show the old flight, which is a second truth.
   - After 305, a flight row is built from the live order: its slices, its booking reference, and `cancelled_at`.
   - If the order can't be read, the row says so ("couldn't read it from the airline just now") and shows no stale times.
   - After a change or a cancel, what she says is read back from the order or the record, never from the request she sent.
3. **Whole class.**
   - Today `change_booking` / `cancel_booking` branch on the model's `what`, and each branch finds its booking in its own list.
   - After 305 there is ONE resolver: the itinerary row the person means. The row's source decides who answers:
     - a Duffel order → Duffel;
     - an AgAPI act (a restaurant, a spa, a hotel stay) → `venue.change_booking` by its route;
     - Sasha's own TEST stay → said plainly that no hotel holds it.
   - No flight-only conversation, and no hotel-only search.

## Blocker for item 3 (the hotel's nights)

AgAPI's `venue.change_booking` has no field for a stay's nights. A stay act (CR 102) stores `{nights, room}`, but a change takes only `at` / `party`.

"Make it 3 nights instead of 4" can't be sent by the hotel's route until AgAPI takes it. The ask is **AgAPI ask s305-1** (not "CR 136": that number is another session's Sasha CR): `venue.change_booking` accepts `stay: {nights}` on a stay act, and its read-back and message say the new check-out. Until it ships, Sasha says that plainly and sends nothing.
