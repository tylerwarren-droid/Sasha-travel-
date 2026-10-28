-- Sasha 303 · ONE GATE FOR HER LIVE FACE (HeyGen LiveAvatar) — app/avatar_gate.py. Two things the database doesn't have yet:
--   sasha_measures.kind 'avatar'   the LOG: one row per session (who hashed, why it opened, opened/closed, seconds, why it closed)
--   sasha_avatar_day               the gate's own DAY LEDGER (seconds per person per day, and '*' for all of Kanoe): the caps'
--                                  authority (measures are never one — S275). Server-only: RLS on, no policy, nothing granted to
--                                  anon / authenticated; the backend connects as postgres.
-- Read 28 Oct 2026 from sasha-prod (yjafyzywzbmhlilxhzuz):
--   sasha_measures_kind_check  CHECK (kind = ANY (ARRAY['turn','client','booking','daily']))
--   sasha_measures             relrowsecurity true, owner postgres; anon / authenticated hold no grants on it
--   sasha_avatar_day           does not exist
-- Safe to apply before or after the Sasha 303 deploy: until it's applied the gate counts the day in its own process (a restart
-- forgets it) and the avatar log rows are refused by the check (logged once, nothing about her changes).
-- No function is created (CLAUDE.md §3: nothing to revoke by name).

-- preview (read-only)
select conname, pg_get_constraintdef(oid) from pg_constraint where conname = 'sasha_measures_kind_check';
select kind, count(*) from public.sasha_measures group by kind;
select to_regclass('public.sasha_avatar_day');

begin;
alter table public.sasha_measures drop constraint sasha_measures_kind_check;
alter table public.sasha_measures add constraint sasha_measures_kind_check
  check (kind = any (array['turn','client','booking','daily','avatar']));

create table if not exists public.sasha_avatar_day (
  day     date    not null,
  account text    not null,            -- the person's account id, or '*' for all of Kanoe
  seconds integer not null default 0 check (seconds >= 0),
  primary key (day, account)
);
alter table public.sasha_avatar_day enable row level security;
revoke all on table public.sasha_avatar_day from public, anon, authenticated;
commit;

-- verify: 'avatar' in the check; the ledger there, RLS on, no grant to anon / authenticated
select pg_get_constraintdef(oid) from pg_constraint where conname = 'sasha_measures_kind_check';
select relname, relrowsecurity from pg_class where relname = 'sasha_avatar_day';
select grantee, privilege_type from information_schema.role_table_grants
 where table_name = 'sasha_avatar_day' and grantee in ('anon', 'authenticated');   -- expect no rows
