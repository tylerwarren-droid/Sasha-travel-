-- Sasha 332 · GROUP MOVEMENT v1 (Tyler 3 Nov 20:30): a company (the group) moves its workers. ADDITIVE: three new tables, nothing else
-- touched. Each worker's travel lives on ONE trip of theirs (trips + its trip_basket_items, trip_items once booked) — the group's master
-- list is computed from those trips, never stored. The group's rules (price limits) live in ONE place: group_movements.rules.
-- preview (read-only)
select to_regclass('public.groups'), to_regclass('public.group_movements'), to_regclass('public.group_members');

begin;
create table if not exists public.groups (
  id           uuid primary key default gen_random_uuid(),
  owner_id     uuid not null references auth.users(id) on delete cascade,   -- the organiser (the account that talks to Sasha)
  name         text not null check (char_length(name) between 1 and 200),
  created_at   timestamptz not null default now()
);
create table if not exists public.group_movements (
  id           uuid primary key default gen_random_uuid(),
  group_id     uuid not null references public.groups(id) on delete cascade,
  destination  text not null check (char_length(destination) between 1 and 120),
  starts_on    date,
  ends_on      date,
  hotel_area   text check (hotel_area is null or char_length(hotel_area) <= 200),
  rules        jsonb not null default '{}'::jsonb,   -- THE ONE PLACE: {"limits": {"by_grade": {grade: {flight_return_eur, hotel_night_eur}}, "by_member": {member_id: {...}}}}
  created_at   timestamptz not null default now()
);
create table if not exists public.group_members (
  id           uuid primary key default gen_random_uuid(),
  movement_id  uuid not null references public.group_movements(id) on delete cascade,
  name         text not null check (char_length(name) between 1 and 200),
  home_city    text check (home_city is null or char_length(home_city) <= 120),
  out_date     date,
  back_date    date,
  grade        text check (grade is null or char_length(grade) <= 60),
  trip_id      uuid references public.trips(id) on delete set null,   -- the worker's ONE trip (their flights and hotel live there)
  created_at   timestamptz not null default now(),
  unique (movement_id, name)
);
create index if not exists group_members_movement on public.group_members (movement_id);
create index if not exists groups_owner on public.groups (owner_id);
alter table public.groups enable row level security;
alter table public.group_movements enable row level security;
alter table public.group_members enable row level security;
commit;

-- verify
select to_regclass('public.groups'), to_regclass('public.group_movements'), to_regclass('public.group_members');
