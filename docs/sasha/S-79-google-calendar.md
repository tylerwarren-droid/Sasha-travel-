# S-79 · Google Calendar: every booking in the guest's calendar, and a free/busy check before booking

> ✅ **Founder defaults (EU 120):** G-1 = `calendar.app.created` + `calendar.freebusy` (the "Sasha bookings" secondary calendar). G-2 = the connection-consent exception: the sync writes **only Sasha's own bookings** to the "Sasha bookings" calendar. G-3 = the founder as the first test user (Jon later). G-4 = **delete** on cancel. **020 and 021 are already applied** to sasha-prod (chat, EU 120), so step 1 of §8 is 022 only.

*EU session, 2 Oct 2026 (EU 119), spec ahead of the Sasha tab. Code read at **`22ccc0e`**. Google was read at source
today. Nothing built or run.*

## 0. Facts this rests on

**Google, at source:**
- **Scopes** (`developers.google.com/workspace/calendar/api/auth`):
  - `calendar.events`: *"View and edit events on all your calendars"*;
  - `calendar.events.owned`: *"See, create, change, and delete events on Google calendars you own"*;
  - `calendar.freebusy`: *"View your availability in your calendars"*;
  - `calendar.app.created`: *"Make secondary Google calendars, and see, create, change, and delete events on them"*.
  - Google: *"choose the most narrowly focused scope possible"*.
  - ○ (a search summary of Google's pages): `calendar.events` and `calendar.app.created` are **sensitive** scopes.
- **Testing mode** (support.google.com, Google Cloud console help, via search):
  - **up to 100 test users**;
  - *"Authorizations by a test user will expire seven days from the time of consent. If your OAuth client requests an
    offline access type and receives a refresh token, that token will also expire."*;
  - an "unverified app" warning for sensitive scopes until verified.

**Sasha at `22ccc0e`:**
- **No Google OAuth, Calendar code or Google client library exists.** The only Google auth is the hand-rolled
  service-account JWT for Cloud KMS (`vault/kms.py:58–100`).
- **The vault (S-78) is built:**
  - `vault/crypto.py:47` `seal`, `:91–93` `use(account, item_id, *, approval, approved_lines, action_kind,
    action_ref)`;
  - routes at `/api/booking/vault` (`vault/api.py:36`, mounted at `routes.py:523`);
  - **`kind = 'oauth'` exists in the schema** (`sql/021_vault.sql:15`), but the API **refuses** it: `api.py:89–90`
    `"vault_oauth_unavailable", "no site is connected by sign-in yet…"`;
  - **migration 021 is not applied** (its header).
- **Bookings live in `trip_items`:**
  - `status`, `date_time timestamptz`, `duration_minutes`, `provider_name` (the venue), `booking_reference`
    (`migrations/001_initial_schema.sql:180–210`);
  - `party_size`, `local_timezone` (`sql/001_booking_storage.sql:143–144`);
  - the venue address only in `request.where.address` (`reservation.py:138–140`).
- **Status is written in 11 places:**
  - `ladder_store.py:145, 170, 408, 450`;
  - `store.py:354, 367`;
  - `form_rung.py:437`;
  - `stop.py:243`;
  - `inbound_phone.py:173`;
  - `cancel_routes.py:273`;
  - `call_store.py:441`.
- **Status values** (011's header): `pending prepared attempting requested declined unreachable confirmed failed
  escalated cancelled unclear link_sent guest_booked proposed quoted waitlisted`.
- **A change is a new request** (no reschedule purpose, `reservation.py`).

---

## 1. Decisions (defaults proposed; the founder rules)

- **G-1, scopes. Proposed: `calendar.app.created` + `calendar.freebusy`, not `calendar.events`.**
  - Sasha writes into **a secondary calendar she creates, "Sasha bookings"**, which shows in the guest's Google
    Calendar beside their own.
  - She reads only **free/busy**, never event titles.
  - That's narrower than `calendar.events` (which reads and edits **all** the guest's calendars), and it removes the
    chance of touching the guest's own events.
  - If the founder keeps `calendar.events` (his EU 119 wording), the flow below is unchanged, and the calendar is the
    guest's primary instead.
- **G-2, how this fits V-2 ("standing permission OFF").**
  - Calendar sync writes on every status change, without a fresh yes each time. **That's a standing permission by
    nature.**
  - Proposed: **the Google connection is its own consent, separate from site logins.** At connect time the guest
    approves, in Sasha's words: *"Sasha will add your bookings to a 'Sasha bookings' calendar, keep them up to date,
    and check when you're free before booking. She won't read your events."*
  - The token is a vault item `kind 'oauth'`, `provider 'google.com'`, used **only** by the sync and free/busy code
    paths (never by a booking executor), and **every use is logged and shown**.
  - V-2 still holds for **site logins**. ⚖ The founder confirms this exception, or the alternative: calendar writes
    only when the guest taps "Add to my calendar" per booking (no standing sync).
- **G-3, test users.** The founder first (his Google account), then the B2B pilot's guests, up to 100. **The 7-day
  expiry means every test user re-consents weekly** (§6).

---

## 2. Google Cloud setup (the founder, one sitting, ~10 min, in his own browser)

1. In the Google Cloud project that already holds the KMS key (`SASHA_VAULT_KMS_KEY`), **enable the Google Calendar
   API**.
2. **OAuth consent screen (Google Auth Platform):**
   - User type **External**, publishing status **Testing**;
   - app name **"Sasha by Kanoe"**, support email tyler@kanoe.ai, home page `https://project.kanoe.ai/kanoe-legal`
     (the same as S-71), privacy policy the live `/sasha-privacy` page;
   - **Scopes:** per G-1;
   - **Test users:** the founder's Google address.
3. **Credentials → OAuth client ID → Web application:**
   - Authorized redirect URI: `{SASHA_API_PUBLIC_BASE}/api/booking/google/callback` (the backend, on Railway).
4. **The founder sets the env vars on Railway himself** (rule 17: names only, never values):
   `SASHA_GOOGLE_OAUTH_CLIENT_ID`, `SASHA_GOOGLE_OAUTH_CLIENT_SECRET`, `SASHA_GOOGLE_OAUTH_REDIRECT`.

---

## 3. Data (migration `022_calendar.sql`, for chat to apply; DRAFT, not applied)

```sql
-- Preview: expect NULL twice
select to_regclass('public.calendar_links'), to_regclass('public.calendar_outbox');

-- One Google connection per guest. The refresh token itself lives in vault_items (kind 'oauth'); this row points at it.
create table public.calendar_links (
  account_id uuid primary key references auth.users(id) on delete cascade,
  vault_item_id uuid not null references public.vault_items(id) on delete cascade,
  google_calendar_id text,                    -- the 'Sasha bookings' secondary calendar (G-1), or 'primary'
  scopes text[] not null,
  consent_at timestamptz not null, consent_wording_version text not null, consent_text_sha256 text not null,
  last_ok_at timestamptz, needs_reconnect_at timestamptz   -- set on invalid_grant (the 7-day testing expiry, or revoke)
);
-- Which Google event mirrors which booking.
create table public.calendar_events (
  trip_item_id uuid primary key references public.trip_items(id) on delete cascade,
  account_id uuid not null references auth.users(id) on delete cascade,
  google_event_id text not null, etag text, synced_status text not null, synced_at timestamptz not null default now()
);
-- ONE place that sees every status change, whichever of the 11 writers made it.
create table public.calendar_outbox (
  id bigserial primary key, trip_item_id uuid not null, status text not null,
  created_at timestamptz not null default now(), done_at timestamptz, attempts int not null default 0, last_error text
);
create or replace function public.trip_items_status_to_outbox() returns trigger language plpgsql as $$
begin
  if new.status is distinct from old.status or new.date_time is distinct from old.date_time then
    insert into public.calendar_outbox (trip_item_id, status) values (new.id, new.status);
  end if;
  return new;
end $$;
create trigger trip_items_calendar_outbox after update of status, date_time on public.trip_items
  for each row execute function public.trip_items_status_to_outbox();
alter table public.calendar_links enable row level security;   -- backend only, no policies (as 015:3)
alter table public.calendar_events enable row level security;
alter table public.calendar_outbox enable row level security;
-- Verify: select tgname from pg_trigger where tgname = 'trip_items_calendar_outbox';  -- expect 1 row
```

- **Why a trigger:** status is written in **11 places**. A Python hook in each would be missed by the 12th writer; the
  trigger can't be.
- **It depends on 021** (`vault_items`). Apply 021 first.

---

## 4. What goes in the calendar

| `trip_items.status` | Calendar |
|---|---|
| `confirmed`, `guest_booked` | **event**: title `{provider_name}`, start `date_time`, end `date_time + duration_minutes` (default 120 min for a meal, 60 otherwise), time zone `local_timezone`; location `request.where.address`; description *"Booked by Sasha · {party_size} people · ref {booking_reference} · {link to the reservation}"*; `transparency: opaque` |
| `proposed`, `quoted`, `waitlisted` | **tentative event** (`status: tentative`), title `"(proposed) {provider_name}"`, description *"The venue offered this; not booked until you say yes."* |
| `cancelled`, `declined`, `failed` | **delete** the event if one exists (title-prefix `"Cancelled · "` and keep it is a G-4 option; default: delete) |
| everything else (`pending`, `prepared`, `attempting`, `requested`, `link_sent`, `unclear`, `escalated`, `unreachable`) | **nothing**; no event for a booking that isn't one |

- A change of time is a new request (`reservation.py`), so it arrives as a new `trip_item` plus a cancellation. Both
  flow through the outbox, which is correct by construction.
- **No guest data beyond the booking goes to Google:** no chat text, no other guests' names.

---

## 5. Code (new module `backend/booking_signer/calendar_sync.py`, plus a router)

1. **OAuth routes** (`/api/booking/google`, mounted beside `vault` at `routes.py:522–524`):
   - `GET /connect`: account-bound (`account_for`). It mints `state` (HMAC of the account plus a nonce, 10 min) and
     redirects to Google's auth endpoint with `access_type=offline`, `prompt=consent`, the G-1 scopes and
     `include_granted_scopes=false`.
   - `GET /callback`:
     - verify `state` → exchange the code at `oauth2.googleapis.com/token` (httpx; **no new library**, as `kms.py`
       does);
     - **seal the refresh token into the vault**: `vault/crypto.seal(account, item_id, 'oauth', token_bytes)` plus the
       store insert with `provider='google.com'`, `label='Google Calendar'`;
     - create the "Sasha bookings" calendar (`POST /calendars`) if G-1 is the secondary-calendar model;
     - write `calendar_links`; log `vault_events('created')`; redirect to `/settings?google=connected`.
   - `DELETE /google`: revoke at Google (`POST oauth2.googleapis.com/revoke`), crypto-shred via the vault revoke
     (`api.py:201` path), delete `calendar_links`. Revoke-all (`api.py:217`) also does this.
   - **`api.py:89–90` stays refusing** OAuth items created by hand. Only this callback creates them.
2. **Token use without breaking the vault's one rule.**
   - `vault.use()` needs a per-action approval (`crypto.py:91–93`); a sync has none.
   - **New sibling `vault.use_connection(account, item_id, *, purpose)`** in `vault/crypto.py`:
     - allowed only for `kind == 'oauth'` and `purpose in item.allowed_purposes` (`{'calendar_sync',
       'calendar_freebusy'}`, written at connect);
     - logs a `vault_uses` row per call (`action_kind = purpose`, `approval_sha256 = 'connection:' + consent_sha`);
     - returns an **access token only** (the refresh exchange happens inside; the refresh token never leaves
       `crypto.py`).
   - The test that forbids importing `_open` elsewhere (`tests/test_vault_s78.py`) stays true.
3. **The outbox drainer:** `calendar_sync.drain()`, a background loop started in FastAPI's lifespan (the backend is
   long-running on Railway). Every 20 s it takes up to 50 undone rows, `for update skip locked`, and for each:
   - no `calendar_links` row for the item's account → mark it done (nothing to sync);
   - compute §4's action → `events.insert` / `events.patch` (with etag) / `events.delete` → upsert `calendar_events` →
     `done_at = now()`;
   - `invalid_grant` → set `needs_reconnect_at`, leave the row undone (it retries after reconnect), and tell the guest
     once (§6);
   - any other error → `attempts += 1`, `last_error`, backoff; after 10 attempts, stop and log (`console`-equivalent
     `logger.error`).
4. **Free/busy before booking.**
   - In the prepare step (the read-back is built before the yes: `call_routes.py` prepare, `form_rung.py` put,
     `ladder_store` put), call `calendar_sync.busy(account, start, end)`, which is `POST /freeBusy` over
     `[primary]` (+ the Sasha calendar).
   - If busy, add **one read-back line**, *"Your calendar shows something at that time ({start}–{end})."*, so it's
     inside the hash and the guest approves knowing it.
   - **Never block; the guest decides.** Free/busy returns busy **ranges only**, never titles.
   - No link → no line, as today.

---

## 6. The 7-day testing expiry, handled honestly

- In testing, every test user's refresh token dies after 7 days.
- On `invalid_grant`, `needs_reconnect_at` is set and the guest gets one message (web banner, or WhatsApp via S-75's
  `deliver` if linked): *"Your Google Calendar connection has expired (a limit while we're in testing). Reconnect:
  {link}"*. The settings page shows **"Expired, reconnect"**, never "Connected".
- After reconnect, the undone outbox rows drain, so nothing is lost.
- **Moving to production** (later): consent-screen verification for the sensitive scopes (no CASA security assessment;
  that's for restricted scopes), with the privacy policy and a demo video. It removes the weekly expiry and the
  100-user cap.

---

## 7. Tests (each step green before the next)

1. `test_calendar_outbox_sql`: against a test DB or fixture, an `update trip_items set status = 'confirmed'` from
   **each** of the 11 writer statements inserts one outbox row; an update that doesn't change status or `date_time`
   inserts none.
2. `test_calendar_map`: §4's table as a pure function `calendar_action(status, row) -> insert|tentative|delete|none`,
   over every status value in 011's list.
3. `test_use_connection`:
   - refuses a non-oauth item, and a purpose not in `allowed_purposes`;
   - logs one `vault_uses` row per call;
   - the refresh token never appears in the return value or the logs (scrub).
4. `test_oauth_state`: a forged or expired `state` → 400; a callback for account A can't attach to account B.
5. `test_drain`:
   - insert → event created (Google mocked);
   - confirmed → cancelled → event deleted;
   - `invalid_grant` → `needs_reconnect_at` set, the row kept, one guest message (not one per row).
6. `test_freebusy_readback`: a busy range → the read-back gains the line **and** the hash changes; no link → identical
   read-back.
7. **Live (the founder's account, testing mode):** connect → book a real form-rung venue → the event appears in
   "Sasha bookings" → cancel → the event disappears. Read `calendar_events` and `vault_uses` back. Disconnect → the
   token is revoked at Google, and `wrapped_dek is null`.

## 8. Build order

1. **Apply 021** (the vault) if not yet applied, then **022** (chat applies both, preview first).
2. §2 console setup (the founder).
3. §5.1 OAuth + §5.2 `use_connection` (tests 3, 4).
4. §5.3 drainer + §4 mapping (tests 1, 2, 5).
5. §5.4 free/busy (test 6).
6. Live (test 7).

## Founder decisions

- **G-1:** the scopes (proposed: secondary calendar + freebusy).
- **G-2:** the connection-consent exception to V-2, or per-booking "Add to calendar".
- **G-3:** the test users.
- **G-4:** delete vs mark a cancelled event.

---

## Built, Sasha 109–110 (2 Oct 2026, `c4aec72`): §5.1–5.4 in code

- **`booking_signer/calendar_sync.py`:**
  - connect, the callback and disconnect, with a signed 10-minute state (the callback is gate-exempt and names the
    account only through that state);
  - §4's map;
  - the outbox drainer (`SASHA_CALENDAR_LOOP`, running only once Google is configured);
  - the 7-day expiry: "Expired, reconnect", the guest told once, rows kept;
  - free/busy: one read-back line inside the hash, on the call path.
- **`vault.use_connection`** (in `crypto.py`): oauth, google.com, the calendar purposes only, every use logged. The
  refresh token is exchanged there and never leaves it.
- **Migration 022** is drafted (row 119), with the trigger. **Web:** the "Google Calendar" block on the booking page.
- **Waiting on:**
  - the founder's §2 console setup (Calendar API, the consent screen in testing, the OAuth client, the three env vars);
  - the vault being open (Cloud KMS, S-78 V-1; it needs his `gcloud auth login`);
  - free/busy on the form and email rungs (only the call rung is wired so far).
