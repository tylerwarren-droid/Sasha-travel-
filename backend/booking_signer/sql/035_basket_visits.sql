-- CR 54 · CAMPUS VISITS IN THE TRIP BASKET (docs/sasha/mes-as-skills-design.md §2.4). DRAFT — NOT APPLIED.
-- ⛔ APPLY AFTER DEPLOY 82e1675 (CR 54: the commit that ships backend/booking_signer/basket_visits.py; apply only once a
--    Railway deploy containing it shows SUCCESS) — the founder runs it in the
--    Supabase SQL editor; this tab never applies it. Before it is applied, CampusMe's visit tools refuse honestly ("the
--    tour's visits can't be saved yet") — nothing else changes.
-- Needs 033_trip_basket.sql. Idempotent. Widens two checks; nothing is deleted, no row changes, no other table is touched.
--   kind:  + 'visit'
--   state: + 'prepared' · 'registered' · 'not_confirmed'   (a visit: suggested → prepared → registered | not_confirmed | cancelled)
-- Who writes a visit's state (booking_signer/basket_visits.py): Magellan suggested · Austen prepared ·
-- Pacioli registered / not_confirmed — ONLY from the school's own confirmation, matched (products/campus/confirm.py).

-- preview (read-only): the two checks as they stand
-- select conname, pg_get_constraintdef(oid) from pg_constraint
--  where conrelid = 'public.trip_basket_items'::regclass and contype = 'c';

begin;

alter table public.trip_basket_items drop constraint if exists trip_basket_items_kind_check;
alter table public.trip_basket_items add constraint trip_basket_items_kind_check
  check (kind in ('flight', 'stay', 'venue', 'visit'));

alter table public.trip_basket_items drop constraint if exists trip_basket_items_state_check;
alter table public.trip_basket_items add constraint trip_basket_items_state_check
  check (state in ('suggested', 'chosen', 'pending_payment', 'booked', 'failed', 'cancelled',
                   'prepared', 'registered', 'not_confirmed'));

-- a visit is a school's, never a provider order: only 'visit' rows may hold the visit-only states
alter table public.trip_basket_items drop constraint if exists trip_basket_items_visit_states;
alter table public.trip_basket_items add constraint trip_basket_items_visit_states
  check (kind = 'visit' or state not in ('prepared', 'registered', 'not_confirmed'));

create index if not exists trip_basket_items_visits on public.trip_basket_items (account_id, day) where kind = 'visit';

commit;

-- verify (read-only)
-- select pg_get_constraintdef(oid) from pg_constraint where conname in
--   ('trip_basket_items_kind_check', 'trip_basket_items_state_check', 'trip_basket_items_visit_states');
