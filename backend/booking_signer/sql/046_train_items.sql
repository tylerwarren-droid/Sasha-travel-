-- Sasha 327 · TRAINS ARE TRAINS — a ticket he bought himself (read by AgAPI's ONE reader, venue.confirmation) is a trip item of type
-- 'train' on the ONE trip record (booking_signer/trains.py). Only trip_items_type_check changes: 'train' is added to the list 011 set.
-- Nothing else in the table changes (no new column): the act link rides in escalation_notes ("agapi_act:<act_id>"), the price stays on
-- AgAPI's act (price_usd never holds euros).
-- Safe to apply before or after the Sasha 327 deploy: until it's applied, writing a train is refused by the check — the code logs it,
-- keeps the ticket on AgAPI's act and the mailbox find, and writes the train at the next mailbox sync after this is applied.
-- Never stored as 'other'.

-- preview (read-only): the current list (011's), and the 'other' items the re-read may turn into trains
select pg_get_constraintdef(oid) from pg_constraint where conrelid = 'public.trip_items'::regclass and conname = 'trip_items_type_check';
select type, count(*) from public.trip_items group by type order by type;

begin;
alter table public.trip_items drop constraint trip_items_type_check;
alter table public.trip_items add constraint trip_items_type_check check (type = any (array[
  'flight','hotel','restaurant','golf','transfer','experience','visa','insurance','doctor','beauty','dog_walking','coworking',
  'appointment','other','train']));
commit;

-- verify: 'train' in the check
select pg_get_constraintdef(oid) from pg_constraint where conrelid = 'public.trip_items'::regclass and conname = 'trip_items_type_check';
