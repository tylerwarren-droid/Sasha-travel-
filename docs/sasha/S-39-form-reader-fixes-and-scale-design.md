# S-39 — The form reader fixed, proven on the pages that failed; and the 500-site measurement, designed

**Filed:** 30 September 2026. **Fixes built and tested in Applied Diligence; not committed. The measurement is
designed, not run.** SQL 005 is still unapplied: `railway login` has not been approved.

## 0. Blunt answer

- **All five fixes hold on the real pages that failed** (§2).
  - **Every wrong role from S-38 is gone.** On those pages, **17 of 17** role assignments are now correct.
  - Challenges are recognised and stop the run.
  - Casa Lucas reports *"slot must be chosen first"*.
- ⚠ **Those pages are no longer never-seen.** The fixes were made looking at them. **The honest rate needs the
  500-site run (§3), with the vocabulary frozen before it starts.**
- ⚠ **A correction to S-38:** labuganvilla's `field_5` is **not a honeypot**. It has its own `<label for>`, and the
  site itself labels it *"Comentario Nombre Correo"* on one page and *"mensaje electrónico Nombre"* on another. The
  real failure was guessing from a label that names three things. It is now **unknown**, by rule.
- **The scale run** has four parts:
  - the venue list from **Overture Places** (open data; the seeder `scripts/overture-seed.ts` exists and has never
    run);
  - the fetch as **a one-off Railway service**. ⚠ `railway run` executes **on this machine**, from the home IP, so
    it is **not** that;
  - the analysis offline, here, over the stored pages.
  - **About $1, about an hour on Railway, and 1 day to build**, plus 1–2 hours to label the truth (§3.4).

## 1. The fixes (Applied Diligence, uncommitted)

| # | the founder's fix | what was built |
|---|---|---|
| 1 | **hidden / trap fields never mapped or filled**; **own label only** | `form-map.ts` records `trap_signals` for each field: its **own or its container's** inline style hiding it (display:none, visibility:hidden, off-screen, zero-size, opacity 0), `tabindex=-1`, `aria-hidden`, or a honeypot-like name, id or class. A trap is never mapped and is listed under `never_filled`. **Roles come from the field's own label only** (`<label for>`, aria, a wrapping label, its placeholder or title). **Text that merely precedes a field is not its label**: the field is reported **unlabelled**, and its role, if any, comes from its **name or id**. An own label naming things from different groups (a name **and** an email **and** a message) is **unknown**, never a guess |
| 2 | **consent recognised; whole words only** | a checkbox is `consent` (acepto / privacidad / Datenschutz / stimme… zu / policy…) or `unknown`, **never one of the six**. **Every vocabulary word is bounded by `\b`**: "personen" no longer matches inside "personenbezogenen" |
| 3 | **split names as a pair** | a bare *Nombre / Name / Nome / Vorname* beside a surname field becomes the **given** name. `name_parts` reports `{given, family}` or `{full}`, and `found.person_name` is the pair |
| 4 | **challenges → CHALLENGE; she stops** | reCAPTCHA, hCaptcha and Turnstile response fields, any `<noscript>` fallback, and questions in the field's label **or the text beside it** (*"Spamschutz: 88 + 3 ="*, *"¿cuánto es"*, *"are you human"*, *"not a robot"*) are `challenge`. `challenges[]` is non-empty, so **the run stops and the step is handed to the guest**. ⛔ Never solved, never read back as something Sasha fills |
| 5 | **the wizard as its own state** | `slotFirst(html, maps)` returns *"slot must be chosen first — the WordPress Booked calendar and a month grid of date cells; its fields arrive only after a date is picked"*. It is not a failure, and not a form |

- **Kept additive:** `form-map.ts` still derives `preceding_text` labels for the **register** maps; only the booking
  vocabulary refuses them. The new fields are optional, so maps written before S-39 still read.
- **Tests:**
  - `booking-roles.test.ts` gains 22 checks, one or more per rule, on **synthetic** forms (no captured page enters the
    repo);
  - the existing Getink check was updated, because *"Attachments"* is text before the file input, now read back as
    an unlabelled field;
  - AD `npm test`: **ALL PASS, 133 files**; `tsc --noEmit` 0; eslint clean on the three files.

## 2. Proof on the pages that failed (offline, the pages saved in S-38; no new fetch)

