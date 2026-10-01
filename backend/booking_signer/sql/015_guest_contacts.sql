-- 015 · S-62 step 5 · a guest's name and mobile, stored ONCE with their consent — booking_signer's own table (the CTO's
-- user_profiles has no phone, and his migrations are not ours). Verified against the live schema on 1 Oct 2026:
-- no guest_contacts table; auth.users.id is uuid; booking tables run RLS on with no policies (backend only).
-- ⛔ NOT APPLIED by any session: the founder approves, then it runs via railway run (preview, transaction, verify).

-- PREVIEW (read-only): must be 0
select count(*) as guest_contacts_tables from information_schema.tables where table_schema = 'public' and table_name = 'guest_contacts';

begin;
create table guest_contacts (
  account_id               uuid        primary key references auth.users (id) on delete cascade,
  name                     text        not null check (char_length(btrim(name)) between 1 and 80),
  mobile_e164              text        not null check (mobile_e164 ~ '^\+[1-9][0-9]{7,14}$'),
  consent_at               timestamptz not null,
  consent_wording_version  text        not null check (consent_wording_version ~ '^v[0-9]+$'),
  consent_text_sha256      text        not null check (consent_text_sha256 ~ '^[0-9a-f]{64}$'),
  updated_at               timestamptz not null default now()
);
-- the backend's own connection only, like every booking table: RLS on, no policies
alter table guest_contacts enable row level security;
commit;

-- VERIFY (read-only)
select relrowsecurity, (select count(*) from pg_policies where tablename = 'guest_contacts') as policies
from pg_class where relname = 'guest_contacts';
