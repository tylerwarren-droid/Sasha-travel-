-- ── S-17 · WHERE A BOOKING LIVES — DRAFTED FOR THE FOUNDER TO RUN. NOTHING HAS APPLIED THIS. ──────────
--
-- Target: Sasha's Postgres — the database behind Railway's DATABASE_URL (Supabase, per CLAUDE.md). The
-- booking routes read DATABASE_URL and nothing else; until these tables exist every booking route answers
-- 503 `storage_not_provisioned` and GET /api/booking/health says which tables are missing.
--
-- ⚠ It could NOT be checked against Sasha's live schema: no session has access to that database. It WAS run,
-- start to finish, against a throwaway PostgreSQL 16.2, and the routes' full suite passed against it
-- (docs/sasha/S-17-signer-mounted.md §6). Supabase runs PostgreSQL 15 or 17; nothing below is version-specific.
--
-- ⚠ PLAIN `CREATE TABLE`, deliberately NOT `IF NOT EXISTS`. If a table of the same name already exists with a
-- different shape, `IF NOT EXISTS` would silently keep the wrong one. This fails loudly instead.
--
-- ── 1 · PREVIEW — run this first. It must return NO rows. ───────────────────────────────────────────────
--
--   select table_name from information_schema.tables
--    where table_schema = 'public'
--      and table_name in ('booking_pairing_challenges','booking_devices','booking_intents',
--                         'booking_tasks','booking_reports','reservations');
--
-- ── 2 · THE TABLES ─────────────────────────────────────────────────────────────────────────────────────

begin;

-- A pairing challenge (contract §4): issued to one account, used once, short-lived.
create table public.booking_pairing_challenges (
  challenge   text        primary key check (char_length(challenge) >= 32),
  account_id  text        not null,
  issued_at   timestamptz not null,
  expires_at  timestamptz not null,
  used_at     timestamptz null,
  check (expires_at > issued_at)
);

-- A paired browser: one helper installation, bound to ONE account. `device_id` = sha256(SPKI DER).
create table public.booking_devices (
  device_id          text        primary key check (device_id ~ '^[0-9a-f]{64}$'),
  account_id         text        not null,
  device_public_spki text        not null,
  paired_origin      text        not null,
  paired_at          timestamptz not null,
  revoked_at         timestamptz null
);
create index booking_devices_account on public.booking_devices (account_id);

-- ⚠ THE INTENT IS RECORDED BEFORE ANYTHING IS SIGNED (contract §3.5). It holds the particulars as the user
-- gave them, the unsigned task built from them, and the exact words read back.
create table public.booking_intents (
  intent_id            uuid        primary key,
  account_id           text        not null,
  venue_key            text        not null,
  mode                 text        not null check (mode in ('dry_run','live')),
  local_date           date        not null,          -- the table's date, at the venue
  local_time           time        not null,          -- the table's clock time, at the venue
  venue_timezone       text        not null,          -- IANA, e.g. Europe/Lisbon
  party                integer     not null check (party between 1 and 100),
  guest_name           text        not null,
  guest_email          text        not null,
  guest_phone          text        not null,
  task                 jsonb       not null,          -- unsigned, without its instants
  standing             jsonb       not null,
  read_back_lines      jsonb       not null,
  read_back_sha256     text        not null check (read_back_sha256 ~ '^[0-9a-f]{64}$'),
  filled_values_sha256 text        not null check (filled_values_sha256 ~ '^[0-9a-f]{64}$'),
  itinerary_id         text        null,              -- the chat store's itinerary; it lives in SQLite, so no FK
  status               text        not null check (status in ('awaiting_approval','issued','reported')),
  created_at           timestamptz not null
);
create index booking_intents_account on public.booking_intents (account_id, created_at desc);

