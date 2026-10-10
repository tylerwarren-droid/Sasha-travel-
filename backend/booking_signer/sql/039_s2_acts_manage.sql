-- Sasha 226 · the Activity view's rows for "I'm running late" and "change my booking" (036's s2_acts): widens the kind check.
-- DRAFT — apply in Supabase AFTER the Sasha tab deploys Sasha 226 (and after 037); never applied by a tab. Until it runs, those
-- two kinds are not recorded in Activity (the act itself still happens and is said); nothing else changes.
-- preview (read-only): select pg_get_constraintdef(oid) from pg_constraint where conname = 's2_acts_kind_check';
begin;
alter table public.s2_acts drop constraint if exists s2_acts_kind_check;
alter table public.s2_acts add constraint s2_acts_kind_check
  check (kind in ('email', 'whatsapp', 'calendar', 'keep_save', 'keep_use', 'keep_show', 'keep_delete', 'venue_late', 'booking_change'));
commit;
-- check (read-only): the preview again — the two new kinds are listed.
