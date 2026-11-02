# Sasha 327 (Part 2) · Trains are trains

A Renfe, Iryo or OUIGO ticket in his Gmail is a **train** on his trip. It is not an "other" item and it is not a dinner.

## Root test answers

### 1. The ONE record, the ONE reader
- **The ONE trip record is `trip_items`.** A train is a row there with `type = 'train'` and `status = 'confirmed'`. It sits under the account's bookings trip (`BOOKINGS_TRIP_TITLE`), and `journeys.file` moves it into a journey when one fits. The columns are used for what they mean:
  - `provider_name`: the operator
  - `booking_reference`: the localizador
  - `date_time`: the departure (Europe/Madrid)
  - `duration_minutes`: arrival minus departure
  - `location_name`: "Origin → Destination"
  - `party_size`: the number of passengers
  - `price_usd`: NULL, because it never holds euros
  - `escalation_notes`: `agapi_act:<act_id>`, the link to AgAPI's booking record
- **The ONE Gmail reader is `booking_signer/mailbox.py` `sync()`.** It passes the email to `agapi/self_booked.from_mail`, which calls AgAPI's ONE reader, `venue.confirmation` (CR 152). AgAPI's kind table decides whose email it is, and its `rail()` decides what it says. `booking_signer/trains.py` `keep()` writes AgAPI's answer onto the trip record. Nothing else writes a train.
- **The view reads on demand.** It does not copy. `trains.view()` reads `venue.manage_options` from AgAPI when the trip is shown (cached for 5 minutes because the Trip tab polls every 6 s). That read gives the operator, the fare, the departure, the fare's change/cancel rules and the operator's own manage page ("Manage your ticket"). The other fields come from AgAPI's reader's answer as the mailbox find kept it: train number, coach, seat, arrival, passengers and price. These all reach the same places:
  - the Trip tab (`/api/booking/journeys` → `TrainLine`)
  - My bookings
  - `itinerary.of` (my_plans)
  - the reminders (`proactive._rows`)
- **One booking, one row.** The train item is the ticket, so its AgAPI act is not listed a second time. This is handled by `itinerary.venue_rows` and `trains.one_row`.

### 2. PATCH check
- There is **no train table**. The only SQL is `sql/046_train_items.sql`, which replaces `trip_items_type_check` to add `'train'`. It adds no column.
- There is **no rail reader in Sasha**. Sasha has no regex over a localizador, coach, seat or train label, and no operator list (the mailbox and `trains.py` never name an operator). AgAPI's `confirmations.rail` is the reader. `test_10_sasha_has_no_rail_parser_of_its_own` scans every backend file. It first proves its detector catches AgAPI's own rail regexes.
- **Re-read.** An `'other'` item becomes `'train'` only when AgAPI's record ties it to a train. Any one of these counts as a tie:
  - its act link
  - its reference on an act AgAPI answered as `kind: "train"`
  - the mailbox find AgAPI read for it

  Anything else is left as it is, and the log says why. Sasha never guesses from the item's name. This is `trains.reread`, run once per mailbox sync, and it is idempotent.

### 3. A train ticket can't land as "other"
- `test_1_renfe_iryo_ouigo_become_three_train_items_with_every_field`: three real-format confirmations go through `mailbox.sync`, and AgAPI's answers are faked from its own `rail()` output. The result is three `type 'train'` items, and every field is shown on view.
- `test_3_a_train_never_lands_as_other`: no item of any other type is written. The only insert path writes `type 'train'`.
- `test_5_constraint_missing_keeps_the_act_logs_and_writes_it_after`: before the SQL, the database refuses `'train'`. The refusal is logged. Nothing is stored, and in particular nothing is stored as "other". The ticket stays on AgAPI's act and on the mailbox find (`facts.act_id`). After the SQL, the next sync's `reread` writes the train once.
- `test_2_…idempotent…`: the same email, or the same act, never makes a second item.

```
cd backend && python3 -m unittest tests.test_s327_trains -v
```

## Gaps (stated plainly)
- **Passenger name.** AgAPI's reader (`confirmations.rail`) does not return it. Sasha does not parse it, so it is not shown. This needs an AgAPI CR that adds `passenger_name` to `rail()` and to the act.
- **The train's own fields are not readable from the act.** AgAPI keeps them on its act (`venue_act_booking.trip`), but no op returns them: neither `venue.bookings` nor `venue.manage_options` gives train number, coach, seat, arrival, passengers or price. Until an AgAPI CR exposes `trip` on `venue.bookings`, Sasha shows them from the mailbox find. That find holds AgAPI's reader's answer, kept once and without the card. A train re-read from an old "other" item that has no find shows only what `manage_options` and the item itself give.
- **Constraint.** Until Tyler runs `046_train_items.sql` ("SQL FOR CHAT"), tickets wait on AgAPI's act and the mailbox find. They are written as trains at the first sync after it.
