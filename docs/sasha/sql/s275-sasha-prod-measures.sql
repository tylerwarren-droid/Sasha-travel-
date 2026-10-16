-- SASHA 275 · S1 MEASURE — SQL FOR CHAT, project sasha-prod (the database Sasha's DATABASE_URL points at).
-- A DERIVED copy (agapi/measure.py): ids only (hashed), no content, names, phones or emails. RLS on, NO policies: only the service
-- role / the backend's own connection (postgres, bypasses RLS) can read or write it. Rows expire after 90 days (the daily job deletes).
-- Preview first (nothing destructive here): select to_regclass('public.sasha_measures');
create table if not exists public.sasha_measures (
  id          text primary key,                                  -- 't:<turn>' · 'c:<turn>' · 'b:<request cid>' · 'd:<day>'
  kind        text not null check (kind in ('turn', 'client', 'booking', 'daily')),
  at          timestamptz not null default now(),
  day         date not null,                                     -- Europe/Madrid
  data        jsonb not null,
  mv          integer not null,                                  -- measure-derivation version (MEASURE_VERSION)
  sasha       text not null,                                     -- the Sasha commit that wrote it
  agapi       text,                                              -- the AgAPI that served it (version or target)
  expires_at  timestamptz not null                               -- at + 90 days
);
create index if not exists sasha_measures_day_kind on public.sasha_measures (day, kind);
create index if not exists sasha_measures_kind_at on public.sasha_measures (kind, at);
create index if not exists sasha_measures_expires on public.sasha_measures (expires_at);
create index if not exists sasha_measures_acts on public.sasha_measures using gin ((data -> 'acts'));
alter table public.sasha_measures enable row level security;
revoke all on table public.sasha_measures from public, anon, authenticated;
-- VERIFY (expect: rls true, 0 policies, anon/authenticated without any privilege):
select relrowsecurity as rls, (select count(*) from pg_policies where tablename = 'sasha_measures') as policies,
       has_table_privilege('anon', 'public.sasha_measures', 'select') as anon_select,
       has_table_privilege('authenticated', 'public.sasha_measures', 'select') as authenticated_select
from pg_class where oid = 'public.sasha_measures'::regclass;
