-- 055 · Sasha 351 · ONE vault per person — step 3 of 3: a trip's row is never a vault owner.
--
-- Run AFTER the fold (booking_signer/vault_fold.py) reports "left": 0. Refuses (rolls back) while any vault is still owned by a trip row.
-- A vault is a signed-in account's (user_id) or a roster person's (person_id) — exactly one. Idempotent.


begin;

do $$ declare n int; begin
  if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'keep_owners' and column_name = 'member_id') then
    execute 'select count(*) from public.keep_owners where member_id is not null' into n;   -- dynamic: on a re-run the column is gone
    if n > 0 then
      raise exception 'Sasha 351: % vaults are still owned by trip rows — run the fold (booking_signer/vault_fold.py) first; nothing changed', n;
    end if;
  end if;
end $$;

alter table public.keep_owners drop constraint if exists keep_owners_exactly_one;
alter table public.keep_owners drop constraint if exists keep_owners_id_is_its_source;
alter table public.keep_owners drop column if exists member_id;
alter table public.keep_owners add constraint keep_owners_exactly_one check (num_nonnulls(user_id, person_id) = 1);
alter table public.keep_owners add constraint keep_owners_id_is_its_source check (id = coalesce(user_id, person_id));

commit;

select (select count(*) from public.keep_owners where user_id is not null) as account_vaults,
       (select count(*) from public.keep_owners where person_id is not null) as person_vaults,
       (select count(*) from information_schema.columns where table_name = 'keep_owners' and column_name = 'member_id') as member_id_column;
