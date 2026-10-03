-- Sasha 130 · EMAIL, THEN A CALL AT OPENING. The proactive ledger's kind check gains 'no_reply_call' (the dedupe of the
-- one WhatsApp question "no reply yet — they've just opened — shall I call them?").
-- The live constraint, read 3 Oct 2026 from pg_constraint on sasha-prod (yjafyzywzbmhlilxhzuz):
--   proactive_sent_kind_check CHECK (kind = ANY (ARRAY['day_before','not_confirmed','leave_now','written_confirmation','morning_brief']))
-- After applying: set SASHA_NO_REPLY_CALL=1 on Railway. Until then Sasha neither offers the call nor promises it.

-- preview (read-only): the constraint as it stands, and the kinds in use
select conname, pg_get_constraintdef(oid) from pg_constraint where conrelid = 'public.proactive_sent'::regclass and conname = 'proactive_sent_kind_check';
select kind, count(*) from public.proactive_sent group by kind;

begin;
alter table public.proactive_sent drop constraint proactive_sent_kind_check;
alter table public.proactive_sent add constraint proactive_sent_kind_check
  check (kind = any (array['day_before','not_confirmed','leave_now','written_confirmation','morning_brief','no_reply_call']));
commit;
