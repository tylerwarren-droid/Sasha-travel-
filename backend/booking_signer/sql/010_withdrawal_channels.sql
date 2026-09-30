-- ── S-56 · A STOP IS RECORDED ON THE CHANNEL IT WAS SAID ON — ONE BLOCK, FOR SASHA'S SUPABASE (xlqtveusyfpffaejegiq) ─────
--
-- 008 allowed three channels (whatsapp · web_submit · email_confirm): the channels a venue can OPT IN to. A venue can
-- say STOP on others too — an email reply, a phone call, an SMS — and the withdrawal row must name where it was said.
-- This widens the check for WITHDRAWN rows only: an active opt-in is still one of the three.
--
-- Verified live before writing (pg_constraint): the check is named venue_optins_channel_check and is
-- CHECK (channel = ANY (ARRAY['whatsapp','web_submit','email_confirm'])). No row is changed; the table stays append-only.
--
-- Run ONCE, whole, AFTER 008. It refuses if already applied.

do $$
begin
  if to_regclass('public.venue_optins') is null then
    raise exception 'STOP: 008_venue_optins.sql has not been applied — nothing was changed.';
  end if;
  if pg_get_constraintdef((select oid from pg_constraint where conname = 'venue_optins_channel_check'
                           and conrelid = 'public.venue_optins'::regclass)) like '%phone%' then
    raise exception 'STOP: 010 is already applied — nothing was changed.';
  end if;
end $$;

alter table public.venue_optins drop constraint venue_optins_channel_check;
alter table public.venue_optins add constraint venue_optins_channel_check check (
  channel in ('whatsapp','web_submit','email_confirm')
  or (status = 'withdrawn' and channel in ('email','phone','sms')));

select 'venue_optins takes a withdrawal said by email, phone or sms' as check,
       pg_get_constraintdef((select oid from pg_constraint where conname = 'venue_optins_channel_check'
                             and conrelid = 'public.venue_optins'::regclass)) like '%phone%' as ok;
