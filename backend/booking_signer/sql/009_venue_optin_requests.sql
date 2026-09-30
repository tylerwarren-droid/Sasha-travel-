-- ── S-55 · "WORK WITH SASHA" REQUESTS — ONE BLOCK, FOR SASHA'S SUPABASE (xlqtveusyfpffaejegiq) ──────────────────────
--
-- S-49 §2 method 3: the page's submission waits here until the venue clicks the link emailed to it (double opt-in).
-- ⛔ Nothing here is consent. Only the confirmation writes venue_optins rows (008), one per ticked channel, carrying
-- this request's fields as their evidence.
--
-- The link's token is never stored — only its sha256. The table is mutable (sent, confirmed, withdrawn are stamped on
-- it); the consent record itself stays append-only in venue_optins.
--
-- Row level security on, no policies: only the server's own connection reads or writes it.
--
-- Run ONCE, whole, AFTER 008. It refuses if already applied.

do $$
begin
  if to_regclass('public.venue_optin_requests') is not null then
    raise exception 'STOP: venue_optin_requests already exists — nothing was changed.';
  end if;
  if to_regclass('public.venue_optins') is null then
    raise exception 'STOP: 008_venue_optins.sql has not been applied — nothing was changed.';
  end if;
end $$;

create table public.venue_optin_requests (
  request_id          uuid        primary key,
  token_sha256        text        not null unique check (token_sha256 ~ '^[0-9a-f]{64}$'),
  created_at          timestamptz not null,
  expires_at          timestamptz not null,
  lang                text        not null check (lang in ('en','es')),
  venue_id            text        not null,
  venue_name          text        not null,
  contact_name        text        not null,
  contact_role        text        not null,
  email               text        not null,
  channels            jsonb       not null,   -- [{channel, scope, wording_version, wording_sha256, wording_text}]
  submitted           jsonb       not null,   -- the form exactly as submitted
  email_status        text        not null default 'pending' check (email_status in ('pending','sent','not_sent')),
  email_provider_id   text        null,
  email_why           text        null,
  confirmed_at        timestamptz null,
  withdrawn_at        timestamptz null,
  check (expires_at > created_at)
);
create index venue_optin_requests_email on public.venue_optin_requests (lower(email), created_at desc);
create index venue_optin_requests_created on public.venue_optin_requests (created_at desc);
alter table public.venue_optin_requests enable row level security;

select 'venue_optin_requests exists, with row level security on' as check,
       (select relrowsecurity from pg_class where oid = 'public.venue_optin_requests'::regclass) as ok;
