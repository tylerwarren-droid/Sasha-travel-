-- 058 · Sasha 355 · ONE INBOUND MESSAGE IS HANDLED EXACTLY ONCE — each message's processing steps, in a table of their own.
--
-- Found (Sasha 350's live log, 7 Nov): every WhatsApp logged "MessageSid not checked: CheckViolationError … guest_inbound_sids". Sasha 294
-- wrote derived keys ("agapi-in:<sid>", "agapi-took:<sid>") into guest_inbound_sids, whose check accepts only a plain Twilio SID — every
-- one was refused, the check failed OPEN, and a Twilio retry was handed to AgAPI again ("AgAPI took it" was never recorded either).
-- guest_inbound_sids keeps exactly what it was made for (a turn per MessageSid, 034). A message's steps are rows here, keyed as written:
--   agapi_in    the message was handed to AgAPI's ONE inbound op (once — a retry never again)
--   agapi_took  AgAPI took it (matched): a retry stops here, nothing else answers it
-- Idempotent.

select to_regclass('public.guest_message_steps') as already;

begin;
create table if not exists public.guest_message_steps (
  message_sid  text not null check (message_sid ~ '^(SM|MM|WA)[0-9a-fA-F]{32}$'),
  step         text not null check (step in ('agapi_in', 'agapi_took')),
  at           timestamptz not null default now(),
  primary key (message_sid, step)
);
create index if not exists guest_message_steps_at on public.guest_message_steps (at);
-- server-side only (the service role): RLS on, no policy, no grant to the client roles
alter table public.guest_message_steps enable row level security;
revoke all on table public.guest_message_steps from anon, authenticated;
commit;

select to_regclass('public.guest_message_steps') as made, has_table_privilege('anon', 'public.guest_message_steps', 'select') as anon_can_read;
