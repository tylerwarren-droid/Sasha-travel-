# CR 1 rehearsal 1 — 20261005-0739 UTC

Real code, real schools, real vault, real model (published specimen), real Postgres, as the FOUNDER account (11111111…). WhatsApp captured on a fictional number (nothing sent). Vault item present at start: False. Afterwards it removed only what it created: cases 3, bookings (campus visits, the clinic, CR 10 appointments) 0, call rows 0, vault items it created 0.

**Beats: 23/23 as expected · the room waits 230 s in all (compute + 3.1 s per sandbox message) · script wall time 79 s.**

| beat | sent | compute s | msgs | the room waits s | ok |
|---|---|---|---|---|---|
| M1 relocation | relocation | 2.2 | 2 | 8.4 | ✓ |
| M2 first | first | 2.1 | 1 | 5.2 | ✓ |
| M3 me | me | 2.0 | 1 | 5.1 | ✓ |
| M4 myself | myself | 2.0 | 2 | 8.2 | ✓ |
| M5 DEMO | DEMO | 2.9 | 5 | 18.4 | ✓ |
| M6 SIGNED | SIGNED | 3.7 | 2 | 9.9 | ✓ |
| M7 UK | UK | 3.6 | 3 | 12.9 | ✓ |
| M8 SKIP | SKIP | 4.0 | 2 | 10.2 | ✓ |
| M9 1 March 2027 | 1 March 2027 | 3.9 | 2 | 10.1 | ✓ |
| MR1 massage, inside RelocateMe | book me a 60-minute massage near my hotel on arrival | 4.7 | 6 | 23.3 | ✓ |
| MR2 pick OUR test venue (card 3) | pick:e8a340:2 | 1.7 | 1 | 4.8 | ✓ |
| MR3 the day and time | 1 March 2027 at 11:05 | 0.6 | 1 | 3.7 | ✓ |
| MR3b for how many | 1 person | 7.2 | 3 | 16.5 | ✓ |
| MR4 the one yes | yes:8b3bec89:0a29daa47a85bedc | 11.6 | 3 | 20.9 | ✓ |
| MR5 back to the file | relocation | 0.6 | 1 | 3.7 | ✓ |
| MR6 web itinerary has it | web: what do I have on 1 March 2027? | 1.1 | 1 | 1.1 | ✓ |
| MR7 web: the same ask inside RelocateMe | web: book me a 60-minute massage near my hotel on arrival | 1.3 | 1 | 1.3 | ✓ |
| ME1 españa | españa | 3.3 | 1 | 6.4 | ✓ |
| ME2 1 → Salud | 1 | 1.9 | 2 | 8.1 | ✓ |
| ME3 massage, inside EspañaMe | book me a 60-minute massage near my hotel on arrival | 2.8 | 6 | 21.4 | ✓ |
| ME4 back to españa | españa | 0.6 | 1 | 3.7 | ✓ |
| MX1 cancel our test-venue massage | cancel my Sasha Test Venue booking | 8.7 | 2 | 14.9 | ✓ |
| MX1b yes, cancel it (ours) | yes:ceee7dd8:24e36f95d2247010 | 5.8 | 2 | 12.0 | ✓ |

## What WhatsApp would have shown

### M1 relocation
> relocation

```
Relocation to Spain 🇪🇸 — the residence form EX-01 (non-lucrative residence). I assemble it from your answers, check every field, and hand you the official PDF. *You* sign it and *you* lodge it: I never file anything, and I never tick or sign the parts that are yours to decide. Ask me anything else at any time — a booking, a flight — and we'll come back to this.
First: is this your *first* application (made from outside Spain, at a consulate) or a *renewal* of a residence you already hold?
```

### M2 first
> first

```
Who holds the economic resources the application relies on — *you*, or a *family member*?
```

### M3 me
> me

```
Will you present the application *yourself*, or will a *representative* present it for you?
```

### M4 myself
> myself

```
Now your details, as your passport shows them. (Or send a photo of your passport's photo page and I'll read it — you confirm each value. Type DEMO to use a fictional applicant.)
Your passport number?
```

### M5 DEMO
> DEMO

