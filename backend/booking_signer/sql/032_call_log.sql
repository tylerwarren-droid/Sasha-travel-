-- Sasha 144 · THE CALL AND BOOKING LOG: every call in booking_calls (test calls marked as tests), and every guest
-- receipt recorded. Checked against the live schema on 4 Oct 2026 (information_schema.columns, pg_constraint):
--   booking_calls.trip_item_id uuid NOT NULL, FK → trip_items(id); no is_test column; no receipts table exists.
-- Why: a call to the TEST LINE has no reservation, so until now it could not be written to booking_calls at all — the
-- Sasha 130 language tests and the 4 Oct test call (Bland ed4770da…) are in Bland's log and in no log of ours.
-- Receipts were only in the server log.
-- Run once, in the Supabase SQL editor (project yjafyzywzbmhlilxhzuz). Idempotent. Nothing is deleted or rewritten.

-- preview (read-only): what this touches
-- select count(*) as calls, count(*) filter (where trip_item_id is null) as without_item from public.booking_calls;

begin;

-- 1 · a test call has no reservation; every other call still must have one
alter table public.booking_calls alter column trip_item_id drop not null;
alter table public.booking_calls add column if not exists is_test boolean not null default false;
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'booking_calls_item_or_test') then
    alter table public.booking_calls add constraint booking_calls_item_or_test check (is_test or trip_item_id is not null);
  end if;
end $$;

-- 2 · every guest receipt Sasha sent (or tried to): what, to whom (account), for which booking, and what happened
create table if not exists public.booking_receipts_sent (
  id            bigserial primary key,
  account_id    uuid not null references auth.users(id) on delete cascade,
  trip_item_id  uuid references public.trip_items(id) on delete cascade,
  call_id       uuid references public.booking_calls(call_id) on delete set null,
  kind          text not null check (kind in ('booking', 'cancel')),
  venue         text not null,
  route         text not null,
  status_words  text,
  outcome       text not null,          -- 'sent', or 'not sent: <why>'
  provider_id   text,                   -- the email provider's id, when sent
  sent_at       timestamptz not null default now()
);
create index if not exists booking_receipts_sent_item on public.booking_receipts_sent (trip_item_id);
create index if not exists booking_receipts_sent_account on public.booking_receipts_sent (account_id, sent_at desc);

-- server-side only (the service role): RLS on, no policy, and no grant to the client roles
alter table public.booking_receipts_sent enable row level security;
revoke all on table public.booking_receipts_sent from anon, authenticated;
revoke all on sequence public.booking_receipts_sent_id_seq from anon, authenticated;

commit;

-- check (read-only):
-- select column_name, is_nullable from information_schema.columns where table_name = 'booking_calls' and column_name in ('trip_item_id','is_test');
-- select has_table_privilege('anon', 'public.booking_receipts_sent', 'select');   -- expect false
