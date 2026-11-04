# Sasha 334 · Group movement v1 complete

## Root test (written first)

**Each thing lives in exactly one place:**

- **One trip per worker.** This is the worker's basket rows, under their `trip_id` from Sasha 332.
  - The master list is computed from those rows.
  - Booking or cancelling settles those same rows. There is no second "group booking" table in Sasha.
- **One booking record.** This is AgAPI's `group_bookings` (CR 163).
  - Sasha reads it each time with `group.bookings`: for the invoice, and to find a worker's live booking to cancel or swap.
  - Sasha never copies it.
- **One vault.** This is the Keep, under the member's own id (Sasha 333).
  - AgAPI receives only `keep:<id>` references.
  - The values leave the Keep only through the Keep resolver, during AgAPI's supplier call.

Any second copy is a PATCH.

**The whole class is impossible.** `tests/test_s334.py::TheOneRecords` checks that:

- group_book has no table of its own;
- it reads `group.bookings`;
- it grants references only for the act in progress, then revokes them;
- the `group` family is pinned to the sandbox, so TEST only, even with `all=live`.

## The pieces

### 1. The Keep resolver

- **Endpoint:** `POST /api/booking/keep/resolve`. The code is in `booking_signer/keep_resolver.py`.
- **Signing:** the body `{ref, at}` carries HMAC-SHA256 in the `x-agapi-signature` header. The secret is `SASHA_KEEP_RESOLVE_SECRET`, and AgAPI holds the same one.
- **Refusals:**

  | Case | Status |
  |---|---|
  | Unsigned or bad signature | 401 |
  | Stale (more than 60 s) | 401 |
  | A reference with no live grant (the person is not in the booking Sasha is making right now) | 403 |
  | Unknown item | 404 |
  | Not configured | 503 |

- **Values** pass through only. The log records the item type alone.

### 2. Master-list actions

The endpoints are `/group/act` and `/group/confirm`. Chat tools: `group_book`, `group_swap`, `group_cancel`. Buttons on `/group`: **Book all planned**, per-row Book and Cancel, and Swap.

- **The read-back card.** AgAPI's own read-back appears on one card with the 330 Yes/No buttons.
  - The tap is claimed once (`card_tap:<account>:<card>:<choice>`).
  - The list updates from the settled rows.
- **Over-limit rows** are skipped unless the organiser names the worker and says yes to that.
- **A swap** to someone with no passport in their vault invites that person instead of booking.

### 3. One invoice per movement

`GET /group/invoice`, the public token link `/invoice/<token>` (signed, 30 days), and the chat tool `group_invoice`, which sends the link on WhatsApp.

- **Read from:** AgAPI's records.
- **Contents:**
  - one line per booked worker (who, route, dates, hotel nights, price);
  - adjustments (a swap refunds the flights; a cancellation refunds in full);
  - the total;
  - the REAV note (the number is still to be added);
  - the number `KAN-…-TEST`.

## Proof

`tests/test_s334.py` runs offline. It uses the 20 fictional workers and a fake AgAPI that follows the CR 163 contract and opens each reference through Sasha's real, signed resolver.

1. **Book all:** 19 booked. Rania, who is over the limit, is held. After an explicit "No", she stays held.
2. **Swap:** Bruno is swapped for Zoe.
3. **Cancel:** Hanna is cancelled.
4. **Invoice:** 18 lines, 2 adjustments, total €9,720.00.
5. **No leak:** no passport number appears in Sasha's logs or in AgAPI's answers. All 20 reached the supplier call.

## To switch on end to end (environment, Tyler's go)

- **Sasha:** `SASHA_KEEP_RESOLVE_SECRET`.
- **agapi-sandbox:** the same secret, plus `AGAPI_KEEP_SOURCE=sasha` and `SASHA_KEEP_RESOLVE_URL=https://sasha-travel-production.up.railway.app/api/booking/keep/resolve`.

Until then, the resolver answers 503 and nothing opens.
