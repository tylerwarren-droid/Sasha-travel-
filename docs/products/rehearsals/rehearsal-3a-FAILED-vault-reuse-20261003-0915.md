# CR 1 rehearsal 3 — 20261003-0915 UTC

Real code, real schools, real vault, real model (published specimen), real Postgres, as the DEMO account. WhatsApp captured (nothing sent). Vault item present at start: True.

**Beats: 18/22 as expected · the room waits 153 s in all (compute + 3.1 s per sandbox message) · script wall time 42 s.**

| beat | sent | compute s | msgs | the room waits s | ok |
|---|---|---|---|---|---|
| C1 April (not published) | campus visits at Yale and Penn in April for my son | 5.5 | 3 | 14.8 | ✓ |
| C2 November cards | campus Yale and Penn in November for my son | 17.3 | 2 | 23.5 | ✓ |
| C3 pick 1 → vault read-back | 1 | 0.6 | 2 | 6.8 | ✓ |
| C5 yes → prepared | cmyes:3c78c7a51536bf6d | 1.6 | 1 | 4.7 | ✗ expected: ✅ Prepared. |
| C6 hand-over page | GET /campus-handover/ | 0.9 | 0 | 0.9 | ✗ expected: prepared, not sent |
| C7 REGISTERED | REGISTERED | 0.0 | 1 | 3.1 | ✗ expected: registered on your word |
| C8 vague confirmation stays | Thank you for registering for a campus visit. We look forwar | 0.0 | 1 | 3.1 | ✗ expected: doesn't name |
| C9 exit | exit | 0.0 | 1 | 3.1 | ✓ |
| R1 relocation | relocation | 0.0 | 2 | 6.2 | ✓ |
| R2 first | first | 0.0 | 1 | 3.1 | ✓ |
| R3 me | me | 0.0 | 1 | 3.1 | ✓ |
| R4 myself | myself | 0.0 | 2 | 6.2 | ✓ |
| R5 specimen photo → read | 📷 specimen photo | 5.4 | 3 | 14.7 | ✓ |
| R6 yes, all right | rx:doc:yes | 0.0 | 2 | 6.2 | ✓ |
| R7 surname | De Bruijn | 0.0 | 1 | 3.1 | ✓ |
| R8 DEMO → prepared | DEMO | 1.0 | 5 | 16.5 | ✓ |
| R9 reviewer page | GET /relocation-file/rLiO_MXblYjTykUnyN73jQ | 1.8 | 0 | 1.8 | ✓ |
| R10 the PDF | GET /api/products/relocation/rLiO_MXblYjTykUnyN73jQ/EX-01-pr | 2.3 | 0 | 2.3 | ✓ |
| R11 SIGNED | SIGNED | 1.8 | 2 | 8.0 | ✓ |
| R12 UK → consulate + checklist | UK | 1.5 | 4 | 13.9 | ✓ |
| R13 entry date → reminders | 1 March 2027 | 2.1 | 1 | 5.2 | ✓ |
| R14 exit | exit | 0.0 | 1 | 3.1 | ✓ |

## What WhatsApp would have shown

### C1 April (not published)
> campus visits at Yale and Penn in April for my son

```
Reading Yale and Penn's own visit calendars for April 2027…
⏳ *Yale* hasn't published April 2027 yet — its calendar runs to 12 December 2026.
⏳ *Penn* hasn't published April 2027 yet — its calendar runs to 7 December 2026.
I'll check daily and message you the day April opens.
Want me to look at another month? Just name it, e.g. "November".
```

### C2 November cards
> campus Yale and Penn in November for my son

```
Reading Yale and Penn's own visit calendars for November 2026…
1. *Yale* — Campus Tour
Sun 1 Nov, 11:30 AM · Visitor Center · 64 spaces left

2. *Yale* — Campus Tour
Sun 1 Nov, 12:30 PM · Visitor Center · 76 spaces left

3. *Penn* — Morning Information Session
Mon 2 Nov, 9:30 AM · Undergraduate Admissions Visitor Center · open

4. *Penn* — Morning Tour
Mon 2 Nov, 10:15 AM · Undergraduate Admissions Visitor Center · open

Read just now from apps.admissions.yale.edu, key.admissions.upenn.edu — the schools' own calendars. Spaces change; I re-check before you register.

Which one? Reply with a number, 1–4.
```

### C3 pick 1 → vault read-back
> 1

```
Exactly what I'll do:
• I'll use your saved CampusMe student details (Sam) from your vault.
• Yale University: Campus Tour, Sunday 1 November 2026 at 11:30 AM (New Haven, CT time), 64 spaces left when read.
• Registering your son as the prospective student, with 1 guest.
• I'll prepare Yale's own registration form and stop before its Register button: you press it. I send nothing to Yale.
• Registering creates a record for the student in Yale's admissions system, and the school will email them.
Prepare it?
[Yes, prepare it · No]
```

### C5 yes → prepared
> cmyes:3c78c7a51536bf6d

```
❌ Not prepared: your saved student details couldn't be opened (that yes has already been used once).
```

### C6 hand-over page
> GET /campus-handover/

```
HTTP 404, 0 bytes
```

### C7 REGISTERED
> REGISTERED

```
CampusMe here 🎓 I read each university's own visit calendar, show you real sessions, prepare the school's registration form with your student's details, and you press Register. Tell me the schools and the month, e.g. "Yale and Penn in November for my son". Say EXIT to go back to Sasha.
```

