-- Sasha 231 · MEMORY ACROSS VISITS on /s2: per account, the recent conversation (≤ 20 lines, masked — never a passport, card or ID
-- value), a short running summary, the thing they were looking at, and anything unfinished (a hold awaiting their yes, a question
-- she asked). One row per account, replaced turn by turn (agapi/s2_memory.py). Read only by the backend (service role).
-- DRAFT — apply in Supabase AFTER the Sasha tab deploys Sasha 231; never applied by a tab. Until then the memory lives in the
-- process (a restart or redeploy forgets it; nothing fails).
-- preview (read-only): select to_regclass('public.s2_memory');   -- null before
begin;
create table if not exists public.s2_memory (
  account_id  uuid primary key references auth.users(id) on delete cascade,
  memory      jsonb not null default '{}'::jsonb,
  updated_at  timestamptz not null default now()
);
alter table public.s2_memory enable row level security;
revoke all on table public.s2_memory from anon, authenticated;
commit;
-- check (read-only): select count(*) from public.s2_memory;   -- 0, no error
