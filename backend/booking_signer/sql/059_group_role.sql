-- 059 · Sasha 358 · THE ROSTER carries ROLE / DEPARTMENT beside grade ("engineer", "sales") — needed for "all engineers" next (359).
-- A person's own detail, kept once on the roster (group_people); every trip reads it from there. Lowercased by the app (read as words).
-- Idempotent; nothing existing changes (the column starts empty).

select exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'group_people' and column_name = 'role')
  as already;

begin;
alter table public.group_people add column if not exists role text;
alter table public.group_people drop constraint if exists group_people_role_len;
alter table public.group_people add constraint group_people_role_len check (role is null or char_length(role) between 1 and 80);
create index if not exists group_people_role on public.group_people (group_id, role) where role is not null;
commit;

select count(*) as people, count(role) as with_role from public.group_people;
