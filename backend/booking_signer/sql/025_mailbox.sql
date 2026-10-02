-- 025 · S-82 · Gmail, read-only, testing mode: the guest's connection (its token sealed in the vault, 021) and what was
-- FOUND — extracted facts and a body hash only, never an email body. Depends on 021 (applied) and 022.
-- Verified against the live schema (sasha-prod) on 2 Oct 2026: neither table exists; trip_items.id uuid.
-- ⛔ NOT APPLIED by any session: the founder approves, then it is applied by chat (preview, transaction, verify).

-- PREVIEW (read-only): must be two NULLs
select to_regclass('public.mailbox_links'), to_regclass('public.mailbox_finds');

begin;
create table mailbox_links (
  account_id               uuid        primary key references auth.users (id) on delete cascade,
  vault_item_id            uuid        not null references vault_items (id) on delete cascade,
  consent_at               timestamptz not null,
  consent_wording_version  text        not null,
  consent_text_sha256      text        not null check (consent_text_sha256 ~ '^[0-9a-f]{64}$'),
  last_sync_at             timestamptz,
  history_id               text,
  needs_reconnect_at       timestamptz,
  told_reconnect_at        timestamptz
);
create table mailbox_finds (
  id                uuid        primary key default gen_random_uuid(),
  account_id        uuid        not null references auth.users (id) on delete cascade,
  gmail_message_id  text        not null,
  body_sha256       text        not null check (body_sha256 ~ '^[0-9a-f]{64}$'),
  kind              text        not null check (kind in ('confirmation', 'cancellation', 'change', 'bill', 'receipt', 'other')),
  facts             jsonb       not null,               -- {venue, at, party, reference, amount_minor, currency} — never the body
  parsed_by         text        not null check (parsed_by in ('rules', 'model')),
  trip_item_id      uuid        references trip_items (id) on delete set null,
  match_basis       text        check (match_basis in ('reference', 'venue_and_time', 'sasha_ref')),
  offered_action    text,
  offered_sentence  text,                                 -- the ONE sentence the hash covers (facts, never the body)
  offer_sha256      text,
  action_status     text        not null default 'none' check (action_status in ('none', 'offered', 'accepted', 'declined', 'done')),
  found_at          timestamptz not null default now(),
  unique (account_id, gmail_message_id)
);
alter table mailbox_links enable row level security;
alter table mailbox_finds enable row level security;
commit;

-- VERIFY (read-only): two rows rls true / 0 policies
select relname, relrowsecurity, (select count(*) from pg_policies p where p.tablename = c.relname) as policies
from pg_class c where relname in ('mailbox_links', 'mailbox_finds') order by relname;
