# CR 1 — demo run of show: CampusMe and relocation on WhatsApp (Wed 7 Oct)

*One sandbox number serves Sasha, CampusMe and relocation, by mode. Production needs one number per product
(`CR-1-spec.md` §1), so say so if asked.*

## Before the day — one command each (from the founder's Mac)

```
bash ~/Developer/Sasha-travel-/backend/scripts/cr1_demo.sh health      # must say "store":"postgres"
bash ~/Developer/Sasha-travel-/backend/scripts/cr1_demo.sh rehearse    # the whole demo, WhatsApp CAPTURED (nothing reaches a phone), timed
bash ~/Developer/Sasha-travel-/backend/scripts/cr1_demo.sh reset       # back to the start: CampusMe + relocation + health (or name one)
bash ~/Developer/Sasha-travel-/backend/scripts/cr1_demo.sh reset all --vault   # also forget the saved student details
```

- **Run `reset` before going on stage, and between run-throughs.** The first run sets itself up, which takes about a minute.
- ⚠ **Whose account:** the founder's WhatsApp is linked to the **demo account** (`11111111…`). `FOUNDER_ACCOUNT_ID` isn't
  set on Railway, so the founder acts as the demo account. `reset` says so when it runs. `rehearse` uses the same
  account, with WhatsApp captured in memory, so run `reset` after rehearsing.
- **Vault, first time or second:**
  - `reset all --vault` → CampusMe asks the five student questions (≈ 40 s more), then offers "Keep in your vault?";
  - plain `reset` after one run → straight to the read-back from the vault.
