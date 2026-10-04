# CR 15 · Applied Diligence PREVIEW on WhatsApp — the contract (pinned with the US tab, 4 Oct 2026)

**Status:** the WhatsApp side is built (`backend/products/diligence.py`). **Whether AD exposes the endpoint, its per-day
cap and who pays for a preview are the founder's decisions** — until then WhatsApp says "the register service isn't
connected here yet, so nothing was checked".

## Call
`POST {AD_PREVIEW_URL}/api/preview/register` · header `X-Kanoe-Key: {AD_PREVIEW_KEY}` — server to server from Railway.
The key is given by the founder to the tabs; the US tab sets it on Vercel, this tab sets it on Railway, via CLI, never
printed, never in a repo or a chat.

Request: `{"country": ISO-3166 alpha-2, "name": str|null, "registration_number": str|null}` — exactly one of the two.
**Companies only**: a person is refused (4xx with a reason on AD's side; refused locally on ours, never sent).

## Answer
```
{"status": "identified"|"ambiguous"|"not_found"|"not_covered"|"uncovered_preview"|"not_in_preview",
 "entity": {"legal_name","registration_number","register",
            "status_raw": the register's own word, verbatim,
            "status": normalised, or null when no honest mapping exists,
            "address","incorporated"} | null,
 "standing": {"value": "active"|"ceased"|null, "expressible": bool, "because": "<one line, always present>"},
 "candidates": [{"legal_name","registration_number"}],   // names that RESEMBLE the query — never matches
 "source": {"name","url"},
 "retrieved_at": when AD read the register,
 "source_as_of": the publisher's own as-of, or null for a live fetch,
 "scope": the PER-COUNTRY scope text,
 "preview": true}
```
`not_covered` no rail · `uncovered_preview` a rail, not certified for sale · `not_in_preview` certified, but the licence
forbids onward supply (NL, MT, AT …).

## How WhatsApp shows it
- Heading "🔎 Applied Diligence — PREVIEW", then **the scope line** (second line: a cut message never loses it).
- The register's status in its own words; **standing never silent**: "Standing: not shown — <because>".
- Both dates: "Read from the register" and "The source's own data as of".
- Ambiguous: "Names that resemble X — possible matches, not confirmed". Unreachable ≠ not found ≠ refused.
- A sole trader (SIRENE catégorie juridique 1000) is a person: never shown.
- NL, MT, AT are refused locally as well (a licence term deserves two independent refusals).

## Per-country notes (EU tab, measured)
France is the demo country: SIRENE is Etalab Open Licence 2.0 (attribution only), queried live, not stored. It carries
**administrative state only** (A/C) — no insolvency or proceedings (those are RCS/BODACC, not called): "active" means
administratively registered, not solvent. Suggested FR scope wording: "Identified in the Sirene administrative register
(INSEE)". SIRENE caps at 30 requests/min per key with no rate headers: one request per lookup.

## Optional sample (off by default)
`AD_PREVIEW_SAMPLE=1` with no live service shows the US tab's fixed TotalEnergies example, labelled **SAMPLE (a fixed
example response, not a live register lookup)**, with no read date, for that one query only. A demonstration of the
message, not of a lookup — the founder's choice whether to use it on Wednesday.
