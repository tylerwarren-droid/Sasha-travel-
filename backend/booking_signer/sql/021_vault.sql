-- 021 · S-78 · the vault: a guest's own accesses, sealed per item (AES-256-GCM, a DEK wrapped by Google Cloud KMS), every
-- use logged, revoke = crypto-shred. Verified against the live schema (sasha-prod) on 2 Oct 2026: no vault_* table;
-- auth.users.id is uuid; booking tables run RLS on with no policies (backend only). 020 is S-75's (guest_channels).
-- ⛔ NOT APPLIED by any session: the founder approves, then it is applied by chat (preview, transaction, verify).

-- PREVIEW (read-only): must be three NULLs
select to_regclass('public.vault_items'), to_regclass('public.vault_uses'), to_regclass('public.vault_events');

begin;
create table vault_items (
  id                       uuid        primary key default gen_random_uuid(),
  account_id               uuid        not null references auth.users (id) on delete cascade,
  provider                 text        not null check (char_length(provider) between 3 and 253),
  label                    text        not null check (char_length(btrim(label)) between 1 and 80),
  kind                     text        not null check (kind in ('oauth', 'app_password', 'passkey', 'password', 'identifier')),
  ciphertext               bytea,                                   -- null for a passkey, and after revoke
  nonce                    bytea,
  wrapped_dek              bytea,
  kek_version              text,
  special_category         boolean     not null default false,      -- health etc. (Art. 9)
  consent_at               timestamptz,
  consent_wording_version  text,
  consent_text_sha256      text,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now(),
  last_used_at             timestamptz,
  revoked_at               timestamptz,
  constraint sealed_or_revoked check (kind = 'passkey' or revoked_at is not null
                                      or (ciphertext is not null and nonce is not null and wrapped_dek is not null and kek_version is not null)),
  constraint special_needs_consent check (not special_category or consent_at is not null)
);
create index vault_items_account on vault_items (account_id);
create table vault_uses (
  id                       uuid        primary key default gen_random_uuid(),
  account_id               uuid        not null references auth.users (id) on delete cascade,
  item_id                  uuid        not null references vault_items (id) on delete cascade,
  action_kind              text        not null,
  action_ref               text        not null,
  approval_sha256          text        not null check (approval_sha256 ~ '^[0-9a-f]{64}$'),
  status                   text        not null check (status in ('pending', 'in_use', 'done', 'failed', 'cancelled')),
  started_at               timestamptz not null default now(),
  ended_at                 timestamptz,
  outcome_words            text
);
create unique index vault_uses_one_per_approval on vault_uses (item_id, approval_sha256);   -- one yes, one use
create table vault_events (
  id                       bigserial   primary key,
  account_id               uuid        not null references auth.users (id) on delete cascade,
  item_id                  uuid,
  event                    text        not null,
  at                       timestamptz not null default now(),
  detail                   jsonb
);
-- the backend's own connection only, like every booking table: RLS on, no policies (no browser ever reads these)
alter table vault_items  enable row level security;
alter table vault_uses   enable row level security;
alter table vault_events enable row level security;
commit;

-- VERIFY (read-only): three rows, each rls true and 0 policies; then the two constraints and the one-use index
select relname, relrowsecurity, (select count(*) from pg_policies p where p.tablename = c.relname) as policies
from pg_class c where relname in ('vault_items', 'vault_uses', 'vault_events') order by relname;
select conname from pg_constraint where conrelid = 'public.vault_items'::regclass and contype = 'c' order by conname;
select indexname from pg_indexes where tablename = 'vault_uses' and indexname = 'vault_uses_one_per_approval';
