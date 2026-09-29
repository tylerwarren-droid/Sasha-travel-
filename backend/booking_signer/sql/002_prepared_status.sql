-- ── S-26 · A DRY RUN LEAVES THE RESERVATION "PREPARED" — ONE BLOCK, FOR SASHA'S SUPABASE (xlqtveusyfpffaejegiq) ──
--
-- After a dry run the helper has filled the venue's form on the user's device, checked every value against
-- what was approved, and stopped before sending. That is a fact worth showing on the trip item — it is not
-- `pending` (nothing done) and it is never `requested` or `confirmed` (nothing was sent). So trip_items gains
-- one status, `prepared`. No booking_attempts row is written for it: an attempt is something SENT.
--
-- Run ONCE, whole. It refuses if already applied, and returns a one-row checklist that must say ok = true.
-- Applied AFTER 001_booking_storage.sql. Until it is applied, GET /api/booking/health reports storage as NOT
-- provisioned (loud), rather than a dry run failing mid-demo on a CHECK violation.

do $$
begin
  if (select pg_get_constraintdef(oid) from pg_constraint where conname = 'trip_items_status_check') like '%prepared%' then
    raise exception 'STOP: trip_items already accepts ''prepared'' — nothing was changed.';
  end if;
end $$;

alter table public.trip_items drop constraint trip_items_status_check;
alter table public.trip_items add constraint trip_items_status_check check (status in
  ('pending','prepared','attempting','requested','declined','unreachable','confirmed','failed','escalated','cancelled'));

select 'trip_items accepts prepared, and still every earlier status' as check,
       (select pg_get_constraintdef(oid) from pg_constraint where conname = 'trip_items_status_check')
         ~ 'pending.*prepared.*attempting.*requested.*declined.*unreachable.*confirmed.*failed.*escalated.*cancelled' as ok;
