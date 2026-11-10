-- 060 · Sasha 364 · a trip can be ARCHIVED, never deleted: the demo starts clean (Tyler's dry run, 9 Nov: 12 old test trips in "Your
-- trips", and old Rome/Paris/London trips on the Trip tab) while every row stays — its bookings, its invoice, its history.
-- Readers leave out archived trips (the Group page's trips, the Trip tab). Idempotent; nothing existing changes (the columns start empty).

select (select count(*) from information_schema.columns where table_schema = 'public' and column_name = 'archived_at'
        and table_name in ('trips', 'group_movements')) as already;

begin;
alter table public.trips add column if not exists archived_at timestamptz;
alter table public.group_movements add column if not exists archived_at timestamptz;
create index if not exists trips_owner_live on public.trips (owner_id) where archived_at is null;
create index if not exists group_movements_live on public.group_movements (group_id) where archived_at is null;
commit;

select (select count(*) from public.trips where archived_at is not null) as trips_archived,
       (select count(*) from public.group_movements where archived_at is not null) as group_trips_archived;
