# S-17 — The signer is mounted, and a booking has somewhere to live

**Filed:** 28 September 2026. **Built and tested. Not committed, not pushed, the SQL not run.**

⛔ **Live submission stays off, and nothing here can send a real booking.** A `mode: "live"` intent is refused
before anything is recorded (`live_submit_disabled_in_this_build`), and the helper refuses live tasks on its
own as well. Only dry runs can be recorded, signed and reported, and a dry run stops before the venue's submit.

## 1. What was built

All of it lives in `backend/booking_signer/`, outside `backend/app/`, so a CTO sync never deletes it.

| file | what it does |
|---|---|
| `routes.py` | the eight `/api/booking/*` routes (§2) |
| `venues.py` | **the server builds the task.** The page sends only the booking's particulars (date, time, party, name, email, phone). This turns them into Psi's own formats (`October 2, 2026`, `8:00 PM`), the fields, the spec, the standing and the five read-back lines. The page never builds, edits or re-signs a task (contract §5.5), so it never chooses a selector, a pattern or a URL. **It matches the contract's §12 vector byte for byte**, tested |
| `outcome.py` | a verified report becomes the contract's §7 outcome and §8 words. `sent: false` records **no** outcome |
| `store.py` | a Postgres store (`DATABASE_URL`) and an in-memory test double. **The suite runs against both** |
| `account.py` | whose booking it is: always the one demo account (§4) |
| `sql/001_booking_storage.sql` | the storage, **drafted for you to run** (§3) |

**The mount** is three lines in `backend/app/main.py`. `CLAUDE.md` now has the Stage B re-apply command, which
is tested: it reproduces the file exactly and does nothing if the lines are already there. It also has the
Stage E probe. A forgotten mount shows as `{"detail":"Not Found"}` at `/api/booking/health`: loud, not a
silent loss.

## 2. The routes