- Re-join the Twilio sandbox from the demo phone the day before (it expires after 3 days).
- **Put the specimen photo on the demo phone:** AirDrop `docs/products/specimen/NL-passport-specimen-2014-RvIG-CC0.jpg`
  (the RvIG's published specimen, a fictional holder, CC0). Never use a real person's passport on stage.
  - Expect the read-back to flag **the surname** (the printed "De Bruijn e/v Molenaar" vs "DE BRUIJN" in the MRZ) and
    **"this passport has EXPIRED"** (9 March 2024). Both are true, and both are good honesty beats.
- ✅ Done in CR 2: 028 applied, backend on Postgres, `ANTHROPIC_API_KEY` present on Railway, the photo read proven live on
  the published RvIG specimen (`docs/products/specimen/`).
- Optional: `CAMPUSME_WATCH_LOOP=1` on Railway for the daily "April opens" read.

## Timings (rehearsals 3 and 4, 3 Oct; "room" = compute + 3.1 s per sandbox message)

| Beat | Room waits | Note |
|---|---|---|
| C1 April → "not published" | 15 s | the Yale and Penn reads in parallel |
| C2 November → cards | 23–24 s | the slowest beat: Penn costs 3 paced reads; "Reading…" goes out first, so talk over it |
| C3 pick → read-back | 7 s (vault) / 22 s + 13 s (five questions + keep) | |
| C5 yes → prepared | 11–12 s | re-reads the session, opens the vault, reads Yale's form |
| C7 REGISTERED | 9 s | |
| R1–R4 relocation intro | 19 s | |
| R5 specimen photo → read | 14–18 s | the model call is 5–9 s |
| R8 DEMO → prepared | 16 s | 5 messages, including the PDF |
| R11–R13 signed → consulate → reminders | 27 s | |
| **Whole demo** | **≈ 2 min 50 s (vault) – 3 min 15 s (fresh)** | plus talking |

Transcripts: `docs/products/rehearsals/`. 3a FAILED: the same session asked twice reused one approval hash, so the vault
refused a second use. Fixed by giving each read-back its own "Ref CM-…". The rest passed after the fixes.

## Public example pages (for the site; never reset; fictional people; kept until 31 Dec)
- CampusMe: https://project.kanoe.ai/campus-handover/vuvpvu6fG71M5b_rxtEsag
- Relocation: https://project.kanoe.ai/relocation-file/KZjdXS_8HLk5I9nW76SW_A

## Part 1 — CampusMe (≈3 min)

| Send | What comes back | Say |
|---|---|---|
| `campus visits at Yale and Penn in April for my son` | "Reading Yale and Penn's own visit calendars for April 2027…" → **"Yale hasn't published April 2027 yet — its calendar runs to 30 November 2026. I'll check it daily and message you the day April opens."** (and the same for Penn) | *"It reads the school's own calendar, and when there's nothing there, it says so. No invented slots."* |
| `campus Yale and Penn in November for my son` | ONE message of numbered cards (Yale Campus Tour, Sun 1 Nov, 11:30 AM, "64 spaces left" · Penn Morning Information Session…) + "Read just now from apps.admissions.yale.edu, key.admissions.upenn.edu" + "Reply with a number, 1–4" | 8 of 10 top schools run Slate. One reader with two variants covers them |
| type **1** | first time: five questions (name, email, birth date, school, graduation year) → "Keep them in your vault?". Second time: the vault line | the vault opens only inside the yes |
| — | **"Exactly what I'll do:"** the session as read, *"…stop before its Register button: you press it. I send nothing to Yale."* + *"Registering creates a record for the student in Yale's admissions system"* | **one yes**, hash-bound |
| **Yes, prepare it** | "✅ Prepared … filled from your vault" + the link | — |
| open the link | the hand-over: Yale's own form, question by question, each answer with **"from: your vault"**, statements marked **"yours to tick"**, "Open Yale's registration page ↗" | *"Nothing is submitted. A person presses. That's the founder's model."* |
| `REGISTERED` | "registered on your word" + Google Calendar link + .ics; it's in "You → My bookings" | paste a confirmation that **doesn't** name the day → it stays "on your word" |

⛔ **Founder's decision (CR 2): no real registration in this demo. The hand-over page IS the demo.** Don't press
Register on the school's page.

## Part 2 — Relocation (≈4 min)

| Send | What comes back |
|---|---|
| `relocation` | "…*You* sign it and *you* lodge it: I never file anything…" → "first application or renewal?" |
| `first` · `me` · `myself` | the questions start: "Your passport number?" |
| `book me flights to Madrid on 1 March` | **CR 10 · one Sasha, not rooms:** Sasha's own flight answer, in the same chat (no "say EXIT" — there's no wall) |
| `relocation` | "Back to your EX-01. Your passport number?" — exactly where it was |
| a **SPECIMEN** passport photo | "Reading your passport photo page… It goes to Anthropic's AI model to be read, once; I don't keep the photo." → **"I read: • Passport number: … ✓ (the passport's own check digit agrees)"** → Yes → "Kept 8 values…" |
| *(or)* `DEMO` | the rest filled with the **fictional** Ana Ejemplo Prueba, marked as such everywhere |
| answers… | "✅ Your EX-01 is prepared: 31 boxes filled… 8 left for you" → reviewer link + **the official PDF in the chat** |
| open the link | the reviewer screen: 96 fields, every value "from: …". The reviewer agent: e.g. **"postcode 08010 is in Barcelona, but the province written is Madrid"**, **"“3º B” may not fit this box on paper"**. The signature box reads **"LEFT FOR THE APPLICANT — NOT SIGNED"** |
| `SIGNED` | "signed by you, on your word. I didn't sign or tick anything" → "Which country do you live in?" |
| `UK` | "*Consulado General de España en Londres*. Its own sheet says: 'Applicants must request their appointment following the instructions on the Consulate's website' → link. You book it and go in person." + the checklist (11 items from the consulate's sheet, **dated 11 Feb 2022**, said as such; the passport's ≥ 1 year **computed**) |
| `1 2 3` | **CR 12 · the document pack**: each document named and numbered in the sheet's own order ("01_…"), gathered ✓ / still to gather ☐ |
| `1 March 2027` | reminders: apply from 1 Dec (the 90-day window); the TIE within a month of entry, with the official *cita previa de extranjería* page. The reminders are listed in "You → Reminders" |
| `consulate booked 12 November 10:00` | "Added to your itinerary: your consulate appointment … — booked by you. I'll remind you the day before". It shows in "You → My bookings", like any booking |

