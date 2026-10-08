# CR 53 · The Me's as Sasha's skills — design

**Design only.** No code and no deploys come with this document. Nothing here is built until the founder approves it.

Written 8 Oct 2026 from the code at `253bd22` (Sasha 208). It covers:
- the /next agent (`app/agent/sasha.py`, Sasha 203–205);
- AgAPI v0 (`agapi/v0.py`);
- the trip basket (`booking_signer/basket.py`, Sasha 198);
- the three products as they stand after CR 52 (`backend/products/`).

## 0 · The direction in one paragraph

Sasha is the one front door. CampusMe, RelocateMe and EspañaMe stop being separate interfaces with their own routers, buttons and step machines. Each becomes a **skill**: a named set of AgAPI tools that Sasha's agent uses only while that skill is open, plus a short skill card for her prompt.

The parts that are hard to get right stay exactly as they are today; they become the tools' back ends:
- reading a school's own calendar;
- filling the EX-01 box by box;
- each consulate's fees for one nationality;
- the SERMAS centre finder.

The rules that matter are enforced in code, never in the prompt:
- **nothing submitted for the person**;
- **statements and signatures are theirs**;
- **human steps happen on their phone**;
- **real identity documents stay fictional until the DPA is signed**.

Every result lands in the platform as a **journey item with a state**, in the same basket the trips use.

---

## 1 · Each product's flow as AgAPI tools

The four AgAPI roles keep their meaning:
- **Magellan** finds;
- **Sherlock** reads and checks;
- **Austen** acts, always idempotent, and never past the person's own last step;
- **Pacioli** records and is the only source of status.

Every tool runs for **one account** (`Ctx.account`) and returns the honest error shape `{ok:false, error:{code,message}}`. Every fact-bearing result carries `sources: [{label, url, read_at}]`, so rule 4 of CR 52 ("one link, behind Sources") holds on every surface.

### 1.1 Skill `campus` (CampusMe)

| Tool | Role | What it does | Back end reused | Guards in code |
|---|---|---|---|---|
| `find_schools` | Magellan | Names → the school records (aliases, visit pages), or "unreadable" with the reason | `campus/schools.py` (`find_schools`, `unreadable_named`) | robots first; AI-forbidding or bot-walled sites return `site_refuses_agents` and the link |
| `find_visit_sessions` | Magellan | One school, one week → its real sessions from its own calendar | `campus/slate.py` (`dates`, `sessions`, `parse_widget_list`), `campus/live.py` | only the school's own pages; never a guessed time — "check its page" plus the link |
| `plan_tour` | Magellan | Schools + week + where from → the day-by-day tour, drives checked with Google Routes, a night near each next school | `campus/tour.py` (`schedule`, `compact`, `lines`, `pdf`, `card`) | drive times only from Routes; rail "not checked" unless a timetable was read |
| `save_student` | Austen | The student's and family's details, asked once; kept in the vault only on a yes | `campus/request.py`, `relocation/keep.py` (`keepable`, `save`) | keeping needs `approval.said` (their words); vault encrypted and deletable |
| `prepare_registration` | Austen | One school's own registration form, filled in the cloud browser, **stopped before its Submit**; returns a phone hand-over link | `campus/live.py` (`open_campus_handover`, `open_tour_handover`), `booking_signer/handover.py` | no submit verb exists; every non-GET aborted; statement boxes never ticked; CAPTCHA, payment field or platform frame → `no_handover`; real students only under the founder override or the DPA, otherwise read-only with a fictional student |
| `check_confirmation` | Sherlock | The school's page after the person's Submit, or its email pasted in → matches school, student, day and time? | `campus/confirm.py` (`expect`, `read`, `line`, `record`) | "Registered ✓" only when every field matches; otherwise "not confirmed" plus what is missing |
| `get_campus` | Pacioli | The tour's items and their states | `campus/visits.py`, `products/agenda.py` | the only source for "registered" |

### 1.2 Skill `relocate` (RelocateMe)

