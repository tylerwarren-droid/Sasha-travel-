-- Sasha 227 · car rentals the person TOLD Sasha about on /s2 (she books none): for My plans, and — for the founder only, behind
-- SASHA_PROACTIVE_RENTALS — CR 75's "day before pickup" line. moment_at = the one moment claimed per rental (never two).
-- DRAFT — apply in Supabase AFTER the Sasha tab deploys Sasha 227; never applied by a tab. Until then rentals live in the process's
-- memory (a restart forgets them; nothing fails).
-- preview (read-only): select to_regclass('public.s2_rentals');   -- null before
begin;
create table if not exists public.s2_rentals (
  id              uuid primary key,
  account_id      uuid not null references auth.users(id) on delete cascade,
  rental_company  text not null check (length(rental_company) between 1 and 80),
  country         text not null check (country ~ '^[A-Z]{2}$'),
  place           text check (place is null or length(place) <= 120),
  pickup_date     date not null,
  pickup_time     text check (pickup_time is null or pickup_time ~ '^[0-2][0-9]:[0-5][0-9]$'),
  days            integer check (days is null or days between 1 and 90),
  created_at      timestamptz not null default now(),
  moment_at       timestamptz,
  moment_outcome  text check (moment_outcome is null or length(moment_outcome) <= 200)
);
create index if not exists s2_rentals_account on public.s2_rentals (account_id, pickup_date);
alter table public.s2_rentals enable row level security;
revoke all on table public.s2_rentals from anon, authenticated;
commit;
-- check (read-only): select count(*) from public.s2_rentals;   -- 0, no error
