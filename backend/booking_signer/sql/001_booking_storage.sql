-- ── S-17 · WHERE A BOOKING LIVES — ONE BLOCK, FOR SASHA'S SUPABASE (xlqtveusyfpffaejegiq) ──────────────
--
-- Supersedes the six-table draft. A reservation now lives in the repo's own trip model (model A,
-- migrations/001_initial_schema.sql): a TRIP_ITEMS row is the reservation, and each time something is SENT
-- to the venue a BOOKING_ATTEMPTS row records what came back. Five new tables hold only what nothing existing
-- can: the signer's ledger (docs/sasha/S-17-existing-tables.md §3).
--
-- Run ONCE, whole. In order, it:
--   0. refuses, changing nothing, if any part of it already exists
--   1. creates the demo AUTH USER that owns the demo's trips — no email, no password: it cannot sign in
--   2. creates the five tables, row-level security ON, no policies
--   3. extends trip_items and booking_attempts — additively; both are empty (0 rows, read 28 Sept 2026)
--   4. returns a checklist: every row must say ok = true
-- Sent as one script, Postgres runs it as ONE transaction: if any statement fails, nothing is changed.
--
-- Verified against the live schema before drafting (28 Sept 2026): auth.users' columns and unique indexes, the
-- three existing auth users' conventions (instance_id zero, aud/role 'authenticated', token columns '' not
-- NULL — counts only, no row read), and the exact names of trip_items_status_check and
-- booking_attempts_status_check. Run end to end against a throwaway PostgreSQL 16.2 carrying those tables as
-- read live (tests/fixtures/model_a_live_2026-09-28.sql), where the whole route suite passed.

-- ── 0 · THE GUARD ─────────────────────────────────────────────────────────────────────────────────────────
do $$
begin
  if exists (select 1 from information_schema.tables where table_schema = 'public'
               and table_name in ('booking_pairing_challenges','booking_devices','booking_intents','booking_tasks','booking_reports'))
     or exists (select 1 from information_schema.columns where table_schema = 'public'
               and ((table_name = 'trip_items' and column_name in ('party_size','local_timezone'))
                 or (table_name = 'booking_attempts' and column_name in ('task_digest','observed_by'))))
     or exists (select 1 from auth.users where id = '11111111-1111-4111-8111-111111111111') then
    raise exception 'STOP: part of the S-17 booking storage already exists — nothing was changed.';
  end if;
end $$;

-- ── 1 · THE DEMO ACCOUNT, AS AN AUTH USER ─────────────────────────────────────────────────────────────────
-- The id is the chat store's DEMO_USER_ID ("Jon Peters"), so booking_signer/account.py needs no change.
-- ⚠ NO email and NO password, deliberately: it owns rows, and nobody can sign in as it or reset it. When real
-- sign-in arrives, real users are auth users too, and account_for(request) returns auth.uid().
insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password,
  confirmation_token, recovery_token, email_change_token_new, email_change,
  raw_app_meta_data, raw_user_meta_data, is_super_admin, is_sso_user, is_anonymous, created_at, updated_at
) values (
  '00000000-0000-0000-0000-000000000000', '11111111-1111-4111-8111-111111111111', 'authenticated', 'authenticated', null, null,
  '', '', '', '',
  '{"providers": []}'::jsonb,
  '{"display_name": "Jon Peters (demo)", "purpose": "S-17: owns the demo account''s trips and bookings. No email, no password — cannot sign in."}'::jsonb,
  false, false, false, now(), now()
);

-- ── 2 · THE SIGNER'S LEDGER — five tables nothing existing has columns for ────────────────────────────────

-- A pairing challenge (contract §4): issued to one account, used once, short-lived.
create table public.booking_pairing_challenges (
  challenge   text        primary key check (char_length(challenge) >= 32),
  account_id  uuid        not null references auth.users (id) on delete cascade,
  issued_at   timestamptz not null,
  expires_at  timestamptz not null,
  used_at     timestamptz null,
  check (expires_at > issued_at)
);

-- A paired browser: one helper installation, bound to ONE account. device_id = sha256(SPKI DER).
create table public.booking_devices (
  device_id          text        primary key check (device_id ~ '^[0-9a-f]{64}$'),
  account_id         uuid        not null references auth.users (id) on delete cascade,
  device_public_spki text        not null,
  paired_origin      text        not null,
  paired_at          timestamptz not null,
  revoked_at         timestamptz null
);
create index booking_devices_account on public.booking_devices (account_id);

