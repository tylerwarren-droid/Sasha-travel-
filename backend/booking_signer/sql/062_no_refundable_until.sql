-- 062 · Sasha 423 · FP-4 · NO REFUNDABILITY WITHOUT A FACT (KANOE 26 Nov 11:08). payment_requests.refundable_until (024) is a booking
-- term held by Sasha: a second copy of what AgAPI's fine-print record governs (fine_print_facts, read through facts.answer). Nothing in
-- the code writes or reads it (payments_t0.py inserts every other column), so the column goes. The ratchet
-- (backend/tests/test_s423_no_term_without_a_fact.py) reads the SQL files in order and fails while it is still standing.
-- ⛔ NOT APPLIED by any session: the founder approves, then it is applied by chat (preview, transaction, verify).

-- PREVIEW (read-only): 0 or 1 row; if 1, how many rows hold a value (expect 0 — nothing ever wrote it)
select column_name from information_schema.columns where table_schema = 'public' and table_name = 'payment_requests'
  and column_name = 'refundable_until';
select count(*) filter (where refundable_until is not null) as with_a_value from payment_requests;   -- skip if the table is absent

begin;
alter table if exists payment_requests drop column if exists refundable_until;
commit;

-- VERIFY (read-only): 0 rows
select column_name from information_schema.columns where table_schema = 'public' and table_name = 'payment_requests'
  and column_name = 'refundable_until';
