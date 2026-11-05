-- Sasha 345 · REPAIR group_movements.rules: every row an OBJECT. Data only, idempotent (a second run finds nothing). Same class as 051:
-- the pool's jsonb codec already JSON-encodes, so groups.set_rules' `json.dumps(rules)::jsonb` stored a JSON STRING (read back by a second
-- json.loads, so it "worked" — until anything reads the column in SQL). The code now writes `$3::text::jsonb` (an object).

-- preview (read-only): 5 Nov — string 4 · object 6
-- select jsonb_typeof(rules) t, count(*) from public.group_movements group by 1;

begin;
update public.group_movements
   set rules = (rules #>> '{}')::jsonb
 where jsonb_typeof(rules) = 'string' and left(btrim(rules #>> '{}'), 1) = '{';
commit;

-- check (read-only): only object
-- select jsonb_typeof(rules) t, count(*) from public.group_movements group by 1;
