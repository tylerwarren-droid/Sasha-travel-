# S-17 — The storage block, for chat to apply to xlqtveusyfpffaejegiq

**Filed:** 28 September 2026. **Drafted and tested; NOT applied, NOT committed, NOT pushed.**

## 1. The block

**File:** `backend/booking_signer/sql/001_booking_storage.sql`, **one block, run once, whole.** To hand it to
chat, copy it with one line (the file holds no secret):
```
cd ~/Developer/Sasha-travel- && pbcopy < backend/booking_signer/sql/001_booking_storage.sql && echo copied
```

**In order, it:**
1. **Refuses, changing nothing**, if any part of it already exists: any of the five tables, any of the four
   new columns, or the demo user.
2. **Creates the demo auth user.**
   - It uses id `11111111-1111-4111-8111-111111111111`, the chat store's `DEMO_USER_ID`, so
     `booking_signer/account.py` is unchanged.
   - **No email and no password: nobody can sign in as it or reset it.**
   - It matches the three existing auth users' conventions, checked as counts only: `instance_id` all zeros,
     `aud` and `role` `'authenticated'`, and the token columns `''` rather than `NULL` (Supabase's auth
     service is known to fail listing users whose token columns are `NULL`).
3. **Creates the five tables**: challenges, devices, intents, tasks and reports.
   - Every `account_id` is now a `uuid` **referencing `auth.users`**.
   - `booking_intents` references the **trip item**, and no longer holds the venue, date, time or party
     (those live once, on the trip item).
   - RLS is on, with no policies.
4. **Extends model A.**
   - `trip_items`: `requested`, `declined` and `unreachable` added to its status CHECK, plus `party_size` and
     `local_timezone`.
   - `booking_attempts`: ⛔ **the `'sent'` default is dropped**, the same three words are added, plus
     `task_digest` (unique, referencing the signed task) and `observed_by`.
5. **Returns a six-row checklist.** Every row must say `ok = true`.

**Sent as one script it is one transaction: any failure leaves nothing changed.**

**Tested**, on a throwaway PostgreSQL 16.2 carrying `auth.users` and model A **exactly as read live**
(`backend/tests/fixtures/model_a_live_2026-09-28.sql`, with every column, default, CHECK, FK and unique index):

| case | result |
|---|---|
| clean run | the checklist: **6 × true** |
| run again | refused: `STOP: part of the S-17 booking storage already exists — nothing was changed` |
| ⛔ **a `booking_attempts` insert with no status**, after the block | **refused** (`NotNullViolation`). Before the block, it would have claimed `'sent'` |
| a failure at the **last** statement | **nothing left behind**: 0 new tables, 0 auth users, and the old `'sent'` default still in place |

## 2. How a booking is stored now

| step | rows written |
|---|---|
| **intent** | the account's **"Sasha bookings"** trip, found or created (or a given `trip_id` of its own) → a **`trip_items`** row: `type 'restaurant'`, **`status 'pending'`**, `provider_name`, `date_time` (**computed by Postgres** from the local date, time and IANA zone), `local_timezone` and `party_size`; then the `booking_intents` row pointing at it. **One transaction** |
| **issue** | a `booking_tasks` row. The trip item stays `pending`: nothing has been asked of the venue |
| **report, nothing sent** (dry run, refusal) | a `booking_reports` row **only**. No attempt, no status change |
| **report, sent** | the report **and** a `booking_attempts` row (`web_form`, the outcome as its status, the venue's words, the device's read time, `task_digest`, `observed_by = "the user's device"`), **and** the trip item takes the outcome as its status. **One transaction** |
| **GET /api/booking/reservations** | the account's trip items that something was **sent** for, with their latest attempt |

**Verified in the Postgres tests:** 20:00 in Lisbon on 2 October 2026 is stored as **19:00 UTC**
(summer time), and a second booking joins the same trip rather than opening another.

## 3. Model B — recommendation: **leave it, and ask the CTO**. Do not drop it.

**What is established:**
- `itineraries`, `itinerary_items`, `travellers`, `preferences` and `users` are **empty**, and **no view or
  function depends on them**.
- **No code in the repo references them, in any commit, ever.** A search of the entire history finds
  `itinerary_items` nowhere.
- ⚠ **But they were not created by accident.** `backend/app/models/itinerary.py`, the CTO's unused Pydantic
  model, matches `itinerary_items` **column for column**: `expedia_product_id`, `expedia_rate_id`,
  `display_name`, `detail`, `traveller_ids`, `price_fiat`, `price_currency` (`'GBP'`), `price_locked_at`,
  `is_refundable`, `cancellation_policy`, `confirmation_ref`, `media`, `sasha_rationale`, and status
  `suggested`. **Model B is the CTO's design**, and that file ships in every CTO zip.
- The database's own access statistics show zero writes, but **they were very likely reset when the project
  was restored today**, so they say nothing about history.

**So:**
- **Do not drop it.** Something outside the repo, the CTO's own plan, describes it. Dropping it would be
  deciding his schema for him.
- **Do not build on it either.** Neither `itinerary_items` nor the CTO's `ItineraryItem` has **any date or
  time field**, and his item types have **no `restaurant`**. A reservation cannot live there without the
  CTO's design changing.
- ⚠ **Ask the CTO which trip model his code will write.** If it is B, then from the day he ships it, S-17's
  bookings in model A become the parallel set. The block is **additive**, so moving them later is a data
  move, not a rescue. That is the decision to take with him. Until then the two coexist, as they already
  did before S-17, and S-17 adds nothing to model B.

## 4. What changed in code (uncommitted)

- **`store.py`:** a reservation is a trip item.
  - `put_intent` writes the trip, the trip item and the intent together.
  - `record_report` writes the attempt and updates the trip item.
  - `reservations` reads trip items and their latest attempt.
  - The `reservations` table is gone.
  - `status()` also checks for the four new columns, so a database with model A but **without** the block
    reads as **not provisioned**, not as ready.
- **`routes.py`:**
  - the intent returns `trip_item_id` and accepts an optional `trip_id` (refused `404 trip_unknown` if the
    trip isn't the account's);
  - a sent outcome becomes an attempt;
  - the reservations fields are renamed (`booking_reference`, `observed_by`, `trip_id`).
- **`outcome.py`:** one unused constant removed.
- **Tests:**
  - the Postgres half now loads the live-shaped fixture and then **the block itself**;
  - four new tests:
    - the trip item's instant;
    - an unknown trip;
    - a dry run leaves the item `pending`, with no attempt;
    - an attempt cannot be inserted without a status.
- **Unchanged:** the signer, the verifier, the venue builder, the outcome mapping, the mount and
  `account.py`.

## 5. Verification

- **68 tests pass, none skipped.** They include the 36 booking-route tests, run against the in-memory store
  **and** against Postgres built from the live-shaped fixture plus the block.
- **Stage B import:** `from app.main import app` loads clean, with 50 routes.
- **Live, read-only, before drafting:**
  - `auth.users` columns and unique indexes;
  - the three existing users' conventions (counts only);
  - that `guest@example.com` is not taken (though the block uses no email);
  - that the demo id is not an auth user;
  - the exact constraint names being replaced.

## 6. After chat applies it

1. The checklist must show six rows, all `true`.
2. `DATABASE_URL` still has to be set on Railway (`S-17-which-database.md` §3 B) before the routes can reach it.
3. The rotation of the committed `service_role` key (`S-17-which-database.md` §1) still stands.
