-- Sasha 336 · ONE OWNER RECORD PER VAULT — keep_owners: an auth user (a Sasha account) OR a group member (Sasha 333's worker), exactly one.
-- Found in SASHA 335: 042 tied keep_keys / keep_items / keep_fills to auth.users, so a group member's vault (keyed by the member id)
-- could never save. keep_owners.id IS the source id (a check), so every existing account_id is already right: nothing is rewritten.
-- Cascades: auth.users / group_members → keep_owners → keep_keys, keep_items, keep_fills. Needs 037, 042 and 048 first.
-- Safe order, ONE transaction: the table → every existing vault's owner row → the new FKs (validated) → only then the old ones go.

-- preview (read-only): the counts that must be the same after
-- select (select count(*) from public.keep_keys) keys, (select count(*) from public.keep_items) items, (select count(*) from public.keep_fills) fills;
-- select count(distinct account_id) from (select account_id from public.keep_keys union select account_id from public.keep_items
--                                        union select account_id from public.keep_fills) a;   -- = the owner rows 050 creates

begin;

create table if not exists public.keep_owners (
  id          uuid primary key,
  user_id     uuid unique references auth.users(id) on delete cascade,
  member_id   uuid unique references public.group_members(id) on delete cascade,
  created_at  timestamptz not null default now(),
  constraint keep_owners_exactly_one check (num_nonnulls(user_id, member_id) = 1),
  constraint keep_owners_id_is_its_source check (id = coalesce(user_id, member_id))
);

-- every vault that exists today belongs to an account (042's FKs guaranteed it): its owner row
insert into public.keep_owners (id, user_id)
select a.account_id, a.account_id
  from (select account_id from public.keep_keys union select account_id from public.keep_items union select account_id from public.keep_fills) a
 where exists (select 1 from auth.users u where u.id = a.account_id)
on conflict (id) do nothing;

-- the new references first (validated now: every row already has its owner) …
alter table public.keep_keys  drop constraint if exists keep_keys_owner_fkey;
alter table public.keep_items drop constraint if exists keep_items_owner_fkey;
alter table public.keep_fills drop constraint if exists keep_fills_owner_fkey;
alter table public.keep_keys  add constraint keep_keys_owner_fkey  foreign key (account_id) references public.keep_owners(id) on delete cascade;
alter table public.keep_items add constraint keep_items_owner_fkey foreign key (account_id) references public.keep_owners(id) on delete cascade;
alter table public.keep_fills add constraint keep_fills_owner_fkey foreign key (account_id) references public.keep_owners(id) on delete cascade;
-- … then 042's go (auth.users still cascades — through keep_owners now)
alter table public.keep_keys  drop constraint if exists keep_keys_account_fkey;
alter table public.keep_items drop constraint if exists keep_items_account_fkey;
alter table public.keep_fills drop constraint if exists keep_fills_account_fkey;

-- server-side only, like the rest of the Keep
alter table public.keep_owners enable row level security;
revoke all on table public.keep_owners from anon, authenticated;

commit;

-- check (read-only): the same counts as the preview; owners = the distinct account_ids; the FKs point at keep_owners
-- select (select count(*) from public.keep_keys) keys, (select count(*) from public.keep_items) items, (select count(*) from public.keep_fills) fills,
--        (select count(*) from public.keep_owners) owners;
-- select conrelid::regclass, conname, pg_get_constraintdef(oid) from pg_constraint
--  where contype = 'f' and conrelid::regclass::text in ('keep_keys','keep_items','keep_fills','keep_owners');