| Tool | Role | What it does | Back end reused | Guards in code |
|---|---|---|---|---|
| `read_passport` | Sherlock | A passport photo or PDF → the MRZ checked, the facts with their source | `relocation/docread.py` (`on_media`, `mrz_check`, `to_facts`) | **real identity documents: not stored without the DPIA**; until then fictional only (`DEMO`); founder override as today |
| `ask_missing` | Sherlock | What the form still needs from this person, as questions | `relocation/facts.py` (`questions_for`), `ex01.py` (`rows`, `counts`) | asks only what applies to this case (CR 52 rule 2) |
| `prepare_form` | Austen | `form ∈ {EX-01, visa_national, 790-052, 790-012, TA.1, EX-17}` → the filled official PDF, a highlighted card, and "N boxes filled, M left for you" | `ex01.py` (`fill`, `read_back`), `visa_form.py`, `three.py` (`fill_790`), `arrival.py` (`fill_ta1`, `fill_ex17`, `p790_012`) | never signs or ticks; the signature and declaration boxes are always in "left for you"; the forms are filled exactly as today, byte for byte — gate-tested |
| `consulate_route` | Sherlock | Country / state / county → the consulate, its fees **for this nationality only**, how it books (email draft or URL), its own document list | `relocation/consulates.py`, `three.py` (`fees`, `booking_messages`, `page_consulate`, `which`) | figures only from the consulate's page as read (`consulates_read.json`, sha kept); the email is a `mailto:` the person sends — **never sent by us** |
| `build_pack` | Austen | What they've gathered → the pack PDF in the consulate's order, prepared items marked "you sign it" | `three.py` (`pack`), `consulates.py` (`pack`, `checklist`), `package.py` | — |
| `check_file` | Sherlock | The whole file as a consular officer would read it → flags | `checker.py`, `officer.py` | flags only; never "approved" |
| `set_entry_date` | Austen | The entry date → the deadlines and reminders | `after.py` (`reminders`, `due`), `move.py` | reminders follow WhatsApp's 24-hour rule, said once |
| `after_arrival` | Sherlock | Padrón → EX-17 + 790-012 → TA.1 → health card, as items | `arrival.py` (`present`, `step`, `refresh`) | — |
| `get_relocation` | Pacioli | The file, its forms, deadlines and states | `relocation/package.py`, `journeys._relocation_forms` | the only source for "signed", "lodged" and "ready" |

### 1.3 Skill `espana` (EspañaMe)

| Tool | Role | What it does | Back end reused | Guards in code |
|---|---|---|---|---|
| `read_dni` | Sherlock | DNI/NIE photo → TD1 MRZ checked, the facts | `health/tarjeta.py` (`mrz_td1`, `checks`, `from_read`, `read_back`) | same identity-document rule as `read_passport` |
| `prepare_1449F1` | Austen | The health-card application (Comunidad de Madrid 1449F1) filled; "left for you" listed | `tarjeta.py` (`fill`, `rows`, `split_address`) | never signs; consent below must already be on file |
| `find_centre` | Magellan | Address → their centro de salud, from SERMAS's own finder | `health/cita.py` (`centre`, `find`, `candidates`, `municipalities`), `health/address.py` | the public site's own finder; never signs in on it |
| `cita_route` | Sherlock | How that centre gives an appointment (app, web, phone) → a link or a call script for the person | `cita.py` (`detail`, `card`, `call_prepare`, `gcal`) | **never books, signs in or presses on a public health website** for them |
| `es_areas` | Sherlock | Padrón, identity, social security, DGT, education: what applies to them, in a few lines | `health/espana.py` (`areas`, `short`, `card`), `espana_sources.json` | concepts only (as today); one "Official information: <link>" line |
| `get_espana` | Pacioli | The health card and cita items and their states | `health/status.py`, `journeys.health_card` | — |

**Consent, as a guard (EspañaMe):** before any `espana` tool touches health data, `record_consent` (Austen) must hold `approval.said`, the person's own yes in this turn. This works exactly like `book`'s `explicit_yes`, and the model cannot supply it. The consent text is the one shown today, word for word. Health data is kept for at most 30 days, and the reason for a doctor is never asked for.

