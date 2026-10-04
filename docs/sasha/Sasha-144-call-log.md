# Sasha 144: every call in the log, and one place for a dispute

*4 Oct 2026. Commit d0c0b4c (gate green, 1,052 backend tests). **Migration 032 is drafted, not applied: chat applies
it.***

## 1. Where the test calls went

They went nowhere of ours.
- **Who placed them:** my own scratch scripts (`s130_lang.py` for the Sasha 130 language test, `s143_call.py` for today's
  call). They called Bland directly (`calls.place_call`) and wrote no row.
- **Why the app couldn't log them anyway:** every app path logs its calls, but `booking_calls.trip_item_id` is NOT NULL
  with a foreign key, so a call with no reservation had no place to go.
- **What Bland has that we don't** (dry run against Bland's own list, nothing written): **9 test-line calls**.
  - 2 Oct, 05:16 and 05:28;
  - 3 Oct, 11:08–11:16 (the six language tests);
  - 4 Oct, 10:16 (`ed4770da`).
- **No call to any other number is missing.** Bland lists 21 calls; our log has 12.

**Fixed**
- `sql/032_call_log.sql` adds the following. Live schema checked first.
  - `booking_calls.is_test`;
  - `trip_item_id` may be null **only** when `is_test` (a CHECK constraint);
  - `booking_receipts_sent`, with RLS on and anon/authenticated revoked.
- **The only way to place a test call now** is `POST /api/booking/ops/calls/test` (the ops log's "Place a logged test
  call"). Its order:
  1. it writes the row first (`is_test`, no reservation, the founder's mobile kept as its hash, the read-back without
     its digits);
  2. it places the call;
  3. it records Bland's answer.
  - The sweeper reads the outcome like any call. A test call moves no reservation, sends no receipt and triggers no
    follow-up.
- **The 9 missing calls:** after 032 is applied, "Import test calls Bland has" (`POST /ops/calls/import-bland`) writes
  them as tests, and the sweeper reads each outcome from Bland.
  - A call to any other number would be **listed, never invented**.
- **My scripts no longer call Bland directly.**

## 2. The call and booking log: `/booking-helper/log` (founder only, linked from Ops)

**Every call shows:**
- TEST, where it's a test;
- the venue, when, purpose and language;
- the outcome, or why it wasn't placed;
- the venue's own words;
- the K-reference and the booking's status;
- Bland's call id, minutes and price;
- "**Bland's record**", read now from Bland: its transcript and status. **No recording exists**, because calls are
  placed with `record: false`, and the page says so instead of linking nothing.

**Every booking shows:**
- when (local) and party;
- the venue and its type;
- its status;
- the venue's reference and Sasha's K-reference (from the call, or the email);
- which routes were used;
- **the receipt:** sent or not, from 032 on. Before 032 it says "not recorded";
- **the calendar:** the event, or "no event now — removed when it was cancelled; synced 2× (last …)".

**Filters:**
- a search across every field (venue, references, words, Bland id);
- calls and/or bookings;
- tests included, excluded or only;
- the last 7–365 days.

**Read live against production** (read-only): 18 calls, 47 bookings. The queries are robust before and after 032.

**Receipts recorded from now on:** every receipt attempt (after a call, a form, an email, a one-tap page or a cancel)
writes one row, `sent` or `not sent: <why>`. A recording failure is logged and never fatal.

## 3. "cualquier momento (booked by you)"

- **Its source:** the Gmail mailbox reader. A confirmation email's small print ("…cancelar tu reserva **en cualquier
  momento**…") matched the venue pattern "reserva en X", so the venue was named "cualquier momento".
- **What happened next:** the founder's "Add it to your itinerary?" made it a `guest_booked` restaurant for 4 Oct 15:15
  (created 08:45 UTC).
- **Fixed:** a venue name must be written as a name (a capital or a digit first), and never one of the small-print
  phrases. Test: "Casa Lucio" and "100 Montaditos" still read; "cualquier momento" doesn't.
- **The item itself was left as it is.** It's the founder's record, it is now past, and the email it came from isn't
  stored, so the real venue can't be recovered here. Say if it should be cancelled.

## 4. Found on the way

- **B2QEPT was cancelled by my perf harness.** The founder's iPhone-paid TEST flight was cancelled at 08:31 UTC today,
  by the demo reset that my Sasha 140 harness runs at its end, and its calendar event was removed with it. It was a TEST
  booking, which the reset is built to clear, but it was his, and that wasn't said. **The harness won't reset again
  without asking.**
