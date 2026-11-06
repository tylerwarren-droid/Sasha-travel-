-- 053 · Sasha 351 · THE ROSTER: a company's people are ONE standing roster; every trip is a SELECTION from it, never a copy.
--
-- Before: group_members belonged to a movement and carried name, home city, grade, email, phone per trip, and the vault owner
-- (keep_owners.member_id) was that per-trip row — the same worker on two trips was two records with two passports (sasha-prod, 6 Nov:
-- "Obras Ejemplo SL", 82 rows for 21 people, 56 vaults).
-- After:
--   group_people   one row per worker, under the company (groups): name, grade, home airport, home city, email, phone — and their
--                  vault (keep_owners.person_id). A change here (a new home airport, a new passport) is what every future trip reads.
--   group_members  the LINK: a person on a movement (person_id, movement_id, out/back dates, trip_id) — nothing about the person copied.
-- Migrated through the data's own duplicates (the same name in the same company), each person taking the id of the row whose vault is
-- kept (the Keep's items are sealed with that id: nothing re-keyed). ARCHIVED FIRST: every old row is copied before anything changes.
-- Idempotent; refuses (rolls back) rather than guess.

select to_regclass('public.group_people') as already;

begin;

-- 1 · nothing lost: the rows as they were
create table if not exists public.group_members_archive_351 as select * from public.group_members;
create table if not exists public.keep_owners_archive_351 as select * from public.keep_owners;
alter table public.group_members_archive_351 enable row level security;
alter table public.keep_owners_archive_351 enable row level security;

-- 2 · the roster
create table if not exists public.group_people (
  id            uuid primary key default gen_random_uuid(),
  group_id      uuid not null references public.groups(id) on delete cascade,
  name          text not null check (char_length(name) between 1 and 200),
  grade         text check (grade is null or char_length(grade) <= 60),
  home_airport  text check (home_airport is null or home_airport ~ '^[A-Z]{3}$'),
  home_city     text check (home_city is null or char_length(home_city) <= 120),
  email         text check (email is null or (char_length(email) <= 254 and email ~ '^[^@\s]+@[^@\s]+\.[a-z]{2,}$')),
  phone         text check (phone is null or phone ~ '^\+[0-9]{8,15}$'),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index if not exists group_people_group on public.group_people (group_id);
create index if not exists group_people_phone on public.group_people (phone) where phone is not null;
alter table public.group_people enable row level security;

-- 3 · a trip's member is a link to a person
alter table public.group_members add column if not exists person_id uuid references public.group_people(id) on delete cascade;
alter table public.group_members alter column name drop not null;
create unique index if not exists group_members_movement_person on public.group_members (movement_id, person_id) where person_id is not null;

-- 4 · the vault belongs to the person
alter table public.keep_owners add column if not exists person_id uuid unique references public.group_people(id) on delete cascade;
alter table public.keep_owners drop constraint if exists keep_owners_exactly_one;
alter table public.keep_owners drop constraint if exists keep_owners_id_is_its_source;
alter table public.keep_owners add constraint keep_owners_exactly_one check (num_nonnulls(user_id, member_id, person_id) = 1);
alter table public.keep_owners add constraint keep_owners_id_is_its_source check (id = coalesce(user_id, member_id, person_id));

-- 5 · the people, as the data shows them: one per company and name (trimmed, case-folded); each takes the id of its row whose vault is
--     kept (the most recent with a vault, else the most recent row); contacts: the latest given
with r as (
  select gm.id, gm.name, gm.grade, gm.home_city, gm.email, gm.phone, gm.created_at, m.group_id, lower(btrim(gm.name)) as k,
         exists (select 1 from public.keep_owners o where o.member_id = gm.id) as has_vault
    from public.group_members gm join public.group_movements m on m.id = gm.movement_id
   where gm.person_id is null and gm.name is not null
), pick as (
  select distinct on (group_id, k) group_id, k, id, name, grade, home_city from r order by group_id, k, has_vault desc, created_at desc
), contact as (
  select group_id, k, (array_agg(email order by created_at desc) filter (where email is not null))[1] as email,
         (array_agg(phone order by created_at desc) filter (where phone is not null))[1] as phone
    from r group by group_id, k
)
insert into public.group_people (id, group_id, name, grade, home_city, email, phone)
select p.id, p.group_id, btrim(p.name), p.grade, p.home_city, c.email, c.phone from pick p join contact c using (group_id, k)
on conflict (id) do nothing;

update public.group_members gm set person_id = gp.id
  from public.group_movements m, public.group_people gp
 where m.id = gm.movement_id and gp.group_id = m.group_id and lower(btrim(gp.name)) = lower(btrim(gm.name)) and gm.person_id is null;

-- the vault kept for each person: owned by the person now (its id unchanged — the Keep's sealed items stay valid)
update public.keep_owners o set person_id = o.member_id, member_id = null
 where o.member_id is not null and exists (select 1 from public.group_people gp where gp.id = o.member_id);

-- 6 · the link keeps nothing about the person (the archive above has every original)
update public.group_members set name = null, home_city = null, grade = null, email = null, phone = null where person_id is not null;

-- refuse rather than guess: every row must have its person
do $$ begin
  if exists (select 1 from public.group_members where person_id is null) then
    raise exception 'Sasha 351: a group_members row has no person — nothing changed';
  end if;
end $$;

commit;

select (select count(*) from public.group_people) as people,
       (select count(*) from public.group_members) as links,
       (select count(*) from public.keep_owners where person_id is not null) as person_vaults,
       (select count(*) from public.keep_owners where member_id is not null) as old_member_vaults_kept,
       (select count(*) from public.group_members_archive_351) as archived_rows;
