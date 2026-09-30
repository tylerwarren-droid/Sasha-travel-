# S-36 — The ladder, built. Report before committing

**Filed:** 30 September 2026. **Built and tested; not committed; nothing fetched, dialled or sent from here.**

## 0. Blunt answer

- **The chooser is built.**
  - Magellan reads a venue's own site (robots first) and/or its Google listing.
  - Every phone, email, WhatsApp link, booking form and platform is kept as **a fact with its source**: URL, moment,
    hash, snippet.
  - Sasha says what she can do: *"They have no booking form. I'll call them — or I can email and we wait. Which?"*
- **The phone rung dials the number READ.** The read-back says where it came from: *"I'll phone La Contra,
  +34915001122 — the number on their website, lacontra.test."* The three-a-day limit is unchanged and tested against
  read numbers.
- **The email rung is built:**
  - the exact email is read back, and **the yes binds to its hash**;
  - it goes out through Resend, and **"sent" only on HTTP 200 with an id** ("accepted by our mail service", never
    "delivered");
  - both addresses go to the venue: Sasha's `act-{id}@…` as reply-to, and the guest in CC;
  - replies arrive **svix-verified**, are **matched by address**, and are shown word for word; unmatched mail is
    quarantined.
- **WhatsApp works today.** Sasha writes the message and the guest sends it from their own phone.
- **Tests:** 163, including 41 new, in memory **and** on Postgres with `001`–`004`. Frontend `tsc` 0; 3 surfaces clean.
- ⚠ **Almost everything is inert until the founder does §3.** SQL `003` and `004` first: without them every new route
  answers `503 storage_not_provisioned`.

## 1. What was built

| file | what |
|---|---|
| `booking_signer/venue_read.py` | **Magellan's read.** It takes `tel:` links, JSON-LD `telephone`/`email`, `mailto:`, emails written in the text, `wa.me` / `api.whatsapp.com`, booking-shaped forms, and platform links and embeds. Guards: **robots first**, **public hosts only** (resolved and checked on every redirect hop), http(s) on standard ports, at most 3 pages (home plus 2 same-host contact/reservation pages), 2 MB, **never a booking platform's host** (recorded from the link alone). It also queries **Google Places (Text Search, New)** when `GOOGLE_PLACES_API_KEY` is set. No model is consulted anywhere |
| `booking_signer/ladder.py` | **the chooser**: rungs in ladder order, each with `available` or a plain-words `why_not`, and her sentence. A rung that cannot run is never offered. For email, a mailbox that says reservations beats a general one |
| `booking_signer/emailing.py` | compose (six languages, AI disclosure, "we can't agree to a deposit or a different time by email"); the read-back; **send, with Resend's answer read**; svix verification; the received-email fetch |
| `booking_signer/ladder_routes.py` | `POST /venues/read`, `GET /venues/read/{id}`, `POST /emails`, `POST /emails/{id}/send`, `GET /emails/{id}`, `POST /email/inbound` |
| `booking_signer/ladder_store.py` | memory and Postgres. One email per yes (claimed before Resend is asked); a 5-a-day email ceiling |
| `booking_signer/sql/004_ladder.sql` | `venue_reads`, `booking_emails`, `booking_email_replies`, `booking_email_quarantine`. **For the founder to run** |
| `calls.py` / `call_routes.py` (S-33) | `POST /calls` takes `read_id`, and the number is the read one. **`SASHA_PHONE_NUMBER` becomes caller ID** when set |
| `frontend/…/Ladder.tsx` | "Find how to book a venue": look up → facts with sources → her sentence → Phone / Email / WhatsApp |
| `tests/test_booking_ladder.py` | 41 tests: reading, guards, Places, the chooser's sentences, email hash, Resend answers, svix, inbound match and quarantine, calls on read numbers, the limit |

**Found and fixed while testing:**
1. The email picked `hola@` over `reservas@`. A reservations mailbox now wins, and the read-back names the one chosen.
2. **Recording Bland's or Resend's answer could crash with a 500 after the call or email had gone** (a duplicate id).
   It is now caught, logged, and said: *"Bland answered placed, but it could not be recorded"*.
