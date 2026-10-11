-- Sasha 236 · ACCOUNT DELETE = DELETE EVERYTHING (Tyler: "yes, we delete everything"). An account's Keep (fills, items, its key) and
-- its /s2 records (Activity, WhatsApp contacts and replies) go with the account itself: each table's account_id references
-- auth.users ON DELETE CASCADE, as s2_memory already does (041). The code purges them explicitly too (booking_signer/purge.py,
-- called by DELETE /api/booking/account/data) — this is the floor under it: an auth user deleted any other way takes them with it.
-- Found in 235: a deleted scratch guest left 3 keep_items, its keep_keys row and 12 s2_acts rows.
-- DRAFT — apply in Supabase AFTER the Sasha tab deploys Sasha 236; never applied by a tab. Nothing depends on it being applied first.
-- Schema verified live (11 Oct): account_id is uuid NOT NULL on all six; none has an FK to auth.users; keep_fills → keep_items cascades.

-- preview (read-only): the rows whose account no longer exists — deleted below (11 Oct: s2_acts 1, every other table 0)
-- select t, count(*) from (
--   select 'keep_fills' t, account_id from public.keep_fills union all select 'keep_items', account_id from public.keep_items
--   union all select 'keep_keys', account_id from public.keep_keys union all select 's2_acts', account_id from public.s2_acts
--   union all select 's2_wa_contacts', account_id from public.s2_wa_contacts union all select 's2_wa_replies', account_id from public.s2_wa_replies) x
-- where not exists (select 1 from auth.users u where u.id = x.account_id) group by t;

begin;

delete from public.keep_fills     f where not exists (select 1 from auth.users u where u.id = f.account_id);
delete from public.keep_items     i where not exists (select 1 from auth.users u where u.id = i.account_id);
delete from public.keep_keys      k where not exists (select 1 from auth.users u where u.id = k.account_id);
delete from public.s2_acts        a where not exists (select 1 from auth.users u where u.id = a.account_id);
delete from public.s2_wa_replies  r where not exists (select 1 from auth.users u where u.id = r.account_id);
delete from public.s2_wa_contacts c where not exists (select 1 from auth.users u where u.id = c.account_id);

alter table public.keep_fills     add constraint keep_fills_account_fkey     foreign key (account_id) references auth.users(id) on delete cascade;
alter table public.keep_items     add constraint keep_items_account_fkey     foreign key (account_id) references auth.users(id) on delete cascade;
alter table public.keep_keys      add constraint keep_keys_account_fkey      foreign key (account_id) references auth.users(id) on delete cascade;
alter table public.s2_acts        add constraint s2_acts_account_fkey        foreign key (account_id) references auth.users(id) on delete cascade;
alter table public.s2_wa_replies  add constraint s2_wa_replies_account_fkey  foreign key (account_id) references auth.users(id) on delete cascade;
alter table public.s2_wa_contacts add constraint s2_wa_contacts_account_fkey foreign key (account_id) references auth.users(id) on delete cascade;

commit;

-- check (read-only): seven cascades to auth.users
-- select conrelid::regclass, conname from pg_constraint
--  where confrelid = 'auth.users'::regclass and confdeltype = 'c'
--    and conrelid::regclass::text in ('keep_fills','keep_items','keep_keys','s2_acts','s2_wa_replies','s2_wa_contacts','s2_memory');
