# S-17 — Before six new tables: what Sasha's database already holds, and whether the booking work should use it

**Filed:** 28 September 2026. **Report only. Nothing was created, altered or run.** Every query against
`xlqtveusyfpffaejegiq` was read-only: columns, constraints, policies, triggers and **counts**. No row content was
read, including from `auth.users`.

## 0. The short answer

**Use what exists for the reservation, and keep new tables only for what nothing existing can hold.**
- **The reservation belongs in `trip_items`**, with its sent attempt in **`booking_attempts`**. Those are the
  repo's own specified trip model, and between them they have the reservation number, the absolute date and
  clock time, the venue and the `restaurant` type. **My `reservations` table should not be created**: it would
  be a **third** place a booking can live.
- **Five of my six tables have no existing counterpart**, measured by columns (§3). They are the signer's
  ledger (challenges, device keys, the approved read-back, signed payloads and digests, device-signed
  reports), not trip structure.
- ⛔ **One decision blocks using `trips`: `trips.owner_id` is `NOT NULL REFERENCES auth.users(id)`**, and the
  demo account `11111111-…` **is not an auth user.** Three auth users exist; the demo id is not one of them.
  So no trip can be created for the demo account as things stand (§4).
- ⚠ **Sasha's database already has TWO parallel trip models, not one.** That is the duplication to undo, and it
  predates this work (§1). This report picks the one to build on and says why; dropping the other is the
  founder's call.

## 1. What is there — two models, both empty, neither used

| model | tables | where it came from | rows |
|---|---|---|---|
| **A — trips** | `trips` · `trip_items` · `booking_attempts` · `escalations` · `calendar_events` · `documents` · `conversations` · `user_profiles` · `traveler_profiles` · `organizations` | **in the repo**: `backend/migrations/001_initial_schema.sql` (12 June 2026, *"uses Supabase built-in auth.users"*), specified in `docs/data_model.md` | **0 in every table** |
| **B — itineraries** | `itineraries` · `itinerary_items` · `travellers` · `preferences` · `users` | **in no migration in the repo**, so created outside it. Expedia/OTA-shaped (`ota_channel`, `expedia_product_id`, `expedia_rate_id`, `total_crypto`) | **0 in every table** |

Both are **empty**, **neither has triggers**, and **no code reads or writes either**. S-18 was right about the
code and incomplete about the database: the structures exist, unused.

**Why model A and not model B**, in columns:

| needed for a reservation | A: `trip_items` | B: `itinerary_items` |
|---|---|---|
| **reservation number** | ✅ `booking_reference text` (*"confirmation number from provider"*) | ✅ `confirmation_ref text` |
| **absolute date and clock time** | ✅ **`date_time timestamptz`**, an instant | ⛔ **no date or time column at all**. Only `detail jsonb`, untyped |
| **kind = restaurant** | ✅ `type` CHECK includes `'restaurant'` | ⚠ `type text`, unconstrained |
| **venue** | ✅ `provider_name`, `provider_email`, `provider_phone`, `location_name`, `location_address` | ⚠ `display_name` only |
| **status** | ⚠ CHECK `pending \| attempting \| confirmed \| failed \| escalated \| cancelled`, which **lacks** `requested`, `declined`, `unreachable` | ⚠ `status text` default `'suggested'`, unconstrained |
| **a record of each attempt** | ✅ **`booking_attempts`** (*"audit trail for every method used to confirm a trip item — email, phone, or web form"*) | ⛔ none |
| **owner** | `trips.owner_id` → **`auth.users`** (what real accounts will be), with RLS policies already written on `auth.uid()` | `itineraries.user_id` → `public.users` (a separate user table, **0 rows**, no policies) |

**Model B cannot hold a clock time in a typed column**, so it cannot hold this reservation without adding
one. Model A already can.

## 2. The two specific questions

**Does `booking_attempts` already hold what a signed task needs? No. It holds what a SENT task produced, which
is a different thing.**

| column | fits? |
|---|---|
| `trip_item_id` (NOT NULL, FK) | ✅ the reservation it is an attempt at |
| `method` CHECK `email \| phone \| web_form` | ✅ **`web_form`** |
| `attempted_at` | ✅ |
| `status` CHECK `sent \| delivered \| confirmed \| failed \| no_response`, **default `'sent'`** | ⛔ **Wrong vocabulary, and a dangerous default.** The contract's outcomes (§7) are `requested / declined / unreachable / failed`. `failed` here would have to cover both *"the venue said no"* (declined) and *"we could not read the page"* (failed), which are opposite facts. `no_response` reads silence as an outcome. And **a row inserted without a status claims `sent`** |
| `response_received`, `response_at` | ✅ the venue's words, and when the device read them |
| `bland_call_id`, `resend_email_id` | not used here |
| `browserbase_session_id` | ⚠ a **server-side** browser. The contract's one line is that the request leaves the user's own Chrome, never a server, so this column must stay null for this path |
| **intent id, device id, signed payload, signature, digest, mode, issued/expires** | ⛔ **no column for any of them** |

So `booking_attempts` is the right home for **the outcome of a sent task**, given three changes (§5). It
cannot be the task ledger. A task can be signed and never run, or run as a dry run and never send anything,
and neither is an *"attempt to confirm a trip item"*.

**Do `itinerary_items` have room for a reservation number, an absolute date and a clock time?**
- **Reservation number: yes**, `confirmation_ref`.
- **Absolute date and clock time: no.** There is **no date or time column**, only `detail jsonb`.
- **`trip_items` does**: `date_time timestamptz` is the absolute instant (20:00 in Lisbon on 2 October 2026 is
  one instant), and `booking_reference` is the reservation number. What `trip_items` lacks is the **party
  size** and the **venue's timezone** (needed to *show* 8:00 PM rather than a UTC time), plus the three status
  words.

