-- Sasha 131 · THE ESCALATION POLICY: a one-tap page the guest hasn't pressed on within SASHA_TAP_WINDOW_MIN → ONE WhatsApp
-- question ("shall I email them instead?"). The proactive ledger's kind check gains 'tap_expired' (its dedupe).
-- The live constraint, read 3 Oct 2026 from pg_constraint on sasha-prod (yjafyzywzbmhlilxhzuz), after 030:
--   proactive_sent_kind_check CHECK (kind = ANY (ARRAY['day_before','not_confirmed','leave_now','written_confirmation','morning_brief','no_reply_call']))
-- After applying: set SASHA_TAP_ESCALATION=1 on Railway. Until then Sasha neither offers the email nor promises it.

-- preview (read-only)
select conname, pg_get_constraintdef(oid) from pg_constraint where conrelid = 'public.proactive_sent'::regclass and conname = 'proactive_sent_kind_check';
select kind, count(*) from public.proactive_sent group by kind;

begin;
alter table public.proactive_sent drop constraint proactive_sent_kind_check;
alter table public.proactive_sent add constraint proactive_sent_kind_check
  check (kind = any (array['day_before','not_confirmed','leave_now','written_confirmation','morning_brief','no_reply_call','tap_expired']));
commit;
