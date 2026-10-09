-- CR 63 · THE KEEP — a person's numbers and codes (passport, DNI/NIE, loyalty numbers, door codes…), encrypted under the
-- person's OWN data key, which Google Cloud KMS wraps (the KMS S-78's vault already uses: SASHA_VAULT_KMS_KEY). The database
-- holds only ciphertext, a wrapped key, a mask and a KEYED fingerprint — never a value, never a plain hash of one.
-- DRAFT — apply in Supabase AFTER the Sasha tab deploys cr/s2-keep (and AFTER 036, which it extends); never applied by a tab.
-- Until it runs, the Keep is CLOSED and says so (it never keeps secrets in memory).
--   keep_keys   one row per account: its data key, wrapped by KMS. Deleting it shreds every value at once (deletion on request).
--   keep_items  one row per saved item: type, tier, mask, keyed fingerprint, nonce, ciphertext.
--   keep_fills  an item bound to a booking: bound → approved (the read-back they said yes to named it) → used / failed.
-- Idempotent. Adds only, except the s2_acts kind check, which is widened (the old kinds stay valid).

-- preview (read-only)
-- select to_regclass('public.keep_keys'), to_regclass('public.keep_items'), to_regclass('public.keep_fills');   -- null ×3 before
-- select to_regclass('public.s2_acts');   -- NOT null: 036 first

begin;

create table if not exists public.keep_keys (
  account_id   uuid primary key,
  wrapped_dek  bytea not null check (length(wrapped_dek) between 32 and 1024),
  kek_version  text not null,
  created_at   timestamptz not null default now()
);

create table if not exists public.keep_items (
  id            uuid primary key,
  account_id    uuid not null,
  type          text not null check (type in ('preference', 'loyalty', 'home_address', 'passport', 'national_id', 'trusted_traveller',
                                              'visa_residence', 'insurance_policy', 'health_card', 'booking_reference', 'door_code',
                                              'wifi', 'esim')),
  tier          text not null check (tier in ('free', 'yes', 'read_back')),
  masked        text not null check (length(masked) <= 120),
  fingerprint   text not null check (fingerprint ~ '^hmac:[0-9a-f]{64}$'),
  nonce         bytea not null check (length(nonce) = 12),
  ciphertext    bytea not null check (length(ciphertext) between 17 and 4096),
  created_at    timestamptz not null default now(),
  last_used_at  timestamptz,
  unique (account_id, fingerprint)
);
create index if not exists keep_items_account on public.keep_items (account_id);

create table if not exists public.keep_fills (
  id                uuid primary key,
  account_id        uuid not null,
  item_id           uuid not null references public.keep_items(id) on delete cascade,
  purpose           text not null check (purpose in ('fill')),
  line              text,
  state             text not null check (state in ('bound', 'approved', 'used', 'failed', 'replaced')),
  session_id        text,
  said              text check (said is null or length(said) <= 300),
  read_back_sha256  text check (read_back_sha256 is null or read_back_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  expires_at        timestamptz not null,
  used_at           timestamptz,
  created_at        timestamptz not null default now()
);
create index if not exists keep_fills_account_state on public.keep_fills (account_id, state);

-- the Activity view's rows for the Keep (036's s2_acts): every save, use, show, deletion
alter table public.s2_acts drop constraint if exists s2_acts_kind_check;
alter table public.s2_acts add constraint s2_acts_kind_check
  check (kind in ('email', 'whatsapp', 'calendar', 'keep_save', 'keep_use', 'keep_show', 'keep_delete'));

-- server-side only (the service role): RLS on, no policy, no grant to the client roles
alter table public.keep_keys enable row level security;
alter table public.keep_items enable row level security;
alter table public.keep_fills enable row level security;
revoke all on table public.keep_keys, public.keep_items, public.keep_fills from anon, authenticated;

commit;

-- check (read-only):
-- select count(*) from public.keep_keys; select count(*) from public.keep_items; select count(*) from public.keep_fills;   -- 0, no error