### 1.4 What none of the skills has

There is **no tool for any of these**, in any role: submit, file, lodge, sign, tick a consent or statement for someone, create an account, send an email for them, or solve a CAPTCHA.

Because the verbs don't exist, the model can't call them. That is a stronger guarantee than a prompt rule. `tests/test_agapi_skill_guards.py` pins it by asserting no tool name or description in a skill matches `submit|file|lodge|sign|send|register` as an action Sasha performs.

---

## 2 · Entering and leaving; the phone; the platform

### 2.1 Strict spaces, as code (Sasha 194, unchanged in meaning)

A skill is **entered only by its own word or button**: "campus", "relocate", "españa", a product tab, or a tap on a skill button Sasha offers. **Code** decides that, not the model.

The agent turn gets a `skill` from the request:
- a tap carries `skill:<name>`;
- a typed line is matched against today's `START_WORD`;
- otherwise it is read from the account's stored current space (`products.web.current_space`, kept).

What each state means:

| State | Tools the model is given | What she says, once |
|---|---|---|
| No skill (Sasha) | travel tools only (Magellan/Sherlock/Austen/Pacioli for trips) + `offer_skill(name)` | When a request belongs to a skill she offers it with a button: "That's CampusMe's — shall we plan your campus tour?" **She cannot enter it herself.** |
| Skill open | that skill's tools + `plan_getting_there` (the skill's own trip hand-off) + all Pacioli reads | On entry, once: "Let's plan your campus tour." / "Let's get your residence file ready." / "Let's do your Spanish health card." |
| Leaving | — | Only "sasha" or the skill's Back button: "Back to Sasha — your tour is kept." |

