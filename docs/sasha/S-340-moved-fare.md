# Sasha 340 · Book all on CR 166: a moved fare is re-asked alone; limits read from `priced`

## Root test (written first)

**One yes, one card, and the rest stay booked.** When AgAPI answers an act with `approval_void` / `payload_changed` (CR 166), nothing was booked for THAT worker. What happens next:

- **With a fresh read-back** (its id, its lines, its `priced`): that worker gets their OWN card, in the same card store, with the same Yes/No from 330's one place. The card's lines are AgAPI's own: "The fare moved since your yes: now €y, was €x". It shows on /group (one card at a time) and in S2's chat.
- **With no read-back** (the offer is gone): that worker is prepared again (re-planned once, as in Sasha 339), then gets their own card, or is held with the reason.
- The other workers' bookings stand. Nothing is re-asked for them.
- Not done: a second card store, re-asking the whole card, or retrying the act without a new yes. Each would be a PATCH.

**Limits use AgAPI's own read-back prices.** `approval_required` now carries `details.priced`. Sasha compares the flights' `amount_minor` (out + back) with `flight_return_eur`, and the stay's `per_night_minor` with `hotel_night_eur`. It never reads a sentence and never guesses a currency other than EUR. Only an AgAPI that sends no `priced` falls back to its own offer prices.

**PATCH removed.** 051 is applied: all 1,520 snapshot rows are objects. So the readers' old-shape handling (strings inside strings, arrays) and the object-safe supersede merge are gone. Readers take objects; supersede is a plain `||`.

**The whole class** (`tests/test_s340_moved_fare.py`):

- one Yes books 18 workers, and the one with a moved fare gets their own card with their own Yes, which then books them too;
- the master list and the invoice match AgAPI's record (19);
- an offer gone at the act is prepared again for that worker alone;
- the read-back's €190 a night is held against a €150 limit, even though the offer said €90;
- the readers take objects only.
