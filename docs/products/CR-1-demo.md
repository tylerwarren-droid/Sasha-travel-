# CR 1 — demo run of show: CampusMe and relocation on WhatsApp (Wed 7 Oct)

*One sandbox number serves Sasha, CampusMe and relocation, by mode. Production needs one number per product
(`CR-1-spec.md` §1), so say so if asked.*

## Before the day — one command each (from the founder's Mac)

```
bash ~/Developer/Sasha-travel-/backend/scripts/cr1_demo.sh health      # must say "store":"postgres"
bash ~/Developer/Sasha-travel-/backend/scripts/cr1_demo.sh rehearse    # the whole demo, WhatsApp CAPTURED (nothing reaches a phone), timed
bash ~/Developer/Sasha-travel-/backend/scripts/cr1_demo.sh reset       # back to the start: CampusMe + relocation (add "campus" or "relocation" for one)
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
| a **SPECIMEN** passport photo | "Reading your passport photo page… It goes to Anthropic's AI model to be read, once; I don't keep the photo." → **"I read: • Passport number: … ✓ (the passport's own check digit agrees)"** → Yes → "Kept 8 values…" |
| *(or)* `DEMO` | the rest filled with the **fictional** Ana Ejemplo Prueba, marked as such everywhere |
| answers… | "✅ Your EX-01 is prepared: 31 boxes filled… 8 left for you" → reviewer link + **the official PDF in the chat** |
| open the link | the reviewer screen: 96 fields, every value "from: …". The reviewer agent: e.g. **"postcode 08010 is in Barcelona, but the province written is Madrid"**, **"“3º B” may not fit this box on paper"**. The signature box reads **"LEFT FOR THE APPLICANT — NOT SIGNED"** |
| `SIGNED` | "signed by you, on your word. I didn't sign or tick anything" → "Which country do you live in?" |
| `UK` | "*Consulado General de España en Londres*. Its own sheet says: 'Applicants must request their appointment following the instructions on the Consulate's website' → link. You book it and go in person." + the checklist (11 items from the consulate's sheet, **dated 11 Feb 2022**, said as such; the passport's ≥ 1 year **computed**) |
| `1 March 2027` | reminders: apply from 1 Dec (the 90-day window); the TIE within a month of entry, with the official *cita previa de extranjería* page |

**The honest lines, if asked:**
- *"Do you file it?"* — No. Never, by design. The fill refuses to touch the signature, consent or intent boxes.
- *"Is the checklist current?"* — It's the consulate's own sheet, dated 2022; the screen says so. A consulate we haven't
  read gets no link.
- *"Pre-filled cita previa?"* — Neither the consulate's nor the Extranjería system takes a pre-filled link. We give the
  official page plus every value to copy. The person presses.

## Not shown, and why
- A real registration or a real filing: by design, until the founder decides.
- Relocation sections 2 and 3 (a family member's resources, a representative): not built. The file marks them "not
  your case".
- Consulates other than London: not read yet.
