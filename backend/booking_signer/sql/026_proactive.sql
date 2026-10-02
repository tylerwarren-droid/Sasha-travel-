-- 026 · S-83 · proactive Sasha: the ledger (one of each kind per booking, ever; the daily cap), per-guest opt-outs, and
-- a guest's saved starting point for "time to leave". Verified against the live schema (sasha-prod) on 2 Oct 2026: none
-- of the three tables exists; trip_items.id and auth.users.id are uuid; booking tables run RLS on with no policies.
-- One change from the spec's draft (S-83 §3): guest_places keeps the ADDRESS THE GUEST TYPED, and lat/lng are nullable
-- and left empty — coordinates looked up from Google would be Google content (the S-64 / 013 lesson), and the Routes
-- API takes an address as the origin.
-- ⛔ NOT APPLIED by any session: the founder approves, then it is applied by chat (preview, transaction, verify).

-- PREVIEW (read-only): must be three NULLs
select to_regclass('public.proactive_sent'), to_regclass('public.proactive_prefs'), to_regclass('public.guest_places');

begin;
create table proactive_sent (
  id             bigserial   primary key,
  account_id     uuid        not null references auth.users (id) on delete cascade,
  trip_item_id   uuid        references trip_items (id) on delete cascade,              -- null for the morning brief
  kind           text        not null check (kind in ('day_before', 'not_confirmed', 'leave_now', 'written_confirmation', 'morning_brief')),
  local_day      date        not null,                                                  -- the booking's local date (cap, dedupe)
  status_at_send text,                                                                  -- trip_items.status when sent: the honesty audit
  channel        text        not null check (channel in ('whatsapp_session', 'whatsapp_template', 'skipped')),
  outcome        text        not null,                                                  -- "sent" | "not sent: <reason>"
  sent_at        timestamptz not null default now()
);
create unique index proactive_once on proactive_sent (trip_item_id, kind) where trip_item_id is not null;
create unique index proactive_brief_once on proactive_sent (account_id, local_day) where kind = 'morning_brief';
create index proactive_day on proactive_sent (account_id, local_day);

-- per guest, per kind: absence = on, ONLY for a guest whose guest_channels.consent_wording_version is v3 or later (§3a)
create table proactive_prefs (
  account_id uuid        primary key references auth.users (id) on delete cascade,
  off_kinds  text[]      not null default '{}',
  all_off    boolean     not null default false,
  updated_at timestamptz not null default now()
);

-- a starting point the guest SAVES ("my hotel", "home") — never inferred
create table guest_places (
  id         uuid             primary key default gen_random_uuid(),
  account_id uuid             not null references auth.users (id) on delete cascade,
  label      text             not null check (char_length(btrim(label)) between 1 and 40),
  address    text             not null check (char_length(btrim(address)) between 3 and 200),
  lat        double precision,
  lng        double precision,
  is_default boolean          not null default false,
  created_at timestamptz      not null default now()
);
create unique index guest_places_one_default on guest_places (account_id) where is_default;
alter table proactive_sent  enable row level security;
alter table proactive_prefs enable row level security;
alter table guest_places    enable row level security;
commit;

-- VERIFY (read-only): three rows, each rls true and 0 policies
select relname, relrowsecurity, (select count(*) from pg_policies p where p.tablename = c.relname) as policies
from pg_class c where relname in ('proactive_sent', 'proactive_prefs', 'guest_places') order by relname;
