-- 024 · S-81 · payment requests: "Pay the €20 deposit to X?" — one amount, one yes. Tier 0 only this week (EU 120):
-- the guest pays the venue directly; no money touches Kanoe; ids only, never card data (S-78 §8).
-- Verified against the live schema (sasha-prod) on 2 Oct 2026: no payment_requests table; trip_items.id uuid.
-- ⛔ NOT APPLIED by any session: the founder approves, then it is applied by chat (preview, transaction, verify).

-- PREVIEW (read-only): must be NULL
select to_regclass('public.payment_requests');

begin;
create table payment_requests (
  id                    uuid        primary key default gen_random_uuid(),
  account_id            uuid        not null references auth.users (id) on delete cascade,
  trip_item_id          uuid        not null references trip_items (id) on delete cascade,
  payee                 text        not null,
  purpose               text        not null,                                    -- "deposit", "prepayment"
  amount_minor          int         check (amount_minor is null or amount_minor > 0),   -- null when they named no amount
  currency              text        not null default 'EUR' check (currency ~ '^[A-Z]{3}$'),
  refundable_until      timestamptz,
  venue_terms_quote     text,                                                    -- the venue's own words, verbatim
  read_back_lines       text[]      not null,
  read_back_sha256      text        not null check (read_back_sha256 ~ '^[0-9a-f]{64}$'),
  approval              jsonb,                                                   -- {by, how, said, at, read_back_sha256}
  tier                  text        not null check (tier in ('guest_direct', 'guest_link_wallet', 'kanoe_issuing')),
  stripe_payment_intent text, stripe_issuing_card text, link_spend_request text, -- ids only, never card data
  link_asked_by         text,                                                    -- sms | email | none
  status                text        not null default 'awaiting_approval' check (status in
    ('awaiting_approval', 'approved', 'link_sent', 'paid', 'refunded', 'refund_due', 'failed', 'cancelled')),
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);
create unique index payment_requests_one_per_approval on payment_requests ((approval->>'read_back_sha256')) where approval is not null;
create unique index payment_requests_one_per_item on payment_requests (trip_item_id, purpose) where status not in ('cancelled', 'failed');
alter table payment_requests enable row level security;
commit;

-- VERIFY (read-only): rls true, 0 policies
select relrowsecurity, (select count(*) from pg_policies where tablename = 'payment_requests') as policies
from pg_class where relname = 'payment_requests';
