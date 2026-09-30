-- ── S-37 · THE SLOT LINK — ONE BLOCK, FOR SASHA'S SUPABASE (xlqtveusyfpffaejegiq) ───────────────────────────────
--
-- A link Sasha hands the guest to the venue's own platform page, and what came back: the guest's word ("I booked
-- it") and the platform's confirmation, forwarded by the guest to act-{link_id}@<inbound>, kept verbatim.
--
-- trip_items gains two statuses:
--   link_sent     the guest opened the link — nothing is reserved yet, nothing was asked of the venue
--   guest_booked  the guest says they booked — their word, not yet the platform's confirmation
-- A forwarded confirmation that names the venue or the platform moves it to `confirmed`.
--
-- Run ONCE, whole, AFTER 001–004. It refuses if already applied or if 004 is missing.

-- ── PREVIEW — run on its own first; it changes nothing ─────────────────────────────────────────────────────────
-- select pg_get_constraintdef(oid) from pg_constraint where conname = 'trip_items_status_check';

do $$
begin
  if to_regclass('public.booking_links') is not null then
    raise exception 'STOP: booking_links already exists — nothing was changed.';
  end if;
  if to_regclass('public.venue_reads') is null then
    raise exception 'STOP: 004_ladder.sql has not been applied — nothing was changed.';
  end if;
  if (select pg_get_constraintdef(oid) from pg_constraint where conname = 'trip_items_status_check') not like '%unclear%' then
    raise exception 'STOP: 003_phone_calls.sql has not been applied — nothing was changed.';
  end if;
end $$;

create table public.booking_links (
  link_id           uuid        primary key,
  account_id        uuid        not null references auth.users (id) on delete cascade,
  trip_item_id      uuid        not null references public.trip_items (id),
  read_id           uuid        not null references public.venue_reads (read_id),
  platform          text        not null,
  url               text        not null check (url ~ '^https://'),
  slot_filled       boolean     not null,
  read_back_lines   jsonb       not null,
  read_back_sha256  text        not null check (read_back_sha256 ~ '^[0-9a-f]{64}$'),
  status            text        not null check (status in ('offered','link_sent','guest_booked','confirmed')),
  created_at        timestamptz not null,
  opened_at         timestamptz null,
  guest_said        jsonb       null,
  guest_said_at     timestamptz null,
  confirmed_at      timestamptz null
);
create index booking_links_account on public.booking_links (account_id, created_at desc);

create table public.booking_link_confirmations (
  provider_id  text        primary key,
  link_id      uuid        not null references public.booking_links (link_id),
  from_addr    text        null,
  subject      text        null,
  body_text    text        null,
  counted      boolean     not null,     -- true only when it names the venue or the platform
  note         text        null,
  received_at  timestamptz not null
);
create index booking_link_confirmations_link on public.booking_link_confirmations (link_id, received_at);

alter table public.booking_links              enable row level security;
alter table public.booking_link_confirmations enable row level security;

alter table public.trip_items drop constraint trip_items_status_check;
alter table public.trip_items add constraint trip_items_status_check check (status in
  ('pending','prepared','attempting','requested','declined','unreachable','confirmed','failed','escalated','cancelled','unclear',
   'link_sent','guest_booked'));

select 'booking_links and booking_link_confirmations exist, with row level security on' as check,
       (select count(*) from pg_class where relname in ('booking_links','booking_link_confirmations')
          and relnamespace = 'public'::regnamespace and relrowsecurity) = 2 as ok
union all
select 'trip_items accepts link_sent and guest_booked, and still unclear',
       (select pg_get_constraintdef(oid) from pg_constraint where conname = 'trip_items_status_check') like '%guest_booked%'
   and (select pg_get_constraintdef(oid) from pg_constraint where conname = 'trip_items_status_check') like '%unclear%';
