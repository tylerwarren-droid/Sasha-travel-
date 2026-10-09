-- CR 61 · Sasha's "Add to calendar" links survive a deploy (CR 60's links lived in memory). DRAFT — apply after the Sasha tab
-- deploys cr/s2-powers (sha in its wiring commit); never applied by a tab. Until it runs, agapi/s2_tools.py keeps the links in
-- memory (a deploy clears them; the .ics is also returned inline, so the person can re-ask).
--   One row per link: the token's sha256 (the token itself is never stored), the account, the .ics text, the event's sha256.
--   Kept until 30 days after the event ends; the route refuses an expired link.
-- Idempotent. Adds only; nothing is altered in place or deleted.

-- preview (read-only)
-- select to_regclass('public.sasha_calendar_links');   -- null before

begin;

create table if not exists public.sasha_calendar_links (
  token_sha256  text primary key check (token_sha256 ~ '^[0-9a-f]{64}$'),
  account_id    uuid not null,
  event_sha256  text not null check (event_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  ics           text not null check (length(ics) between 1 and 20000),
  created_at    timestamptz not null default now(),
  expires_at    timestamptz not null
);
create index if not exists sasha_calendar_links_account on public.sasha_calendar_links (account_id);
create index if not exists sasha_calendar_links_expires on public.sasha_calendar_links (expires_at);

-- server-side only (the service role): RLS on, no policy, no grant to the client roles
alter table public.sasha_calendar_links enable row level security;
revoke all on table public.sasha_calendar_links from anon, authenticated;

commit;

-- check (read-only):
-- select count(*) from public.sasha_calendar_links;   -- 0 rows, no error
