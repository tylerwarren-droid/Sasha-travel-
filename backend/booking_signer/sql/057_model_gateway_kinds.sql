-- 057 · Sasha 353 · THE MODEL GATEWAY's two records in sasha_measures (found by the first recording run, 6 Nov: every save refused by
-- sasha_measures_kind_check — the gate's 204 recorded replies were not kept, nor the day's usage that keeps the caps across restarts):
--   model_day     the day's model usage (total, per account, per model, per caller) — what the daily caps count from after a restart
--   model_replay  one recorded model reply, by its replay key — what the deploy gate answers from (kept a year)
-- Idempotent.
begin;
alter table public.sasha_measures drop constraint if exists sasha_measures_kind_check;
alter table public.sasha_measures add constraint sasha_measures_kind_check
  check (kind = any (array['turn', 'client', 'booking', 'daily', 'avatar', 'model_day', 'model_replay']));
commit;
select pg_get_constraintdef(oid) as kinds from pg_constraint where conname = 'sasha_measures_kind_check';
