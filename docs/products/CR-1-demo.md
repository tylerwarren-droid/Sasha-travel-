# CR 1 — demo run of show: CampusMe and relocation on WhatsApp (Wed 7 Oct)

*One sandbox number serves Sasha, CampusMe and relocation, by mode. Production needs one number per product
(`CR-1-spec.md` §1), so say so if asked.*

## Before the day (founder or chat)

- [ ] **Apply 028** (`tab_messages` id 159) on sasha-prod, then redeploy. Without it, cases live in server memory, and a
      redeploy mid-demo loses the open hand-over and file pages.
- [ ] **Re-join the Twilio sandbox** from the demo phone the day before (it expires after 3 days), and link the number
      (`LINK ######` from /you).
- [ ] **Confirm Railway has `ANTHROPIC_API_KEY`.** The passport-photo read is the only model call. It hasn't been run
      against the live API yet (no key on the build machine), so rehearse it once with a **SPECIMEN** passport image,
      never a real person's.
- [ ] Optional: `CAMPUSME_WATCH_LOOP=1` on Railway. It runs the daily read for "April opens".
- [ ] **Re-run** `python -m scripts.campusme_live_read "Yale and Penn in November"` on the morning. Sessions and spaces
      change, so quote the numbers from that run.

## Part 1 — CampusMe (≈3 min)

| Send | What comes back | Say |
|---|---|---|
| `campus visits at Yale and Penn in April for my son` | "Reading Yale and Penn's own visit calendars for April 2027…" → **"Yale hasn't published April 2027 yet — its calendar runs to 30 November 2026. I'll check it daily and message you the day April opens."** (and the same for Penn) | *"It reads the school's own calendar, and when there's nothing there, it says so. No invented slots."* |
| `campus Yale and Penn in November for my son` | numbered cards: Yale Campus Tour, Sun 1 Nov, 11:30 AM, "64 spaces left" · Penn Information Session… + "Read just now from apps.admissions.yale.edu, key.admissions.upenn.edu" | 8 of 10 top schools run Slate. One reader with two variants covers them |
| tap **1** | first time: five questions (name, email, birth date, school, graduation year) → "Keep them in your vault?". Second time: the vault line | the vault opens only inside the yes |
| — | **"Exactly what I'll do:"** the session as read, *"…stop before its Register button: you press it. I send nothing to Yale."* + *"Registering creates a record for the student in Yale's admissions system"* | **one yes**, hash-bound |
| **Yes, prepare it** | "✅ Prepared … filled from your vault" + the link | — |
| open the link | the hand-over: Yale's own form, question by question, each answer with **"from: your vault"**, statements marked **"yours to tick"**, "Open Yale's registration page ↗" | *"Nothing is submitted. A person presses. That's the founder's model."* |
| `REGISTERED` | "registered on your word" + Google Calendar link + .ics; it's in "You → My bookings" | paste a confirmation that **doesn't** name the day → it stays "on your word" |

⛔ **Don't press Register on a real school's page on stage** unless the founder decides to do one real registration, for a
real student, with consent.

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
