# CR 22 · THE LAST PRESS — findings before building (5 Oct 2026)

How it was found: public vendor docs and venues' own published links only, robots.txt first. No booking platform's
booking page was opened, probed or submitted; every template below is **unverified** until the founder opens one real
link once (`verify-once.json`). Data: `engines-hotels.json`, `engines-restaurants-spas.json`. It fits the Sasha tab's
existing `booking_signer/slot_link.py` (S-37 `Recipe` with `observed` / `verified`; Sasha 138 `HOTEL_PREFILL`) — the
library is DATA for that, not a second system.

## 1 · The prefill library — what one link can do, per engine

| Engine | Kind | Prefills (from the source) | Taps left after opening | Basis | In our cities |
|---|---|---|---|---|---|
| **TableCheck** | restaurant | date, time, party | ~6 (≈3 with partner SSO) | **documented** | Hoi An ✓ |
| **SevenRooms** | restaurant | date, time, party | ~7 | seen in links, undocumented; ToS bans automation & framing | Madrid ✓ Lisbon ✓ |
| CoverManager · Zenchef · TheFork · OpenTable · Restoo · Quandoo | restaurant | — (venue page only) | ~8–9 | no public prefill | Madrid/Lisbon ✓ |
| **Mews** | hotel | in, out, adults, children, promo | ~10–13 | **documented** | Lisbon (vendor claim) |
| **SynXis** | hotel | in, out, adults, children, rooms, promo | ~10–13 | **documented** | — |
| **Cloudbeds** | hotel | in, out, adults, kids, promo | ~10–13 | **documented** | Hoi An ✓ |
| **WebHotelier · Bookassist** | hotel | in, out, adults, children, rooms (+promo) | ~10–13 | **documented** | — |
| **Guestcentric** | hotel | in, nights, rooms, adults, children | ~10–13 | documented (2012) | Lisbon ✓ |
| **SiteMinder** | hotel | in, out, adults, children | ~10–13 | seen in links | Hoi An ✓ |
| **Omnibees** | hotel | in, out, rooms, adults, children | ~10–13 | seen in links | Lisbon ✓ |
| Simple Booking · RoomCloud | hotel | in, out, adults (+promo) | ~10–13 | links / 2015 manual | — |
| Little Hotelier · D-EDGE · Neobookings · eZee · Avirato · Hotetec | hotel | — (dates by hand) | ~13–16 | none public | Madrid (D-EDGE, Neobookings, Avirato) |
| Fresha · Treatwell · Booksy · Mindbody · SimplyBook.me | spa | — (Fresha/SimplyBook: a service, venue-made links) | ~7–9 | none | Hoi An (Fresha) ✓ Madrid ✓ |

**What it means.** A link alone gets a restaurant to ~6–7 taps at best (TableCheck, SevenRooms) and a hotel to ~10–13
(room, rate, guest details, card, terms) — because **no engine takes guest details or payment in a URL** (TableCheck's
only route is a whitelisted partner SSO). The biggest Madrid restaurant engines (CoverManager, TheFork) publish no
prefill at all. Corrections to the Sasha tab's code: Cloudbeds children is `kids` (not `adults`-only); Little Hotelier's
date parameters are not supported by any source; SynXis needs `chain=`; Mews adds `mewsChildCount`/`mewsVoucherCode`.
Neobookings advertises an MCP/API for AI agents — a partner route, not a link, worth a founder conversation.

**Verification (the founder, once each):** six real links in our cities (`verify-once.json`): TableCheck (Hill Station,
Hoi An), SevenRooms (EVOK Brach, Madrid), Cloudbeds (Fuse Old Town, Hoi An), SiteMinder (ÊMM, Hoi An), Omnibees (Masa
Campo Grande, Lisbon), Guestcentric (Emporium Lisbon Suites). He answers filled / not filled; only then does a recipe get
`verified` and Sasha say "your table is filled in".

## 2 · The live hand-over — prototype on OUR test venue only

`handover-proto.mjs`: a browser opens our test venue's own form, fills it from Sasha's draft (date, time, party, name,
email, phone, note — the honeypot left alone) and **stops before Book**. Result (iPhone viewport): 7/7 visible fields
filled, 0 required left, no challenge, **1 tap left (Book)**, nothing submitted (`handover-test-venue-filled.png`).

Not built, and why:
- **The live view itself needs a cloud-browser provider** (e.g. Browserbase's live-view URL): none is configured on
  Railway — a founder decision (cost, a data-processing agreement: the guest's name and phone pass through it).
- **CAPTCHA escalation could not be measured honestly on our venue** (it has none). Measuring it means running cloud
  sessions against third-party sites — not done without a decision, and never against a platform.

Where it would be fine vs break terms:
- ✅ **A venue's OWN website form** (its robots allow, its terms don't forbid automation): Sasha fills, the guest presses
  in the live view — the human step stays human. This is the case for a large share of small venues.
- ⛔ **Platform booking pages** — SevenRooms (bans robots and framing), TheFork (bans robots/automatic devices), Fresha
  (bans scraping; robots disallow booking paths), and platforms generally: a cloud browser filling their page is the
  automated access their terms forbid, live view or not. Use their deep link (or a partner API) instead.
- ⛔ **Any payment step** (hotels, deposits): a card typed into a browser WE host puts Kanoe in PCI scope. Never hand a
  payment step through a cloud session; the guest pays on the engine's own page in their own browser.
- ⚠ A CAPTCHA shown in the live view and solved by the guest is still a human solving it — but on a platform it remains
  automated access; on a venue's own site it's fine.

## 3 · "Taps to book" — the metric

`taps_to_book` = the guest's taps from opening Sasha's message/link to the venue's confirmation: 1 (open) + selections
left + fields left + checkboxes + the Book press. Recorded per booking with `how`: `measured` (our test venue, a
founder-verified recipe, a live hand-over) or `estimated` (from the library above), and aggregated per engine. Where it
lives: the Sasha tab's ops log (asked; theirs to render — I'd compute it).

Today's floor, honestly: **1 tap** (live hand-over on a venue's own form) · **~6–7** (TableCheck/SevenRooms link) ·
**~8–9** (a restaurant engine's page) · **~10–13** (a hotel engine with prefilled dates) · **~13–16** (a hotel engine
without prefill).

## Recommended next steps (for the founder)
1. Open the six `verify-once` links once each; promote the ones that fill to verified recipes in `slot_link.py`.
2. Decide on a cloud-browser provider for the live hand-over on venues' own forms — and its DPA.
3. Explore partner routes where they exist: TableCheck (guest-details SSO, "concierge services" audience), Neobookings
   (MCP/API for AI agents), SevenRooms / TheFork / OpenTable partner programmes — the only way to below ~6 taps on
   platforms within their terms.