-- ⚠ THE INTENT IS RECORDED BEFORE ANYTHING IS SIGNED (contract §3.5): the immutable record of what the user
-- said yes to — the guest's details, the unsigned task, the exact words read back and both hashes. The
-- reservation itself (venue, date, time, party) lives ONCE, on its trip item.
create table public.booking_intents (
  intent_id            uuid        primary key,
  account_id           uuid        not null references auth.users (id) on delete cascade,
  trip_item_id         uuid        not null references public.trip_items (id),
  venue_key            text        not null,
  mode                 text        not null check (mode in ('dry_run','live')),
  guest_name           text        not null,
  guest_email          text        not null,
  guest_phone          text        not null,
  task                 jsonb       not null,
  standing             jsonb       not null,
  read_back_lines      jsonb       not null,
  read_back_sha256     text        not null check (read_back_sha256 ~ '^[0-9a-f]{64}$'),
  filled_values_sha256 text        not null check (filled_values_sha256 ~ '^[0-9a-f]{64}$'),
  status               text        not null check (status in ('awaiting_approval','issued','reported')),
  created_at           timestamptz not null
);
create index booking_intents_account on public.booking_intents (account_id, created_at desc);
create index booking_intents_trip_item on public.booking_intents (trip_item_id);

-- ⚠ ONE TASK PER INTENT, EVER: the primary key is the intent. A retry is a NEW intent (contract §9).
create table public.booking_tasks (
  intent_id    uuid        primary key references public.booking_intents (intent_id),
  task_digest  text        not null unique check (task_digest ~ '^[0-9a-f]{64}$'),
  account_id   uuid        not null references auth.users (id) on delete cascade,
  device_id    text        not null references public.booking_devices (device_id),
  mode         text        not null check (mode in ('dry_run','live')),
  payload      jsonb       not null,
  signature    text        not null,
  issued_at    timestamptz not null,
  expires_at   timestamptz not null,
  check (expires_at > issued_at)
);

-- A device-signed report that PASSED verification (contract §5.4) — including those where NOTHING was sent
-- (a refusal, a dry run), which is why this is not booking_attempts. Append-only by use.
create table public.booking_reports (
  id               bigint      generated always as identity primary key,
  received_at      timestamptz not null,
  account_id       uuid        not null references auth.users (id) on delete cascade,
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
create unique index booking_reports_one_per_task on public.booking_reports (task_digest) where task_digest is not null;

alter table public.booking_pairing_challenges enable row level security;
alter table public.booking_devices            enable row level security;
alter table public.booking_intents            enable row level security;
alter table public.booking_tasks              enable row level security;
alter table public.booking_reports            enable row level security;

-- ── 3 · MODEL A, EXTENDED ─────────────────────────────────────────────────────────────────────────────────

-- trip_items: the three outcomes this surface produces (contract §7), the party, and the venue's timezone so
-- the reservation shows 8:00 PM at the venue rather than a UTC time. date_time already holds the absolute
-- instant; booking_reference already holds the venue's reservation number.
alter table public.trip_items drop constraint trip_items_status_check;
alter table public.trip_items add constraint trip_items_status_check check (status in
  ('pending','attempting','requested','declined','unreachable','confirmed','failed','escalated','cancelled'));
alter table public.trip_items add column party_size integer null check (party_size between 1 and 100);
alter table public.trip_items add column local_timezone text null;

-- booking_attempts: ⛔ its default status of 'sent' is DROPPED — an attempt inserted without a status would
-- claim a send that nobody established. Every insert must now say what happened. It gains the contract's
-- outcome words, a link to the signed task it records, and who read the page ("the user's device" — never ours).
alter table public.booking_attempts alter column status drop default;
alter table public.booking_attempts drop constraint booking_attempts_status_check;
alter table public.booking_attempts add constraint booking_attempts_status_check check (status in
  ('sent','delivered','requested','declined','unreachable','confirmed','failed','no_response'));
alter table public.booking_attempts add column task_digest text null unique references public.booking_tasks (task_digest);
alter table public.booking_attempts add column observed_by text null;

-- ── 4 · THE CHECKLIST — the result panel shows this. Every row must say ok = true. ─────────────────────────
select 'demo auth user exists, with no email and no password' as check,
       exists (select 1 from auth.users where id = '11111111-1111-4111-8111-111111111111' and email is null and encrypted_password is null) as ok
union all
select 'five new tables, each with row-level security on',
       (select count(*) from pg_tables where schemaname = 'public' and rowsecurity
          and tablename in ('booking_pairing_challenges','booking_devices','booking_intents','booking_tasks','booking_reports')) = 5
union all
select 'booking_attempts.status has NO default',
       (select column_default from information_schema.columns where table_schema = 'public'
          and table_name = 'booking_attempts' and column_name = 'status') is null
union all
select 'booking_attempts accepts requested, declined, unreachable',
       (select pg_get_constraintdef(oid) from pg_constraint where conname = 'booking_attempts_status_check') like '%unreachable%'
union all
select 'trip_items accepts requested, declined, unreachable',
       (select pg_get_constraintdef(oid) from pg_constraint where conname = 'trip_items_status_check') like '%unreachable%'
union all
select 'trip_items has party_size and local_timezone; booking_attempts has task_digest and observed_by',
       (select count(*) from information_schema.columns where table_schema = 'public'
          and ((table_name = 'trip_items' and column_name in ('party_size','local_timezone'))
            or (table_name = 'booking_attempts' and column_name in ('task_digest','observed_by')))) = 4;