### C8 vague confirmation stays
> Thank you for registering for a campus visit. We look forward to seeing you soon!

```
CampusMe here 🎓 I read each university's own visit calendar, show you real sessions, prepare the school's registration form with your student's details, and you press Register. Tell me the schools and the month, e.g. "Yale and Penn in November for my son". Say EXIT to go back to Sasha.
```

### C9 exit
> exit

```
Back to Sasha — tell me what to book. (Say CAMPUS or RELOCATION to switch again.)
```

### R1 relocation
> relocation

```
Relocation to Spain 🇪🇸 — the residence form EX-01 (non-lucrative residence). I assemble it from your answers, check every field, and hand you the official PDF. *You* sign it and *you* lodge it: I never file anything, and I never tick or sign the parts that are yours to decide. Say EXIT at any time to go back to Sasha.
First: is this your *first* application (made from outside Spain, at a consulate) or a *renewal* of a residence you already hold?
```

### R2 first
> first

```
Who holds the economic resources the application relies on — *you*, or a *family member*?
```

### R3 me
> me

```
Will you present the application *yourself*, or will a *representative* present it for you?
```

### R4 myself
> myself

```
Now your details, as your passport shows them. (Or send a photo of your passport's photo page and I'll read it — you confirm each value. Type DEMO to use a fictional applicant.)
Your passport number?
```

### R5 specimen photo → read
> 📷 specimen photo

```
Reading your passport photo page… It goes to Anthropic's AI model to be read, once; I don't keep the photo.
I read:
• Passport number: SPECI2014 ✓ (the passport's own check digit agrees)
• First surname: De Bruijn e/v Molenaar ⚠ the machine-readable zone gives the surname as DE BRUIJN; the printed field reads “De Bruijn e/v Molenaar” — tell me which belongs on the form
• Given names: Willeke Liselotte
• Sex: female — M (mujer) on the Spanish form ✓ (matches the machine-readable zone)
• Date of birth: 10 March 1965 ✓ (the passport's own check digit agrees)
• Place of birth: Specimen
• Nationality: Nederlandse
• Expires: 9 March 2024 ✓ (the passport's own check digit agrees) ⚠ this passport has EXPIRED
Is every line right?
[Yes, all right · No]
```

### R6 yes, all right
> rx:doc:yes

```
Kept 7 values from your passport, each marked as read from it.
Your first surname, exactly as on your passport?
```

### R7 surname
> De Bruijn

```
Your second surname? (Say NONE if your passport shows only one.)
```

### R8 DEMO → prepared
> DEMO

```
Filled the rest with a *fictional* applicant, Ana Ejemplo Prueba — every value says so on the file.
✅ Your EX-01 is prepared: 31 boxes filled from your answers, each naming its source; 8 left for you (section 5, the Dehú consent, your signature).
The reviewer checked every field: 37 fine, 1 to look at, 1 problem. Read it field by field here, with the official PDF to download:
https://project.kanoe.ai/relocation-file/rLiO_MXblYjTykUnyN73jQ
The official EX-01, prepared — not signed, not filed.  📎 https://project.kanoe.ai/api/products/relocation/rLiO_MXblYjTykUnyN73jQ/EX-01-prepared.pdf
When you've checked it: print it, complete section 5 yourself, decide on the Dehú consent, write the place and date, and sign in the FIRMA box. Reply SIGNED when that's done.
```

### R9 reviewer page
> GET /relocation-file/rLiO_MXblYjTykUnyN73jQ

```
HTTP 200, 177591 bytes
```

### R10 the PDF
> GET /api/products/relocation/rLiO_MXblYjTykUnyN73jQ/EX-01-prepared.pdf

```
HTTP 200, 734626 bytes
```

### R11 SIGNED
> SIGNED

```
Noted — signed by you, on your word. I didn't sign or tick anything for you. You lodge it yourself; I never file anything in Spain.
A first application is lodged in person, at the Spanish consulate for where you live. Which country do you live in now?
```

### R12 UK → consulate + checklist
> UK

```
Your consulate: *Consulado General de España en Londres*. Its own sheet says: “Applicants must request their appointment following the instructions on the Consulate's website”:
http://www.exteriores.gob.es/Consulados/LONDRES/en/Consulado/Pages/Visas.aspx
You book it and you go in person — each appointment is for one person only — family members applying need their own. I don't book or press anything.
(From the consulate's sheet dated 11 Feb 2022, read 3 Oct 2026; its website didn't answer when I checked today, so open the link yourself.)
Your checklist from that sheet: 11 items — 10 for you to gather, the EX-01 done. It's on your file page:
https://project.kanoe.ai/relocation-file/rLiO_MXblYjTykUnyN73jQ
⚠ your passport is valid until 2024-03-09: LESS than a year from today — the sheet asks for at least one year.
When do you plan to enter Spain? (a date, e.g. 1 March 2027 — or SKIP)
```

### R13 entry date → reminders
> 1 March 2027

```
I'll remind you here:
• 1 Dec 2026: You can apply for your visa from today
• 22 Mar 2027: You entered Spain about three weeks ago
(WhatsApp lets me write first only within 24 hours of your last message; otherwise the reminder waits for your next message, and it's always on your file page.)
```

### R14 exit
> exit

```
Back to Sasha — tell me what to book. (Say CAMPUS or RELOCATION to switch again.)
```