-- ⚠ ONE TASK PER INTENT, EVER: the primary key is the intent. A retry is a NEW intent (contract §9).
-- `task_digest` is what every report quotes (contract §5.4).
create table public.booking_tasks (
  intent_id    uuid        primary key references public.booking_intents (intent_id),
  task_digest  text        not null unique check (task_digest ~ '^[0-9a-f]{64}$'),
  account_id   text        not null,
  device_id    text        not null references public.booking_devices (device_id),
  mode         text        not null check (mode in ('dry_run','live')),
  payload      jsonb       not null,
  signature    text        not null,
  issued_at    timestamptz not null,
  expires_at   timestamptz not null,
  check (expires_at > issued_at)
);

-- A report that PASSED verification (contract §5.4). A report that fails is discarded, never stored.
-- `task_digest` is NULL when the helper refused before it could verify the task: nothing ran, nothing sent.
-- ⚠ Append-only by use: nothing updates or deletes a row here.
create table public.booking_reports (
  id               bigint      generated always as identity primary key,
  received_at      timestamptz not null,
  account_id       text        not null,
  device_id        text        not null references public.booking_devices (device_id),
  task_digest      text        null references public.booking_tasks (task_digest),
  intent_id        uuid        null references public.booking_intents (intent_id),
  task_verified    boolean     not null,
  report           jsonb       not null,
  device_signature text        not null,
  outcome          text        null check (outcome in ('requested','declined','unreachable','failed')),
  check (task_verified = (task_digest is not null)),
  check (task_verified or outcome is null)
);
-- A report re-sent on PENDING (its ACK was lost) is RECOGNISED, not recorded twice.
create unique index booking_reports_one_per_task on public.booking_reports (task_digest) where task_digest is not null;

-- ⚠⚠ THE RESERVATION — what S-18 found Sasha had nowhere to keep. Created only when something WAS sent
-- (contract §7): a dry run, a refusal or a stop records no reservation, because nothing was asked of the venue.
create table public.reservations (
  id              uuid        primary key default gen_random_uuid(),
  intent_id       uuid        not null unique references public.booking_intents (intent_id),
  task_digest     text        not null references public.booking_tasks (task_digest),
  account_id      text        not null,
  itinerary_id    text        null,
  venue_key       text        not null,
  venue_name      text        not null,
  venue_origin    text        not null,
  local_date      date        not null,        -- an ABSOLUTE date, at the venue
  local_time      time        not null,        -- a CLOCK time, at the venue
  venue_timezone  text        not null,
  party           integer     not null,
  -- ⛔ 'confirmed' is allowed by the table and written by NOTHING: this surface cannot reach it (contract §8).
  -- It arrives, if ever, by the venue's email — and nothing in Sasha receives email yet (S-18).
  status          text        not null check (status in ('requested','declined','unreachable','failed','confirmed')),
  status_basis    text        not null,        -- "read on the user's device" — never our own observation
  venue_reference text        null,            -- the venue's reservation number, when it gave one. Psi's page gives none.
  venue_words     text        null,            -- what the page said; only for requested and declined
  observed_at     timestamptz null,            -- when the device read the page
  created_at      timestamptz not null,
  check (status not in ('unreachable','failed') or venue_words is null)
);
create index reservations_account on public.reservations (account_id, local_date);

-- ── 3 · ROW-LEVEL SECURITY: ON, WITH NO POLICIES ─────────────────────────────────────────────────────────
-- The backend connects with DATABASE_URL as the database owner, which bypasses RLS. Supabase's anon and
-- authenticated roles — whose key ships in browser code — get NOTHING. These tables hold guests' names,
-- email addresses and telephone numbers.
alter table public.booking_pairing_challenges enable row level security;
alter table public.booking_devices            enable row level security;
alter table public.booking_intents            enable row level security;
alter table public.booking_tasks              enable row level security;
alter table public.booking_reports            enable row level security;
alter table public.reservations               enable row level security;

commit;

-- ── 4 · AFTER — run this. It must list all six, each with rowsecurity = true. ────────────────────────────
--
--   select tablename, rowsecurity from pg_tables
--    where schemaname = 'public'
--      and tablename in ('booking_pairing_challenges','booking_devices','booking_intents',
--                        'booking_tasks','booking_reports','reservations')
--    order by tablename;
--
-- Then: GET https://sasha-travel-production.up.railway.app/api/booking/health → "provisioned": true.
