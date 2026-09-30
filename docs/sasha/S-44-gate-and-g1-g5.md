# S-44 — The booking gate, and S-41's G1–G5. Built; report before committing

**Filed:** 30 September 2026. **Built and tested; not committed.**

**Also in this session:**
- `SASHA_CALLS_ENABLED=0` on production at 13:29; health showed `calls.enabled: false` from 13:30:47.
- The Berlin fix and the email-key rename were committed and pushed (`f205c7f`, `ce0bbd4`).
- Measurement run 3 seeded all three cities, then crashed on its first database writes (§4).

## 0. Blunt answer

- **No anonymous caller can reach a booking route any more.** Every `/api/booking/*` route needs the booking key,
  except two:
  - `/health`, which reports configuration only;
  - the svix-signed email webhook.
- **The browser never holds the key.** The booking page talks to the frontend's own server. That server checks the
  founder's signed session cookie, and only then adds the key.
- **G1–G5 are done:**
  - **G1:** the dry-run banner covers the form helper only, and the phone panel says *"This places a REAL phone call"*.
  - **G2:** the guest picks the number, each shown with where it was read.
  - **G3:** the server reads finished calls itself, every minute.
  - **G4:** she asks for the name or reference, and it is stored **only if the venue actually said it**.
  - **G5:** reservations list phone, email and link bookings, with the venue's words and reference.
- **Tests:** backend **204 OK** (Postgres included); frontend `tsc` 0; 4 page surfaces clean; `page.tsx` has the
  same 4 lint problems as HEAD.
- ⚠ **Four variables the founder sets himself** (§3) before it works. Until then the booking page shows *"sign in"*,
  or *"not configured"*: **closed, not open.**

## 1. The gate

| layer | what it does |
|---|---|
| **backend** `booking_signer/gate.py` | every `/api/booking/*` route (all routers included under it) requires `x-sasha-booking-key` = `SASHA_BOOKING_KEY`, compared in constant time. **Exempt:** `GET /health`, and `POST /email/inbound` (its own svix check). ⛔ **If `SASHA_BOOKING_KEY` is unset, every gated route answers 503: fails closed** |
| **frontend** `app/api/booking-proxy/[...path]/route.ts` | the booking page's only way in. **No valid founder session → 401, and nothing reaches the backend.** It adds the key server-side, forwards only `/api/booking/…` paths, and lifts FastAPI's `detail` so the page reads `{rule, message}` |
| **frontend** `lib/founder-session.ts` + `app/api/founder-session/route.ts` | the passphrase (`FOUNDER_PASSPHRASE`) → a **signed HttpOnly, Secure, SameSite=Strict** cookie for 12 hours (HMAC with `FOUNDER_SESSION_SECRET`). **Fails closed** if either secret is unset or short |
| **frontend** `FounderGate.tsx` | signed out, `/booking-helper` is a passphrase field and nothing else |

Tests (`test_booking_gate.py`):
- 12 routes × (no key, wrong key) → 401;
- no server key → 503;
- the right key passes the gate;
- health and the webhook are exempt.

Every existing suite now runs with the key.

## 2. G1–G5

| # | fix | where | proof |
|---|---|---|---|
| G1 | the page heading is *"Book a table"*; the dry-run banner is scoped to the **form helper** steps; the phone panel opens with *"⚠ This places a REAL phone call…"* | `page.tsx`, `PhoneCall.tsx` | — |
| G2 | choosing Phone lists **every read number, each with its source**; nothing is called until one is chosen; its `fact_index` goes to the server | `Ladder.tsx` → `PhoneCall.tsx` → `POST /calls` (already honoured `fact_index`) | — |
| G3 | **a server sweeper**, every 60 s: each `placed` call is read from Bland and recorded once it has finished. `record_reading` refuses a second time, so the page's GET and the sweeper can never both record. State lives in the database, so a redeploy loses nothing | `call_routes.sweep_once`, started at app startup (`SASHA_CALL_SWEEP`, on by default) | test: nothing recorded while the call is on; recorded once when finished; never twice |
| G4 | the brief: *"ask what name or reference the booking is held under"*. The reader returns `reference`, **kept only if it appears verbatim in what the venue said**. On a yes it goes onto `trip_items.booking_reference`; a reference the venue never said is dropped | `calls.py`, `call_store.py` | tests: "Johnson" stored from the venue's own line; an invented "ABC123" never stored |
| G5 | `GET /reservations` lists **every channel** (`channel`: form / phone / email / link), with date, time, party, venue, status words, `booking_reference` and **the venue's own words** | `store.py` reservations query; `routes.py` status words | test (Postgres): a confirmed call listed with `phone`, date, time, party, "Johnson" and their words |

⚠ **G5's limit:** the list is `/api/booking/reservations`, shown on the booking page. The product's *YouPanel* reads
`/api/trips` from the chat store, which is `backend/app/`, replaced wholesale by every CTO drop. Wiring it there is
the CTO's surface. **Not done.**

## 3. What the founder sets (names only: values never in chat, rule 17)

| where | variable | what |
|---|---|---|
| **Railway** (production service "Sasha-travel-") | `SASHA_BOOKING_KEY` | a long random string |
| **Vercel** (the frontend project) | `SASHA_BOOKING_KEY` | **the same string** |
| **Vercel** | `FOUNDER_PASSPHRASE` | 12+ characters, what you type at `/booking-helper` |
| **Vercel** | `FOUNDER_SESSION_SECRET` | 32+ random characters (signs the cookie) |

**Order:** set all four, commit and push (Railway and Vercel both redeploy), then sign in at `/booking-helper`.

## 4. The measurement: the crash, and its fix (uncommitted)

**Run `7af2692d`:**
- all three boxes: Madrid (locality), Lisbon (county), **Berlin (region)**; 340 drawn per city, **1,020 in total**;
- then *"asyncpg … another operation is in progress"*: the parallel reads shared **one** database connection;
- it stored 1 host and 0 pages, and the run is **unfinished**, so the scorer never exports it;
- up to 10 sites (the first parallel batch) may have been read and their results lost.

**Fix:** the reads stay parallel, and the writes take turns behind a lock (`store_host`). A test fails if two writes
ever overlap. The service is disconnected. **Re-running needs this commit.**

## 5. Step 3, the first real booking: what it needs

1. §3's four variables set, this commit pushed and deployed, and a sign-in that works.
2. **The founder's phone number.** Sasha does not store it: onboarding keeps only a browser draft, and the booking
   page's profile is the demo "Jon Peters". **He types it into the call form**, and it is given to La Contra only if
   they ask (the read-back says so).
3. Calls on (`SASHA_CALLS_ENABLED=1`) for the session only, then off again.
