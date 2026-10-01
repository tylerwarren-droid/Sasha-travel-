-- 014 · Sasha 64 · a call on a Google Maps LISTING number stores its hash, never its digits (places_terms.py):
-- dialled_number is "sha256:<64 hex>" for those calls, E.164 as before for a number on the venue's own site.
-- Found 1 Oct 2026 when 013 hit the old check on the live database (rolled back, nothing changed): without this, a
-- listing-number call could not be recorded at all. Calls are off, so nothing was refused in use.
-- Verified against the live schema (pg_constraint) before writing: the constraint is booking_calls_dialled_number_check,
-- CHECK ((dialled_number ~ '^\+[1-9][0-9]{7,14}$')).

-- PREVIEW (read-only): every current value already satisfies the new check
select count(*) total, count(*) filter (where dialled_number ~ '^\+[1-9][0-9]{7,14}$' or dialled_number ~ '^sha256:[0-9a-f]{64}$') passing
from booking_calls;

begin;
alter table booking_calls drop constraint booking_calls_dialled_number_check;
alter table booking_calls add constraint booking_calls_dialled_number_check
  check (dialled_number ~ '^\+[1-9][0-9]{7,14}$' or dialled_number ~ '^sha256:[0-9a-f]{64}$');
commit;

-- VERIFY (read-only)
select pg_get_constraintdef(oid) from pg_constraint where conname = 'booking_calls_dialled_number_check';
