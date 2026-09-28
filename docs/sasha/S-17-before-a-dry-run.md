# S-17 — What remains before a dry run works end to end

**Filed:** 28 September 2026, straight after the push (`5f247fb`, deployed). **Nothing here has been changed
by this session; each step is the founder's, except step 4, which is the next build ticket.**

## Where things stand, measured

`GET https://sasha-travel-production.up.railway.app/api/booking/health`, answered by the new deploy:

| part | health says | meaning |
|---|---|---|
| the mount | `"mounted": true` | ✅ the eight routes are live |
| the signer | `"configured": false` — *"SASHA_BOOKING_TASK_SIGNING_KEY is not set"* | ⛔ **the service answering this domain has no signing key.** It may be set on another service or environment |
| the storage | `"configured": true`, `"provisioned": false`, `"error": "OSError"` | ⛔ **`DATABASE_URL` IS set** (my earlier inference that it probably was not was wrong), **but the connection fails before it reaches the database** |
| the database itself | applied, and re-checked read-only after the push: 5 tables with RLS, `booking_attempts.status` no default, 4 new columns, demo user | ✅ |

**Why the storage fails, as far as I can tell from here:** through a public resolver (1.1.1.1),
`db.xlqtveusyfpffaejegiq.supabase.co` has **only an IPv6 address** (AAAA, no A record). A Railway service
generally cannot reach an IPv6-only host, and that fails as exactly this kind of `OSError`. **So `DATABASE_URL`
most likely points at the direct host and must be the pooler's instead**, which has IPv4. The value itself was
not seen.

## The steps, in order

### 1 · Put the signing key on the service that answers this domain  *(founder, Railway, ~2 minutes)*
1. Railway → the project → the service whose **Settings → Networking** shows
   **`sasha-travel-production.up.railway.app`** → **Variables**, in the **production** environment.
2. Look for **`SASHA_BOOKING_TASK_SIGNING_KEY`**.
   - **Absent:** add it with the value you set before (base64 of the 32-byte seed). The value never goes into
     chat.
   - **Present:** it was not applied to this deploy. Press **Redeploy** from the latest deployment's ⋯ menu.
3. Railway redeploys. The health route must then show under `signer`: `"configured": true`,
   `"fingerprint": "525f7027ed4f62b2"`, **`"matches_pinned": true`**.
   - `matches_pinned: false` with another fingerprint means that value is a **different key** from the one the
     helper pins, and every task it signed would be refused.

### 2 · Point `DATABASE_URL` at the pooler  *(founder, Supabase then Railway, ~3 minutes)*
1. Supabase → project **`xlqtveusyfpffaejegiq`** → the **Connect** button at the top → **Transaction pooler**
   (port **6543**). Copy the URI. The host is `aws-0-eu-west-1.pooler.supabase.com` and the user is
   `postgres.xlqtveusyfpffaejegiq`.
2. Put the database password in place of `[YOUR-PASSWORD]`. If you don't have it: **Project Settings →
   Database → Reset database password**. Nothing working today depends on the old one: the live backend uses
   the REST key, and the current `DATABASE_URL` cannot connect anyway.
3. Railway → the same service → Variables → **`DATABASE_URL`** = that URI (replace the current value). Railway
   redeploys.
4. The health route must then show under `storage`: `"configured": true`, **`"provisioned": true`**,
   `"missing": []`.

**Check steps 1–2 with one line in Terminal:**
```
curl -s https://sasha-travel-production.up.railway.app/api/booking/health
```

### 3 · Load the helper in Chrome  *(founder, ~1 minute)*
1. Chrome → `chrome://extensions` → **Developer mode** on (top right) → **Load unpacked** → choose
   **`/Users/tylerwarren/Developer/Applied Diligence/extension-sasha`**.
2. **Write down the ID** Chrome shows under "Sasha booking helper". Its manifest pins no `key`, so **this ID
   belongs to this installation**, and the page in step 4 must be given it.
3. It already pins the signing key (fingerprint `525f7027ed4f62b2`) and only accepts connections from
   `https://project.kanoe.ai`. Live submission is off in it.

### 4 · The booking page  *(NOT BUILT — the next ticket)*
**Nothing on `project.kanoe.ai` talks to the helper or to these routes yet. Without a page, there is no dry
run.** The helper accepts only a **top-level tab** on `https://project.kanoe.ai`, never the Demo tab (it frames
Sasha, so it is refused; option B, S-12).

What the page must do, in order (contract §4–§7; the routes are live):
1. connect to the helper by its ID from step 3, and send `HELLO`, which gives the `device_id`;
2. if that device is not in `GET /api/booking/devices`: `POST /pairing/challenge`, then `PAIR` to the
   helper, then `POST /pairing` with its answer;
3. `POST /intents` with venue `restaurante-psi`, the date, time, party, name, email and phone, and `mode:
   "dry_run"`;
4. **show the five read-back lines**; the user presses **Yes**;
5. `POST /intents/{id}/issue` with the `device_id` and `approval: {how: "button"}`, which returns
   `{payload, signature}`;
6. send `RUN` to the helper with exactly those, and show the `PROGRESS` phases;
7. relay the `REPORT` to `POST /reports`, show its `say`, then send `ACK` to the helper;
8. on reconnect, send `PENDING`.

It is a Next.js page in `frontend/` (the `sasha-heygen` Vercel project serves `project.kanoe.ai`). **Say "go" and
it is the next S-ticket**, dry-run only.

### 5 · The dry run itself  *(founder, once 1–4 are done)*
1. Open the page in **its own tab** on `https://project.kanoe.ai`.
2. Book **Restaurante Psi** for a date **at least 24 hours ahead**, **Monday to Saturday**, at a time **Psi serves
   in 30-minute steps** (12:30–15:00 or 19:30–22:00). Any name, email and phone: a dry run sends nothing.
3. Listen to or read the five lines, then press **Yes**.
4. The **first time only**, the helper names Psi's site and Chrome asks for permission: click **Allow**.
5. The helper opens Psi's page in a **background tab**, fills it, checks every value against what you approved,
   and **stops before sending**. The page says: *"I've filled in their form on your computer and stopped just
   before sending, as planned. Nothing was sent."*
6. **What proves it worked:**
   - `GET /api/booking/reservations` is still **empty**, because nothing was sent.
   - In Supabase: one `trips` row (**"Sasha bookings"**, owned by the demo user), one **`trip_items`** row
     with `status = 'pending'` and the right `date_time`, one `booking_intents` row (`reported`), one
     `booking_tasks` row and one `booking_reports` row.
   - **No `booking_attempts` row.**

## Not blocking a dry run, but before any real guest's details are stored

- **Rotate the committed `service_role` key** (`S-17-which-database.md` §1). It is on GitHub, valid until 2036,
  and it opens everything in this project, including the guest names, emails and phones these tables will hold.
- **Live stays off** in both places. Turning it on is a founder decision and a new helper build.
