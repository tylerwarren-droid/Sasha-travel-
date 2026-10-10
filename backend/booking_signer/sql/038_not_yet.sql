-- Sasha 225 · WHAT SASHA CAN'T DO YET — every "not yet" on /s2, kept for the founder (GET /api/agent/not-yet), MASKED: what was
-- asked with digits, emails and phone numbers removed, and the account only as a short one-way hash. Server-side only.
-- DRAFT — apply in Supabase AFTER the Sasha tab deploys Sasha 225; never applied by a tab. Until it runs, the list is kept in
-- the process's memory and Railway's log ([s2-not-yet]) — nothing fails without it.
-- preview (read-only): select to_regclass('public.s2_not_yet');   -- null before

begin;

create table if not exists public.s2_not_yet (
  id     uuid primary key,
  who    text not null check (who ~ '^acct:[0-9a-f]{10}$'),
  asked  text not null check (length(asked) <= 200),
  at     timestamptz not null default now()
);
create index if not exists s2_not_yet_at on public.s2_not_yet (at desc);

alter table public.s2_not_yet enable row level security;
revoke all on table public.s2_not_yet from anon, authenticated;

commit;

-- check (read-only): select count(*) from public.s2_not_yet;   -- 0, no error
