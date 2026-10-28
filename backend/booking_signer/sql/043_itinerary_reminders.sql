-- Sasha 300 · THE ONE ITINERARY's reminders. A booking AgAPI sent (its act, act_…) or handed over (a platform's page, his own
-- WhatsApp) has no trip_items row, so the proactive ledger's dedupe (trip_item_id uuid, FK trip_items) can't hold it: it gains
-- booking_key (the act id / the hand-over's key), unique per kind like trip_item_id. And the "~2 hours before" reminder is a kind:
-- 'two_hours'. Read 28 Oct 2026 from sasha-prod (yjafyzywzbmhlilxhzuz): proactive_sent has no booking_key; its kind check is
--   CHECK (kind = ANY (ARRAY['day_before','not_confirmed','leave_now','written_confirmation','morning_brief','no_reply_call','tap_expired']))
-- APPLY AFTER DEPLOY of the Sasha 300 commit. Until it's applied, the code sends no reminder for those bookings and no 'two_hours'
-- reminder: each claim is refused by the database, logged once, and nothing is sent. The old ladder's reminders are unchanged.

-- preview (read-only): booking_key must be absent; the kinds in use
select column_name from information_schema.columns where table_schema = 'public' and table_name = 'proactive_sent' and column_name = 'booking_key';
select conname, pg_get_constraintdef(oid) from pg_constraint where conrelid = 'public.proactive_sent'::regclass and conname = 'proactive_sent_kind_check';
select kind, count(*) from public.proactive_sent group by kind;

begin;
alter table public.proactive_sent add column booking_key text check (booking_key is null or char_length(booking_key) between 1 and 300);
create unique index proactive_once_key on public.proactive_sent (booking_key, kind) where booking_key is not null;
alter table public.proactive_sent drop constraint proactive_sent_kind_check;
alter table public.proactive_sent add constraint proactive_sent_kind_check
  check (kind = any (array['day_before','not_confirmed','leave_now','written_confirmation','morning_brief','no_reply_call','tap_expired',
                           'two_hours']));
commit;

-- verify: booking_key text, the new index, 'two_hours' in the check
select column_name, data_type from information_schema.columns where table_schema = 'public' and table_name = 'proactive_sent' and column_name = 'booking_key';
select indexname from pg_indexes where tablename = 'proactive_sent' and indexname = 'proactive_once_key';
select pg_get_constraintdef(oid) from pg_constraint where conrelid = 'public.proactive_sent'::regclass and conname = 'proactive_sent_kind_check';
