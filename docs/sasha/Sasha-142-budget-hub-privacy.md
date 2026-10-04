# Sasha 142: the budget, the hub, and the public demo

*4 Oct 2026. Commits:*
- *cd27a17: the privacy fix;*
- *8443358: the hub and the root;*
- *f72174d: the second Places loop;*
- *this commit: hub polish and this report.*

## 1. Google: the budget, and a second loop

**Budget, set via gcloud** (the Cloud Billing Budget API had to be enabled first, on `applied-diligence-site-project`)
- Name: "Kanoe monthly €30 (Sasha 142)", on billing account `017700-99478D-BA4C53`, id `9c3b1b30-…`.
- €30 a month, with alerts at 50%, 90% and 100% of actual spend, and at 100% of forecast spend.
- **It counts spend BEFORE credits** (`EXCLUDE_ALL_CREDITS`). Counting after credits, the trial credit would hide
  everything, and it would never fire.
- **Who is emailed:** the billing account's admins (the default).
- **Expect an alert now:** October's gross spend is already above €30 (3–4 Oct).

**The hourly Places count after the Sasha 141 deploy did not reach 0**

| When (UTC) | GetPlace calls per 10 minutes |
|---|---|
| Before the deploy | 17–19 |
| After it (~09:00) | 8–13 |

- **Cause:** a day-before reminder counts as "due" from the evening before until the booking starts. Every minute, the
  tick re-read every phone booking's name, and only then found the reminder "already sent".
- **Fixed (f72174d):** the status is re-read without names, and names are composed only after the send's claim
  succeeds. Test: `test_places_cost_s141.AlreadySentCostsNothing`.
- **Expect:** ≈ 0 overnight. Re-check with `s142_10m.py` (scratchpad).

## 2. The privacy finding (CR's): fixed, live

- **The leak:** a web visitor who wasn't signed in WAS the founder's account (`DEMO_USER_ID` = 11111111-…), so a stranger
  could see his itinerary.
- **Now:** no sign-in means `PUBLIC_DEMO_ID` (00000000-0000-4000-8000-0000000d3e00), its own empty account.
- **The founder's web chat keeps his account** through `/api/sasha/…`, a same-origin pass-through.
  - It checks his cookie, then adds `x-sasha-session: founder` and the booking key.
  - The backend accepts that header only with the key.
  - A visitor calling it gets 401 (checked live).
- **What no longer runs for the public demo:** the products, which are now told `signed_in=False`, and the itinerary
  questions. The voice page's fallback is the public demo too.
- **Verified live:** an anonymous "what is my itinerary this week?" names none of his venues.
- **Not yet routed through the pass-through:** the voice page (`/voice`). For the founder it now acts as the public demo
  there.

## 3. The site

- **project.kanoe.ai (/)** is the Sasha Vietnam site: the same page as /vietnam, which still works.
  - Since Sasha 123 (3 Oct), the root had been the new six-tab site.
  - The page before that, kept in /archive, was the investor portal, not Vietnam.
- **project.kanoe.ai/agapi** is the hub: AgAPI on top (the four agents, the status line, the WhatsApp words), then five
  tabs: Sasha (Vietnam) · Applied Diligence · CampusMe · RelocateMe · EspañaMe.
  - **Copy:** EU 152's `docs/business/agapi-hub-pitches.md`, as typed data (`frontend/app/agapi/content.ts`).
  - **Every claim is marked:** ✅, 🧪, ○ or ◐.
  - **Every figure carries [S], [V], [E] or [F].** Each [S] or [V] figure links its source from EU's research, ● read at
    source or ○ seen in a search summary.
  - Vendor ranges are shown as ranges; SOMs as their variables.
  - A tab is shown only when its `ready` flag is set. All five are in.
  - **Demo links:** CR's /preview pages (CampusMe, RelocateMe, EspañaMe), applieddiligence.com, and the root for Sasha.
- **Tests:** `npm test` now runs `scripts/agapi-hub.test.mjs` as well (17 pass).
- **Kept, not removed:** the six-tab pages (/sasha, /applied-diligence, /campusme, /relocation, /spain-services). Their
  AgAPI tab now leads to /agapi. **Founder:** say if they should go.

## 4. Bland

- Waiting for the founder's "topped up". Then I re-read the balance and place one test call to the test line.

## 5. Still open (CR's rehearsal, mine)

1. The web hotel hand-off ("a hotel in Madrid … 2027-03-01 to 2027-03-04 for 1") answers "brief connection issue".
2. The product tab's empty opening turn shows an empty user bubble.
