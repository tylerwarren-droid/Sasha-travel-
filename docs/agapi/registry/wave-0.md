# The registry survey, wave 0: registry operations in AgAPI on the certified core

*CR 73 · 10 Oct 2026 · branch `cr/agapi-api` · built to EU 214 (`docs/agapi/registry/*` in the AD repo: model, discovery, api,
coverage-plan, build-plan). Read-only for AD: its database was only SELECTed from.*

## What exists now

**The model** (`agapi_service/registers/model.py`): Country → Register → Document type → Access route.
- **Every fact is a claim:** `source_url`, `read_at`, a verbatim `quote`, `quote_sha256`, `method` and `confidence`.
- **A field with no claim behind it is `unknown`.** It is never guessed.
- **Claims are never edited:** a re-read writes a new claim and supersedes the old one.
- **Ids:** `rgr_` register · `rdt_` document type · `rrt_` route · `rcl_` claim. They're deterministic, so a reload is idempotent.
- **Tables:** `registry_jurisdictions`, `registry_registers`, `registry_documents`, `registry_routes`, `registry_claims`,
  `registry_checks`, `registry_loads`. They live in the sandbox's own store (Postgres), never in AD's database.

**The operations** (Kanoe extensions until EU formalizes them in 1.3; `spec/ext/operations.ext.json`):

| Operation | Agent | Cost | What it answers |
|---|---|---|---|
| `registry.countries` | magellan | read | per jurisdiction: register / document / route counts, automation mix, kinds, `as_of` |
| `registry.get` | magellan | read | a jurisdiction's registers, every field with its claim; the pages read and the ones not read (with why) |
| `registry.documents` | magellan | read | what can be obtained: kind, subject, who may obtain it (as the source states it), the routes summary |
| `registry.obtain_plan` | magellan | search (1) | the ranked routes for an actor (`agapi` · `person` · `subject`), `requires[]`, `obtainable_by_agapi` |
| `registry.verify` | pacioli | read | re-reads a claim's page now: `fresh` / `drifted` / `broken` (with `failure_layer`) |

**`registry.obtain` is OFF.** It isn't registered: calling it gives `unknown_operation`. Every plan says "off — plans only". Nothing is
bought, no account is used, no CAPTCHA is solved.

**EU 214's error codes** ride on EU's existing codes until 1.3 adds them, as `details.registry_code`:
- `jurisdiction_unknown` and `document_unknown` → `not_found`;
- `source_unreachable` → `upstream_unreachable` (503, retryable; never "drifted").

## Where the facts come from

1. **AD's catalogue, read-only** (`registers/data/ad_export.json`):
   - SELECTs on production: `jurisdiction_record_types` with a `certified_config_hash` (the 20 live-hash cells), their
     `jurisdictions`, each cell's latest passed `jurisdiction_certifications` row, and every `acquisition_route_policies` row (1: GR);
   - AD's internal prose (`legal_basis_notes`, `process_description`, `notes`) is **not** copied;
   - these become `ad_catalogue` claims (confidence `desk`) and `certification` claims (`proven`), each citing its AD row
     (`ad://jurisdiction_record_types/<id>`, `ad://jurisdiction_certifications/<id>`).
