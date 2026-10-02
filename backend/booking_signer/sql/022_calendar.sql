-- 022 · S-79 · Google Calendar: the guest's connection (its refresh token sealed in the vault, 021), which Google event
-- mirrors which booking, and ONE outbox fed by a trigger — status is written in eleven places, and a Python hook in
-- each would be missed by the twelfth writer; the trigger can't be.
-- Verified against the live schema (sasha-prod) on 2 Oct 2026: 021 (vault_items) is applied; trip_items has status
-- text, date_time timestamptz; none of the three tables exists. Depends on 021.
-- ⛔ NOT APPLIED by any session: the founder approves, then it is applied by chat (preview, transaction, verify).

-- PREVIEW (read-only): must be three NULLs, and vault_items present
select to_regclass('public.calendar_links'), to_regclass('public.calendar_events'), to_regclass('public.calendar_outbox'),
       to_regclass('public.vault_items') as vault_items_present;

begin;
create table calendar_links (
  account_id               uuid        primary key references auth.users (id) on delete cascade,
  vault_item_id            uuid        not null references vault_items (id) on delete cascade,
  google_calendar_id       text,                                 -- the "Sasha bookings" secondary calendar (G-1)
  scopes                   text[]      not null,
  consent_at               timestamptz not null,
  consent_wording_version  text        not null,
  consent_text_sha256      text        not null check (consent_text_sha256 ~ '^[0-9a-f]{64}$'),
  last_ok_at               timestamptz,
  needs_reconnect_at       timestamptz,                          -- invalid_grant: the 7-day testing expiry, or a revoke
  told_reconnect_at        timestamptz                           -- the guest is told ONCE per expiry
);
create table calendar_events (
  trip_item_id     uuid        primary key references trip_items (id) on delete cascade,
  account_id       uuid        not null references auth.users (id) on delete cascade,
  google_event_id  text        not null,
  etag             text,
  synced_status    text        not null,
  synced_at        timestamptz not null default now()
);
create table calendar_outbox (
  id            bigserial   primary key,
  trip_item_id  uuid        not null,
  status        text        not null,
  created_at    timestamptz not null default now(),
  done_at       timestamptz,
  attempts      int         not null default 0,
  last_error    text
);
create index calendar_outbox_undone on calendar_outbox (created_at) where done_at is null;
create or replace function trip_items_status_to_outbox() returns trigger language plpgsql as $fn$
begin
  if new.status is distinct from old.status or new.date_time is distinct from old.date_time then
    insert into calendar_outbox (trip_item_id, status) values (new.id, new.status);
  end if;
  return new;
end $fn$;
create trigger trip_items_calendar_outbox after update of status, date_time on trip_items
  for each row execute function trip_items_status_to_outbox();
alter table calendar_links  enable row level security;
alter table calendar_events enable row level security;
alter table calendar_outbox enable row level security;
commit;

-- VERIFY (read-only): three rows rls true / 0 policies; the trigger present
select relname, relrowsecurity, (select count(*) from pg_policies p where p.tablename = c.relname) as policies
from pg_class c where relname in ('calendar_links', 'calendar_events', 'calendar_outbox') order by relname;
select tgname from pg_trigger where tgname = 'trip_items_calendar_outbox';
