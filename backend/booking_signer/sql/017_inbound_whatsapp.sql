-- 017 · S-71 · a venue's WhatsApp message to Sasha's own number lands like an SMS (inbound_phone.py), and its outcome is
-- recorded as a WhatsApp attempt, not a phone one.
-- Verified live on sasha-prod (yjafyzywzbmhlilxhzuz) before writing, pg_constraint, 1 Oct 2026:
--   booking_inbound_channel_check   CHECK (channel = ANY (ARRAY['sms','voicemail']))
--   booking_attempts_method_check   CHECK (method = ANY (ARRAY['email','phone','web_form']))
-- Both are only WIDENED: no row is changed, every existing value stays valid. venue_optins already takes 'whatsapp'.
-- Run ONCE, whole, after 016. It refuses if already applied.

-- PREVIEW (read-only): both false before, both true after
select pg_get_constraintdef(oid) like '%whatsapp%' as applied, conname from pg_constraint
where conname in ('booking_inbound_channel_check', 'booking_attempts_method_check');

begin;
do $$
begin
  if to_regclass('public.booking_inbound') is null then
    raise exception 'STOP: 016_inbound_phone.sql has not been applied — nothing was changed.';
  end if;
  if pg_get_constraintdef((select oid from pg_constraint where conname = 'booking_inbound_channel_check')) like '%whatsapp%' then
    raise exception 'STOP: 017 is already applied — nothing was changed.';
  end if;
end $$;
alter table public.booking_inbound drop constraint booking_inbound_channel_check;
alter table public.booking_inbound add constraint booking_inbound_channel_check check (channel in ('sms', 'voicemail', 'whatsapp'));
alter table public.booking_attempts drop constraint booking_attempts_method_check;
alter table public.booking_attempts add constraint booking_attempts_method_check check (method in ('email', 'phone', 'web_form', 'whatsapp'));
commit;

-- VERIFY (read-only)
select pg_get_constraintdef(oid) like '%whatsapp%' as applied, conname from pg_constraint
where conname in ('booking_inbound_channel_check', 'booking_attempts_method_check');