| route | what it does |
|---|---|
| `GET /api/booking/health` | **Stage E probes this.** It shows the signer (configured, fingerprint, **matches the helper's pin `525f7027ed4f62b2`**), the storage (configured, provisioned, which tables are missing) and `live_issue_enabled: false` |
| `POST /api/booking/pairing/challenge` | issues a random challenge (43 characters), valid for 10 minutes, usable once |
| `POST /api/booking/pairing` | spends the challenge, verifies the helper's PAIR answer (contract §4), and stores the device **against the account** |
| `GET /api/booking/devices` | the account's paired devices |
| `POST /api/booking/intents` | **records the intent before anything is signed** (contract §3.5), and returns the read-back lines the user must hear |
| `POST /api/booking/intents/{id}/issue` | the user said yes, so the task is signed. **The approval is bound by the server** from what it recorded; the page supplies only *how* the user said yes and *what* they said. **One task per intent, ever**: a second attempt is `intent_already_issued`, and a retry is a new intent |
| `POST /api/booking/reports` | verifies the relayed report (paired device, the digest this server recorded, the device signature), then records the outcome and, **only if something was sent**, a reservation. A report re-sent on `PENDING` is recognised, never recorded twice |
| `GET /api/booking/reservations` | the account's reservations |

**Every refusal answers with its rule by name**, and so does missing storage: `503 storage_not_configured`
when there is no `DATABASE_URL`, and `503 storage_not_provisioned` when the tables are missing.

**Two guards the ticket did not ask for, both refusals only:**
- **The issue route refuses to sign with a key the helper does not pin** (`signing_key_not_pinned_in_helper`).
  Every installed helper would refuse such a task anyway; this says so at the source.
- **A bad or missing key does not stop Sasha from starting.** The contract says to refuse at startup, loudly.
  The signer logs the reason at startup, and every issue answers `503 signer_not_configured` with it. **A bad
  signing key must not take Sasha's chat and voice down with it**, so the rest of the backend keeps running.

## 3. The storage — for you to run in Sasha's Supabase SQL editor

**File:** `backend/booking_signer/sql/001_booking_storage.sql`. It creates six tables:

| table | holds |
|---|---|
| `booking_pairing_challenges` | challenges: one account, used once, short-lived |
| `booking_devices` | paired browsers, each bound to **one** account |
| `booking_intents` | the particulars as the user gave them, the unsigned task, and the exact words read back |
| `booking_tasks` | the issued task and **its digest**. The primary key is the intent, so there is one task per intent |
| `booking_reports` | reports that **passed** verification (failures are discarded, per contract §5.4). Append-only by use |
| **`reservations`** | ✅ **an absolute date, a clock time and the venue's timezone, the party, the status, the venue's reservation number, what the page said, and a link back to the intent and the task digest**, plus the trip's `itinerary_id` |

**Three things about it:**
- **Row-level security is on, with no policies.** The backend's direct connection bypasses it; Supabase's
  anon key, which ships in browser code, gets nothing. **These tables hold guests' names, emails and
  phones.**
- **It uses plain `CREATE TABLE`, not `IF NOT EXISTS`.** If a table of the same name already exists, it
  fails loudly instead of keeping a wrongly-shaped one. The file starts with a preview query that must return
  no rows.
- **`confirmed` is allowed as a status and written by nothing.** This surface cannot reach it (contract
  §8). It could only come from the venue's email, and Sasha receives no email yet (S-18).

⚠ **I could not check it against Sasha's live database: no session has access to it.** I did run it, start
to finish, against a throwaway **PostgreSQL 16.2**, and the whole route suite then passed against those
tables (§6). Running it a second time fails with `DuplicateTableError`, as intended.

## 4. ⚠ One demo account: what that means now, and what breaks when real accounts arrive

**Now:** `account_for(request)` returns the demo account (`11111111-…`, "Jon Peters"; a test holds it equal to
the chat store's `DEMO_USER_ID`) **for every caller**. There is no authentication, so **anyone who can reach
the API acts as that account**. They can:
- pair a browser;
- record an intent with whatever name, email and phone they type;
- have a **dry-run** task signed for any browser paired to that account;
- list its reservations (venue, date, time, party and status; no names).

**What stops that from harming anyone today:**
- **live is off in two places**;
- a task only runs inside a helper that receives it from a top-level `project.kanoe.ai` tab;
- a stranger's paired browser only ever runs tasks in the stranger's own browser;
- the guest's details come back only in the issue response, to whoever holds that intent's random id.

⚠ **This is not safe to leave once live is on.**

**When real accounts arrive:**
1. **`account.py` is the one place to change.** Every route asks `account_for(request)` and nothing else.
2. **Every browser paired in the meantime is bound to the demo account**, and the store refuses to pair a
   browser to a second account (`device_paired_to_another_account`). So a real user whose browser was paired
   during the demo **cannot pair it to their own account** until that demo row is revoked or deleted. Plan a
   one-off cleanup.
3. **Every task signed until then says `approval.by: "11111111-…"`.** The signed record of who said yes names
   the demo user, not the person. Those tasks are signed and cannot be rewritten; new ones will be right.
4. **Every intent, report and reservation row carries the demo account.** They have to be reassigned (only if
   you know whose they were, and today nothing records that) or left as demo history.
5. **`reservations.itinerary_id` points into the chat store's SQLite file**, which (S-18) does not survive a
   redeploy without a volume. Those links will dangle; there is no foreign key to stop it.

## 5. What is not built, and what you do

**Not built:**
- **The page.** Nothing on `project.kanoe.ai` opens the helper's port yet, pairs a browser, reads the words
  back, relays `RUN` or sends reports and `ACK`s. These routes are what that page will call.
- **Rate limiting on `/api/booking`.** The rate limiter lives in `backend/app/`, the CTO's file, and only
  covers metered services, so these routes aren't in it. They spend nothing, but anyone can write rows.
  Adding them there would be overwritten by the next CTO drop.
- **Email, and so `confirmed`** (S-18).

**What you do, in this order:**
1. **In Sasha's Supabase SQL editor:** run the preview query at the top of the SQL file (no rows), then the
   file, then the check at its end (six tables, each `rowsecurity = true`).
2. **Say "Push"** when you want it deployed. Railway builds from `main`, so pushing puts the mount live. Until
   step 1 is done, every booking route answers `503 storage_not_provisioned`; nothing breaks.
3. **Stage E probe:** `https://sasha-travel-production.up.railway.app/api/booking/health` should show
   `"matches_pinned": true` (the key you set on Railway) and `"provisioned": true`. If `configured` is false
   under `storage`, `DATABASE_URL` is not set on the Railway service. I cannot see whether it is.

## 6. Verification

- **63 tests pass, none skipped:**
  - the **31 new route tests** run against the in-memory store **and** a real PostgreSQL 16.2, whose tables
    were created by the drafted SQL, exactly as you will run it;
  - the 29 existing signer tests, parity and vectors;
  - the 3 Duffel tests.
- **Stage B import:** `from app.main import app` loads clean, with **50 routes** (42 before), including the
  eight `/api/booking/*`. With no key set locally, the signer logs its reason and the rest of the app still
  loads.
- **Tested on Python 3.9 locally; Railway runs 3.11.** Nothing used is version-specific.
- **The contract vector:** from the §12 particulars, the server builds exactly the vector's task, fields,
  spec, standing, read-back and both hashes. A task signed through the route verifies against the signer's
  public key.
- **What was deliberately exercised although no helper can produce it yet:** reports with `sent: true`, to
  pin the §7 mapping (`requested`, `declined`, `unreachable`, `failed`), each making a reservation with the
  right date, time, timezone, status, words and task link. **`confirmed` never appears.**

## 7. For the commit (Sasha repo)

```
backend/app/main.py                               (the mount: 3 lines)
backend/booking_signer/__init__.py                (docstring)
backend/booking_signer/account.py                 (new)
backend/booking_signer/outcome.py                 (new)
backend/booking_signer/routes.py                  (new)
backend/booking_signer/store.py                   (new)
backend/booking_signer/venues.py                  (new)
backend/booking_signer/sql/001_booking_storage.sql (new — drafted, not run)
backend/tests/test_booking_routes.py              (new)
CLAUDE.md                                         (Stage B re-apply, Stage E probe, item 4)
docs/sasha/S-17-signer-mounted.md
```

⚠ The Sasha repo already has one unpushed commit, `1f1d027` (S-18 + S-19). A push sends both.
