-- 028 · CR 1 · product cases: one row per CampusMe request (a prepared hand-over, or a month being watched) and per
-- relocation file (the applicant's facts, each with its source; the EX-01 rows). backend/products/store.py.
-- The id is the capability for the case's page (22 random url-safe characters), so it is text, not a uuid.
-- Personal data (a student's name, email and birthdate; an applicant's passport facts): RLS ON with NO policy — only the
-- server's database role reads or writes it, never a guest's Supabase session. Every row expires after 30 days; the
-- products' daily job deletes expired rows (logged in retention_log, as S-53's job logs its own).
-- Until this is applied, the products run on this server's memory and /api/booking/products/health says "memory".
-- ⛔ NOT APPLIED by any session: the founder approves, then it is applied by chat (preview, transaction, verify).
-- Target: sasha-prod (yjafyzywzbmhlilxhzuz), where guest_wa_state and trip_items live.

-- PREVIEW (read-only): must return NULL (the table does not exist yet)
select to_regclass('public.product_cases') as already_there;

begin;
do $x$ begin
  if to_regclass('public.product_cases') is not null then raise exception 'STOP: product_cases already exists — 028 already applied'; end if;
end $x$;

create table public.product_cases (
  id            text        primary key check (length(id) >= 20),
  product       text        not null check (product in ('campus', 'relocation')),
  account_id    uuid        not null,
  wa_id_sha256  text        not null,
  state         jsonb       not null default '{}'::jsonb,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  expires_at    timestamptz not null default now() + interval '30 days'
);
create index product_cases_account on public.product_cases (account_id, product, created_at desc);
create index product_cases_expires on public.product_cases (expires_at);
create index product_cases_watching on public.product_cases (product) where (state->'watch'->>'open') = 'true';
alter table public.product_cases enable row level security;   -- and no policy: the server's role only
comment on table public.product_cases is 'CR 1 (CampusMe, relocation). Personal data; 30-day expiry; server role only.';
commit;

-- VERIFY (read-only): the table, RLS on, and zero policies
select relname, relrowsecurity from pg_class where oid = 'public.product_cases'::regclass;
select count(*) as policies from pg_policies where schemaname = 'public' and tablename = 'product_cases';