```
Filled the rest with a *fictional* applicant, Ana Ejemplo Prueba — every value says so on the file.
✅ Your EX-01 is prepared: 31 boxes filled from your answers, each naming its source; 8 left for you (section 5, the Dehú consent, your signature).
The reviewer checked every field: 38 fine, 1 to look at, 0 problems. Read it field by field here, with the official PDF to download:
https://project.kanoe.ai/relocation-file/5Bap_fNWfl3sDK2U3olfCw
The official EX-01, prepared — not signed, not filed.  📎 https://project.kanoe.ai/api/products/relocation/5Bap_fNWfl3sDK2U3olfCw/EX-01-prepared.pdf
When you've checked it: print it, complete section 5 yourself, decide on the Dehú consent, write the place and date, and sign in the FIRMA box. Reply SIGNED when that's done.
```

### M6 SIGNED
> SIGNED

```
Noted — signed by you, on your word. I didn't sign or tick anything for you. You lodge it yourself; I never file anything in Spain.
A first application is lodged in person, at the Spanish consulate for where you live. Which country do you live in now?
```

### M7 UK
> UK

```
Your consulate: *Consulado General de España en Londres*. Its own sheet says: “Applicants must request their appointment following the instructions on the Consulate's website”:
http://www.exteriores.gob.es/Consulados/LONDRES/en/Consulado/Pages/Visas.aspx
You book it and you go in person — each appointment is for one person only — family members applying need their own. I don't book or press anything.
(From the consulate's sheet dated 11 Feb 2022, read 3 Oct 2026; its website didn't answer when I checked today, so open the link yourself.)
Your checklist from that sheet: 11 items — 9 for you to gather, the EX-01 done. It's on your file page:
https://project.kanoe.ai/relocation-file/5Bap_fNWfl3sDK2U3olfCw
Your *document pack* — which of these have you gathered? Reply with the numbers (e.g. 1 3 4-6), ALL, or SKIP:
1. National visa application form
2. A recent passport photo with a white background
3. Passport valid for at least one year
4. Your valid UK residence permit and a copy
5. Criminal record certificate from every country you lived in for the last five years
6. Public or private health insurance with an insurer authorised to operate in Spain
7. Medical certificate from a registered doctor
8. Proof of economic means for one year
9. Form 790-052
10. The EX-01 — prepared by me, signed by you
11. The visa fee
```

### M8 SKIP
> SKIP

```
Your document pack, in Consulado General de España en Londres's own order — name your files like this and they sort the way it asks:
☐ 01_National-visa-application-form — still to gather
☐ 02_A-recent-passport-photo-with-a-white-background — still to gather
☐ 03_Passport-valid-for-at-least-one-year — still to gather
☐ 04_Your-valid-UK-residence-permit-and-a-copy — still to gather
☐ 05_Criminal-record-certificate-from-every-country-you-lived-in — still to gather
☐ 06_Public-or-private-health-insurance-with-an-insurer-authorise — still to gather
☐ 07_Medical-certificate-from-a-registered-doctor — still to gather
☐ 08_Proof-of-economic-means-for-one-year — still to gather
☐ 09_Form-790-052 — still to gather
✓ 10_The-EX-01 (prepared; you sign it)
☐ 11_The-visa-fee — still to gather
10 still to gather. Say PACK and the numbers any time to update it.
When do you plan to enter Spain? (a date, e.g. 1 March 2027 — or SKIP)
```

### M9 1 March 2027
> 1 March 2027

```
I'll remind you here:
• 1 Dec 2026: You can apply for your visa from today
• 22 Mar 2027: You entered Spain about three weeks ago
(WhatsApp lets me write first only within 24 hours of your last message; otherwise the reminder waits for your next message, and it's always on your file page.)
When you've booked your consulate appointment — and later, in Spain, your TIE one — tell me the day and time (e.g. "consulate booked 12 November 10:00") and I'll put it in your itinerary.
```

### MR1 massage, inside RelocateMe
> book me a 60-minute massage near my hotel on arrival

