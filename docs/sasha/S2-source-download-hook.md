# CR 77 · S2 hook: "Download source" and offline rules (for the Sasha tab to wire)

AgAPI keeps a copy of every source it reads, as it was read. Every quoted line it returns already carries its `claim_id`:
`cards.rental_cover` (the counter card) and `cards.accident_*` (the accident flow) both do. Nothing new is needed on the AgAPI side.

## 1 · The "source" toggle can offer the download

When the person opens a line's source on the counter card, or in an accident step, call:

    sources.get {"claim_id": "<the line's claim_id>"}

You get back `url` (a signed link that works for 10 minutes; ask again after that), `sha256`, `read_at`, `source_url`, `format`
(`pdf` or `html`), and `pdf_available` for a web page. For a web page, `{"claim_id": …}` returns the HTML; to get the PDF rendered
from it, call `{"copy_id": "<copy_id>", "format": "pdf"}`.

Show it as **"Download source · read 10 Oct 2026"**. Show the original `source_url` beside it as the official page. Never cache
the signed `url`.

A file a person supplied, such as BBVA's certificate, says `supplied_by`: show it as "supplied by a person".

## 2 · The accident flow can save the country's rules to the person's Keep

Offer **"Save these rules for offline"** once the accident flow has started for a country. Save one Keep item for that
country's rules: each step's quoted line, its `source_url` and `read_at`, plus the kept copy's `sha256`. Save the text, not the
signed link. An offline copy never needs a network call to read. Before relying on a saved item, re-check it with
`sources.get` (by sha256) whenever there is signal.

Where the government publishes an official PDF of the same law, AgAPI keeps that too (role `official_pdf`): the BOE for Ley
50/1980, and gesetze-im-internet.de for StVO and VVG. Its `copy_id` is in the read; it can be offered as "the law, official PDF".

## Not wired yet

None of this is on Sasha main. Its scope is the S2 branches only. S1 is untouched.
