-- 056 · Sasha 351 · the organiser's OPEN trip: their trips are many (each a selection from the one roster), and the one every action is
-- about (the master list, Book all, the invoice, what they ask Sasha) is the one they OPENED last — never just the newest made (found live,
-- 6 Nov: starting a Porto trip left the Lisbon trip's booking and invoice unreachable). Idempotent.

begin;
alter table public.group_movements add column if not exists opened_at timestamptz not null default now();
-- the rows the column was just added to (now() is this transaction's one time): each opened when it was made, as before
update public.group_movements set opened_at = created_at where opened_at = now();
create index if not exists group_movements_opened on public.group_movements (group_id, opened_at desc);
commit;

select count(*) as trips, max(opened_at) as last_opened from public.group_movements;
