# CR 1 rehearsal 1 — 20261004-1027 UTC

Real code, real schools, real vault, real model (published specimen), real Postgres, as the FOUNDER account (11111111…). WhatsApp captured on a fictional number (nothing sent). Vault item present at start: False. Afterwards it removed only what it created: cases 0, bookings (campus visits, the clinic, CR 10 appointments) 0, call rows 0, vault items it created 0.

**Beats: 19/20 as expected · the room waits 107 s in all (compute + 3.1 s per sandbox message) · script wall time 24 s.**

| beat | sent | compute s | msgs | the room waits s | ok |
|---|---|---|---|---|---|
| M1 relocate | relocate | 1.8 | 2 | 8.0 | ✓ |
| M2 sasha → back | sasha | 0.6 | 1 | 3.7 | ✓ |
| M3 campus | campus | 1.8 | 1 | 4.9 | ✓ |
| M4 sasha → back | sasha | 0.6 | 1 | 3.7 | ✓ |
| M5 españa → the menu | españa | 1.9 | 1 | 5.0 | ✓ |
| M6 2 → padrón (CONCEPT) | 2 | 1.4 | 2 | 7.6 | ✓ |
| M7 5 → DGT (CONCEPT) | 5 | 1.2 | 2 | 7.4 | ✓ |
| M7b 3 → identity and access (CONCEPT) | 3 | 1.3 | 2 | 7.5 | ✓ |
| M7c 4 → social security and tax (CONCEPT) | 4 | 1.2 | 2 | 7.4 | ✓ |
| M7d 6 → education (CONCEPT) | 6 | 1.2 | 2 | 7.4 | ✓ |
| M8 1 → Salud (LIVE) → consent | 1 | 1.3 | 2 | 7.5 | ✓ |
| M9 sasha → back | sasha | 0.6 | 1 | 3.7 | ✓ |
| M10 espana (no ñ) | espana | 1.8 | 1 | 4.9 | ✓ |
| M11 sasha → back | sasha | 0.6 | 1 | 3.7 | ✓ |
| M12 diligence | diligence | 1.8 | 1 | 4.9 | ✓ |
| M13 check TotalEnergies in France | check TotalEnergies in France | 1.8 | 2 | 8.0 | ✓ |
| M14 the Netherlands → refused | check Shell in the Netherlands | 1.4 | 1 | 4.5 | ✓ |
| M15 ad + a person → refused | ad check Mr Patrick Pouyanné in France | 0.7 | 1 | 3.8 | ✓ |
| M16 sasha → back | sasha | 0.7 | 1 | 3.8 | ✓ |
| LIVE one real message to the account's own WhatsApp | (live) | 0 | 1 | 0 | ✗ expected: sent |

## What WhatsApp would have shown

### M1 relocate
> relocate

```
Relocation to Spain 🇪🇸 — the residence form EX-01 (non-lucrative residence). I assemble it from your answers, check every field, and hand you the official PDF. *You* sign it and *you* lodge it: I never file anything, and I never tick or sign the parts that are yours to decide. Ask me anything else at any time — a booking, a flight — and we'll come back to this.
First: is this your *first* application (made from outside Spain, at a consulate) or a *renewal* of a residence you already hold?
```

### M2 sasha → back
> sasha

```
Back to Sasha — ask me anything: a booking, a flight, your plans.
```

### M3 campus
> campus

```
CampusMe here 🎓 I read each university's own visit calendar, show you real sessions, prepare the school's registration form with your student's details, and you press Register. Tell me the schools and the month, e.g. "Yale and Penn in November for my son". Anything else — a booking, a flight — just ask; we'll come back to this.
```

### M4 sasha → back
> sasha

```
Back to Sasha — ask me anything: a booking, a flight, your plans.
```

### M5 españa → the menu
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

### M6 2 → padrón (CONCEPT)
> 2

```
○ *Padrón — registering at the town hall* — CONCEPT, not built yet
*What you need* (from the official page): the application, signed by the adults; your identity documents, in force; documents showing you use the home (and any authorisations)
*The official route:* an appointment at the town hall, booked on its own page
https://servpub.madrid.es/GNSIS_WBCIUDADANO/tramitePorCodigoWeb.do?codTramite=PAD
*What I would prepare:* the list of what to bring, in order, and its own appointment page.
*You press:* booking the appointment and going in person.
Source: Trámites de Padrón y censo electoral con cita previa — Ayuntamiento de Madrid — read 3 Oct 2026.
Another area? Reply 1–6.
[1. Salud (live) · 2. Padrón · 3. Identity & access]
```

### M7 5 → DGT (CONCEPT)
> 5

```
○ *DGT — exchanging a foreign driving licence* — CONCEPT, not built yet
I haven't read its official page yet (DGT — exchanging a foreign licence: its site refused automated connections (robots.txt and the page both failed to connect, 4 Oct 2026)), so no list and no route here — nothing from memory.
Another area? Reply 1–6.
[1. Salud (live) · 2. Padrón · 3. Identity & access]
```

### M7b 3 → identity and access (CONCEPT)
> 3

