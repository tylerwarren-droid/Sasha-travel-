-- 019 · Sasha 90 (a) · a venue's written confirmation EMAILED to Sasha's own address (sasha@booking.kanoe.ai) after a
-- call — matched to that booking by Sasha's own reference (K-XXXX) or, unambiguously, by the guest's surname — lands
-- on the reservation like an SMS (inbound_phone.py). The sender is kept as its sha256 key, like a number.
-- Verified live on sasha-prod (yjafyzywzbmhlilxhzuz), 1 Oct 2026, pg_constraint:
--   booking_inbound_channel_check  CHECK (channel = ANY (ARRAY['sms','voicemail','whatsapp']))
-- Only WIDENED: no row changes. ⛔ Applied by chat via MCP after review, never by the Sasha tab.

-- PREVIEW (read-only): applied = false before, true after
select pg_get_constraintdef(oid) like '%email%' as applied from pg_constraint where conname = 'booking_inbound_channel_check';

begin;
do $$
begin
  if pg_get_constraintdef((select oid from pg_constraint where conname = 'booking_inbound_channel_check')) like '%email%' then
    raise exception 'STOP: 019 is already applied — nothing was changed.';
  end if;
end $$;
alter table public.booking_inbound drop constraint booking_inbound_channel_check;
alter table public.booking_inbound add constraint booking_inbound_channel_check check (channel in ('sms', 'voicemail', 'whatsapp', 'email'));
commit;

-- VERIFY (read-only)
select pg_get_constraintdef(oid) like '%email%' as applied from pg_constraint where conname = 'booking_inbound_channel_check';