2. **Magellan's reads of the registers' own official pages** (`registers/data/reads.json`):
   - run **on the sandbox server (Railway)**, never from a laptop: `POST /admin/registry_read` (signed admin) per jurisdiction;
   - the seeds (`registers/data/seeds.json`) come from AD's profiles and catalogue, or the CR tab's desk, as each says. A seed is only
     a starting point;
   - **robots.txt first, strict:** a 200 that is a web page (a login page, a WAF challenge) is `unreadable`, and unreadable means not
     allowed. A robots file that names ClaudeBot / Claude-User / anthropic-ai is honoured for those names too;
   - **AD's never-fetch list** (ported from `scripts/discovery-crawler/guardrails.py`) is refused before any request;
   - at most 12 pages a jurisdiction, ~1 a second, html only; a site's own search results and challenge pages are not sources;
   - **the AI reader** (Opus 5.5, AgAPI's own key, structured outputs) drafts facts. **Every quote is checked word for word against
     its page; one that isn't there is dropped.** Text that tries to instruct an AI is never a claim. Values outside the model's
     vocabulary are dropped. The reader never decides automation, eligibility or tiers: `plan.py` derives those from the claims;
   - these become `magellan_fetch` claims (`read_at_source`), plus `magellan_robots` claims for each route's own host.

## How `obtain_plan` ranks (`registers/plan.py`; `spec/ext/vectors/registry-plan.json`, 22 cases)

1. **Drop** what this actor can't use: a resident eID for AgAPI; the subject's own routes outside lane S; authority-only documents.
2. **A route whose robots.txt disallows us, can't be read, or is on the never-fetch list is not automated.** It stays as human-only:
   a person can still use the site.
3. **An account route is a person's job.** AgAPI never logs in for anyone.
4. **Tiers:**
   1. api with a certified rail (not withdrawn in AD's catalogue);
   2. web_form with an enabled route policy;
   3. web_form without one, an uncertified api, or a withdrawn rail ("needs a decision");
   4. human-only.
5. **Within a tier:** cheaper, then faster, then fresher claims; an unknown cost or date ranks last.
6. **`obtainable_by_agapi`:** `yes` (tiers 1–2) · `with_human` · `no` (only the subject).

## The demo

https://agapi-sandbox-production.up.railway.app/registry (no key; read-only)

1. Pick a country to see its registers, then what you can get from them.
2. Every value has a **source** link: the sentence quoted from the page, its URL, the date it was read, the method and the confidence.
3. **How do I get it?** shows the plan.
4. **Check now** re-reads that one sentence's page live. It's budgeted: 20 per host an hour, 60 an hour for the page.

## Results

**All 19 wave-0 jurisdictions are in the registry** (10 Oct 2026):
- **18** were read from their official pages;
- **LT's** register site (registrucentras.lt) answered HTTP 403 to every request, so it rests on AD's catalogue and certification alone,
  and says so.

**The numbers:**
- 188 pages read and **483 facts quoted word for word**. No committed quote is absent from its page: the reader's not-verbatim
  drops were 1, all removed before the snapshot.
- 0 instruction-like texts became claims.
- AI reading cost ≈ **$3.5** in total (Opus 5.5, AgAPI's own key).

| Jurisdiction | Official pages read | Facts quoted | Registers · documents · routes | AD rail's host: robots.txt | Per document: can AgAPI obtain it? |
|---|---|---|---|---|---|
| AT | 12 | 38 | 1 · 11 · 7 | unreadable | with a person 5 · unknown 6 |
| CY | 12 | 22 | 1 · 4 · 5 | unreadable | with a person 4 |
| DE | 6 | 35 | 2 · 10 · 5 | allowed | yes 1 · with a person 3 · unknown 6 |
| DK | 11 | 34 | 3 · 8 · 10 | allowed | with a person 7 · unknown 1 |
| ES | 12 | 15 | 2 · 5 · 2 | n/a: AD's local copy | yes 1 · with a person 1 · unknown 3 |
| FI | 12 (1 refused us) | 19 | 1 · 3 · 5 | unreadable | with a person 3 |
| FR | 12 | 58 | 4 · 11 · 14 | unreadable | with a person 9 · unknown 2 |
| GLOBAL | 12 | 17 | 1 · 5 · 6 | allowed | yes 1 · with a person 4 |
| IE | 12 (1 refused us) | 14 | 1 · 3 · 3 | n/a: operator download | yes 1 · with a person 1 · unknown 1 |
| LT | 0 (2 refused us) | 0 | 1 · 1 · 1 | n/a: operator download | yes 1 |
| LV | 12 | 23 | 2 · 7 · 6 | n/a: operator download | yes 1 · with a person 4 · no (subject/authority only) 1 · unknown 1 |
| MT | 2 | 25 | 3 · 5 · 3 | allowed | with a person 3 · unknown 2 |
| NL | 12 (1 refused us) | 39 | 2 · 8 · 8 | allowed | yes 1 · with a person 6 · unknown 1 |
| SE | 1 (1 refused us) | 11 | 1 · 2 · 3 | n/a: operator download | yes 1 · with a person 1 |
| SI | 12 | 44 | 6 · 9 · 9 | n/a: operator download | yes 1 · with a person 8 |
| US-AL | 12 | 29 | 2 · 7 · 5 | never fetch | with a person 4 · unknown 3 |
| US-HI | 12 | 16 | 1 · 5 · 4 | allowed | yes 1 · with a person 3 · unknown 1 |
| US-ID | 12 | 20 | 2 · 4 · 3 | allowed | yes 1 · with a person 2 · unknown 1 |
| US-ND | 12 (1 refused us) | 24 | 2 · 7 · 6 | unreadable | with a person 6 · unknown 1 |

**What the plans say:**
- **"yes" (a certified instant rail AgAPI may run) in 11:** DE, ES, GLOBAL, IE, LT, LV, NL, SE, SI, US-HI, US-ID.
- **Not instant, said plainly, in 8:**
  - **AD's certified rail sits on a host whose robots.txt can't be read as a robots file:**
    - **AT** (justizonline.gv.at answers its login page). This independently confirms AD's own AT profile verdict;
    - **FI** (avoindata.prh.fi answers a web page);
    - **US-ND** (firststop.sos.nd.gov answers a web page);
    - **CY** (efiling.drcor: the connection drops; this matches AD's CY profile);
    - **FR** (api.insee.fr: read errors twice from Railway).
    - By the profile standard, unreadable means not allowed. So the plan shows these rails as a person's job, with the reason. **This
      changes nothing in AD:** it is a finding for AD's certification owners, not a decision.
  - **The rail is withdrawn in AD's catalogue:** DK, MT, US-AL. **US-AL** is also on AD's never-fetch list (arc-sos.state.al.us),
    which was never requested.
- **"unknown":** a document whose routes no source states. **"no"** is used only when only the subject or an authority can get it.

**The demo** (`registry.verify` live from the sandbox, 10 Oct 06:31Z):
- the Austrian claim "Aktueller Firmenbuchauszug" → **fresh**: the quoted sentence is still on justiz.gv.at, read now.
- The AT plan for the current extract:
  1. JustizOnline, paid web, **EUR 4.89 per document** (quoted): "needs a decision first", with a person;
  2. through a Verrechnungsstelle (intermediary, account): a person's job.

**Fixed along the way:**
- **Robots per scheme:** robots.txt is now read on the URL's own scheme (DK's `http://` endpoint was being checked over https, and
  timed out).
- **Duplicate pages:** session-id URLs (`;jsessionid=`), `?lang=` copies, a site's own search results and redirects to a page
  already read no longer use up the 12-page budget.
- **Failed re-reads:** a re-read that gets no page never replaces a good read.
- **A test time bomb:** CR 71's recorded Duffel quote expired at 05:40Z today. The test now serves it unexpired; the expired case
  is still tested on its own.

## Tests

`agapi_service/tests/test_cr73.py` (25). On SQLite and Postgres, with the rest of the suite. The Docker build runs them.
They cover:
- **the vectors:** plan, drift, claim fingerprints, untrusted;
- **the export:** read-only, the 20 cells, no internal prose;
- **claims:** every loaded fact is a cited claim; no claim means unknown; reloading is idempotent; a new snapshot supersedes, never edits;
- **the operations:** their errors and schemas;
- **the Austrian plan:** honest about robots and accounts;
- **rails:** withdrawn rails; never-fetch hosts are never requested;
- **verify:** fresh / drifted / broken / unreachable, and the host budget;
- **the reader:** robots first, challenge pages and site search skipped, values only in the model's vocabulary;
- **the page.**

## Next (not in this CR)

- **AD-side tables:** EU 214's draft SQL for chat (`registry_*` beside the catalogue) and the `catalogue_cells_v2` shadow view. Nothing
  in AD reads this until M4 (`ad-hookup.md`).
- **Drift schedule:** `registry.verify` per route every 30 days (`reverify_after`), within the host budget.
- **Wave 0's lapsed 10** (BE CZ EE HR NO PL SK, US-CO CT NY): re-certify or delist (Tyler).
- **Then wave 1** (`coverage-plan.md`).
