-- 020 · S-75 · a guest's WhatsApp, linked to their account; the one-use link codes; the WhatsApp conversation's state.
-- Verified against the live schema (sasha-prod) on 2 Oct 2026: none of the three tables exists; guest_contacts (015)
-- and booking_inbound (016/017) do; auth.users.id is uuid; booking tables run RLS on with no policies (backend only).
-- ⛔ NOT APPLIED by any session: the founder approves, then it is applied by chat (preview, transaction, verify).

-- PREVIEW (read-only): must be three NULLs
select to_regclass('public.guest_channels'), to_regclass('public.guest_link_codes'), to_regclass('public.guest_wa_state');

begin;
create table guest_channels (
  account_id               uuid        not null references auth.users (id) on delete cascade,
  channel                  text        not null check (channel in ('whatsapp')),
  wa_id_sha256             text        not null check (wa_id_sha256 ~ '^[0-9a-f]{64}$'),  -- as booking_inbound.from_key
  number_e164              text        not null check (number_e164 ~ '^\+[1-9][0-9]{7,14}$'), -- needed to SEND; never logged
  linked_at                timestamptz not null default now(),
  consent_at               timestamptz not null,
  consent_wording_version  text        not null check (consent_wording_version ~ '^v[0-9]+$'),
  consent_text_sha256      text        not null check (consent_text_sha256 ~ '^[0-9a-f]{64}$'),
  opted_out_at             timestamptz,                                                 -- STOP: never messaged while set
  primary key (channel, wa_id_sha256)
);
create unique index guest_channels_one_per_account on guest_channels (account_id, channel);
alter table guest_channels enable row level security;

create table guest_link_codes (
  code                     text        primary key check (code ~ '^[0-9]{6}$'),
  account_id               uuid        not null references auth.users (id) on delete cascade,
  consent_at               timestamptz not null,
  consent_wording_version  text        not null check (consent_wording_version ~ '^v[0-9]+$'),
  consent_text_sha256      text        not null check (consent_text_sha256 ~ '^[0-9a-f]{64}$'),
  created_at               timestamptz not null default now(),
  used_at                  timestamptz
);
alter table guest_link_codes enable row level security;

-- what the WhatsApp conversation needs between messages: the last lines (the hand-off reads them, as the web chat's
-- history), the ONE pending question (cards / a confirmation), the 24-hour window, and the link tries (rate limit)
create table guest_wa_state (
  wa_id_sha256             text        primary key check (wa_id_sha256 ~ '^[0-9a-f]{64}$'),
  history                  jsonb       not null default '[]'::jsonb,
  pending                  jsonb,
  last_inbound_at          timestamptz,
  link_tries               jsonb       not null default '[]'::jsonb,
  updated_at               timestamptz not null default now()
);
alter table guest_wa_state enable row level security;
commit;

-- VERIFY (read-only): three rows, each rls true and 0 policies
select relname, relrowsecurity, (select count(*) from pg_policies p where p.tablename = c.relname) as policies
from pg_class c where relname in ('guest_channels', 'guest_link_codes', 'guest_wa_state') order by relname;
