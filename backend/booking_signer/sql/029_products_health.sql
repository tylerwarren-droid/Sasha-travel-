-- 029 · CR 4 · product_cases also holds HEALTH cases (backend/products/health/): a SERMAS hand-over or a new-in-Madrid
-- checklist. Same table rules as 028: RLS on, no policy (server role only), 30-day expiry. A health hand-over's
-- identifiers are dropped from its row after 24 hours; a real person's are only ever there if they came from the vault
-- (special category, Art. 9 consent, behind the DPIA). Until this is applied, a health case can't be kept, and the chat
-- says so ("Health isn't switched on on this server yet").
-- ⛔ NOT APPLIED by any session: the founder approves, then it is applied by chat (preview, transaction, verify).
-- Target: sasha-prod (yjafyzywzbmhlilxhzuz).

-- PREVIEW (read-only): the check as it is now — must list 'campus' and 'relocation' only
select conname, pg_get_constraintdef(oid) from pg_constraint
where conrelid = 'public.product_cases'::regclass and contype = 'c' and conname = 'product_cases_product_check';

begin;
do $x$ begin
  if pg_get_constraintdef((select oid from pg_constraint where conrelid = 'public.product_cases'::regclass
                           and conname = 'product_cases_product_check')) like '%health%' then
    raise exception 'STOP: product_cases already accepts health — 029 already applied';
  end if;
end $x$;
alter table public.product_cases drop constraint product_cases_product_check;
alter table public.product_cases add constraint product_cases_product_check
  check (product in ('campus', 'relocation', 'health'));
commit;

-- VERIFY (read-only): the check now lists health
select pg_get_constraintdef(oid) from pg_constraint
where conrelid = 'public.product_cases'::regclass and conname = 'product_cases_product_check';
