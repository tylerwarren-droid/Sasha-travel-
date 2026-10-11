# Sasha 233 — report (11 Oct 2026)

## Live
- main **717c48d** · Railway deploy 36381d17 SUCCESS (backend only; no frontend change in 233's last two commits)
- Commits: 2833e43 (named-platform exception, cards under their line, Thanks interrupts) · a7661b8 (robots `*`/`$`, crawl-delay) ·
  6c27d17 (services + price read back; memory as a jsonb object) · 717c48d (the spa guard fix, found live)
- Units 1885 OK (146 skipped, 1 expected failure) · S1 fingerprint byte-identical to 228's baseline (system 4e2560d4bdfd, tools 5334edda76ee, 24 tools)

## Gate (each deploy, service key `sk-ant-… bc1e05b8d099` — SASHA_GATE_ANTHROPIC_API_KEY still unset)
| deploy | commit | suites | $ |
|---|---|---|---|
| a42c1995 | a7661b8 | FAILED — credit balance exhausted (10 Oct) | — |
| 18418091 | a7661b8 | 149/149 (flight 21, basket 70, agent 21, voice 15, venue 20, whatsapp 1 [123], demo safety 1 [322]) | $1.05 / 243 calls |
| fc157120 | 6c27d17 | 149/149 (demo safety 329) | $1.07 / 246 calls |
| 36381d17 | 717c48d | 149/149 (demo safety 330) | $1.03 / 243 calls |

## Memory after a redeploy (041 applied)
1. 04:27 UTC, deploy 970dca0a: scratch guest 73eb13bc on /s2 — "a massage at a spa near Gran Vía, Saturday 5pm" → 5 cards.
   Row landed in `public.s2_memory` (written as a JSON string — fixed in 6c27d17, both shapes load).
2. Redeploy 18418091 (new process; nothing held in memory).
3. Reopen (`GET /api/agent/s2/memory`, production): **"Welcome back — we were looking at spa massage in Gran Vía, Madrid,
   Saturday 17 October 17:00. Want to carry on?"** with the 5 cards, cards marked on the line that showed them, and her pending question.

## Platforms — robots.txt read by the PRODUCTION server (through the site's booking proxy), 11 Oct
| platform | venue page / listing | open slots | page read on the server |
|---|---|---|---|
| Booksy | allowed (`/es-es/<id>_<slug>`, `/es-es/s/…`) | **disallowed** (`/*/l/book/`, `/*?&date=`) | 200 — schema.org `makesOffer` (name, price) |
| Treatwell | allowed (`/establecimiento/<slug>/`, `/establecimientos/…` except filters) · Crawl-delay 5 | **disallowed** (`/availability`) | 200 — schema.org `hasOfferCatalog` (name, ISO duration, low/high price) |
| Fresha | venue `/a/…` allowed | **disallowed** (`*booking/time*`, `*booking?menu*`) | not read (no Fresha venue in the proofs) |
| Rover | `/es/search/` allowed | `/sitters/availability/`, `/api/` disallowed | **403 Cloudflare "Just a moment…"** — not read, never worked around |

So: no platform lets a reader see free times. She reads the SERVICE and PRICE, hands the venue's page, and the person picks the time and presses Book.

## Proofs
- **Spa (Booksy) — BELMONT, C. de San Marcos 10 (off Gran Vía).** The page route on production, asked "a 60-minute relaxing massage", Sat 17 Oct 17:00, 1:
  > BELMONT takes bookings only through Booksy, so you make the final press — I can't press their button for you.
  > Their Booksy page lists “Masaje relajante / RELAX MASAJE 60 min” (60 min, €86) — that's the one to choose. Booksy doesn't show me which times are free; their page shows you.
  > Here's their Booksy page: pick Saturday 17 October at 5 pm, for 1, there. …

  Link: `https://booksy.com/es-es/153326_belmont_masajes_53009_madrid` (the listing; the slot page is robots-closed). Never opened, never approved.
- **The same spa through /s2 chat:** her read of BELMONT's own site found its WhatsApp, so DIRECT FIRST (232) drafted the WhatsApp
  ("…un masaje relajante de 60 minutos… sábado 17 de octubre a las 17:00…") and asked; Booksy is used only when it is their route.
- **Rover, "dog walker near Gran Vía":** robots allows the search; Cloudflare refuses the server (403). No Rover listings —
  today's behaviour stands (Places pet-care listings, their own contact routes).

## Found and fixed live
- The read never ran for a spa: its guard used `is_restaurant()`, which is TRUE for spas too (the founder's "real" set). Now `eating_out()`.
- Memory was stored as a JSON string inside jsonb (the pool's codec encodes again): now an object; old rows still load.

## Cleanup
Scratch guest 73eb13bc deleted (200); every account table in public + auth: 0 rows. `SASHA_PLATFORM_CHECK_ACCOUNTS` emptied
(staged, applies on the next deploy; the only listed account no longer exists).

## Still open
- **Gate key:** paste the `sasha-gate` key here → set as SASHA_GATE_ANTHROPIC_API_KEY (fingerprint only) → the next gate log's first line names it.
- **10 Oct breach:** robots.txt for the four platforms was fetched from the founder's machine (8 GETs, robots only) — reported in 687.
  Every platform request since has gone Railway-side (the site proxy → production).