3. A Places match is the top search result, so the label now names **which listing**: *"their Google listing (La
   Contra, Calle de la Contra 1, Madrid)"*. A wrong match is heard before the yes.

## 2. What lights up, and what stays inert until then

| when the founder sets… | what works | what stays inert |
|---|---|---|
| **SQL `003` + `004`** (Supabase) | every new route stores | — (without them: `503` everywhere new) |
| `GOOGLE_PLACES_API_KEY` | **La Contra's case**: a venue with no website, read from its listing | without it, only a website given by hand is read |
| `SASHA_CALLS_ENABLED=1` (+ `BLAND_API_KEY`, already set) | **the phone rung on read numbers**; 3 calls a day, across everyone | Bland's international calling needs a credit purchase (S-33 §4.1). Its refusal is shown in its own words |
| **`SASHA_PHONE_NUMBER`** | **caller ID only.** The number must first be **imported into Bland**, or Bland refuses (shown) | ⚠ **Receiving SMS (OpenTable's code) and answering callbacks are NOT built.** No Twilio webhook, no inbound agent. So her number is **never given out as a contact**: a number nobody answers is never handed over (S-32). That is the next build once the number exists and the OpenTable SMS test (S-35 §1.6) passes |
| `SASHA_EMAILS_ENABLED=1`, `SASHA_RESEND_API_KEY` (Sasha's own key; `RESEND_API_KEY` stays payments.py's), **`SASHA_EMAIL_FROM`** (a Resend-verified domain: SPF + DKIM), **`SASHA_INBOUND_DOMAIN`** (MX to Resend inbound), **`RESEND_WEBHOOK_SECRET`**, and Resend's inbound webhook pointed at `https://sasha-travel-production.up.railway.app/api/booking/email/inbound` | **the email rung**, and replies in the panel | until **all** are set, no email read-back is offered (the missing variable is named) |
| nothing | **WhatsApp**: `wa.me` with the message written; the guest sends it | — |

The form rung stays **Psi only**. An unmapped form is reported as a fact: *"They have a booking form, but I can't fill
it yet."*

## 3. The founder's order

1. Run `sql/003_phone_calls.sql`, then `sql/004_ladder.sql` (each has a preview and a guard, and ends with a
   checklist).
2. Set `GOOGLE_PLACES_API_KEY` (Places API (New) enabled; Text Search Enterprise SKU, because phone and website
   fields are billed there).
3. Set `SASHA_CALLS_ENABLED=1`. The 3-a-day ceiling stays until sign-in exists.
4. Email: verify a sending domain in Resend, add the inbound MX and webhook, and set the five variables in §2.
5. Commit and push, then check Stage E: `/api/booking/health` → `ladder` shows what is ready and what is not, named.

## 4. What is genuinely in the way

1. **Nobody signs in.** Any public venue number is now callable by anyone who finds the page. **The 3-a-day ceiling is
   the brake** (5 a day for email, my default; founder's to change). A crafted website could publish any number and
   be read. The ceiling bounds it, and the read-back names the source. The real fix is sign-in.
2. **Numbers written as plain text are not read.** Only `tel:`, JSON-LD and Places. A number in running text is easy
   to misread (a fax, a VAT id), so v1 leaves it. Many small sites show it that way, and **Places is the fallback**.
3. **The OpenTable SMS rung** needs the number, the SMS webhook and the S-35 §1.6 test. Not built.
4. **The non-English call and email templates** need a native speaker before real venues get them.
5. **The venv on this machine was damaged overnight.** macOS's periodic `/tmp` cleanup removed files from it. It was
   rebuilt from `requirements.txt` before these tests ran. No repo effect.

## 5. Checks

**Backend:**
- `test_booking_ladder` (41), `test_booking_calls` (46) and the four earlier suites: **163 OK, 0 skipped**, on memory
  and Postgres;
- `003` and `004` each refuse a second run.

**Frontend:**
- `tsc` 0 errors;
- `check-outcome-surfaces`: 3 surfaces clean, 5 fixtures caught;
- eslint clean on `Ladder.tsx` and `PhoneCall.tsx`;
- `page.tsx` has the same 4 problems as HEAD.

**Not run:** `npm run build`; any live read, call or email. Nothing was fetched from this machine.
