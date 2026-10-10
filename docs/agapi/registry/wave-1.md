# Registry wave 1: the plan (EU 226, priority 5)

**What this is.** The design for registry wave 1, written so the US tab can run it right after AgAPI's repo cutover (US 123).
It is docs only: nothing was run, and nothing was written to AD.
**Inputs:**
- AD's catalogue (`jurisdiction_record_types`, read-only SELECTs, 10 Oct 2026);
- wave 0's reads (`agapi_service/registers/data/reads.json`);
- EU's `coverage-plan.md`;
- PLATFORM-V1 §7c.

## Where we start

| | |
|---|---|
| AD's catalogue | 2,526 checks in 215 jurisdictions. 78 cite a source page, 58 are person-verified, 20 are certified to run |
| Wave 0 (CR 73) | 19 jurisdictions read at source: 188 pages, 483 quoted facts, 10 catalogue rows found stale. **AI reading ≈ $3.54 in total, ≈ $0.19 a jurisdiction** |
| AgAPI today | `registry.*` operations; the claim store; CR 77's **source copies** (every page kept as read, with its sha256) and **Pacioli's auto-check** (verbatim, official domain, numbers in the quote, sha256) |

**The demand signal is thin, and that's said as it is.** AD's cases name only 6 jurisdictions (FR 8 requests, GLOBAL 5,
IE 3, AT/FI/DK 1), and all of them are in wave 0. So wave 1 is ranked on the other signals we actually have:
- **catalogue depth:** jurisdictions curated beyond the 12-row template;
- **rows marked available:** each country's count of rows marked available;
- **API availability:** rows with `has_api`;
- **AD's own interest:** `jurisdiction_certification_status` and `jurisdiction_check_results` rows;
- **EU/UK/US weight:** EU's coverage plan.

## 1 · Which: 30 jurisdictions

**Tier A: the deepest catalogue rows AD already uses (10).**

| # | Jurisdiction | Rows (avail / API / source page / verified) | Why |
|---|---|---|---|
| 1 | **GB** United Kingdom | 19 (13 / 7 / 6 / 3) | the most-used non-wave-0 country in AD: 10 check results, 4 certification rows, 7 API rows (Companies House et al.) |
| 2 | **US** United States (federal) | 26 (21 / 8 / 15 / 4) | 25 check results, the biggest catalogue entry, 15 source pages to confirm (SEC EDGAR, PACER, OFAC …) |
| 3 | **SG** Singapore | 18 (13 / 4 / 6 / 0) | curated beyond the template, 4 APIs (ACRA). A wave-2 pilot country in EU's plan, pulled forward because its rows exist |
| 4 | **AU** Australia | 18 (13 / 5 / 6 / 0) | curated, 5 APIs (ASIC, ABN Lookup), a certification row, 1 check result |
| 5 | **HK** Hong Kong | 17 (12 / 1 / 6 / 0) | curated, a certification row. A wave-2 pilot in EU's plan |
| 6 | **NO** Norway | 12 (6 / 1 / 0 / 1) | EU's wave 1 (it lapsed in wave 0). 2 check results; Brønnøysund has an open API |
| 7 | **US-NY** New York | 1 (1 / 0 / 1 / 1) | a US state AD has a row for and a certification row |
| 8 | **US-CO** Colorado | 1 (1 / 0 / 1 / 1) | as above |
| 9 | **US-CT** Connecticut | 1 (1 / 0 / 1 / 1) | as above |
| 10 | **US-FL** Florida | 1 (0 / 0 / 1 / 0) | the only other US state AD has a row for (Sunbiz), currently not available |

**Tier B: the rest of EU-27 (13).** This is EU's coverage plan for wave 1, unchanged.

| # | Jurisdiction | Rows (avail / API / src / verified) | Why |
|---|---|---|---|
| 11 | **IT** Italy | 12 (7 / 0 / 2 / 1) | EU's wave 1; 2 source pages to confirm (Registro Imprese) |
| 12 | **PL** Poland | 12 (7 / 1 / 0 / 1) | EU's wave 1; KRS has an open API; a certification row |
| 13 | **BE** Belgium | 12 (4 / 1 / 0 / 1) | EU's wave 1; KBO/BCE open data; a certification row |
| 14 | **PT** Portugal | 12 (7 / 0 / 1 / 1) | EU's wave 1; a source page |
| 15 | **CZ** Czechia | 12 (6 / 1 / 0 / 1) | EU's wave 1; ARES API; a certification row |
| 16 | **SK** Slovakia | 12 (4 / 1 / 0 / 1) | EU's wave 1; a certification row |
| 17 | **HR** Croatia | 12 (4 / 0 / 0 / 1) | EU's wave 1; a certification row |
| 18 | **EE** Estonia | 12 (4 / 0 / 0 / 1) | EU's wave 1; e-Business Register; a certification row |
| 19 | **LU** Luxembourg | 12 (7 / 0 / 1 / 1) | EU's wave 1; LBR; high diligence value (funds) |
| 20 | **GR** Greece | 12 (7 / 0 / 1 / 1) | EU's wave 1; GEMI; a Sherlock route already exists |
| 21 | **HU** Hungary | 12 (7 / 0 / 1 / 1) | EU's wave 1; next on the Sherlock order |
| 22 | **BG** Bulgaria | 12 (7 / 0 / 1 / 1) | EU's wave 1 |
| 23 | **RO** Romania | 12 (4 / 0 / 0 / 1) | EU's wave 1; ONRC |

