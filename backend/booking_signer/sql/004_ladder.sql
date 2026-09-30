-- ── S-36 · THE LADDER — ONE BLOCK, FOR SASHA'S SUPABASE (xlqtveusyfpffaejegiq) ─────────────────────────────────
--
-- Four tables, nothing existing changed:
--   venue_reads               what Magellan read at a venue — every fact with its source, URL, moment and hash
--   booking_emails            an email Sasha may send: the exact email read back, its hash, and Resend's answer
--   booking_email_replies     a reply that arrived at act-{email_id}@<inbound>, matched by that address, verbatim
--   booking_email_quarantine  inbound mail that matched no email — kept, never guessed onto one
--
-- An email that Resend ACCEPTED records a booking_attempts row (method 'email', status 'sent') and moves the trip item
-- to 'attempting' — both values model A already allows. A reply never changes a status on its own: the guest reads
-- the venue's words.
--
-- Run ONCE, whole, AFTER 001, 002 and 003. It refuses if already applied or if 003 is missing.

-- ── PREVIEW — run on its own first; it changes nothing ─────────────────────────────────────────────────────────
-- select to_regclass('public.booking_calls') as calls_table_present,
--        to_regclass('public.venue_reads')   as should_be_null;

do $$
begin
  if to_regclass('public.venue_reads') is not null or to_regclass('public.booking_emails') is not null then
    raise exception 'STOP: the S-36 ladder tables already exist — nothing was changed.';
  end if;
  if to_regclass('public.booking_calls') is null then
    raise exception 'STOP: 003_phone_calls.sql has not been applied — nothing was changed.';
  end if;
end $$;

create table public.venue_reads (
  read_id      uuid        primary key,
  account_id   uuid        not null references auth.users (id) on delete cascade,
  query        jsonb       not null,
  venue_name   text        not null,
  country      text        null,
  read         jsonb       not null,          -- facts (each with source_url, fetched_at, sha256, snippet), sources, listing
  created_at   timestamptz not null
);
create index venue_reads_account on public.venue_reads (account_id, created_at desc);

create table public.booking_emails (
  email_id           uuid        primary key,
  account_id         uuid        not null references auth.users (id) on delete cascade,
  trip_item_id       uuid        not null references public.trip_items (id),
  read_id            uuid        not null references public.venue_reads (read_id),
  email              jsonb       not null,    -- from, to, cc, reply_to, subject, text — exactly what is sent
  email_sha256       text        not null check (email_sha256 ~ '^[0-9a-f]{64}$'),
  read_back_lines    jsonb       not null,
  read_back_sha256   text        not null check (read_back_sha256 ~ '^[0-9a-f]{64}$'),
  status             text        not null check (status in ('awaiting_approval','sending','sent','not_sent')),
  created_at         timestamptz not null,
  approval           jsonb       null,
  approved_at        timestamptz null,
  provider_id        text        null unique,
  provider_http      integer     null,
  provider_answer    jsonb       null,
  not_sent_why       text        null,
  sent_at            timestamptz null
);
create index booking_emails_account on public.booking_emails (account_id, created_at desc);
create index booking_emails_approved on public.booking_emails (approved_at) where approved_at is not null;

create table public.booking_email_replies (
  provider_id  text        primary key,       -- Resend's id for the received email: a redelivery is recognised
  email_id     uuid        not null references public.booking_emails (email_id),
  from_addr    text        null,
  subject      text        null,
  body_text    text        null,              -- verbatim; null only when the body could not be fetched (note says why)
  note         text        null,
  received_at  timestamptz not null
);
create index booking_email_replies_email on public.booking_email_replies (email_id, received_at);

create table public.booking_email_quarantine (
  provider_id  text        primary key,
  to_addrs     jsonb       null,
  from_addr    text        null,
  subject      text        null,
  reason       text        not null,
  received_at  timestamptz not null
);

alter table public.venue_reads              enable row level security;
alter table public.booking_emails           enable row level security;
alter table public.booking_email_replies    enable row level security;
alter table public.booking_email_quarantine enable row level security;

select 'the four S-36 tables exist, with row level security on' as check,
       (select count(*) from pg_class where relname in ('venue_reads','booking_emails','booking_email_replies','booking_email_quarantine')
          and relnamespace = 'public'::regnamespace and relrowsecurity) = 4 as ok;
