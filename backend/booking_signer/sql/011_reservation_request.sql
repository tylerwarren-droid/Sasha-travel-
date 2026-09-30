-- ── S-64 step 2 · THE RESERVATION OBJECT'S COLUMNS — ONE BLOCK, FOR SASHA'S SUPABASE (xlqtveusyfpffaejegiq) ──────────
--
-- docs/sasha/S-64-agnostic-reservation.md §1.2, §3, §7 step 2. ADDITIVE AND NULLABLE ONLY: nothing is dropped, no row
-- is changed, and every writer that does not know these columns keeps working (they default to null).
--   · trip_items      + request (jsonb, the reservation/1 object), request_sha256, request_schema
--                     + type 'appointment', 'other'          + status 'proposed', 'quoted', 'waitlisted'
--   · booking_intents / booking_calls / booking_emails / booking_links  + request_sha256 (the request each carried out)
--
-- Verified live before writing (30 Sept 2026, pg_constraint / information_schema):
--   trip_items_status_check = pending prepared attempting requested declined unreachable confirmed failed escalated
--                             cancelled unclear link_sent guest_booked
--   trip_items_type_check   = flight hotel restaurant golf transfer experience visa insurance doctor beauty dog_walking coworking
--   no column named request* on any of the five tables. trip_items: 5 rows, all type restaurant.
-- The two checks are REPLACED by supersets of themselves — every value allowed before is allowed after.
--
-- Run the PREVIEW first (read only), then the block, ONCE. It refuses if already applied.

-- ── PREVIEW (read only) ──
select 'trip_items rows' as what, count(*)::text as value from public.trip_items
union all select 'status values in use', string_agg(distinct status, ', ') from public.trip_items
union all select 'type values in use', string_agg(distinct type, ', ') from public.trip_items
union all select 'request columns already present', coalesce(string_agg(table_name || '.' || column_name, ', '), 'none')
  from information_schema.columns where table_schema = 'public' and column_name like 'request%'
  and table_name in ('trip_items','booking_intents','booking_calls','booking_emails','booking_links');

-- ── THE BLOCK ──
do $$
begin
  if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'trip_items' and column_name = 'request') then
    raise exception 'STOP: 011 is already applied (trip_items.request exists) — nothing was changed.';
  end if;
end $$;

alter table public.trip_items
  add column request        jsonb null,
  add column request_sha256 text  null check (request_sha256 is null or request_sha256 ~ '^[0-9a-f]{64}$'),
  add column request_schema text  null check (request_schema is null or request_schema = 'reservation/1');

alter table public.trip_items drop constraint trip_items_type_check;
alter table public.trip_items add constraint trip_items_type_check check (type = any (array[
  'flight','hotel','restaurant','golf','transfer','experience','visa','insurance','doctor','beauty','dog_walking','coworking',
  'appointment','other']));

alter table public.trip_items drop constraint trip_items_status_check;
alter table public.trip_items add constraint trip_items_status_check check (status = any (array[
  'pending','prepared','attempting','requested','declined','unreachable','confirmed','failed','escalated','cancelled',
  'unclear','link_sent','guest_booked',
  'proposed','quoted','waitlisted']));

alter table public.booking_intents add column request_sha256 text null check (request_sha256 is null or request_sha256 ~ '^[0-9a-f]{64}$');
alter table public.booking_calls   add column request_sha256 text null check (request_sha256 is null or request_sha256 ~ '^[0-9a-f]{64}$');
alter table public.booking_emails  add column request_sha256 text null check (request_sha256 is null or request_sha256 ~ '^[0-9a-f]{64}$');
alter table public.booking_links   add column request_sha256 text null check (request_sha256 is null or request_sha256 ~ '^[0-9a-f]{64}$');

select 'reservation/1 columns and states present' as check,
       (select count(*) from information_schema.columns where table_schema = 'public' and column_name = 'request_sha256'
          and table_name in ('trip_items','booking_intents','booking_calls','booking_emails','booking_links')) = 5
   and pg_get_constraintdef((select oid from pg_constraint where conname = 'trip_items_status_check')) like '%waitlisted%'
   and pg_get_constraintdef((select oid from pg_constraint where conname = 'trip_items_type_check')) like '%appointment%' as ok;
