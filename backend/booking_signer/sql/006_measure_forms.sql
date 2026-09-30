-- ── S-40 · THE FORM MEASUREMENT'S STORAGE — ONE BLOCK, FOR SASHA'S SUPABASE (xlqtveusyfpffaejegiq) ──────────────
--
-- Three tables the one-off Railway service writes (booking_signer/measure_forms.py) and nothing else reads but the
-- offline scorer. Per page it keeps only the <form> blocks, the <label>s, frame/script hosts and calendar markers,
-- gzip'd — not whole pages. Nothing here touches the booking tables.
--
-- Run ONCE, whole. It refuses if already applied. Independent of 001–005.

do $$
begin
  if to_regclass('public.measure_runs') is not null then
    raise exception 'STOP: measure_runs already exists — nothing was changed.';
  end if;
end $$;

create table public.measure_runs (
  run_id            uuid        primary key,
  started_at        timestamptz not null,
  finished_at       timestamptz null,
  scorer_commit     text        not null,
  overture_release  text        not null,
  sample_seed       bigint      not null,
  params            jsonb       not null,
  seeding           jsonb       not null,   -- per city: its box and where it came from, rows, exclusions, pools, drawn
  hosts             integer     null
);

create table public.measure_hosts (
  host_id      bigint      generated always as identity primary key,
  run_id       uuid        not null references public.measure_runs (run_id),
  city         text        not null,
  country      text        not null,
  kind         text        not null check (kind in ('food','activity')),
  overture_id  text        not null,
  name         text        not null,
  category     text        not null,
  website      text        not null,
  host         text        not null,
  robots       text        null,
  result       text        null
);
create index measure_hosts_run on public.measure_hosts (run_id);

create table public.measure_pages (
  page_id       bigint      generated always as identity primary key,
  host_id       bigint      not null references public.measure_hosts (host_id),
  url           text        not null,
  status        integer     null,
  bytes         integer     null,
  sha256        text        null,
  fetched_at    timestamptz null,
  note          text        null,
  fragments_gz  bytea       null
);
create index measure_pages_host on public.measure_pages (host_id);

alter table public.measure_runs  enable row level security;
alter table public.measure_hosts enable row level security;
alter table public.measure_pages enable row level security;

select 'the three measurement tables exist, with row level security on' as check,
       (select count(*) from pg_class where relname in ('measure_runs','measure_hosts','measure_pages')
          and relnamespace = 'public'::regnamespace and relrowsecurity) = 3 as ok;
