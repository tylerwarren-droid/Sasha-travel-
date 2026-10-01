-- 016 · S-70 · a venue's SMS or voicemail to Sasha's own number, filed on the reservation it is about (inbound_phone.py).
-- The sender's number is stored only as its sha256 key (Sasha 64: a listing number's digits are never stored).
-- ⛔ NOT APPLIED by any session until the founder approves it; then via railway run (preview, transaction, verify).

-- PREVIEW (read-only): must be 0
select count(*) as booking_inbound_tables from information_schema.tables where table_schema = 'public' and table_name = 'booking_inbound';

begin;
create table booking_inbound (
  provider_id        text        primary key,                 -- Twilio's MessageSid / CallSid: a redelivery is recognised
  channel            text        not null check (channel in ('sms', 'voicemail')),
  from_key           text        not null,                    -- sha256:<hex> of the sender's number, or 'unknown'
  to_number          text        null,                        -- Sasha's own number (not a secret)
  body_text          text        null,                        -- the SMS, verbatim
  recording_url      text        null,                        -- the voicemail, on Twilio
  recording_seconds  integer     null,
  call_id            uuid        null references public.booking_calls (call_id),
  trip_item_id       uuid        null references public.trip_items (id),
  reading            jsonb       null,                        -- how the words were read: confirmed / proposed / none, and why
  received_at        timestamptz not null
);
create index booking_inbound_item on booking_inbound (trip_item_id, received_at desc);
alter table booking_inbound enable row level security;   -- the backend only, like every booking table
commit;

-- VERIFY (read-only)
select relrowsecurity, (select count(*) from pg_policies where tablename = 'booking_inbound') as policies
from pg_class where relname = 'booking_inbound';
