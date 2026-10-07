-- Sasha 198 · R1 · THE TRIP BASKET (docs/sasha/trip-basket-design.md §2–§3). DRAFT — the founder runs it; this tab never applies it.
-- Checked against the live schema on 7 Oct 2026 (information_schema.columns, pg_constraint, pg_policies):
--   trips(id uuid pk, owner_id → auth.users) exists; trip_items stays as it is (booked rows keep landing there, read by every
--   surface). public.travellers EXISTS but is unusable: its user_id → public.users, and public.users has 0 rows (auth.users
--   has 21) — so passengers get their own table keyed to auth.users, named apart so nothing collides; travellers is untouched.
-- Who writes what (the AgAPI roles, in code as basket.py's ROLE names):
--   Magellan  search                → state 'suggested' (offers shown, the plan's stays)
--   Sherlock  details / validation  → snapshot, expires_at refreshed, price re-checked
--   Austen    booking after the yes → 'pending_payment', then the provider order
--   Pacioli   proof and truth       → 'booked' / 'failed' / 'cancelled' + booking_reference + status_line, and basket_events
-- Run once, in the Supabase SQL editor (project yjafyzywzbmhlilxhzuz). Idempotent. Creates only; nothing is altered or deleted.

-- preview (read-only): nothing of these names exists yet
-- select to_regclass('public.trip_basket_items'), to_regclass('public.saved_passengers'), to_regclass('public.basket_events');

begin;

-- 1 · the basket: one row per thing in the trip, whatever its state
create table if not exists public.trip_basket_items (
  id                uuid primary key default gen_random_uuid(),
  trip_id           uuid not null references public.trips(id) on delete cascade,
  account_id        uuid not null references auth.users(id) on delete cascade,
  kind              text not null check (kind in ('flight', 'stay', 'venue')),
  state             text not null default 'suggested'
                    check (state in ('suggested', 'chosen', 'pending_payment', 'booked', 'failed', 'cancelled')),
  slice_key         text,                 -- a flight's leg ("MAD-HAN 2026-11-12"): one chosen flight per slice
  day               date,
  starts_at         timestamptz,
  ends_at           timestamptz,
  party             int check (party is null or party between 1 and 9),
  provider          text not null,        -- 'duffel' · 'test_hotel' · 'duffel_stays' · 'ladder'
  provider_ref      text,                 -- offer id / quote id; the order id once booked
  offer_request_id  text,                 -- Duffel: what to re-search from when the offer has gone
  snapshot          jsonb not null default '{}'::jsonb,   -- what the guest was shown (airline, flight numbers, slices, times, hotel)
  expires_at        timestamptz,
  price_amount      numeric(12, 2),
  price_currency    text,
  price_source      text check (price_source is null or price_source in ('quoted', 'estimate', 'placeholder')),
  paid_session      text,                 -- the Stripe session the yes created (Austen)
  booking_reference text,                 -- Pacioli
  order_id          text,                 -- Pacioli
  status_line       text,                 -- Pacioli writes every booked/paid status line; the model never does
  failed_why        text,
  trip_item_id      uuid references public.trip_items(id) on delete set null,   -- the booked row every surface already reads
  is_test           boolean not null default true,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
create index if not exists trip_basket_items_trip on public.trip_basket_items (trip_id, kind, state);
create index if not exists trip_basket_items_session on public.trip_basket_items (paid_session) where paid_session is not null;
create index if not exists trip_basket_items_order on public.trip_basket_items (order_id) where order_id is not null;
create unique index if not exists trip_basket_items_one_chosen_per_slice
  on public.trip_basket_items (trip_id, slice_key) where kind = 'flight' and state in ('chosen', 'pending_payment', 'booked');

-- 2 · passengers, asked once and saved (Duffel needs these; nothing is a placeholder in live mode)
create table if not exists public.saved_passengers (
  id             uuid primary key default gen_random_uuid(),
  account_id     uuid not null references auth.users(id) on delete cascade,
  is_account_holder boolean not null default false,
  given_name     text not null,
  family_name    text not null,
  born_on        date,
  title          text check (title is null or title in ('mr', 'ms', 'mrs', 'miss', 'dr')),
  gender         text check (gender is null or gender in ('m', 'f')),
  email          text,
  phone_e164     text,
  document       jsonb,                 -- only when an airline requires it (passport no., expiry, country) — never logged
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create unique index if not exists saved_passengers_one_holder on public.saved_passengers (account_id) where is_account_holder;

-- 3 · Pacioli's ledger: every provider event (Duffel webhooks, order results, platform emails), once each
create table if not exists public.basket_events (
  id             bigserial primary key,
  source         text not null,         -- 'duffel_webhook' · 'duffel_order' · 'stripe' · 'email'
  event_id       text not null,         -- the provider's id: a redelivery is recorded once
  event_type     text not null,
  item_id        uuid references public.trip_basket_items(id) on delete set null,
  payload_sha256 text not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
  verified       boolean not null,      -- signature checked (webhooks) or our own call's answer
  received_at    timestamptz not null default now(),
  unique (source, event_id)
);

-- server-side only (the service role): RLS on, no policy, and no grant to the client roles
alter table public.trip_basket_items enable row level security;
alter table public.saved_passengers enable row level security;
alter table public.basket_events enable row level security;
revoke all on table public.trip_basket_items from anon, authenticated;
revoke all on table public.saved_passengers from anon, authenticated;
revoke all on table public.basket_events from anon, authenticated;
revoke all on sequence public.basket_events_id_seq from anon, authenticated;

commit;

-- check (read-only):
-- select has_table_privilege('anon', 'public.trip_basket_items', 'select'), has_table_privilege('authenticated', 'public.saved_passengers', 'select');  -- expect false, false
-- select relname, relrowsecurity from pg_class where relname in ('trip_basket_items','saved_passengers','basket_events');                          -- expect true ×3
