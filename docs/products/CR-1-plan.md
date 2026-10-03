# CR 1 — CampusMe and Spain relocation on Sasha's chassis: the one-page plan

*Fourth build tab, 3 Oct 2026. Demo: Wed 7 Oct. Sources read first: `docs/business/kanoe-site-scope.md` (EU 134/135),
S-77, AD `P807on` (CampusMe scout), AD `P807lt`, `P807lu`, `P807jr/js/jw/id/jy` (EX-01), AD
`docs/relocation/ex01-field-map-2026-09-23.json`, `lib/agapi/relocation/visa-form.ts`. Live reads today:
`docs/campusme/reads/` (each with its sha256 in `docs/campusme/READS.md`).*

## What changed after reading (facts that shape the build)

1. **The Slate calendar's own data endpoints were found and read** (robots read first: `User-agent: *` allowed on both hosts):
   - **Yale:** `/portal/widget/event?…&cmd=event_dates` (JSON) and `cmd=event_list` (HTML). One day, 14 Oct, gave
     "Campus Tour 9:00 AM–10:00 AM · Spaces Available: 51" and three more sessions, plus a `/register/?id=…` form.
   - **Penn:** `/portal/campus-visit?cmd=getDates` and `cmd=getEvents` → "Morning Tour 10:15 AM … Full".
   - That's one reader with **two Slate variants** (portal widget; register datepicker).
2. ⚠ **Neither school has published April 2027.** Yale's calendar ends 12 Dec 2026 and Penn's 7 Dec. So "visits in April"
   honestly answers *"Yale and Penn haven't opened April yet; I'll watch and tell you the day they do"*, then shows the
   nearest real sessions. The demo asks for a month that is open (Oct/Nov), and shows the April answer as the honesty beat.
3. **No CAPTCHA marker in either served form.** Yale's form has 2 pages, Penn's 1. Both render parts by JS, so a CAPTCHA
   can't be ruled out until the form is pressed.
4. **Founder model (P807on §4, 1 Oct): "prepare everything; a person presses."** CampusMe therefore ships **no
   submit**. It reads, fills the hand-over, and the parent (or our staff) presses. A real registration happens only on
   the founder's explicit approval, by a person.
5. **EX-01 is lodged on paper at a Spanish consulate for an initial application** (the form's footnote 6). Renewals are
   electronic. So a "cita previa page" is **the consulate's own appointment page** (initial) or the Extranjería cita page
   (a TIE after arrival), **located from a fetched official page, never composed, never pressed by us** ("locate, never
   book", P807id). Neither system prefills from a link. The honest hand-over is the official page plus every value the
   person types, in order, ready to copy.
6. ⚠ **The 44 / 1 / 51 split conflicts with AD's own test** (43 / 8 / 45 under `classifyEx01Field`). The difference is the
   Dehú **CONSIENTO** box, which plain classification counts as "fillable". **I use the 8-irreducible set:** never tick
   consent or intent, never sign. My screen prints counts derived from my mapping, never a typed 44.

## Build (all repo-only; nothing in a CTO-shipped file)

| Part | Where | Chassis reused |
|---|---|---|
| **Mode switch** on the one sandbox number: "campus…" / "relocation…" enter a mode; "sasha" / "exit" leave it. One guarded hook in `guest_whatsapp.turn()`, marked `CR 1 products` | `backend/products/whatsapp.py` | the linked-sender gate, `Out`, `deliver`, STOP and reminders words, the secret guard |
| **Slate reader:** a school registry (Yale, Penn proven; Williams and Pomona configured, unproven), `dates(month)`, `sessions(day)` with spaces, robots and terms per host, polite pacing, raw reads saved with sha256 | `backend/products/campus/slate.py` | S-38 reading rules |
| **CampusMe turn:** parse schools, month and student → cards (school, day, session, spaces) → pick → student profile from the vault → **one yes** on a hash-bound read-back → the hand-over page (the school's form link plus each answer in the form's order) → "Reply REGISTERED" → a `trip_items` row (`experience`, status pending) gives calendar, reminders and "You" for free → the school's confirmation email, forwarded, gives "confirmed in writing" (Sasha 118) | `campus/turn.py`, `campus/profile.py` | `yes.py`, the vault (`identifier` items, one use per yes), the S-79 calendar outbox, S-83 reminders, Sasha 118 written confirmation |
| **April watch:** a month not yet published is recorded; a daily read (the S-83 loop) messages the parent the day it opens | `campus/watch.py` | the S-83 tick and quiet hours |
| **Relocation intake:** conversational questions, one fact at a time, each stored as `{value, source, read_on}`, plus a passport **photo** read by the model, each value read back for the person's "yes, that's right" before it counts | `relocation/intake.py`, `relocation/docread.py` | inbound `MediaUrl0` (new: today the chassis refuses media) |
| **EX-01 fill:** the official PDF (sha256 `3fd926b6…`), a mapping fixture (field → fact, with basis) and pypdf. ⛔ Raises on any value aimed at a signature, consent or intent box | `relocation/ex01.py`, `relocation/ex01_map.json` | AD's `prepareField` rules, ported |
| **Reviewer screen:** a row per field, five distinct states, plus a **checker agent** (deterministic: formats, cross-fact agreement, staleness, a source on every value) whose verdict and reason show on each row. "Not a filing service" on the screen | `frontend/app/relocation-file/[id]` + `GET /api/products/relocation/{id}` | P807lu design |
| **Sign → cita → checklist → reminders:** "print, sign by hand at FIRMA"; the official appointment page plus values to copy; a checklist with a source per item; reminders through S-83 | `relocation/after.py` | S-83 |

**Storage:** migration **`028_products.sql`** (`product_cases`: id, product, account, wa key, state jsonb, expires_at;
RLS on, no policies, service role only, 30-day expiry). Posted to `tab_messages` for chat to apply on sasha-prod. Until
it's applied, the memory store runs and the products say so.

**Routes avoid the site build:** `/campus-handover/[id]` and `/relocation-file/[id]`, never `/campusme` or
`/relocation/reviewer`, which are the Sasha tab's site pages (§9.4).

## Rules I hold
- Read-only on every university until the founder approves one real registration, which a person presses.
- Never submit to a government site, never sign, never tick consent or intent, never hold a Cl@ve.
- Never fetch a bot-protected host from the founder's network; Slate pages are read on the institution's own domain,
  robots first, ≤1 request / 8 s.
- **The model is called on WhatsApp only to read a document the person sent**, and only in relocation mode. Each value
  is confirmed by the person. Everything else stays deterministic, as in Sasha.
- **Production needs one WhatsApp number per product** (Meta: one business display name per number). The sandbox mode
  switch is a demo device only.

## Order and milestones (a readout to `tab_messages` after each)
- **M1 (Sat–Sun): CampusMe** reader + turn + hand-over, proven on Yale and Penn live (read-only), tests green, pushed.
- **M2 (Mon): relocation** intake + EX-01 fill + reviewer screen, tests green, pushed.
- **M3 (Tue): sign / cita / checklist / reminders**, the doc reader, the demo script, a dress rehearsal on the sandbox.
- **Honest scope:** CR 1 sized this at 8–10 days; the demo is in 4. What isn't true by Wednesday is written as "not yet"
  in the readout, not shown.
