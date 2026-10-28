-- Sasha 301 · THE FINE PRINT ON EVERY BOOKING. Two kinds the database doesn't allow yet:
--   keep_items.type 'my_card'       his card as he told her: its name, the LAST FOUR only, a perk in his words (agapi/keep.py)
--   proactive_sent.kind 'cancel_by' the reminder before a cancellation deadline the venue stated (booking_signer/proactive.py)
-- Read 28 Oct 2026 from sasha-prod (yjafyzywzbmhlilxhzuz):
--   keep_items_type_check      CHECK (type = ANY (ARRAY['preference','loyalty','home_address','passport','national_id','trusted_traveller',
--                                     'visa_residence','insurance_policy','health_card','booking_reference','door_code','wifi','esim']))
--   proactive_sent_kind_check  CHECK (kind = ANY (ARRAY['day_before','not_confirmed','leave_now','written_confirmation','morning_brief',
--                                     'no_reply_call','tap_expired','two_hours']))
-- APPLY AFTER DEPLOY of the Sasha 301 commit. Until it's applied: a card he tells her isn't saved (she says so; loyalty numbers save
-- as before), and no cancel_by reminder is sent (each claim is refused by the database, logged once, nothing sent).

-- preview (read-only): both checks as above; the kinds and types in use
select conrelid::regclass, conname, pg_get_constraintdef(oid) from pg_constraint
 where conname in ('keep_items_type_check', 'proactive_sent_kind_check');
select type, count(*) from public.keep_items group by type;
select kind, count(*) from public.proactive_sent group by kind;

begin;
alter table public.keep_items drop constraint keep_items_type_check;
alter table public.keep_items add constraint keep_items_type_check
  check (type = any (array['preference','loyalty','home_address','passport','national_id','trusted_traveller','visa_residence',
                           'insurance_policy','health_card','booking_reference','door_code','wifi','esim',
                           'my_card']));
alter table public.proactive_sent drop constraint proactive_sent_kind_check;
alter table public.proactive_sent add constraint proactive_sent_kind_check
  check (kind = any (array['day_before','not_confirmed','leave_now','written_confirmation','morning_brief','no_reply_call','tap_expired',
                           'two_hours','cancel_by']));
commit;

-- verify: 'my_card' and 'cancel_by' in the checks
select conname, pg_get_constraintdef(oid) from pg_constraint
 where conname in ('keep_items_type_check', 'proactive_sent_kind_check');