Inside a skill, the model **cannot see** the other skills' tools or the general travel tools. "Book my flights" inside RelocateMe therefore goes through `plan_getting_there`, which pre-fills the journey's dates and place (today's `tp:go:relocation`). It never wanders into a fresh trip. In Sasha, "book my flights" never opens a skill.

The tool list is filtered in `tools_for_model(skill)`. Choosing the tool list in code makes strict spaces structural rather than a rule the model has to remember.

### 2.2 One step at a time (CR 52), kept

The skill card in her prompt carries CR 52's four rules:
- one step per message, one next button;
- only what applies to this person;
- about four lines;
- every fact sourced, behind "Sources".

The **tools enforce the parts that matter**:
- each Sherlock/Magellan result returns `{step, needs, next, details, sources}`, where `details` is what CR 52's `steps.stash` keeps behind "More";
- the UI renders `details` and `sources` collapsed by default.

A guard extends today's price check (`guard_check`):
- every **$, £ or € figure** must come from a tool result in this conversation;
- "registered", "submitted", "filed", "lodged" or "signed" may only be said when Pacioli has that item in that state.

A reply that breaks either is rewritten once, and the offending sentence is then replaced, as for prices today.

### 2.3 What goes on the phone

| Human step | How it reaches the phone | Who does it |
|---|---|---|
| A school's statement box + its Submit | `prepare_registration` → a hand-over link ("Tap to finish") sent to their phone (the same guest page as today) | the person |
| Signing a form | the filled PDF + "print, sign, reply SIGNED" | the person; "signed" is recorded **on their word**, labelled so |
| The consulate appointment email | a `mailto:` draft opened in their own mail app | the person sends it |
| A BLS / consulate / SERMAS online booking | the official page's link, the details to copy behind "Copy my details" | the person |
| The cita phone call | a call script, or Sasha's phone rung only where today's rules allow (never a public health line) | the person, or as today |
| Reminders before deadlines | WhatsApp within its 24-hour window; otherwise waiting on the file page | — |

The agent stream gets one new event, `{"type":"phone","kind":"handover|pdf|mailto|link","url","why"}`. The web shows it as a card ("Sent to your phone"), and on WhatsApp it is the message itself.

### 2.4 How each lands in the platform: journey items with states

**Recommendation: extend the trip basket rather than add a second table.** One journey (a `trips` row, as today: "Campus tour, Nov", "Move to Madrid", "Madrid health card") owns its items in `trip_basket_items`. New `kind` values, each with its own allowed states and a single writer (Pacioli's record functions):

| kind | States (→ order) | Who moves it |
|---|---|---|
| `visit` | `suggested` → `prepared` (form filled, hand-over sent) → `registered` (school's confirmation matched) · `not_confirmed` · `cancelled` | `check_confirmation` only, for `registered` |
| `form` | `to_prepare` → `prepared` (PDF ready, M boxes left) → `signed_by_you` (on their word) → `lodged_by_you` (on their word, with date) | Austen for `prepared`; the person's own words for the last two |
| `cita` | `centre_found` → `route_given` → `booked_by_you` (on their word or a pasted confirmation) | the person's words / Sherlock read |
| `deadline` | `upcoming` → `due` → `done` · `missed` | the date; `done` on their word |
| `document` | `missing` → `gathered` · `prepared` (by us; you sign it) | `build_pack` |

The platform's journey tabs (`journeys.journeys`, Sasha 177) then render the basket for these kinds the same way as for flights and stays:
- one row each, with its state badge and its source;
- the ✕ removes only a `suggested` or `to_prepare` row;
- nothing past "prepared" is ever removed by us.

Today's `journeys.product_rows` (read-only agenda rows) is replaced by these real rows.

---

## 3 · Reused vs retired; tests; partner white-label

### 3.1 Reused, as the tools' back ends (unchanged)

These are about 70% of `backend/products/` by lines:
- **campus:** `slate.py`, `schools.py`, `confirm.py`, `visits.py`, `live.py`, `handover.py`, `request.py`, `watch.py`;
- **campus `tour.py`:** the planning half (`schedule`, `compact`, `lines`, `pdf`, `card`, `as_trip`);
- **relocation:** `docread.py`, `facts.py`, `ex01.py`, `visa_form.py`, `consulates.py`, `checker.py`, `officer.py`, `package.py`, `move.py`, `keep.py`, plus the fill and fee functions of `three.py`, `arrival.py` and `after.py`;
- **health:** `tarjeta.py`'s read, check and fill; `cita.py`'s centre, find, detail, card and gcal; `address.py`; `espana.py`; `status.py`; `sources.py`;
- **shared:** `formcard.py`, `agenda.py`, `itinerary.py`, `products/store.py` (cases), the vault, and `booking_signer/handover*.py`;
- **all the official PDFs and the reads with their sha256** (`consulates_read.json`, `espana_sources.json`, the field maps).

### 3.2 Retired, but only after the agent also serves WhatsApp

The agent at /next is web-only and takes no photos yet. Until both change, WhatsApp keeps today's flows, so **nothing is retired in the first phases**. Once the agent covers both channels, these go:
- the conversation routers: `campus/turn.py`, `relocation/turn.py`, `health/turn.py`;
- the step machines: `tour.on_message`, `after.on_message`, `three.present` / `walk`, `arrival.step`, `tarjeta.on_*`, `cita.on_*`;
- the `claims` / `context` functions;
- `products/steps.py`, whose job moves into the tools' `details`;
- `products/web.py`;
- the product half of `products/whatsapp.py`: `PREFIX`, `_resume`, `_say_back`, the strict-space branches, and the CR 13 trip hand-off. `booking_signer/switching.py`'s space logic goes the same way, with spaces moving into the agent's `skill` state.

That is about 30% of `products/` by lines, plus the routing in `whatsapp.py`.

### 3.3 Tests

- **Kept and re-pointed at the tools:** the back-end tests:
  - fees per consulate and nationality;
  - EX-01 / 790 / TA.1 / EX-17 / 1449F1 fills, byte for byte;
  - consulate territories;
  - MRZ checks;
  - Slate parsing;
  - confirmation matching;
  - the centre finder.

  Today 313 tests in 33 files touch `products/`. I'd expect roughly half of them to be back-end tests of this kind; that's an estimate, to be counted file by file in step 7.
- **Retired with the routers:** the conversation tests that pin wording and buttons. These are `calm.py`'s presses and the conversation parts of the `test_*_cr*` files. They are retired only when the agent serves that channel.
- **New:**
  - `test_agapi_skill_guards.py`:
    - no submit/sign/send verbs exist;
    - `record_consent` and keeping need the person's own words;
    - identity documents are fictional-only without the DPIA flag;
    - robots-first refusals;
    - the $/£/€ figure guard and the "registered/lodged" claim guard;
    - each tool's account scope.
  - `test_skill_spaces.py`: tool lists per skill; entering only by word or tap; `offer_skill` cannot enter.
  - **Skill conversations** in `scripts/agent_suite.py`, like Sasha 203's ten. Each skill is walked start to finish on a scratch guest, which is deleted after, with assertions for:
    - one step per message;
    - ≤ 4 lines;
    - message counts no worse than CR 52's (RelocateMe 22, CampusMe 18, EspañaMe 16);
    - every item landing in the basket with the right state.
  - The deploy gate gets a **SKILLS** step that runs these.
  - CR 40's 45-phrase sweep becomes an agent sweep: the same phrases, with the expected skill and first tool.

### 3.4 Partner white-label: same engine, own name

The tenant layer (`app/services/tenant.py`: `ClientConfig` with `display_name` and a free `config` dict, resolved by hostname or API key) gains three settings, kept in `config`:
- `assistant_name` (e.g. "Ana" instead of "Sasha");
- `skills_enabled` (e.g. only `relocate`);
- `skill_names` (e.g. RelocateMe → "Move to Spain with Acme").

**What never varies by tenant:**
- the AgAPI contract;
- the guards in code;
- the official sources;
- the forms;
- the phone hand-over rules.

A partner that brings its **own** agent calls the same skills through AgAPI's REST/MCP surface (promised in v0's header), scoped to its accounts, with the same refusals. Journey items carry `tenant` so a partner sees only its own. The persona text (`sasha-persona.md`) is per tenant; the charter's hard rules are not.

---

## 4 · Steps and estimates

All estimates are working days for one tab, and nothing starts before approval. Each step ships behind /next only, with the deploy gate passing, and today's products stay untouched until step 9.

| # | Step | Estimate | Depends on |
|---|---|---|---|
| 1 | Agent prerequisites: photos/PDFs into an agent turn (for `read_passport` / `read_dni`); the `skill` state, entry by word or tap, the per-skill tool list, `offer_skill` | 2 d | — |
| 2 | Basket kinds `visit` · `form` · `cita` · `deadline` · `document` with their states and single writers; journey tabs render them | 2 d | 1 |
| 3 | The guards: no forbidden verbs, consent/keep need their words, identity fictional-only without the DPIA flag, $/£/€ figures from tools, claim words from Pacioli; the `phone` event | 1–2 d | 1 |
| 4 | CampusMe skill: 7 tools, skill card, renderers, scripted conversations | 3 d | 2, 3 |
| 5 | RelocateMe skill: 9 tools (6 forms behind `prepare_form`), skill card, renderers, conversations | 4 d | 2, 3 |
| 6 | EspañaMe skill: 6 tools + `record_consent`, skill card, renderers, conversations | 2–3 d | 2, 3 |
| 7 | Gate: the SKILLS step, the agent sweep, message counts against CR 52 | 1–2 d | 4–6 |
| 8 | White-label: `assistant_name`, `skills_enabled`, `skill_names`; tenant on journey items | 2 d | 4–6 |
| 9 | When the agent serves WhatsApp (the Sasha tab's track): retire the routers and step machines in §3.2, and the conversation tests with them | 2 d | agent on WhatsApp |
| | **Total** | **19–22 d** (about 17–20 before WhatsApp) | |

### Decisions for the founder

1. **Extend the trip basket** with the new kinds (recommended), or keep product items in a separate table.
2. **The order of the skills.** I'd do CampusMe first: it has the fewest tools, and its hand-over is already proven live on Penn.
3. **When the agent goes to WhatsApp.** Retirement waits for that; until then both paths run, and the deterministic one stays the WhatsApp path.
4. **Partner naming.** Can a partner rename the assistant as well as the skills?
