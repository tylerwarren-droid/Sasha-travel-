-- Sasha 206 (EU 186, docs/sasha/whatsapp-architecture.md §4) · WhatsApp correctness. DRAFT — the founder runs it; never applied by a tab.
-- Checked against the live schema on 8 Oct 2026: guest_wa_state has wa_id_sha256, history, pending, last_inbound_at, link_tries,
-- updated_at (no last_to; 127 rows); public.guest_inbound_sids does not exist.
--   R1 · last_to — the number the guest last wrote to: the payment-result and Duffel-change messages need it (the turn always
--        set it, but put_state could not store it). Until this runs the code sends from the permanent sender instead.
--   R2 · guest_inbound_sids — every inbound guest message's Twilio MessageSid, once: a Twilio retry never runs a turn twice.
--        Until this runs the code de-duplicates in memory (one worker; enough for Twilio's retries, not across a restart).
-- Idempotent. Adds only; nothing is altered in place or deleted.

-- preview (read-only)
-- select count(*) from guest_wa_state;  select to_regclass('public.guest_inbound_sids');

begin;

alter table public.guest_wa_state add column if not exists last_to text;

create table if not exists public.guest_inbound_sids (
  message_sid  text primary key check (message_sid ~ '^(SM|MM|WA)[0-9a-fA-F]{32}$'),
  received_at  timestamptz not null default now()
);
create index if not exists guest_inbound_sids_received on public.guest_inbound_sids (received_at);

-- server-side only (the service role): RLS on, no policy, no grant to the client roles
alter table public.guest_inbound_sids enable row level security;
revoke all on table public.guest_inbound_sids from anon, authenticated;

commit;

-- check (read-only):
-- select column_name from information_schema.columns where table_name = 'guest_wa_state' and column_name = 'last_to';   -- 1 row
-- select has_table_privilege('anon', 'public.guest_inbound_sids', 'select');                                          -- false