**The honest lines, if asked:**
- *"Do you file it?"* — No. Never, by design. The fill refuses to touch the signature, consent or intent boxes.
- *"Is the checklist current?"* — It's the consulate's own sheet, dated 2022; the screen says so. A consulate we haven't
  read gets no link.
- *"Pre-filled cita previa?"* — Neither the consulate's nor the Extranjería system takes a pre-filled link. We give the
  official page plus every value to copy. The person presses.

### Part 2b — An American moving to Spain (CR 12, ≈1½ min; rehearse alone with `cr1_demo.sh rehearse us --account founder`)

| Send | What comes back |
|---|---|
| … `DEMO` · `SIGNED` → `USA` | "Which US state do you live in? … I match yours from the consulate's own page, never a guess." |
| `New Jersey` | "*Consulado General de España en Nueva York* — its own page (dated 23 de marzo de 2022) names New Jersey." Its route in its own words: an appointment request by **email** → "I've drafted that email in Spanish … you send it from your own address … I never send it." Its own 10-item list on the file page |
| `1 3 4 6-8` | the **document pack**, in New York's order: `01_National-visa-application-form` ✓ … `05_Proof-of-economic-means` ☐ still to gather — with its words on originals and copies |
| open the file page | the drafted email (To / Subject / the lettered lines, passport number left *[to fill]*) with "Open it in your email app — you press Send"; the pack; the source page and its read date |
| `1 March 2027` | one reminder: the TIE within 1 month of entry — the only date New York's page gives (no 90-day window: it doesn't state one) |

**The honest lines, if asked:** *"Other US consulates?"* — Seven of eight read on 3 Oct 2026. Only New York adapts the
ministry's text; Washington, Los Angeles, Miami, Chicago, Boston and San Francisco publish the template with "Lugar de
presentación" empty — Sasha says so and gives no route. Houston's site answered 503 twice: no list from it. California is
split by county exactly as Los Angeles's page lists them. (docs/products/reads/us/READS.md)

### Part 2c — The products and Sasha's travel, together (CR 13, ≈3 min; rehearse with `cr1_demo.sh rehearse trip --account founder`)

| Send (after the relocation file is signed, the entry date given) | What comes back |
|---|---|
| `book my flights` | "Which city will you fly from? (asked once …)" |
| `London` | the plan: ✈ flights London → Madrid on the entry date · 🏨 3 first nights near the new address · 📋 one itinerary — then **Sasha's own** Duffel TEST cards; her read-back and her one yes as always (TEST checkout) |
| `NEXT` | Sasha's hotel search near the new address, 3 nights — TEST booking or a real request, her choice buttons |
| `NEXT` | 📋 one itinerary: every booking (flights, hotels, appointments, visits) and every document deadline, by day |
| (two campus visits registered) `plan the trip around the visits` → `Chicago` | ✈ into New Haven the day before Yale · 🏨 near each campus the night before · 🚗 "Yale Sun 11:30 → Penn Mon 09:30: yes, 3 h 36 by car" (Google Routes, traffic-aware; rail not checked) |
| `what do I need to do this week?` | Sasha's week: her bookings and the products' deadlines together |

