# Sasha 234 — report (11 Oct 2026)

## Live
- Backend **979c33d** · Railway deploy 6717d9b5 SUCCESS (backend only; no frontend change)
- Commits: 8f505ba (merge CR 78, cr/78-s2 @ 2a7ba00) · ed9826c (an accident's place, found live) · 979c33d (the asked service: no bundle, found live)
- Units 1913 OK (146 skipped, 1 expected failure) · S1 fingerprint byte-identical to 228's baseline after each commit

## 0 · Credits
One 1-token call with the production key (`sk-ant-… bc1e05b8d099`): OK. SASHA_GATE_ANTHROPIC_API_KEY: not set.

## 1 · a7661b8 (robots `*`/`$`, Crawl-delay, ≤1 page/s)
Already live and gated in 233 (deploy 18418091, 149/149, $1.05); every deploy below carries it.

## Gate (service key `sk-ant-… bc1e05b8d099` — the gate key is still unset)
| deploy | commit | suites | $ |
|---|---|---|---|
| 3b18e23b | 8f505ba (CR 78 merged) | 149/149 (flight 21, basket 70, agent 21, voice 15, venue 20, whatsapp 1 [123], demo safety 1 [330]) | $1.05 / 243 calls |
| 55866982 | ed9826c | 149/149 (demo safety 332) | $1.07 / 251 calls |
| 6717d9b5 | 979c33d | 149/149 (demo safety 334) | $1.05 / 244 calls |

## 2 · CR 78 on production /s2 → agapi-sandbox (scratch guest ae367ad2; SASHA_S2_VIA_AGAPI = shadow → sandbox)
- **Found live:** with the case open, the model re-sent `place: "Lisbon"` beside `facts.place: "Rotunda do Marquês"`, and the city won
  (notify read-back said "Place: Lisbon"). Fixed in ed9826c: the facts' own place wins; the city the case opened with is never re-sent.
- **After the fix**, the rental company's read-back: "Date: 2026-10-11 · Time: 14:00 · Place: Rotunda do Marquês · Other vehicle: plate AA-00-ZZ · Injuries: none".
  The notify was approved, because the claim exists only after it. This was in the sandbox: Example Rentals is a fixture, so the
  message was captured and never sent.
- "Which card did you pay the rental with? … the Example Bank Travel Visa. Was it that one?" was asked at the clocks step, at notify and at the claim.
- **The claim read-back** (NOT approved): "File a rental car damage claim on your Travel Visa with Example Assistance … What happened
  (2026-10-11): Accident at Rotunda do Marquês at 14:00; the other vehicle's plate AA-00-ZZ. … notify by 10 December 2026."
- **Money back:** "My flight Madrid–London was 3 hours 40 late" → she asked for the airline and date → "Example Air EX123, yesterday,
  Madrid to Heathrow" → **"Your flight EX123 from Madrid is covered under EU rules, and you may be owed €250. Want me to claim it?"**
  Nothing was claimed.

## 3 · 233's proofs
- **Memory after a redeploy:** seeded on 36381d17 at 06:15 UTC ("A massage at a spa near Gran Vía, Saturday 5pm" → 5 cards). The
  `s2_memory` row is a jsonb **object**. After deploy 3b18e23b (a new process), the reopen returned: "Welcome back — we were looking at spa
  massage in Gran Vía, Madrid, Saturday 17 October 17:00. Want to carry on?" with the same 5 cards.
- **Treatwell spa — Método Javier Panizo (C. de Zurbarán 7, Chamberí).** Production read the page (robots allows
  `/establecimiento/`; the calendar `/availability` is disallowed) and found 11 services.
  - **Found live:** "a 60-minute massage" picked "Pack masaje anticelulítico (masaje + presoterapia)" because it was listed first.
    Fixed in 979c33d: a bundle loses unless it was asked for, then fewer unasked words win, then the closer duration.
  - After the fix: "Their Treatwell page lists 'Masaje deportivo' (55 min, €55–€430) — that's the one to choose. Treatwell doesn't
    show me which times are free; their page shows you." She handed over the venue's page with Saturday 17 October 12:00, for 1, in
    words. Nothing was opened or approved.
- **Rover "dog walker near Gran Vía":** robots allows `/es/search/`. Production got **403, Cloudflare "Just a moment…"** again (11 Oct,
  08:25). There are no listings, and it was not worked around; today's behaviour stands.

## Cleanup
- Scratch guest ae367ad2 deleted (200). Every public and auth account table holds 0 rows for it.
- `SASHA_PLATFORM_CHECK_ACCOUNTS` was set to the guest for the Rover/Treatwell reads, then emptied (skip-deploys; staged).

## Still open
- **Gate key:** paste the `sasha-gate` key here. I'll set it as SASHA_GATE_ANTHROPIC_API_KEY (fingerprint only), and the next gate
  log's first line will name it.
- **Not fixed (seen in a proof):** the first Treatwell read-back said "pick Saturday 17 October at 5 pm", but this venue's Saturday
  hours are 8:00–14:00. The page route doesn't check the asked time against the hours it read; /s2 chat checks it before the cards.