| page | S-38 | now |
|---|---|---|
| **apne2** reservierung | 6/6 roles, but **two consent checkboxes → party**, a garbled label, and the spam question unrecognised | **6/6 roles, 0 wrong.** The fields are reported **unlabelled** (its labels are table text before each input), with roles from `nachname`, `email`, `telefonnummer`, `personenzahl`, `datum`, `uhrzeit`. The consent box is **consent**. *"Spamschutz"* is a **CHALLENGE → stop**. The *Kopie* checkbox is unknown |
| **labuganvilla** (home + contacto) | *"Comentario Nombre Correo"* → **email**; *Nombre* → a **full** name | *"Comentario Nombre Correo"* and *"mensaje electrónico Nombre"* → **unknown** (the label names a message, a name and an email). *Nombre* + *Apellidos* are a **given + family pair**. The privacy checkbox is **consent** |
| **gurulab** | the reCAPTCHA box → free text | **CHALLENGE → stop** (by its name `g-recaptcha-response`, and because it sits in `<noscript>`) |
| **Casa Lucas** | "no form" | **slot must be chosen first**: the Booked calendar plus a month grid of date cells |

## 3. The scale measurement: about 500 venue own-domain sites. Designed, not run

### 3.1 The venue list

1. **Overture Places** (CDLA Permissive 2.0 / Apache 2.0, a public S3 dataset), queried with the existing seeder
   (`scripts/overture-seed.ts`, which refuses a bounding box without a named source and never runs without `--run`):
   **food and drink categories** in **Madrid, Lisbon and Berlin**, with a non-empty `websites` field.
2. **Own domain only.** The seeder's `classifyWebsite` drops social and aggregator hosts (Facebook, Instagram,
   TripAdvisor, Google, link-in-bio). **A booking platform's domain is dropped and never fetched**, using the
   registry's `PLATFORMS` plus `BOOKING_ENGINES` hosts. One site per registrable domain, so chains count once.
3. **A stratified random sample: about 170 per city, about 510 hosts.** The seed and the draw are recorded so the
   sample can be re-drawn exactly.
4. ⚠ **Expected yield**, from the registry's 2–4%: **about 10–20 booking forms**, plus some request forms. That is
   enough for a rate with a wide interval. **For ±10 points, plan about 1,000 hosts** (a second run, same design).

### 3.2 Where it runs, and the fetch

- **A one-off Railway service** in the Sasha project (start command `python -m booking_signer.measure_forms`). It runs
  once and exits.
  - ⚠ **Not `railway run`**: that executes locally, from the founder's home IP, which is the exposure the standing
    rule forbids.
  - The founder creates the service (or approves it). Its egress IP is Railway's.
- **Per host:**
  - `robots.txt` first; a disallow skips the host, and is recorded;
  - the home page, plus **up to 4 same-host pages** whose link says reserv / book / contact / tisch (the S-38 rule);
  - **served markup only, no rendering**, so no platform script or frame is loaded; iframes and scripts are recorded,
    never fetched.
- **Guards:**
  - **own host only**, redirects re-checked hop by hop, public IPs only (the S-36 guards);
  - **never a booking-platform host**;
  - 1 request per second per host, 10 hosts at a time, a 15-second timeout, a 2 MB cap;
  - a user-agent naming Sasha and a contact URL.
- **Stored:** each page's bytes with URL, time, status and sha256, in a **private** Supabase Storage bucket (or a
  Railway volume). **Never in a repo** (the kind rule).

### 3.3 The analysis (here, offline, over the downloaded pages)

- `extractFormMaps` + `bookingRoles` + `slotFirst`, at **the commit frozen before the run**, recorded in the report.
  **No tuning on this sample.** Madrid and Lisbon are the test set; Berlin may be used to develop fixes afterwards,
  never the reverse.
- **For each form:** roles mapped; roles wrong (with the field's own label); plain or wizard; slot first; challenges;
  traps.
- **Totals:** hosts read, refused by robots, unreachable; forms found; booking vs request forms; fully mapped; **the
  fraction of roles correct**; failure causes ranked.
- **Also counted:** hosts whose booking is a platform **embed** (from the served markup), which is the S-37 slot-link
  reach, measured at the same time.

### 3.4 Cost and time

| item | cost | time |
|---|---|---|
| Overture query (DuckDB range reads over 3 bounding boxes) | free; a few hundred MB of egress **from Railway or a server**, not the home network | 10–20 min |
| the Railway one-off service: about 510 hosts × (robots + about 3 pages) ≈ **2,000 requests** | cents of compute; egress ≈ 500 MB ≈ **under $0.10** | **20–40 min** of wall time at 10 hosts in parallel with per-host politeness |
| storage of the pages | negligible (under 1 GB) | — |
| building the job, storage and analysis script, with tests | — | **about 1 day** |
| **the ground truth**: labelling each found form's true roles from its markup, with evidence, as in S-38 | — | **1–2 hours** for 15–30 forms |
| **total** | **about $1** | **about 1 day to build, about 1 hour to run, 1–2 hours to score** |

### 3.5 What the founder does

1. Approve `railway login` (still pending), so SQL 005 and the Railway service can be set up from here.
2. Say go on building `measure_forms` and the one-off service.
3. After the run: nothing, until the report.
