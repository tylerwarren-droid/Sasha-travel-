# CR 1 rehearsal 1 — 20261004-1017 UTC

Real code, real schools, real vault, real model (published specimen), real Postgres, as the FOUNDER account (11111111…). WhatsApp captured on a fictional number (nothing sent). Vault item present at start: False. Afterwards it removed only what it created: cases 0, bookings (campus visits, the clinic, CR 10 appointments) 0, call rows 0, vault items it created 0.

**Beats: 16/17 as expected · the room waits 78 s in all (compute + 3.1 s per sandbox message) · script wall time 19 s.**

| beat | sent | compute s | msgs | the room waits s | ok |
|---|---|---|---|---|---|
| M1 relocate | relocate | 1.8 | 2 | 8.0 | ✓ |
| M2 sasha → back | sasha | 0.6 | 1 | 3.7 | ✓ |
| M3 campus | campus | 1.9 | 1 | 5.0 | ✓ |
| M4 sasha → back | sasha | 0.6 | 1 | 3.7 | ✓ |
| M5 españa → the menu | españa | 1.9 | 1 | 5.0 | ✓ |
| M6 2 → padrón (CONCEPT) | 2 | 1.2 | 2 | 7.4 | ✓ |
| M7 3 → more processes (CONCEPTS) | 3 | 1.2 | 2 | 7.4 | ✓ |
| M8 1 → the health demo | 1 | 1.2 | 1 | 4.3 | ✓ |
| M9 sasha → back | sasha | 0.6 | 1 | 3.7 | ✓ |
| M10 espana (no ñ) | espana | 1.9 | 1 | 5.0 | ✓ |
| M11 sasha → back | sasha | 0.7 | 1 | 3.8 | ✓ |
| M12 diligence | diligence | 1.9 | 1 | 5.0 | ✓ |
| M13 check TotalEnergies in France | check TotalEnergies in France | 1.2 | 1 | 4.3 | ✓ |
| M14 the Netherlands → refused | check Shell in the Netherlands | 1.2 | 1 | 4.3 | ✓ |
| M15 ad + a person → refused | ad check Mr Patrick Pouyanné in France | 0.6 | 1 | 3.7 | ✓ |
| M16 sasha → back | sasha | 0.6 | 1 | 3.7 | ✓ |
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
EspañaMe 🇪🇸 — Spain's public processes, done with you. Pick one:
1. *Health* — a doctor: a private clinic, the public service (SERMAS), or new in Madrid. (working demo)
2. *Padrón* — registering at the town hall. (CONCEPT — not built yet)
3. *More* — Cl@ve and your digital certificate, social security and tax, the DGT, schools. (CONCEPTS — not built yet)
[1. Health · 2. Padrón (concept) · 3. More (concepts)]
```

### M6 2 → padrón (CONCEPT)
> 2

```
🏛 *Padrón* — CONCEPT, not built yet. What it would be, from the town hall's own page (read 3 Oct 2026): what to bring — the application, signed by the adults; your identity documents, in force; documents showing you use the home (and any authorisations) — and its own appointment page, which you book yourself (I never hunt for appointments): https://servpub.madrid.es/GNSIS_WBCIUDADANO/tramitePorCodigoWeb.do?codTramite=PAD
Then a reminder to ask for your volante. Today the padrón step is part of Health → New in Madrid, which works.
Anything else from the menu?
[1. Health · 2. Padrón (concept) · 3. More (concepts)]
```

### M7 3 → more processes (CONCEPTS)
> 3

```
🏛 *Cl@ve and your digital certificate, social security and tax, the DGT, schools* — CONCEPTS, not built yet and not yet studied: each will be read at its official source before anything is built. The rule stays the same: I prepare everything; you sign in and press.
Anything else from the menu?
[1. Health · 2. Padrón (concept) · 3. More (concepts)]
```

### M8 1 → the health demo
> 1

```
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
EspañaMe 🇪🇸 — Spain's public processes, done with you. Pick one:
1. *Health* — a doctor: a private clinic, the public service (SERMAS), or new in Madrid. (working demo)
2. *Padrón* — registering at the town hall. (CONCEPT — not built yet)
3. *More* — Cl@ve and your digital certificate, social security and tax, the DGT, schools. (CONCEPTS — not built yet)
[1. Health · 2. Padrón (concept) · 3. More (concepts)]
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
🔎 Applied Diligence — PREVIEW: the register service isn't connected here yet, so nothing was checked.
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