```
A 60-minute massage in Madrid, near Calle de Ejemplo 12, on Mon 1 Mar 2027 (your entry date) — Sasha's booking takes it from here, one yes as always. When it's done, say “relocation” to come back to where we were.
A 60-minute massage in Madrid — 20 places found. From Google Maps; nobody has been contacted.
Sasha's pick · ZenVida Foot & Body Massage Madrid Centro · ★ 5.0 (502 Google reviews)
Arokaya Thai Massage & Wellness · ★ 5.0 (836 Google reviews)
Rehearsal · Sasha Test Venue — ours, not a real restaurant: booking it contacts no one
Which one?
[ZenVida Foot & Body Massage Madrid Centro · Arokaya Thai Massage & Wellness · Sasha Test Venue]
```

### MR2 pick OUR test venue (card 3)
> pick:e8a340:2

```
What time on Monday 1 March?
```

### MR3 the day and time
> 1 March 2027 at 11:05

```
For how many?
```

### MR3b for how many
> 1 person

```
They take bookings on their own website's form — I'll fill it in after your yes.
Exactly what I'll send:
• I'll send the booking form on Sasha Test Venue's own website (https://sasha-travel-production.up.railway.app/api/booking/test-venue/plain), to https://sasha-travel-production.up.railway.app/api/booking/test-venue/plain, with exactly these fields:
• I'll use your saved Kanoe Test Club number (fictional) from your vault.
• Día: 2027-03-01
• Hora: 11:05
• Personas: 1
• Nombre: Tyler Warren
• Email: tyler@kanoe.ai
• Teléfono: [the account's mobile]
• Comentarios: Por favor, envíen también una copia de la confirmación a sasha@booking.kanoe.ai. · Kanoe Test Club: ⟨your number, added from your vault when it's sent⟩
• plus the page's own hidden fields, sent with the page's values: token.
• I won't tick any box agreeing to their terms, and I stop at any CAPTCHA.
• Their answer page is kept word for word. I send it once. Shall I send it?
Book Sasha Test Venue for 1, Monday 1 March at 11:05, under Warren?
[Yes, book it · No]
```

### MR4 the one yes
> yes:8b3bec89:0a29daa47a85bedc

```
✅ Booked: Sasha Test Venue, Monday 1 March at 11:05, 1 person. Their reference: TV-9E812B-B9.
Their page said: “Reserva confirmada Confirmado: mesa para 1 personas el lunes 1 de marzo a las 11:05, a nombre de Tyler Warren. Localizador: TV-9E812B-B9 Para cancelar: https://sasha-travel-production.up.railway.app/api/booking/test-venue/cancel/TV-9E812B-B9”
No receipt is emailed: this was our own test venue.
```

### MR5 back to the file
> relocation

```
Back to your EX-01. I'll remind you here:
• 1 Dec 2026: You can apply for your visa from today
• 22 Mar 2027: You entered Spain about three weeks ago
(WhatsApp lets me write first only within 24 hours of your last message; otherwise the reminder waits for your next message, and it's always on your file page.)

When you've booked your consulate appointment — and later, in Spain, your TIE one — tell me the day and time (e.g. "consulate booked 12 November 10:00") and I'll put it in your itinerary.
```

### MR6 web itinerary has it
> web: what do I have on 1 March 2027?

```
Monday 1 March:
• 11:05 Sasha Test Venue, 1 people
Your bookings don't say where you'll be that day (no flight or hotel in them).
```

### MR7 web: the same ask inside RelocateMe
> web: book me a 60-minute massage near my hotel on arrival

```
A 60-minute massage in Madrid, near Calle de Ejemplo 12, on Mon 1 Mar 2027 (your entry date) — Sasha's booking takes it from here, one yes as always. When it's done, say “relocation” to come back to where we were.

Let me look for a 60-minute massage in Madrid, ES — from Google Maps; nobody is contacted by looking.
```

### ME1 españa
> españa

```
EspañaMe 🇪🇸 — Spain's public processes, done with you. Reply with a number:
1. *Salud* — health card, family doctor, SERMAS (live)
2. *Padrón* — registering at the town hall (concept)
3. *Identity and access* — Cl@ve, your digital certificate (concept)
4. *Social security and tax* — your social-security number, Agencia Tributaria basics (concept)
5. *DGT* — exchanging a foreign driving licence (concept)
6. *Education* — a school place (concept)
[1. Salud (live) · 2. Padrón · 3. Identity & access]
```

