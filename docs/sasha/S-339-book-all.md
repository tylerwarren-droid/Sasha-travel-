# Sasha 339 · Group v1: the last booking fixes from the SASHA 335 re-run

## Root test (written first)

**1. Book all is ONE background job.** `group_book.start(account, …)` runs the ONE `prepare`. The job's own state is the only thing the page reads: preparing N, k ready, then the result.

- Each worker's read-back is prepared in parallel, at most `BOOK_PARALLEL` (2) at a time. The acts after the Yes run one at a time (`ACT_PARALLEL` = 1): the proof showed Duffel TEST, on one shared token, refusing orders four at once and failing long-haul searches. A search answered `upstream_failed` or `upstream_rate_limited` is tried once more after 5 s.
- AgAPI's "busy" answer (`upstream_rate_limited`) is waited out once, for the `retry_after_s` it gives.
- The result is ONE card listing every bookable worker's read-back, with ONE Yes (330's one place, the same `_CARDS`).
- /group shows the progress: "Preparing 18… 12 ready".
- A request never waits for 18 read-backs, so the 120 s proxy cut can't land on it.
- A page that loses its request says so. It never shows "Nothing to do." for a request that failed.
- Not done: a second card store, a second prepare for the job, or a page-side timer guessing progress. Each would be a PATCH.

**2. Offer gone.** When AgAPI answers `upstream_refused` (offer gone / `offer_no_longer_available`) for a worker's read-back, Sasha re-plans that ONE worker through the planner (`groups.plan(only=[them])`, the same limits), finds again on AgAPI, and asks for the read-back once more. The new fare is on the card. Still none: that worker alone is held, with "no fare left — nothing held".

**3. Limits at booking.** Before a read-back is asked, the worker's limit (`groups.limit_for`, the ONE rules record) is checked against AgAPI's OWN prices for exactly the offers the read-back will price:

- the flights' quoted prices, out plus back, against `flight_return_eur`;
- the stay's `price_per_night`, against `hotel_night_eur`.

Over the limit means held and flagged, e.g. "Hotel Alba (test): hotel €190/night > €150 limit — book anyway?". It is never booked silently. "Book anyway" re-asks with `over_ok` for exactly that worker, and the card then carries a ⚠ line.

AgAPI's approval_required answer has no structured prices (only the lines). Sasha reads `details.priced` first when AgAPI sends it (asked of CR), and AgAPI's own offer prices otherwise. It never parses the sentences.

**4. A swap sends `flights`** (CR 164 · 08ffd01): the newcomer's OWN flights from their home city, as planned (planned first if they never were), each with its `planned_price`. AgAPI books the newcomer first, then cancels the leaver.

**The whole class** (`tests/test_s339_book_all.py`):

- 18 workers prepare in parallel (never more than BOOK_PARALLEL at once), with progress counted;
- a slow AgAPI never reaches the page as "Nothing to do";
- ONE card, ONE Yes;
- a gone offer is re-planned once, then held per worker;
- a stay over the limit is held with the words, and booked only after "book anyway";
- a swap's body carries the newcomer's own flights, each with its planned price.
