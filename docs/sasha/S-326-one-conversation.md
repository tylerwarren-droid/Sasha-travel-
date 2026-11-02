# Sasha 326 · S2 and WhatsApp: one conversation, the right channel

Tyler, 2 Nov 16:02: "the booking form also shows in WhatsApp — not necessary… but I need to refer in WhatsApp to reservations I
started in S2."

## Root test (written before the code)

### 1. The one record and the one decision

**What the person has.** The ONE source is the one trip record: trip_items plus AgAPI's booking record (`venue.bookings`). It is read
through `venue_submit.bookings`, `venues.venue_bookings` and `itinerary.of`.
- S2 and WhatsApp run the same agent: `sasha.turn` with `surface="wa"` is S2's tools.
- That agent reads the same record for the same account.
- There is no WhatsApp-side list of bookings. (`guest_whatsapp._upcoming` is the old ladder's view; only the reminders still read it,
  merged with the acts.)

**Which channel hears about it.** Before this change there was NO such place.
- Every sender chose for itself. About 15 outcome senders went to WhatsApp, to S2, or to both for the same event: the payment
  confirmation, a venue's call result, "no answer yet", the Gmail confirmations, rentals.
- The booking form and hand-over steps went to WhatsApp whenever a number was linked, whichever channel the request came from.
  `venues._book_inner` (draft, prepared, page) and `_platform_handover` never looked at the surface.

Now there is ONE place: `booking_signer/channel.py`.
- **Where the request came from** (`from_request(ctx)`): WhatsApp when the turn came in on WhatsApp (`ctx.via == "wa"`), else S2.
- **Work in progress** (`wip_on_phone(ctx)`): goes to WhatsApp only when the request came from WhatsApp.
- **Outcomes** (`outcome_channel(account)` and `tell(...)`): ONE channel.
  - **S2:** when an S2 page is open now and the person's last turn was on S2.
  - **WhatsApp:** otherwise, when it is linked.
  - **S2's kept news:** when neither applies, so it is said on their return. Nothing is lost.
- The last channel used is recorded once per turn by `sasha.turn`, the one entry for S2, WhatsApp and voice.

### 2. A second copy?

No WhatsApp-side list, no S2-only memory, no per-message "don't forward" flag. Two things are kept:
- The last channel and when it was used: one value per account, written by the one entry.
- Which S2 pages are open: the existing `live_events` subscriptions.

### 3. The whole class

- **Can a work-in-progress step reach a channel the person isn't using?** No.
  - Every WhatsApp send of a form, page or hand-over in `_book_inner` and `_platform_handover` goes through `wip_on_phone`.
  - On S2 the step is the S2 card (`page_link` / `open`).
  - Test: an S2 booking sends nothing to WhatsApp. A scan holds that the hand-over sends never call `GW._tell` without the gate.
- **Can an outcome reach both channels?** No. Every booking-outcome sender goes through `channel.tell`:
  - a booking confirmed or paid (`live_events.completed` and `on_settled`);
  - a venue's call result (`venue_calls.tell`);
  - "no answer yet";
  - Gmail's confirm, cancel and train;
  - the hand-over "booked";
  - rentals;
  - the reminders (`proactive`).
  - Test: S2 open means S2 only; S2 closed means WhatsApp only.
- **Can a booking made in one channel be invisible to the other?** No. Both read the one record. Test: a booking made on S2 is
  answered on WhatsApp ("what time is my table") and cancelled there. Two matching bookings get one short question.

Not in scope, and said here: the payment link to the phone. "Pay here, or on your phone?" is the person's own choice, and it stays.
The S1 / founder "send to my phone" routes are explicit requests to send to the phone, and they stay too.