### ME2 1 → Salud
> 1

```
🟢 *Salud — health card, family doctor, SERMAS* — LIVE
*What you need* (from the official page): your DNI — for foreigners, your residence permit (TIE) in force; the volante de empadronamiento from your town hall, issued in the last 90 days; the DAD from the INSS
*The official route:* your health card at your health centre or online; appointments on SERMAS's own page
https://www.comunidad.madrid/servicios/salud/tarjeta-sanitaria
*What I prepare:* everything for your appointment — the official page, the details to copy — and, for a private clinic, the call itself after your one yes; new in Madrid, the steps in order with reminders.
*You press:* signing in and pressing on the public service's own page; I never sign in or book there for you.
Source: Tarjeta Sanitaria — Comunidad de Madrid; Cita sanitaria — Comunidad de Madrid (SERMAS); Asistencia Sanitaria — Seguridad Social — read 3 Oct 2026.
Health details are sensitive. For this I use only what the appointment needs — never why you need a doctor — and I keep it at most 30 days. I never sign in, book or press on a public health website for you. Is that OK?
[Yes, continue · No]
```

### ME3 massage, inside EspañaMe
> book me a 60-minute massage near my hotel on arrival

```
A 60-minute massage in Madrid — Sasha's booking takes it from here, one yes as always. When it's done, say “españa” to come back to where we were.
A 60-minute massage in Madrid — 20 places found. From Google Maps; nobody has been contacted.
Sasha's pick · ZenVida Foot & Body Massage Madrid Centro · ★ 5.0 (502 Google reviews)  📎 https://static.wixstatic.com/media/b84849_2722a502ffb14589923eca981ccecb3c~mv2.jpg/v1/fill/w_1000,h_1000,al_c/b84849_2722a502ffb14589923eca981ccecb3c~mv2.jpg
Arokaya Thai Massage & Wellness · ★ 5.0 (836 Google reviews)
Rehearsal · Sasha Test Venue — ours, not a real restaurant: booking it contacts no one
Which one?
[ZenVida Foot & Body Massage Madrid Centro · Arokaya Thai Massage & Wellness · Sasha Test Venue]
```

### ME4 back to españa
> españa

```
Back to your health appointment. 🟢 *Salud — health card, family doctor, SERMAS* — LIVE
*What you need* (from the official page): your DNI — for foreigners, your residence permit (TIE) in force; the volante de empadronamiento from your town hall, issued in the last 90 days; the DAD from the INSS
*The official route:* your health card at your health centre or online; appointments on SERMAS's own page
https://www.comunidad.madrid/servicios/salud/tarjeta-sanitaria
*What I prepare:* everything for your appointment — the official page, the details to copy — and, for a private clinic, the call itself after your one yes; new in Madrid, the steps in order with reminders.
*You press:* signing in and pressing on the public service's own page; I never sign in or book there for you.
Source: Tarjeta Sanitaria — Comunidad de Madrid; Cita sanitaria — Comunidad de Madrid (SERMAS); Asistencia Sanitaria — Seguridad Social — read 3 Oct 2026.

Health details are sensitive. For this I use only what the appointment needs — never why you need a doctor — and I keep it at most 30 days. I never sign in, book or press on a public health website for you. Is that OK?
[Yes, continue · No]
```

### MX1 cancel our test-venue massage
> cancel my Sasha Test Venue booking

```
Exactly what I'll send:
• Sasha Test Venue sent a cancel link on their own website: https://sasha-travel-production.up.railway.app/api/booking/test-venue/cancel/TV-9E812B-B9.
• I'll open it once and keep their page word for word. It's cancelled only if their page says so.
Cancel Sasha Test Venue, Monday 1 March at 11:05, for 1, under Tyler Warren?
[Yes, cancel · No]
```

### MX1b yes, cancel it (ours)
> yes:ceee7dd8:24e36f95d2247010

```
Sasha Test Venue has cancelled your booking.
Their words: “Reserva cancelada La reserva TV-9E812B-B9 a nombre de Tyler Warren queda cancelada. Gracias.”
```
