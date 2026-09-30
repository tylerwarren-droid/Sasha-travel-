# S-38 — Form recognition, measured on venues' own sites. Read only

**Filed:** 30 September 2026. **Nothing submitted, nothing called, no code changed. SQL 005 is still unapplied:
`railway login` has not been approved.**

## 0. Blunt answer

- **There is no scale to measure it at in Madrid and Lisbon.** Across the P807nk samples (36 Madrid, 34 Lisbon) the
  venues with **a booking form on their own domain** are:
  - **Psi**, the form the vocabulary was built on. So it is **not** a never-seen page;
  - **Casa Lucas**, a **wizard**: the WordPress *Booked* calendar serves **no fields until a date is clicked**
    (P803jr, re-confirmed today: `wp-content/plugins/booked` present, zero forms in the served page).
- **Every other own-domain form in both cities is a contact or "ask us" form**, not a booking form. That is three
  venues. The engine venues (CoverManager, TheFork, Spotlinker…) keep their fields **inside the platform's frame**. ⛔
  Reading those means fetching the platform's domain, so they were **not read, by rule**.
- **On the pages it had never seen** (4 hosts, 5 form instances, one of them a genuine Berlin booking form outside the
  sample): **15 of 20 role assignments correct (75%)**. The three failure causes are ranked in §4.
- ⚠ **n is small.** Own-domain booking forms are about 2% of venues (`registry.ts`: *"two dedicated booking forms in
  ~95 venue hosts"*). A real rate needs a larger sample of venues that have one.

## 1. What was read, and how

- **Fetched from this machine** (the founder's network) with **robots.txt read first**, the venue's **own domain only**,
  no rendering (so no platform script or frame loaded), and ⛔ **no booking-platform host**. Up to four pages per host:
  the home page plus same-host links saying reservas / contacto / reservierung.
- **Read with the S-29 vocabulary exactly as committed** (`form-map.ts` + `booking-roles.ts`). No retuning.

| host | city | pages | result |
|---|---|---|---|
| gurulabmadrid.com | Madrid | home | a contact form; the booking is a **CoverManager** embed |
| restaurantelalina.com | Madrid | home + 3 `/reservas-*` | a contact form on home; the three reservation pages are **TheFork** embeds (not read) |
| almagro.labuganvilla.es | Madrid | home, `/reservas/`, `/reservar/`, `/contacto/` | one **wpforms** contact form (the same form on home and contacto); reservations are **Spotlinker** (not read) |
| casalucas.es | Madrid | home | **zero forms**: *Booked* calendar. **Wizard; a slot must be picked before any field exists** |
| hotel-mundial.pt | Lisbon | — | **not read**: the connection was refused at robots.txt |
| restaurant-apne2.de | Berlin (**outside the sample**; the only unseen genuine booking form in the corpus) | home, kontakt, reservierung | a **plain booking form** |

Saved pages and full output: scratchpad `s38/` (`fetch-log.json`, `roles.json`). Captured HTML stays out of every
repo (the kind rule).

## 2. Per form

| form | plain / wizard | slot first? | roles mapped correctly | wrong (with the field's own label) |
|---|---|---|---|---|
| **gurulab** contact | plain | no | name, email, phone (3/3). Date, time and party are **absent**, and reported so (`request_form`) | none among the six. ⚠ the **reCAPTCHA response** textarea (*"Aquí la respuesta de reCAPTCHA"*) was read as `free_text`, **a challenge not recognised as one** |
| **lalina** contact | plain | no | name, email (2/2) | none |
| **labuganvilla** contact (home) | plain | no | surname (*Apellidos*), email (2/4) | *"Comentario Nombre Correo"*, a **wpforms honeypot** (`field_5`, unlabelled; the label was stitched from neighbouring text), read as **email**; *"Nombre"* (wpforms `name-first`) read as a **full** name beside a separate *Apellidos* |
| **labuganvilla** contact (contacto) | plain | no | surname, email (2/3); the honeypot correctly `unknown` | *"Nombre"* as a full name (as above) |
| **apne2** booking (Berlin) | **plain** | no | **all six**: *Datum*→date, *Uhrzeit*→time, *Personenzahl*→party, surname (`nachname`)→name, *E-Mail*→email, *Telefonnummer*→phone (6/6) | **two consent checkboxes** (*"Ich stimme der Nutzung meiner personenbezogenen Daten…"*) read as **party size**. The surname's label came out garbled (*"…Bitte beachten Sie hierzu unsere u.a. Datens…"*), so the read-back would have said nonsense. ⚠ An **arithmetic spam check** (*"Spamschutz: 88 + 3 ="*) was `unknown`: correctly not guessed, but **not recognised as a challenge** |
| **Psi** (seen) | plain | no | 6/6 (S-29) | — |
| **Casa Lucas** | **wizard** | **yes** | — (no fields served) | — |

## 3. Totals

| | count |
|---|---|
| venues in the Madrid + Lisbon samples | 70 |
| **own-domain booking forms** | **1 plain (Psi, seen) + 1 wizard (Casa Lucas, no fields)** |
| own-domain contact / request forms read | 3 venues, 4 page instances |
| engine embeds not read (platform domain) | the rest with an engine (P807nk: 18 Madrid, 13 Lisbon) |
| **fully mapped, never seen** | **0 in the sample** (no unseen booking form exists there). Outside it: apne2, all six right **plus two wrong extras** |
| **roles correct on never-seen pages** | **15 of 20 = 75%** (with the duplicated labuganvilla form counted once: 13 of 17 = 76%) |

## 4. The three most common failure causes, ranked

1. **Label derivation** (`form-map.ts`), 2 of the 5 wrong, plus a garbled label on a correct one. Unlabelled or
   CSS-positioned fields take their label from **neighbouring text**. That turned a **honeypot** into "email", and it
   would make the read-back **say nonsense aloud**. ⚠ It is the dangerous one: filling a honeypot marks the request as
   spam.
2. **Vocabulary false positives on consent text** (`booking-roles.ts`), 2 of 5. `personen` inside
   *personenbezogenen* ("personal data") matched **party**. A checkbox should never take party, date or time, and
   party words need word boundaries.
3. **Split names**, 1 of 5 (twice). A bare *Nombre* next to *Apellidos* is a **given** name. The rule reads it as a
   full name, so the read-back would put "Anna Johnson" in *Nombre* and "Johnson" in *Apellidos*.

**Also seen, and not ranked** because it produced no wrong role: **challenges are not recognised inside forms**. That
means a reCAPTCHA response field and an arithmetic spam question. The helper's challenge detector looks for widget
frames and misses both. Both must **stop** the run, not just be read back.

## 5. What would move this

**Fixes, each small, and each shown by a test from today's pages (pages stay out of the repo; derived maps only):**
- a checkbox is never date, time or party; `\bpersonen\b`;
- *Nombre* / *Vorname* / *Prénom* beside a surname field → given name;
- a field whose only label is neighbouring text, with no `for`, `aria-label` or placeholder → **unknown**, never
  guessed. Honeypot signals (`wpforms` `field_…` with no label, off-screen, `tabindex=-1`) → **stop**;
- challenge recognition: `g-recaptcha-response`, and arithmetic questions ("Spamschutz", "¿cuánto es", "3 + 4 =")
  → `challenge`, which stops.

**A real rate needs venues that have own forms.** At about 2%, that means reading about 500 venue sites to find about
10. The honest next sample is **Overture's venues with a website** in Madrid, Lisbon and Berlin, read the same way
(robots first, own domain only). Several hours of fetching, from a server rather than this network.
