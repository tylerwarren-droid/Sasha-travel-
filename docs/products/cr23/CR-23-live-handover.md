# CR 23 · The live hand-over (Browserbase trial) — 5 Oct 2026

## Before building: what Browserbase is, read from its own pages (5 Oct 2026)
- **Plans:** Free $0 (1 browser-hour/month, 3 at once) · Developer $20 (100 h, then $0.12/h) · Startup $99 (500 h,
  then $0.10/h) · Scale custom. The account is on **Free**; this whole rehearsal used **2.9 browser-minutes**.
- **EU hosting:** yes — every session here ran in **eu-central-1 (Frankfurt)**: 6 sessions, all `eu-central-1`, all
  completed, none left running.
- **DPA:** only on **Scale**. The privacy policy names no processor role, sub-processors or SCCs. So **only fictional
  details have gone through it**, and the code refuses a real guest's details until the founder sets
  `BROWSERBASE_DPA=signed` (after signing one).
- Per session: **recording off, logging off, CAPTCHA solving OFF** (it is ON by default at Browserbase), ads blocked,
  phone viewport 390×844, 10-minute cap, released the moment it's done.

## What was built — `backend/booking_signer/handover.py`
It sits ON the form rung (Sasha 89): a **prepared** form (the read-back the guest would have said yes to) →
`POST /api/booking/forms/{form_id}/handover` → Sasha fills the SAME fields in a Frankfurt cloud browser, lands on the
last step, and returns ONE link: `…/api/booking/handover/{id}?t=<32-byte token>` (the live view + her line; on
"✅ Booked" it returns to `return_to`, only a kanoe.ai / wa.me address).

The founder's last-press rules, each enforced in code (and tested, `tests/test_handover_cr23.py`, 20 tests):
| Rule | How |
|---|---|
| Every field pre-filled or no link | after filling, each field must hold Sasha's value AND the page's own `checkValidity()` must pass AND no required visible field empty — else the session is released and the caller gets a refusal |
| Land on the final step | a two-step form's first step (the day) is sent by Sasha; the guest sees only the last page, its Book button scrolled into view and outlined |
| "✅ Booked" within seconds | the press is caught in the page; their answer page is read the moment it loads with the form rung's reading (only a page restating day, time and number with a yes confirms) |
| Operator can take the session | `GET /api/booking/ops/handovers` (founder only) gives each live hand-over's `operator_url` — Browserbase's interactive live view of the same session |
| Venues' own sites only | the form rung's map (our test venue, or a founder-approved host); a platform host or a platform's frame → refused |
| Never a payment step | a card/IBAN field (name or `autocomplete=cc-*`) or a payment provider's frame anywhere → refused |
| CAPTCHA / terms box | refused (no link) — the solver is off; a terms box is the guest's |
| Race | the form is **claimed** at hand-over, so a yes or a second hand-over can't send it twice; refused → form marked not sent |

## Rehearsals (live, Browserbase, fictional guest "Prueba Sasha")
| # | Form | Result | Taps | Press → ✅ | Link ready in |
|---|---|---|---|---|---|
| 1 | test venue, one page | **✅ Booked** TV-32ABA5-00 (cancelled) | **1** | **0.63 s** | 31.5 s (before the fix) |
| 2 | test venue, two steps | **✅ Booked** TV-EE8CAF-D5 (cancelled) — guest landed on step 2 | **1** | **0.71 s** | 32.5 s (before the fix) |
| 3 | test venue, one page | **✅ Booked** TV-D65AD5-3A (cancelled) | **1** | **0.74 s** | **6.0 s** |
| 4 | test venue + terms box | **refused, no link** (`consent_box`) | — | — | — |
| 5 | test venue + CAPTCHA | **refused, no link** (`captcha`) | — | — | — |
| 6 | **Hanakura (Madrid), its own form — READ-ONLY** | all 7 fields filled, their validity check passed, one press left ("Enviar mensaje"), **not pressed**, session ended | (1) | — | **7.0 s** |

The press was made in Browserbase's live view (as the guest would), on our test venue only. Every test booking was
cancelled through the venue's own cancel link.

**The fix between runs 2 and 3:** filling was 22 s, because each field cost about 3 round trips to Frankfurt. Now every
field goes in one in-page call (the element's own value setter, then input/change events), and the live view link is
fetched while the watch is set up. Where the 6.0 s goes: session 0.8 · connect 2.1 · their page 0.5 · fill 0.9 · live
view 1.6.

**Hanakura (run 6):** a venue-own form with no robots.txt, approved by the founder on 2 Oct (Sasha 96). Filled with
nombre, teléfono (9 digits, their own validation), email, comensales 2, fecha 15/12/2026 (their dd/mm/yyyy), hora
21:00, menú (their default). Screenshot: `hanakura-readonly-filled.png`. Their page says online requests are
"confirmed by contacting you". So a real press there would come back as **"Sent — a request until they confirm"**, never
"✅ Booked", and the code says exactly that.

## Taps and seconds per booking — recorded
Each hand-over records `taps` (every pointer-down in the venue's page after Sasha finished), `press_to_answer_ms`,
`open_to_booked_s`, `ready_ms` and `timings_ms`. These go to `GET /api/booking/ops/handovers` → `per_engine`
(engine_library). Measured: **1 tap** on every completed booking.

## Not live yet (waiting on others)
1. **Two one-line hooks in the Sasha tab's files.** `routes.py` mounts the router; `gate.py` adds the guest page's
   token-keyed public path. They were asked for, and the Sasha tab has put both to the founder (a security exception
   in the gate). Until they're in, nothing here is reachable on Railway; it was rehearsed in-process against
   Browserbase.
2. **Sasha's channels:** offer the link in place of "Shall I send it?"; send "✅ Booked" on WhatsApp via `ON_BOOKED`;
   a "Take over" button in the ops console from `operator_url`.
3. **Real guests:** need a signed DPA (Browserbase Scale, or ask for one on Developer/Startup), then
   `BROWSERBASE_DPA=signed`.
4. **Ready time from Railway:** measured from Madrid to Frankfurt. Re-measure once mounted (the server's region
   decides the CDP round trips).
5. **The live view on a phone:** taps work. Browserbase says mobile keyboards aren't supported, which doesn't matter
   here because the guest types nothing. It takes ~1–2 s to paint the first frame.

## Follow-up (5 Oct 2026, after the hooks were mounted — Sasha 150, 7fdcbfc)
- **From Railway (europe-west4):** the link was ready in **2.7 s** (session 0.57 · connect 1.03 · page 0.12 · fill 0.07 ·
  live view 0.95), and **press → ✅ took 0.12 s**, 1 tap (TV-DF9158-3B, cancelled).
- **The founder's own finger, on his phone, in the EMBEDDED live view:** booked, 1 tap ("Reservar"), TV-4BD724-23,
  "Their page confirms it". My four failed presses there came from the browser automation's synthetic click, not from
  the view. "Open it full screen" stays only as a fallback.
- **Fixed on Railway:** the robots check's argument order (8599039).
- **Limit:** a deploy ends any hand-over in flight (in-memory records; the session closes when its connection drops).
  Don't deploy mid-booking.
