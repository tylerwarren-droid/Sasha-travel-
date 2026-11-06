-- 054 · Sasha 351 · ONE vault per person — step 1 of 3: ARCHIVE FIRST.
--
-- After 053 the roster's person owns a vault (keep_owners.person_id), but 38 vaults (sasha-prod, 6 Nov 11:40) are still owned by old trip
-- rows (keep_owners.member_id): SECOND COPIES of a person's vault, from when each trip row had its own. Step 2 (the product,
-- booking_signer/vault_fold.py → s2_keep.fold_into) keeps the newest item per kind in the person's own vault and shreds the rest; step 3
-- (055) drops member_id from keep_owners' allowed owners.
-- This step copies, before anything changes, every row the fold may touch: each copy's owner row, key and items, AND each of their
-- persons' owner row, key and items (the fold may drop a person's older item of a kind). The keys are archived with their items, so an
-- archived item can still be opened (by the key service, never by SQL). Idempotent.

select (select count(*) from public.keep_owners where member_id is not null) as copies_now;

begin;

create table if not exists public.keep_owners_archive_351b as
  select o.* from public.keep_owners o
   where o.member_id is not null
      or o.person_id in (select gm.person_id from public.keep_owners c join public.group_members gm on gm.id = c.member_id);
create table if not exists public.keep_keys_archive_351b as
  select k.* from public.keep_keys k where k.account_id in (select id from public.keep_owners_archive_351b);
create table if not exists public.keep_items_archive_351b as
  select i.* from public.keep_items i where i.account_id in (select id from public.keep_owners_archive_351b);
alter table public.keep_owners_archive_351b enable row level security;
alter table public.keep_keys_archive_351b enable row level security;
alter table public.keep_items_archive_351b enable row level security;
revoke all on table public.keep_owners_archive_351b, public.keep_keys_archive_351b, public.keep_items_archive_351b from anon, authenticated;

commit;

select (select count(*) from public.keep_owners_archive_351b where member_id is not null) as copies_archived,
       (select count(*) from public.keep_owners_archive_351b where person_id is not null) as persons_archived,
       (select count(*) from public.keep_keys_archive_351b) as keys_archived,
       (select count(*) from public.keep_items_archive_351b) as items_archived;
