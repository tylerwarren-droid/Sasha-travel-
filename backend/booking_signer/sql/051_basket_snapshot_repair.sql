-- Sasha 339 · REPAIR trip_basket_items.snapshot: every row an OBJECT again. Data only, no schema change; idempotent (a second run finds nothing).
-- Found in the 335/339 proof: the pool's jsonb codec already JSON-encodes, so basket.py's `json.dumps(...)::jsonb` stored each snapshot as a
-- JSON STRING; supersede's `snapshot || jsonb_build_object('superseded_at', …)` on a string made an ARRAY [string, {superseded_at}] — and
-- the group master list crashed on one. The code now writes objects ($n::text::jsonb) and merges safely (basket.SNAP_OBJECT).

-- preview (read-only): 4 Nov — string 1,454 rows (11 accounts) · array 57 rows (4 accounts) · object 0
-- select jsonb_typeof(snapshot) t, count(*), count(distinct account_id) from public.trip_basket_items group by 1;

begin;

-- 1 · arrays: their elements merged in order into ONE object (a string element is the object it holds; later keys win: superseded_at)
update public.trip_basket_items t
   set snapshot = (select coalesce(jsonb_object_agg(kv.key, kv.value order by e.n), '{}'::jsonb)
                     from jsonb_array_elements(t.snapshot) with ordinality e(el, n),
                          jsonb_each(case jsonb_typeof(e.el) when 'object' then e.el
                                                             when 'string' then (e.el #>> '{}')::jsonb else '{}'::jsonb end) kv)
 where jsonb_typeof(t.snapshot) = 'array';

-- 2 · strings: the object each one holds
update public.trip_basket_items
   set snapshot = (snapshot #>> '{}')::jsonb
 where jsonb_typeof(snapshot) = 'string' and left(btrim(snapshot #>> '{}'), 1) = '{';

commit;

-- check (read-only): every row an object — expect object 1,511 (+ rows written since), nothing else
-- select jsonb_typeof(snapshot) t, count(*) from public.trip_basket_items group by 1;
