-- 061 · Sasha 394 · CR 206 · DELIVER AGAIN — a WhatsApp message AgAPI couldn't decide, kept until Sasha delivers it again (redeliver.py).
--
-- CR 206: an error from messages.whatsapp_inbound means "whose message this is isn't decided" — AgAPI released its claim and recorded
-- nothing. Twilio was answered at once (379a) and doesn't redeliver after a 2xx, so Sasha delivers it again herself, on a backoff, for at
-- most a day. A row lives only while its message is undecided: deleted the moment AgAPI decides (it holds the person's words).
-- Idempotent.

select to_regclass('public.wa_redeliver') as already;

begin;
create table if not exists public.wa_redeliver (
  message_sid  text primary key check (message_sid ~ '^(SM|MM|WA)[0-9a-fA-F]{32}$'),
  payload      jsonb not null,
  attempts     integer not null default 0 check (attempts >= 0),
  why          text,
  next_at      timestamptz not null,
  created_at   timestamptz not null default now()
);
create index if not exists wa_redeliver_next_at on public.wa_redeliver (next_at);
-- server-side only (the service role): RLS on, no policy, no grant to the client roles
alter table public.wa_redeliver enable row level security;
revoke all on table public.wa_redeliver from anon, authenticated;
commit;

select to_regclass('public.wa_redeliver') as made, has_table_privilege('anon', 'public.wa_redeliver', 'select') as anon_can_read;
