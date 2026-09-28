-- ── A FIXTURE, NOT A MIGRATION. Never run this against Sasha's Supabase. ──────────────────────────────────
--
-- The tables booking_signer/sql/001_booking_storage.sql builds on, AS READ LIVE from xlqtveusyfpffaejegiq on
-- 28 September 2026 (information_schema.columns, pg_constraint, pg_indexes — schema only, no rows), so the
-- booking suite can run the real block against the real shape in a throwaway PostgreSQL:
--   · auth.users — every column, its defaults and its unique indexes, as Supabase has them
--   · organizations, trips, trip_items, booking_attempts — model A (migrations/001_initial_schema.sql)
-- Row-level security and its auth.uid() policies are omitted: the backend connects as the owner and bypasses
-- them, and auth.uid() does not exist outside Supabase.

create schema auth;

create table auth.users (
  instance_id uuid null,
  id uuid not null primary key,
  aud varchar null,
  role varchar null,
  email varchar null,
  encrypted_password varchar null,
  email_confirmed_at timestamptz null,
  invited_at timestamptz null,
  confirmation_token varchar null,
  confirmation_sent_at timestamptz null,
  recovery_token varchar null,
  recovery_sent_at timestamptz null,
  email_change_token_new varchar null,
  email_change varchar null,
  email_change_sent_at timestamptz null,
  last_sign_in_at timestamptz null,
  raw_app_meta_data jsonb null,
  raw_user_meta_data jsonb null,
  is_super_admin boolean null,
  created_at timestamptz null,
  updated_at timestamptz null,
  phone text null default null::character varying,
  phone_confirmed_at timestamptz null,
  phone_change text null default ''::character varying,
  phone_change_token varchar null default ''::character varying,
  phone_change_sent_at timestamptz null,
  confirmed_at timestamptz generated always as (least(email_confirmed_at, phone_confirmed_at)) stored,
  email_change_token_current varchar null default ''::character varying,
  email_change_confirm_status smallint null default 0 check (email_change_confirm_status >= 0 and email_change_confirm_status <= 2),
  banned_until timestamptz null,
  reauthentication_token varchar null default ''::character varying,
  reauthentication_sent_at timestamptz null,
  is_sso_user boolean not null default false,
  deleted_at timestamptz null,
  is_anonymous boolean not null default false
);
create unique index confirmation_token_idx on auth.users (confirmation_token) where ((confirmation_token)::text !~ '^[0-9 ]*$'::text);
create unique index recovery_token_idx on auth.users (recovery_token) where ((recovery_token)::text !~ '^[0-9 ]*$'::text);
create unique index email_change_token_current_idx on auth.users (email_change_token_current) where ((email_change_token_current)::text !~ '^[0-9 ]*$'::text);
create unique index email_change_token_new_idx on auth.users (email_change_token_new) where ((email_change_token_new)::text !~ '^[0-9 ]*$'::text);
create unique index reauthentication_token_idx on auth.users (reauthentication_token) where ((reauthentication_token)::text !~ '^[0-9 ]*$'::text);
create unique index users_email_partial_key on auth.users (email) where (is_sso_user = false);
alter table auth.users add constraint users_phone_key unique (phone);

create table public.organizations (
  id uuid not null default gen_random_uuid() primary key,
  name text not null,
  type text not null default 'hotel'::text,
  sasha_config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.trips (
  id uuid not null default gen_random_uuid() primary key,
  owner_id uuid not null,
  organization_id uuid null,
  title text not null,
  status text not null default 'draft'::text,
  destinations jsonb not null default '[]'::jsonb,
  depart_date date null,
  return_date date null,
  travelers jsonb not null default '[]'::jsonb,
  total_cost_usd numeric null,
  currency text not null default 'USD'::text,
  shared_with jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint trips_status_check check ((status = any (array['draft'::text, 'active'::text, 'completed'::text, 'cancelled'::text]))),
  constraint trips_organization_id_fkey foreign key (organization_id) references public.organizations(id) on delete set null,
  constraint trips_owner_id_fkey foreign key (owner_id) references auth.users(id) on delete cascade
);

create table public.trip_items (
  id uuid not null default gen_random_uuid() primary key,
  trip_id uuid not null,
  type text not null,
  status text not null default 'pending'::text,
  booking_reference text null,
  provider_name text null,
  provider_email text null,
  provider_phone text null,
  date_time timestamptz null,
  duration_minutes integer null,
  location_name text null,
  location_address text null,
  location_lat numeric null,
  location_lng numeric null,
  price_usd numeric null,
  currency text null,
  confirmation_deadline timestamptz null,
  escalated_at timestamptz null,
  escalation_notes text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint trip_items_status_check check ((status = any (array['pending'::text, 'attempting'::text, 'confirmed'::text, 'failed'::text, 'escalated'::text, 'cancelled'::text]))),
  constraint trip_items_type_check check ((type = any (array['flight'::text, 'hotel'::text, 'restaurant'::text, 'golf'::text, 'transfer'::text, 'experience'::text, 'visa'::text, 'insurance'::text, 'doctor'::text, 'beauty'::text, 'dog_walking'::text, 'coworking'::text]))),
  constraint trip_items_trip_id_fkey foreign key (trip_id) references public.trips(id) on delete cascade
);

create table public.booking_attempts (
  id uuid not null default gen_random_uuid() primary key,
  trip_item_id uuid not null,
  method text not null,
  attempted_at timestamptz not null default now(),
  status text not null default 'sent'::text,
  response_received text null,
  response_at timestamptz null,
  bland_call_id text null,
  resend_email_id text null,
  browserbase_session_id text null,
  constraint booking_attempts_method_check check ((method = any (array['email'::text, 'phone'::text, 'web_form'::text]))),
  constraint booking_attempts_status_check check ((status = any (array['sent'::text, 'delivered'::text, 'confirmed'::text, 'failed'::text, 'no_response'::text]))),
  constraint booking_attempts_trip_item_id_fkey foreign key (trip_item_id) references public.trip_items(id) on delete cascade
);
