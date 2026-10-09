-- CR 62 · S2: the Activity view's own records (emails, WhatsApps, calendar adds) and WhatsApp to people the user names.
-- DRAFT — apply in Supabase AFTER the Sasha tab deploys cr/s2-powers-2 (the deploy sha goes in its wiring commit); never applied
-- by a tab. Until it runs, agapi/s2_records.py keeps all three in memory (a deploy clears them; the log says so) — nothing breaks.
--   s2_acts         one row per thing S2 did or refused to send: kind, state, the proof (provider id, time, the person's own words,
--                   the read-back's and the message's sha256) and the proof's own sha256 (so a changed row stops verifying).
--   s2_wa_contacts  a number Sasha wrote to FOR an account: when, the name the user gave, when they last wrote back (WhatsApp's
--                   24-hour window), and STOP (final).
--   s2_wa_replies   what they wrote back — kept as THEIR words (untrusted), shown to the user, never acted on.
-- Idempotent. Adds only; nothing is altered in place or deleted.

-- preview (read-only)
-- select to_regclass('public.s2_acts'), to_regclass('public.s2_wa_contacts'), to_regclass('public.s2_wa_replies');   -- null ×3 before

begin;

create table if not exists public.s2_acts (
  id            uuid primary key default gen_random_uuid(),
  account_id    uuid not null,
  kind          text not null check (kind in ('email', 'whatsapp', 'calendar')),
  state         text not null check (state in ('done', 'not_sent', 'failed')),
  about         text check (about is null or length(about) <= 300),
  proof         jsonb not null,
  proof_sha256  text not null check (proof_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  at            timestamptz not null default now()
);
create index if not exists s2_acts_account_at on public.s2_acts (account_id, at desc);

create table if not exists public.s2_wa_contacts (
  account_id       uuid not null,
  number_e164      text not null check (number_e164 ~ '^\+[1-9][0-9]{7,14}$'),
  name             text check (name is null or length(name) <= 120),
  on_behalf_of     text check (on_behalf_of is null or length(on_behalf_of) <= 60),
  first_contact_at timestamptz not null default now(),
  last_inbound_at  timestamptz,
  opted_out_at     timestamptz,
  primary key (account_id, number_e164)
);
create index if not exists s2_wa_contacts_number on public.s2_wa_contacts (number_e164);

create table if not exists public.s2_wa_replies (
  id           uuid primary key default gen_random_uuid(),
  account_id   uuid not null,
  number_e164  text not null,
  body         text not null check (length(body) <= 4096),
  received_at  timestamptz not null default now()
);
create index if not exists s2_wa_replies_account on public.s2_wa_replies (account_id, received_at desc);

-- server-side only (the service role): RLS on, no policy, no grant to the client roles
alter table public.s2_acts enable row level security;
alter table public.s2_wa_contacts enable row level security;
alter table public.s2_wa_replies enable row level security;
revoke all on table public.s2_acts, public.s2_wa_contacts, public.s2_wa_replies from anon, authenticated;

commit;

-- check (read-only):
-- select count(*) from public.s2_acts; select count(*) from public.s2_wa_contacts; select count(*) from public.s2_wa_replies;   -- 0, no error
