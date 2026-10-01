-- 013 · Sasha 64 (finding A) · remove stored Google Maps content from the rows written before places_terms.py.
-- ⛔ NOT APPLIED by any session. The founder runs it in the Supabase SQL editor (Sasha's project), section by section:
--    run the PREVIEW, read it, then the transaction. Nothing outside these rows is touched.
--
-- What it removes, and what it keeps:
--   venue_reads   · each listing fact keeps its kind, place and index (a rung names a fact by index). Its value,
--                   words and label are removed. The listing keeps only its place_id; Places sources lose their
--                   query text. The one read picked from the cards (query has place_id) loses the listing's name.
--   booking_calls · calls dialled on a LISTING number (number_source starts "their Google listing"). The number
--                   becomes number_ref {place_id, sha256}; dialled_number becomes "sha256:<hex>" (S-57 log matching
--                   and stops still work on it). The read-back's first line loses the digits and the listing's name
--                   and address. Bland's stored answers and details lose the digits.
--   NOT touched   · names the guest typed ("La Contra", "Calma"); the venue's own words; reservation/1 requests
--                   (they hold no listing content); request_sha256.
-- ⚠ brief_sha256 and read_back_sha256 keep attesting the ORIGINAL texts. The brief records that it was purged and
--   when, so a later mismatch reads as a purge, not tampering. Two calls still `awaiting_approval` (stale) will then
--   refuse with brief_changed. That is correct: they are more than 15 minutes old and cannot be approved anyway.
-- Reversible in substance: everything removed can be re-read from Google by place_id. The rows themselves are not
-- restored by any script.

-- ── PREVIEW (read-only) ────────────────────────────────────────────────────────────────────────────────────────
select 'venue_reads with listing facts' what, count(*) n from venue_reads
  where exists (select 1 from jsonb_array_elements(read->'facts') f where f->>'source_kind' = 'places' and f->'value' <> 'null'::jsonb)
union all select 'venue_reads picked from cards (name to replace)', count(*) from venue_reads where query->>'place_id' is not null and query ? 'name'
union all select 'booking_calls on a listing number', count(*) from booking_calls where brief->>'number_source' like 'their Google listing%'
union all select '  of which awaiting_approval', count(*) from booking_calls where brief->>'number_source' like 'their Google listing%' and status = 'awaiting_approval';
-- expected on 1 Oct 2026: 22 · 1 · 8 · 2 (the read made by the S-68 proof is already in the new form: not counted)

-- ── THE PURGE ──────────────────────────────────────────────────────────────────────────────────────────────────
begin;

update venue_reads r set
  read = jsonb_set(jsonb_set(jsonb_set(r.read,
    '{facts}', coalesce((select jsonb_agg(case when f->>'source_kind' = 'places' then jsonb_build_object(
        'kind', f->'kind', 'value', null, 'source_kind', 'places', 'source_url', f->'source_url',
        'source_label', 'their Google Maps listing', 'snippet', '', 'fetched_at', f->'fetched_at', 'sha256', f->'sha256',
        'detail', jsonb_build_object('place_id', r.read->'listing'->'place_id',
                                     'withheld', 're-read from the Google Maps listing when needed; never stored'))
      else f end order by o) from jsonb_array_elements(r.read->'facts') with ordinality x(f, o)), '[]'::jsonb)),
    '{listing}', case when r.read->'listing'->>'place_id' is not null
                      then jsonb_build_object('place_id', r.read->'listing'->'place_id') else 'null'::jsonb end),
    '{sources}', coalesce((select jsonb_agg(case when s->>'url' like 'https://places.googleapis.com%' then s - 'query' else s end order by o)
                           from jsonb_array_elements(r.read->'sources') with ordinality y(s, o)), '[]'::jsonb))
where exists (select 1 from jsonb_array_elements(r.read->'facts') f where f->>'source_kind' = 'places' and f->'value' <> 'null'::jsonb);

-- the one read picked from the cards: its name was the listing's
update venue_reads set
  venue_name = 'the place you picked in ' || coalesce(query->>'city', 'the city searched'),
  read = jsonb_set(read, '{name}', to_jsonb('the place you picked in ' || coalesce(query->>'city', 'the city searched'))),
  query = query - 'name'
where query->>'place_id' is not null and query ? 'name';   -- a read written after Sasha 64 has no listing name to replace

update booking_calls c set
  dialled_number = 'sha256:' || encode(sha256(convert_to(c.dialled_number, 'UTF8')), 'hex'),
  brief = c.brief || jsonb_build_object(
    'number', null,
    'number_ref', jsonb_build_object('source', 'places',
                                     'place_id', (select r.read->'listing'->>'place_id' from venue_reads r where 'read:' || r.read_id = c.venue_key),
                                     'sha256', encode(sha256(convert_to(c.dialled_number, 'UTF8')), 'hex')),
    'number_source', 'their Google Maps listing', 'number_source_kind', 'places',
    'purged', jsonb_build_object('at', now(), 'by', '013_purge_places_content', 'note',
      'listing content removed (Sasha 64); brief_sha256 and read_back_sha256 attest the texts as approved, before this')),
  read_back_lines = replace(jsonb_set(c.read_back_lines, '{0}', to_jsonb(regexp_replace(c.read_back_lines->>0,
      ', \+\d+ — the number on their Google listing \(.*\)\.$', ' on the number its Google Maps listing gives.'))
    )::text, c.dialled_number, '⟨the listing''s number⟩')::jsonb,
  bland_details = case when c.bland_details is null then null
                       else replace(c.bland_details::text, c.dialled_number, '⟨the listing''s number⟩')::jsonb end,
  bland_answer = case when c.bland_answer is null then null
                      else replace(c.bland_answer::text, c.dialled_number, '⟨the listing''s number⟩')::jsonb end
where c.brief->>'number_source' like 'their Google listing%';

-- ── CHECK before commit: every count must be 0 ─────────────────────────────────────────────────────────────────
select 'reads still holding a listing value' what, count(*) n from venue_reads
  where exists (select 1 from jsonb_array_elements(read->'facts') f where f->>'source_kind' = 'places' and f->'value' <> 'null'::jsonb)
union all select 'reads with a listing name/address', count(*) from venue_reads where read->'listing' ? 'name' or read->'listing' ? 'address'
union all select 'calls with digits in dialled_number', count(*) from booking_calls where brief ? 'number_ref' and dialled_number not like 'sha256:%'
union all select 'calls whose read-back names the listing', count(*) from booking_calls where read_back_lines::text like '%their Google listing (%'
union all select 'calls whose brief names the listing', count(*) from booking_calls where brief::text like '%their Google listing (%'
union all select 'calls without a place_id to re-read', count(*) from booking_calls where brief ? 'number_ref' and brief->'number_ref'->>'place_id' is null;

commit;   -- or: rollback;