```
○ *Identity and access — Cl@ve, your digital certificate* — CONCEPT, not built yet
*What you need* (from the official pages): the software its 'Configuración previa' lists; the Código de Solicitud emailed after the online request; proving your identity in person at an Oficina de Acreditación de Identidad
*The official route:* Cl@ve — how to register: online (automatic video identification, or an invitation letter), with an electronic certificate or DNIe, or in person at a registration office; then a welcome SMS to your registered mobile · FNMT digital certificate for an individual: set up, request online, prove your identity in person (an appointment is needed at AEAT, Seguridad Social and other offices), then download about an hour later
https://clave.gob.es/en/registro/como-puedo-registrarme
*What I would prepare:* what each route asks of you and the official page to start from.
*You press:* registering and signing in yourself — I never hold your Cl@ve or your certificate.
Source: Cl@ve — how to register (clave.gob.es) — read 4 Oct 2026; FNMT digital certificate for an individual (www.sede.fnmt.gob.es) — read 4 Oct 2026.
Another area? Reply 1–6.
[1. Salud (live) · 2. Padrón · 3. Identity & access]
```

### M7c 4 → social security and tax (CONCEPT)
> 4

```
○ *Social security and tax — your social-security number, Agencia Tributaria basics* — CONCEPT, not built yet
*What you need* (from the official pages): your DNI or NIE details; your mobile and email; your address; without Cl@ve or a certificate: both sides of your DNI/NIE and a selfie with its front; a NIF if you do anything with tax significance — it generally matches your DNI or NIE; without a NIE, a NIF assigned by the tax administration
*The official route:* Your social-security number (NUSS) — Import@ss: online with its 'Solicitar NUSS' button — signed in with Cl@ve, DNIe, a certificate or SMS, or with a selfie and a photo of your ID · Agencia Tributaria — your NIF: online, no visit: Modelo 030 (NIF for an individual without DNI/NIE)
https://portal.seg-social.gob.es/wps/portal/importass/importass/Categorias/Altas,+bajas+y+modificaciones/Altas+y+afiliacion+de+trabajadores/Solicitar+el+numero+de+la+Seguridad+Social
*What I would prepare:* what to bring and the official page for your number, and the tax basics in order.
*You press:* the request, signed in or in person.
Source: Your social-security number (NUSS) — Import@ss (portal.seg-social.gob.es) — read 4 Oct 2026; Agencia Tributaria — your NIF (sede.agenciatributaria.gob.es) — read 4 Oct 2026.
Another area? Reply 1–6.
[1. Salud (live) · 2. Padrón · 3. Identity & access]
```

### M7d 6 → education (CONCEPT)
> 6

```
○ *Education — a school place* — CONCEPT, not built yet
*What you need* (from the official page): the admission application, signed by both parents/guardians; its sworn statement if only one can sign; to file online: Cl@ve, an @SCV registration, or Roble/Raíces credentials; optional: proof of the school's extra criterion if you claim it
*The official route:* Comunidad de Madrid — school admission, 2026-2027: preferably online (Secretaría Virtual), else on paper at the first school on the application; the ordinary period was 11–25 March 2026 — newcomers after that use the extraordinary process (from 25 June / 3 July 2026), online, at a school with places, or at the Servicio de Apoyo a la Escolarización
https://www.comunidad.madrid/educacion/solicita-tu-admision-educacion-infantil-obligatoria-bachillerato
*What I would prepare:* the official calendar and what the application asks for.
*You press:* the application itself.
Source: Comunidad de Madrid — school admission, 2026-2027 (www.comunidad.madrid) — read 4 Oct 2026.
Another area? Reply 1–6.
[1. Salud (live) · 2. Padrón · 3. Identity & access]
```

### M8 1 → Salud (LIVE) → consent
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

### M9 sasha → back
> sasha

```
Back to Sasha — ask me anything: a booking, a flight, your plans.
```

### M10 espana (no ñ)
> espana

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

### M11 sasha → back
> sasha

```
Back to Sasha — ask me anything: a booking, a flight, your plans.
```

### M12 diligence
> diligence

```
Applied Diligence — PREVIEW 🔎 Tell me a company and its country — e.g. “check TotalEnergies in France”, or a registration number with its country. I show what the official register returns, with its source and date. A preview, not a due-diligence report.
```

### M13 check TotalEnergies in France
> check TotalEnergies in France

```
Checking TotalEnergies in the register (FR)…
🔎 Applied Diligence — PREVIEW: the lookup was refused or failed (503: This deployment has no preview key set, so no preview is available.) — nothing claimed.
```

### M14 the Netherlands → refused
> check Shell in the Netherlands

```
🔎 Applied Diligence — PREVIEW: not available for this country — the Dutch company register's terms don't allow passing on its records, by any route — so this preview never shows them.
```

### M15 ad + a person → refused
> ad check Mr Patrick Pouyanné in France

```
🔎 Applied Diligence — PREVIEW checks companies only — not people. Send a company name or registration number.
```

### M16 sasha → back
> sasha

```
Back to Sasha — ask me anything: a booking, a flight, your plans.
```

### LIVE one real message to the account's own WhatsApp
> (live)

```
skipped: KANOE_LIVE_ONE=0 (already sent once)
```