## 3. What has no existing counterpart — kept, and why, in columns

| my table | the columns it needs | nearest existing | why that cannot hold it |
|---|---|---|---|
| `booking_pairing_challenges` | challenge, account, issued/expires, used_at | none | no table holds a one-time challenge |
| `booking_devices` | device_id (sha256 of key), **device public key**, account, paired origin | `users`, `user_profiles` | no key column anywhere; a device is not a person |
| `booking_intents` | particulars **as approved**, the unsigned task, **the exact read-back lines and both hashes** | `trip_items` | `trip_items` holds the *live* item, which can be edited; the intent is the **immutable record of what the user said yes to**. It also has no guest name/email/phone (its contact columns are the *provider's*), no party, and no read-back or hashes. **It will reference the trip item** (§5) rather than stand beside it |
| `booking_tasks` | intent, **signed payload, signature, digest (unique)**, device, mode, issued/expires | `booking_attempts` | no payload/signature/digest columns, and a signed task is not an attempt until it sends (§2) |
| `booking_reports` | the **device-signed report**, its signature, the digest or **null** | `booking_attempts` | it must also hold reports where **nothing was sent** (a refusal, a dry run), and an attempt row for those would claim an attempt that never happened |
| ~~`reservations`~~ | — | **`trip_items` + `booking_attempts`** | **Dropped.** They fit, with the changes in §5 |

## 4. ⛔ The decision the founder must make first: who owns a trip

`trips.owner_id uuid NOT NULL REFERENCES auth.users(id)`. The demo account `11111111-1111-4111-8111-111111111111`
exists only in the chat store's SQLite file. **It is not in `auth.users`**, where three other users are (not
read).

**Choices:**
1. **Create one Supabase Auth user for the demo** (Authentication → Users → Add user), and make its id the
   booking account (`booking_signer/account.py`). **Recommended.** It is the same move real accounts will make
   later: when sign-in arrives, `account_for(request)` returns `auth.uid()`, and model A's RLS policies,
   already written on `auth.uid()`, start working as they are.
2. Relax `trips.owner_id` to nullable. **Not recommended**: it weakens the one model built for real accounts
   in order to fit a demo.
3. Keep my `reservations` table (no owner FK). **Not recommended**: that is the third parallel model.

**Which of the three auth users, if any, is meant to be "Jon Peters", I did not look.** The founder knows.

## 5. What would change — drafted for review, NOT run

**Nothing here has been applied.** The table SQL drafted before (`001_booking_storage.sql`) is **superseded**
by this plan until the founder decides §4. If he agrees, the next pass will:

**A. Create five tables, not six:** challenges, devices, intents, tasks, reports, exactly as drafted, **minus
`reservations`**, and with one change:
- `booking_intents` gains `trip_item_id uuid NOT NULL REFERENCES trip_items(id)`, and **loses** its
  venue/date/time/timezone columns. They live once, on the trip item. It keeps the guest details and the
  read-back, because those are what was approved.

**B. Alter model A, additively; every table is empty, so nothing is migrated:**
```sql
-- REVIEW ONLY — not run. Verified against the live schema, 28 Sept 2026.
-- trip_items: the three outcomes this surface produces; party and the venue's timezone
alter table public.trip_items drop constraint trip_items_status_check;
alter table public.trip_items add constraint trip_items_status_check check (status in
  ('pending','attempting','requested','declined','unreachable','confirmed','failed','escalated','cancelled'));
alter table public.trip_items add column party_size integer null check (party_size between 1 and 100);
alter table public.trip_items add column local_timezone text null;   -- IANA, to show the venue's clock time

-- booking_attempts: the contract's outcome words, no status by default, and a link back to the signed task
alter table public.booking_attempts drop constraint booking_attempts_status_check;
alter table public.booking_attempts add constraint booking_attempts_status_check check (status in
  ('sent','delivered','requested','declined','unreachable','confirmed','failed','no_response'));
alter table public.booking_attempts alter column status drop default;   -- an attempt must SAY what happened
alter table public.booking_attempts add column task_digest text null unique;   -- FK added once booking_tasks exists
alter table public.booking_attempts add column observed_by text null;  -- "the user's device": never our own reading
```

**C. How a booking then flows, in rows:**
1. **intent**: a `trips` row (owned by the demo auth user), then a `trip_items` row with `type 'restaurant'`,
   `status 'pending'`, `date_time`, `party_size`, `local_timezone`, `provider_name`; then the `booking_intents`
   row pointing at it.
2. **issue**: a `booking_tasks` row. `trip_items.status` stays `pending`, because nothing has been asked of
   the venue.
3. **report, nothing sent** (dry run, refusal): a `booking_reports` row **only**. No attempt, no status change.
4. **report, sent**: a `booking_reports` row **and** a `booking_attempts` row (`web_form`, the outcome, the
   venue's words, `task_digest`, `observed_by`), and `trip_items.status` set to the same outcome, all in one
   transaction.
5. **the trip view**: reads `trips` → `trip_items` → the latest `booking_attempts`. **No `reservations`
   table.**

**D. Code:** `store.py` and `routes.py` change where they write the reservation, and the tests follow. The
signer, the verifier, the venue builder and the outcome mapping are unchanged.

## 6. What this corrects

- **S-18** said Sasha had *"nowhere a reservation could live"*. **True of the code; false of the database.**
  Model A's `trip_items` + `booking_attempts` is that place, empty and waiting, and specified in the repo
  since 12 June.
- **S-17's `reservations` table** would have been a third model. It is withdrawn from the plan.
- **Sasha has two trip models**: A in the repo, B from outside it. Building on A leaves B unused, as it is
  today. Dropping B is a separate decision, not taken here.