**Tier C: the diligence hubs buyers ask about (7).**

| # | Jurisdiction | Rows | Why |
|---|---|---|---|
| 24 | **CH** Switzerland | 12 (7 avail) | Zefix (federal index + cantonal registers). It's the European hub outside the EU |
| 25 | **KY** Cayman Islands | 12 (7 avail) | top offshore centre (EU's wave 3 list, pulled forward: high diligence value per row) |
| 26 | **VG** British Virgin Islands | 12 (7 avail) | as above |
| 27 | **JE** Jersey | 12 (7 avail) | as above, and its register is open online |
| 28 | **GG** Guernsey | 12 (7 avail) | as above |
| 29 | **IM** Isle of Man | 12 (7 avail) | as above |
| 30 | **CA** Canada (federal) | 12 (7 avail) | Corporations Canada has an open search; it's the US buyers' next neighbour |

**Rows in scope: 354.**
- Tier A: 114 rows.
- Tier B: 156 rows.
- Tier C: 84 rows.

**Not in wave 1, said so:**
- **The 43 missing US states (and DC).** AD has no jurisdiction rows for them, and that includes Delaware, California,
  Texas, Wyoming and Nevada, the formation states buyers ask about most. EU's plan says these rows must be *created*
  first, which is an AD data change. They lead wave 2 once the rows exist.
- **BR, MX, KE, ZA:** EU's wave 2 pilots, kept there.

## 2 · Per row: what the run does

For each catalogue row (one jurisdiction × one record type):

1. **Re-read at the register's own site.**
   - The seeds are, in order: the row's `manual_process_url` / `api_documentation_url` when it is on the register's
     own domain, then wave 0's register seeds, then discovery (`discovery.md`) when neither exists.
   - **Robots first, and strict:** an HTML robots.txt counts as unreadable, which means not allowed.
   - **The register's own domain only.** Never a booking platform or an aggregator. AD's never-fetch list is honoured.
   - At most 20 pages a jurisdiction, about one fetch a second.
   - **Run on the server, never from a laptop.**
2. **Confirm five things, each with its quote and date read:**
   - the **document** (what you get);
   - the **price** (amount + currency, or "free");
   - the **turnaround**;
   - the **process** (steps, eID or account needed);
   - the **access method** (`api` / `web_form` / `human_only`).
3. **Keep the source copy** (CR 77): the HTML plus a rendered PDF, or the PDF itself, with its sha256 in the bucket.
   Every fact points to its copy.
4. **Pacioli's auto-check** on every fact:
   - (a) the quote is in the copy word for word;
   - (b) the copy is from the register's or government's own domain;
   - (c) every number, currency and deadline in the fact is in its quote;
   - (d) the copy's sha256 matches.
   Facts that pass are accepted as "checked by Pacioli". Any other fact is an **exception** on the review page.
5. **One verdict per row, compared with AD's current values:**

| Verdict | When | What it records |
|---|---|---|
| **verified** | every confirmed field matches AD's value (or AD had none and the source states it) | the facts + copies; AD's value stands |
| **changed** | a confirmed value differs from AD's | **old → new** per field (e.g. price `USD 15 → EUR 18.50`), each new value with its quote, date and copy |
| **gone** | the register says the document or service no longer exists, or the source redirects to a "discontinued" notice | the quote saying so + its copy |
| **unreachable** | robots-disallowed, a login/eID wall, a CAPTCHA/challenge page, 4xx/5xx, or no official page found | **why**, in plain words (never treated as "gone") |

**What the run never does:**
- solve a CAPTCHA;
- log in or create an account;
- submit a form;
- pay;
- read a third-party aggregator as if it were the register.

A row that can't be confirmed without one of those is **unreachable**, with its reason.

## 3 · Write-back

- **AgAPI's claim store is the only place facts are written:**
  - `registry_claims` (already there, one row per fact);
  - a new `registry_row_results` table: catalogue row id, verdict, the old → new field diffs, the copy ids and read_at.
- **AD reflects them through the shadow view** (`catalogue_cells_v2`, PLATFORM-V1 §7c / US 133).
  - AD reads the view next to its own columns.
  - A nightly diff lists every row where the two disagree.
  - AD's columns become **derived** only after 30 nights of zero unexplained diffs.
- **Nothing in AD is overwritten silently.**
  - Until US 133 is live, wave 1's output to AD is a **change list**: one line per `changed` / `gone` row with old → new
    and the source link.
  - A person applies it, or the view does once it is live.
  - `verified` rows update nothing in AD: they add the evidence (copy, date) the row lacked.
  - `unreachable` rows change nothing, and say why.

## 4 · Cost and speed

**Per country (wave 0 actuals, scaled to per-row confirmation):**

| | Wave 0 actual | Wave 1 estimate |
|---|---|---|
| Pages read | 9.9 per jurisdiction (cap 12) | **≈ 14 per jurisdiction** (cap 20: row-specific fee and process pages) |
| AI reading | $0.019 a page · $0.19 a jurisdiction | **≈ $0.30 a jurisdiction** (+25% for a second pass on `changed` rows) |
| Machine time | — | **≈ 6 min a jurisdiction** (fetch ≈ 1/s + rendering + Opus 2–4 min) |
| Copies stored | — | ≈ 14 originals + ≈ 12 rendered PDFs ≈ 15 MB a jurisdiction |
| Person time | 10 stale rows found in 483 facts | **≈ 4 min a jurisdiction**: Pacioli's exceptions + every `changed` / `gone` row read once |

**Wave 1 total (30 jurisdictions, 354 rows):**

| | Total |
|---|---|
| Pages | **≈ 420** |
| AI reading | **≈ $10** (budget $15) |
| Storage | ≈ 450 MB in the bucket, a few cents a month |
| Machine time | **≈ 3 h** run one after another; **≈ 1 h 15 min** with 3 jurisdictions in parallel (different hosts; each host still ≈ 1 fetch/s) |
| Person time | **≈ 2 h**: about 35 rows at ~10% `changed`/exception, plus a spot-check of 10 `verified` rows |
| Elapsed | **1 working day**, run in the morning and reviewed in the afternoon |

**What it tells us for waves 2–3**, to measure in wave 1 and re-size from the actuals:
- **The four numbers that set the size:**
  - pages per row;
  - $ per jurisdiction;
  - % of rows `changed`;
  - % `unreachable`.
- **Waves 2–3 cover 166 catalogue jurisdictions plus the 43 US states once created.**
  - Most are 12-row template entries with **no source page** (`src = 0`), so each one needs discovery first.
  - Expect ≈ 2× the pages, ≈ $0.40–0.60 each and more `unreachable`.
  - **≈ $80–110, ≈ 17–20 machine-hours, ≈ 15–20 person-hours**, split into:
    - **wave 2 (≈ 95):** the 43+DC US states; the remaining G20/FATF members (BR, MX, IN, JP, KR, ZA, AE, IL, NZ, CN,
      TR …); the rest of the offshore centres (PA, BS, BM, GI …);
    - **wave 3 (≈ 115):** the long tail.
- **If wave 1's `changed` rate is over 20%, cut a wave into smaller runs.** A full person review of every changed row
  is the bottleneck, not the machine.

**A lesson from today's CR 77 backfill:** a long read held open as one HTTP request hit Railway's proxy limit (502), and
the client then hung. **Wave 1 must run as a server-side job:**
- start it, then poll its status;
- one jurisdiction per task;
- resumable;
- never a 10-minute request.

## 5 · The US build prompt for wave 1 (one prompt, sized)

> **US — REGISTRY WAVE 1.** After US 123 (AgAPI in its own repo). Branches only, no secret printed, add never remove,
> robots first, register's own domain only, never log in / solve a CAPTCHA / submit / pay, nothing in AD overwritten.
>
> 1. **Row runner.** Add `registry.wave_run` (admin): a **server-side job** (start → status → resume). It takes a list of
>    jurisdictions and works one jurisdiction per task, ≤ 3 in parallel on different hosts. For each catalogue row
>    (AD's `jurisdiction_record_types`, read through the existing read-only export):
>    - seeds: the row's own URLs if they are on the register's domain → wave 0's seeds → `discovery.md`;
>    - read with CR 77's copies on;
>    - confirm document / price / turnaround / process / access method, each quoted;
>    - Pacioli's auto-check;
>    - give a verdict: `verified` / `changed` (old → new per field) / `gone` / `unreachable` (why).
> 2. **Store.** Add `registry_row_results` beside `registry_claims`: row id, verdict, field diffs, copy ids, read_at.
>    Add `registry.row_results` (read op, filter by jurisdiction / verdict). Add the review page's registry tab:
>    exceptions + changed + gone, each with "Download source".
> 3. **AD.** Write a change list for `changed` / `gone` rows (CSV + JSON, old → new + source link) until `catalogue_cells_v2`
>    (US 133) is live. Write nothing to AD's tables.
> 4. **Run** the 30 jurisdictions in docs/agapi/registry/wave-1.md:
>    - report pages, $, machine time and person time per jurisdiction and in total;
>    - report verdict counts and Pacioli pass/fail;
>    - re-size waves 2–3 from the actuals (§4).
> 5. **Tests:**
>    - fakes for every fetch and the reader;
>    - one test per verdict;
>    - an unreachable reason for each wall (robots, login, CAPTCHA, 4xx/5xx);
>    - change-list format;
>    - nothing written to AD;
>    - the suite on SQLite and Postgres.
>
> **Size: 5 engineer-days**:
> - 2 the row runner + the job model;
> - 1 storage + ops + the review tab;
> - 0.5 the change list;
> - 1 the run + its review;
> - 0.5 tests and the report.