The same plan works in the web chat (same words; the Book it (TEST) buttons are the web's). Nothing is booked by the
products: each booking is Sasha's own flow, one yes each, TEST labels unchanged.

## Part 3 — Health, inside S-77's line (≈3 min)

**Before:**
- 029 applied.
- For a LIVE private-clinic call, on Railway for the demo window only: `SASHA_TEST_CALL_NUMBER` = the phone that will
  ring (the founder's own, standing in for the clinic) and `SASHA_CALLS_ENABLED=1`. Without these the beat says
  plainly "nothing to call / calls are off — nothing was dialled".
- Switch calls back off after the demo.

| Send | What comes back | Say |
|---|---|---|
| `health I need a doctor this week` | the consent: "only what the appointment needs — never why you need a doctor — at most 30 days; I never sign in, book or press on a public health website" → Yes | health data: Art. 9, minimum necessary |
| **1. Private clinic** → `Tuesday 10:00` | "Exactly what I'll say: … para reservar **una cita con el médico general** para una persona…" → **Yes, call them** | Sasha's own call path, one yes; the test clinic is the test line |
| — | "📞 Calling Kanoe Test Clinic now" → the phone rings, in Spanish (live only with calls on) | |
| `salud` → Yes → **2. Public (SERMAS)** | "I don't keep health card details yet — that needs Kanoe's data-protection assessment first" + the page | ⚠ honest: no DPIA, so no stored identifiers |
| `DEMO` | the hand-over with a **fictional** patient: the official SERMAS link, card code, date of birth, DNI/NIE ready to copy, "you press" | values come from the vault when the DPIA exists; gone after 24 h |
| `I booked it for 13 October at 10:00` → **Yes** | "Add … to your itinerary? It's then kept with your bookings like any other — not just 30 days" → "Added — booked by you" | added only on an explicit yes |
| `health` → Yes → **3. New in Madrid** | padrón → INSS (DAD) → tarjeta sanitaria → family doctor, each step from its official page; "I never hunt for padrón appointments" | |
| `20 October 2026` | reminders: the volante is valid 90 days | |

**Never:** sign in on SERMAS, submit, look for free slots, call a public health centre, ask why.

**Timings (rehearsals 6 and 7, on the founder's account, Bland faked in-process):** consent + choose 6 s · private →
read-back 19 s (call prepare ≈ 13 s) · yes → "📞 Calling" 9 s · SERMAS page 11 s, DEMO 7 s · new in Madrid 7 s + reminders 4 s.
Whole health part ≈ 1 min 45 s, plus talking. **All three parts: ≈ 4 min 45 s, plus talking.**

## Part 4 — The public sector: "we make citizens arrive complete" (≈1 min, CLICK-THROUGH)

Open **https://project.kanoe.ai/officer/vxgS8Ol0xgzR8D-kNaIk3Q**. Once the site hold lifts it's linked from the
Relocation tab: "For administrations: the case officer's queue (click-through) →".

| Show | Say |
|---|---|
| The banner: CLICK-THROUGH, fictional names | "These five people are invented. The form, the checks and the consulate's checklist are the real ones." |
| "5 applications — 4 need attention before they're assessed", sorted | what an administration, an NGO or a law firm sees: the same checks Sasha runs for the applicant, from the other side |
| Bruno: "postcode 08010 is in Barcelona, but the province written is Madrid", two documents missing | every line is the check's own words, or the consulate's checklist verbatim — no score invented, no percentage |
| Chen: the NIE fails its control letter; "3º B izquierda interior" won't fit the box | |
| Ana: complete — "8 left for the applicant (section 5, the Dehú consent, the signature) — expected, not a fault" | we never sign or declare for anyone |
| **Return to applicant with this list** → "See the message" | "It records the list; in this illustration nothing is sent." |

**Reset:** `bash ~/Developer/Sasha-travel-/backend/scripts/cr1_demo.sh reset officer`. It clears the "returned" marks;
the page stays.
**Rehearsed:** O1–O3 in rehearsals 8 and 9 (≈ 4 s). The rehearsal returns A-1042 and then puts the queue back as it
was. **All four parts: ≈ 4 min 55 s of waiting, plus talking.**

## Not shown, and why
- A real registration or a real filing: by design, until the founder decides.
- Relocation sections 2 and 3 (a family member's resources, a representative): not built. The file marks them "not
  your case".
- Consulates other than London: not read yet.
