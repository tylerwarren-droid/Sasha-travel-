-- ============================================================
-- Sasha Travel — Initial Schema
-- Migration: 001_initial_schema.sql
-- Note: uses Supabase built-in auth.users — no custom users table
-- ============================================================

-- Extensions
create extension if not exists "pgcrypto";
create extension if not exists "uuid-ossp";

-- ============================================================
-- UTILITY: updated_at trigger function
-- ============================================================

create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

-- ============================================================
-- TABLE: user_profiles
-- Extends auth.users with app-level role and display name.
-- id mirrors auth.users(id) — no separate UUID generated.
-- ============================================================

create table if not exists user_profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  name        text,
  role        text not null default 'traveler'
                check (role in ('traveler', 'agent', 'operator', 'admin')),
  created_at  timestamptz not null default now()
);

create index idx_user_profiles_role on user_profiles (role);

alter table user_profiles enable row level security;

create policy "user_profiles_select_own"
  on user_profiles for select
  using (id = auth.uid());

create policy "user_profiles_insert_own"
  on user_profiles for insert
  with check (id = auth.uid());

create policy "user_profiles_update_own"
  on user_profiles for update
  using (id = auth.uid());

-- ============================================================
-- TABLE: organizations
-- ============================================================

create table if not exists organizations (
  id            uuid primary key default gen_random_uuid(),
  name          text not null,
  type          text not null default 'hotel'
                  check (type in ('hotel', 'agency', 'operator', 'enterprise')),
  sasha_config  jsonb not null default '{}',
  created_at    timestamptz not null default now()
);

alter table organizations enable row level security;

-- ============================================================
-- TABLE: traveler_profiles
-- ============================================================

create table if not exists traveler_profiles (
  id                    uuid primary key default gen_random_uuid(),
  user_id               uuid not null unique references auth.users (id) on delete cascade,
  -- Encrypted fields: store pgcrypto ciphertext, decrypt at app layer
  passport_number       text,
  passport_expiry       text,
  nationality           text,
  date_of_birth         text,
  dietary_requirements  text,
  seat_preference       text,
  loyalty_programs      jsonb not null default '[]',
  credit_cards          jsonb not null default '[]',
  emergency_contact     text,
  updated_at            timestamptz not null default now()
);

create index idx_traveler_profiles_user_id on traveler_profiles (user_id);

create trigger trg_traveler_profiles_updated_at
  before update on traveler_profiles
  for each row execute function set_updated_at();

alter table traveler_profiles enable row level security;

create policy "traveler_profiles_select_own"
  on traveler_profiles for select
  using (user_id = auth.uid());

create policy "traveler_profiles_insert_own"
  on traveler_profiles for insert
  with check (user_id = auth.uid());

create policy "traveler_profiles_update_own"
  on traveler_profiles for update
  using (user_id = auth.uid());

-- ============================================================
-- TABLE: trips
-- ============================================================

