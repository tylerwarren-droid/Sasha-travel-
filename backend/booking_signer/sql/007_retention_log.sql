-- ── S-53 · THE RETENTION LOG — ONE BLOCK, FOR SASHA'S SUPABASE (xlqtveusyfpffaejegiq) ─────────────────────────
--
-- Every run of the daily retention job (booking_signer/retention.py) writes one row per rule and table: how many rows
-- it deleted or emptied, and the cutoff it used. Without this table the job deletes nothing.
--
-- Run ONCE, whole. It refuses if already applied.

do $$
begin
  if to_regclass('public.retention_log') is not null then
    raise exception 'STOP: retention_log already exists — nothing was changed.';
  end if;
end $$;

create table public.retention_log (
  id             bigint      generated always as identity primary key,
  run_id         uuid        not null,
  ran_at         timestamptz not null,
  rule           text        not null check (rule in ('bodies','bookings','consent','all')),
  table_name     text        not null,
  rows_affected  integer     not null,
  cutoff         timestamptz not null,
  note           text        null
);
create index retention_log_ran on public.retention_log (ran_at desc);
alter table public.retention_log enable row level security;

select 'retention_log exists, with row level security on' as check,
       (select relrowsecurity from pg_class where oid = 'public.retention_log'::regclass) as ok;
