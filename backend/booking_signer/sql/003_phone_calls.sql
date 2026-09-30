-- ── S-33 · THE PHONE RUNG — ONE BLOCK, FOR SASHA'S SUPABASE (xlqtveusyfpffaejegiq) ─────────────────────────────
--
-- A call Sasha places to a venue, as a concierge, is recorded in ONE new table, booking_calls: the approved brief
-- and read-back (and their hashes), exactly what Bland answered when asked to place it, the finished call's details,
-- and the reading — yes / no / unclear, always with the venue's own words.
--
-- Model A gains one status, `unclear`, on both trip_items and booking_attempts: the venue answered, and it was
-- neither a clear yes nor a clear no ("call back tomorrow", "we can do 9:15 instead", "we'll need a deposit").
-- A yes becomes `confirmed`, a no `declined`, exactly as a form's outcome does. A call that never reached a person
-- changes NOTHING in model A: nothing was agreed, so the reservation stays `pending`.
--
-- Run ONCE, whole, AFTER 001 and 002. It refuses if already applied or if 002 is missing, and returns a
-- checklist that must say ok = true on every row.

-- ── PREVIEW — run this first on its own; it changes nothing. It shows the two constraints this block replaces. ──
-- select conname, pg_get_constraintdef(oid) from pg_constraint
--  where conname in ('trip_items_status_check', 'booking_attempts_status_check', 'booking_attempts_method_check');

-- ── 0 · THE GUARD ─────────────────────────────────────────────────────────────────────────────────────────────
do $$
begin
  if to_regclass('public.booking_calls') is not null then
    raise exception 'STOP: booking_calls already exists — nothing was changed.';
  end if;
  if (select pg_get_constraintdef(oid) from pg_constraint where conname = 'trip_items_status_check') not like '%prepared%' then
    raise exception 'STOP: 002_prepared_status.sql has not been applied — nothing was changed.';
  end if;
  if (select pg_get_constraintdef(oid) from pg_constraint where conname = 'trip_items_status_check') like '%unclear%' then
    raise exception 'STOP: trip_items already accepts ''unclear'' — nothing was changed.';
  end if;
  if (select pg_get_constraintdef(oid) from pg_constraint where conname = 'booking_attempts_method_check') not like '%phone%' then
    raise exception 'STOP: booking_attempts.method does not accept ''phone'' — nothing was changed.';
  end if;
end $$;

-- ── 1 · THE CALL LEDGER ───────────────────────────────────────────────────────────────────────────────────────
-- ⚠ ONE CALL PER APPROVAL, EVER: the row is claimed (awaiting_approval → placing) BEFORE Bland is asked, so a
-- double-click or a retry cannot dial twice. A second call is a new row, a new read-back and a new yes.
create table public.booking_calls (
  call_id           uuid        primary key,
  account_id        uuid        not null references auth.users (id) on delete cascade,
  trip_item_id      uuid        not null references public.trip_items (id),
  venue_key         text        not null,
  dialled_number    text        not null check (dialled_number ~ '^\+[1-9][0-9]{7,14}$'),
  language          text        not null,
  guest_name        text        not null,
  guest_phone       text        null,
  brief             jsonb       not null,
  brief_sha256      text        not null check (brief_sha256 ~ '^[0-9a-f]{64}$'),
  read_back_lines   jsonb       not null,
  read_back_sha256  text        not null check (read_back_sha256 ~ '^[0-9a-f]{64}$'),
  status            text        not null check (status in ('awaiting_approval','placing','placed','not_placed','not_reached','answered')),
  created_at        timestamptz not null,
  approval          jsonb       null,
  approved_at       timestamptz null,
  -- exactly what Bland answered when asked to place the call — kept as it came, success or not
  bland_call_id     text        null unique,
  bland_http_status integer     null,
  bland_answer      jsonb       null,
  not_placed_why    text        null,
  placed_at         timestamptz null,
  -- the finished call, and the reading of it
  bland_details     jsonb       null,
  outcome           text        null check (outcome in ('yes','no','unclear')),
  venue_words       text        null,
  reading           jsonb       null,
  read_at           timestamptz null,
  check ((status = 'answered') = (outcome is not null))
);
create index booking_calls_account on public.booking_calls (account_id, created_at desc);
create index booking_calls_approved on public.booking_calls (approved_at) where approved_at is not null;
alter table public.booking_calls enable row level security;

-- ── 2 · MODEL A: `unclear` ────────────────────────────────────────────────────────────────────────────────────
alter table public.trip_items drop constraint trip_items_status_check;
alter table public.trip_items add constraint trip_items_status_check check (status in
  ('pending','prepared','attempting','requested','declined','unreachable','confirmed','failed','escalated','cancelled','unclear'));
alter table public.booking_attempts drop constraint booking_attempts_status_check;
alter table public.booking_attempts add constraint booking_attempts_status_check check (status in
  ('sent','delivered','requested','declined','unreachable','confirmed','failed','no_response','unclear'));

-- ── 3 · THE CHECKLIST ─────────────────────────────────────────────────────────────────────────────────────────
select 'booking_calls exists, with row level security on' as check,
       (select relrowsecurity from pg_class where oid = 'public.booking_calls'::regclass) as ok
union all
select 'trip_items accepts unclear, and still prepared',
       (select pg_get_constraintdef(oid) from pg_constraint where conname = 'trip_items_status_check') like '%unclear%'
   and (select pg_get_constraintdef(oid) from pg_constraint where conname = 'trip_items_status_check') like '%prepared%'
union all
select 'booking_attempts accepts unclear, and still no_response',
       (select pg_get_constraintdef(oid) from pg_constraint where conname = 'booking_attempts_status_check') like '%unclear%'
   and (select pg_get_constraintdef(oid) from pg_constraint where conname = 'booking_attempts_status_check') like '%no_response%';
