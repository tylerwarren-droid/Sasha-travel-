-- 027 · Sasha 120 · before guest sign-up opens: a signed-in guest may no longer WRITE a booking's status or its attempts
-- directly (PostgREST with their own token), bypassing Sasha. Those rows are the proof the receipt shows ("what the
-- venue said"); only the server (the database role, which RLS does not bind) writes them.
-- Verified against the live schema (sasha-prod) on 3 Oct 2026 — these three policies exist, and nothing uses them:
-- no frontend or backend code writes trip_items or booking_attempts through a guest's Supabase session (the browser
-- never reaches the database: the client bundle carries no Supabase URL).
--   booking_attempts_insert_trip_owner (INSERT), trip_items_insert_trip_owner (INSERT), trip_items_update_trip_owner (UPDATE)
-- The SELECT policies stay: a guest still READS only their own.
-- ⛔ NOT APPLIED by any session: the founder approves, then it is applied by chat (preview, transaction, verify).

-- PREVIEW (read-only): must list the three
select tablename, policyname, cmd from pg_policies
where schemaname = 'public' and policyname in ('booking_attempts_insert_trip_owner', 'trip_items_insert_trip_owner', 'trip_items_update_trip_owner');

begin;
drop policy booking_attempts_insert_trip_owner on public.booking_attempts;
drop policy trip_items_insert_trip_owner on public.trip_items;
drop policy trip_items_update_trip_owner on public.trip_items;
commit;

-- VERIFY (read-only): zero rows; the SELECT policies still there
select policyname from pg_policies where schemaname = 'public' and tablename in ('trip_items', 'booking_attempts') and cmd <> 'SELECT';
select policyname from pg_policies where schemaname = 'public' and tablename in ('trip_items', 'booking_attempts') and cmd = 'SELECT';