create table if not exists trips (
  id               uuid primary key default gen_random_uuid(),
  owner_id         uuid not null references auth.users (id) on delete cascade,
  organization_id  uuid references organizations (id) on delete set null,
  title            text not null,
  status           text not null default 'draft'
                     check (status in ('draft', 'active', 'completed', 'cancelled')),
  destinations     jsonb not null default '[]',
  depart_date      date,
  return_date      date,
  travelers        jsonb not null default '[]',
  total_cost_usd   numeric(10, 2),
  currency         text not null default 'USD',
  shared_with      jsonb not null default '[]',
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create index idx_trips_owner_id        on trips (owner_id);
create index idx_trips_organization_id on trips (organization_id);
create index idx_trips_status          on trips (status);
create index idx_trips_depart_date     on trips (depart_date);

create trigger trg_trips_updated_at
  before update on trips
  for each row execute function set_updated_at();

alter table trips enable row level security;

-- Owner can always see their trips
create policy "trips_select_owner"
  on trips for select
  using (owner_id = auth.uid());

-- Users listed in shared_with can see the trip
create policy "trips_select_shared"
  on trips for select
  using (
    shared_with @> jsonb_build_array(jsonb_build_object('user_id', auth.uid()::text))
  );

create policy "trips_insert_own"
  on trips for insert
  with check (owner_id = auth.uid());

create policy "trips_update_owner"
  on trips for update
  using (owner_id = auth.uid());

create policy "trips_delete_owner"
  on trips for delete
  using (owner_id = auth.uid());

-- Organizations RLS policy — defined here because it references trips
create policy "organizations_select_member"
  on organizations for select
  using (
    exists (
      select 1 from trips
      where trips.organization_id = organizations.id
        and trips.owner_id = auth.uid()
    )
  );

-- ============================================================
-- TABLE: trip_items
-- ============================================================

create table if not exists trip_items (
  id                    uuid primary key default gen_random_uuid(),
  trip_id               uuid not null references trips (id) on delete cascade,
  type                  text not null
                          check (type in (
                            'flight', 'hotel', 'restaurant', 'golf', 'transfer',
                            'experience', 'visa', 'insurance', 'doctor',
                            'beauty', 'dog_walking', 'coworking'
                          )),
  status                text not null default 'pending'
                          check (status in (
                            'pending', 'attempting', 'confirmed',
                            'failed', 'escalated', 'cancelled'
                          )),
  booking_reference     text,
  provider_name         text,
  provider_email        text,
  provider_phone        text,
  date_time             timestamptz,
  duration_minutes      integer,
  location_name         text,
  location_address      text,
  location_lat          numeric(9, 6),
  location_lng          numeric(9, 6),
  price_usd             numeric(10, 2),
  currency              text,
  confirmation_deadline timestamptz,
  escalated_at          timestamptz,
  escalation_notes      text,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

create index idx_trip_items_trip_id   on trip_items (trip_id);
create index idx_trip_items_status    on trip_items (status);
create index idx_trip_items_type      on trip_items (type);
create index idx_trip_items_date_time on trip_items (date_time);

create trigger trg_trip_items_updated_at
  before update on trip_items
  for each row execute function set_updated_at();

alter table trip_items enable row level security;

create policy "trip_items_select_trip_owner"
  on trip_items for select
  using (
    exists (
      select 1 from trips
      where trips.id = trip_items.trip_id
        and (
          trips.owner_id = auth.uid()
          or trips.shared_with @> jsonb_build_array(jsonb_build_object('user_id', auth.uid()::text))
        )
    )
  );

create policy "trip_items_insert_trip_owner"
  on trip_items for insert
  with check (
    exists (
      select 1 from trips
      where trips.id = trip_items.trip_id
        and trips.owner_id = auth.uid()
    )
  );

create policy "trip_items_update_trip_owner"
  on trip_items for update
  using (
    exists (
      select 1 from trips
      where trips.id = trip_items.trip_id
        and trips.owner_id = auth.uid()
    )
  );

-- ============================================================
-- TABLE: booking_attempts
-- ============================================================

create table if not exists booking_attempts (
  id                     uuid primary key default gen_random_uuid(),
  trip_item_id           uuid not null references trip_items (id) on delete cascade,
  method                 text not null
                           check (method in ('email', 'phone', 'web_form')),
  attempted_at           timestamptz not null default now(),
  status                 text not null default 'sent'
                           check (status in (
                             'sent', 'delivered', 'confirmed', 'failed', 'no_response'
                           )),
  response_received      text,
  response_at            timestamptz,
  bland_call_id          text,
  resend_email_id        text,
  browserbase_session_id text
);

create index idx_booking_attempts_trip_item_id on booking_attempts (trip_item_id);
create index idx_booking_attempts_status       on booking_attempts (status);
create index idx_booking_attempts_attempted_at on booking_attempts (attempted_at);

alter table booking_attempts enable row level security;

create policy "booking_attempts_select_trip_owner"
  on booking_attempts for select
  using (
    exists (
      select 1 from trip_items
      join trips on trips.id = trip_items.trip_id
      where trip_items.id = booking_attempts.trip_item_id
        and trips.owner_id = auth.uid()
    )
  );

create policy "booking_attempts_insert_trip_owner"
  on booking_attempts for insert
  with check (
    exists (
      select 1 from trip_items
      join trips on trips.id = trip_items.trip_id
      where trip_items.id = booking_attempts.trip_item_id
        and trips.owner_id = auth.uid()
    )
  );

-- ============================================================
-- TABLE: documents
-- ============================================================

create table if not exists documents (
  id                      uuid primary key default gen_random_uuid(),
  trip_id                 uuid references trips (id) on delete cascade,
  traveler_profile_id     uuid references traveler_profiles (id) on delete cascade,
  type                    text not null
                            check (type in (
                              'visa', 'insurance', 'booking_confirmation', 'passport', 'other'
                            )),
  file_url                text not null,
  expires_at              date,
  issued_for_destination  text,
  created_at              timestamptz not null default now(),
  constraint documents_has_owner check (
    trip_id is not null or traveler_profile_id is not null
  )
);

create index idx_documents_trip_id             on documents (trip_id);
create index idx_documents_traveler_profile_id on documents (traveler_profile_id);
create index idx_documents_expires_at          on documents (expires_at);

alter table documents enable row level security;

create policy "documents_select_own"
  on documents for select
  using (
    (
      trip_id is not null and exists (
        select 1 from trips
        where trips.id = documents.trip_id
          and (
            trips.owner_id = auth.uid()
            or trips.shared_with @> jsonb_build_array(jsonb_build_object('user_id', auth.uid()::text))
          )
      )
    ) or (
      traveler_profile_id is not null and exists (
        select 1 from traveler_profiles
        where traveler_profiles.id = documents.traveler_profile_id
          and traveler_profiles.user_id = auth.uid()
      )
    )
  );

create policy "documents_insert_own"
  on documents for insert
  with check (
    (
      trip_id is not null and exists (
        select 1 from trips
        where trips.id = documents.trip_id and trips.owner_id = auth.uid()
      )
    ) or (
      traveler_profile_id is not null and exists (
        select 1 from traveler_profiles
        where traveler_profiles.id = documents.traveler_profile_id
          and traveler_profiles.user_id = auth.uid()
      )
    )
  );

-- ============================================================
-- TABLE: escalations
-- ============================================================

create table if not exists escalations (
  id               uuid primary key default gen_random_uuid(),
  trip_item_id     uuid not null references trip_items (id) on delete cascade,
  assigned_to      uuid references auth.users (id) on delete set null,
  status           text not null default 'open'
                     check (status in ('open', 'in_progress', 'resolved', 'closed')),
  priority         text not null default 'medium'
                     check (priority in ('low', 'medium', 'high', 'urgent')),
  sla_deadline     timestamptz,
  context          jsonb not null default '{}',
  resolution_notes text,
  resolved_at      timestamptz,
  created_at       timestamptz not null default now()
);

create index idx_escalations_trip_item_id on escalations (trip_item_id);
create index idx_escalations_assigned_to  on escalations (assigned_to);
create index idx_escalations_status       on escalations (status);
create index idx_escalations_priority     on escalations (priority);
create index idx_escalations_sla_deadline on escalations (sla_deadline);

alter table escalations enable row level security;

-- Trip owner can see escalations for their items
create policy "escalations_select_trip_owner"
  on escalations for select
  using (
    exists (
      select 1 from trip_items
      join trips on trips.id = trip_items.trip_id
      where trip_items.id = escalations.trip_item_id
        and trips.owner_id = auth.uid()
    )
  );

-- Assigned agent can see and update their escalations
create policy "escalations_select_assigned"
  on escalations for select
  using (assigned_to = auth.uid());

create policy "escalations_update_assigned"
  on escalations for update
  using (assigned_to = auth.uid());

-- ============================================================
-- TABLE: conversations
-- ============================================================

create table if not exists conversations (
  id                  uuid primary key default gen_random_uuid(),
  trip_id             uuid references trips (id) on delete set null,
  user_id             uuid not null references auth.users (id) on delete cascade,
  messages            jsonb not null default '[]',
  agent_intents_fired jsonb not null default '[]',
  created_at          timestamptz not null default now()
);

create index idx_conversations_user_id    on conversations (user_id);
create index idx_conversations_trip_id    on conversations (trip_id);
create index idx_conversations_created_at on conversations (created_at);

alter table conversations enable row level security;

create policy "conversations_select_own"
  on conversations for select
  using (user_id = auth.uid());

create policy "conversations_insert_own"
  on conversations for insert
  with check (user_id = auth.uid());

create policy "conversations_update_own"
  on conversations for update
  using (user_id = auth.uid());

-- ============================================================
-- TABLE: calendar_events
-- ============================================================

create table if not exists calendar_events (
  id              uuid primary key default gen_random_uuid(),
  trip_item_id    uuid not null references trip_items (id) on delete cascade,
  user_id         uuid not null references auth.users (id) on delete cascade,
  google_event_id text,
  apple_event_id  text,
  synced_at       timestamptz
);

create index idx_calendar_events_trip_item_id on calendar_events (trip_item_id);
create index idx_calendar_events_user_id      on calendar_events (user_id);

alter table calendar_events enable row level security;

create policy "calendar_events_select_own"
  on calendar_events for select
  using (user_id = auth.uid());

create policy "calendar_events_insert_own"
  on calendar_events for insert
  with check (user_id = auth.uid());

create policy "calendar_events_update_own"
  on calendar_events for update
  using (user_id = auth.uid());

create policy "calendar_events_delete_own"
  on calendar_events for delete
  using (user_id = auth.uid());
