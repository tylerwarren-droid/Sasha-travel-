# S-17 — Sasha's database: what is established, and the SQL in one paste

**Filed:** 28 September 2026, after the S-17 commit (`a0b08ac`). **Nothing pushed. No key or connection string is
printed anywhere in this file.**

## 1. What is established, from this end

| question | answer | how it was established |
|---|---|---|
| Which project? | **`xlqtveusyfpffaejegiq`** | named in `README.md:27`, `docs/new_chat_handoff.md:51` ("project: SASHA"), `docs/session_current.md:171`, and **hard-coded** in `frontend/app/api/onboarding/save/route.ts:3` |
| Can chat's connector see it? | ⚠ **Partly. It does not LIST it, but it FETCHES it by id.** `list_organizations` returns only `AppliedDiligence.AI` (`spwmfxsnrcnesptkagvx`), yet `get_project("xlqtveusyfpffaejegiq")` answered | the connector, called today |
| Which account or organisation owns it? | organisation **`xuyvgbmmjpswwpsbmpyh`**, **not** AD's. Project name **"tylerwarren@gmail.com's Project"**, which is Supabase's default name for a project created by that account. Region `eu-west-1`, PostgreSQL 17, created 14 May 2026 | `get_project` |
| ⛔ **Is it running?** | **No. Status `INACTIVE`**, which is what Supabase reports for a **paused** project. Its hostnames (`xlqtveusyfpffaejegiq.supabase.co`, `db.…`) **do not resolve** in DNS, while AD's does | `get_project`; DNS lookup today |
| Is there a Railway Postgres? | **No sign of one** anywhere in the repo | search for `railway.internal`, `rlwy.net`, `postgres.railway` |
| Any env file here? | **None.** No `.env*` exists in this checkout or in `~/Projects/sasha-travel` (all are gitignored) | file search, names only |
| ⛔ **Any credential here?** | **Yes, one, and it is committed.** A **`service_role`** key for `xlqtveusyfpffaejegiq` is **hard-coded** in `frontend/app/api/onboarding/save/route.ts:4`, **valid until 2036-05-13**. It came in with commit `57119c3` ("Phase 3 — B2B client onboarding portal", 29 May 2026), so **it is on GitHub**. It is the only credential in the repository | decoded **claims only** (`role`, `ref`, expiry). The key itself was never printed |

**What that means:**
- **The SQL cannot run until the project is restored.** A paused project has no database to run it against.
- **Whatever the live Sasha backend does with `SUPABASE_URL` today is already failing.** Prompts and tenants
  fall back to their static versions, and `/onboarding`'s save cannot work. That is a guess about which URL
  Railway has set; the fact is that this project answers nothing.
- ⚠ **A `service_role` key bypasses row-level security.** Once the project is restored, anyone with read
  access to the GitHub repo holds full access to its data, including the guests' names, emails and phones the
  booking tables will hold. **Rotate it before the booking tables go live** (§3, step 5). Removing it from the
  file does not remove it from git history; only rotation makes it useless.

## 2. The chat connector could run the SQL — and does not

`get_project` working means the connector *may* be able to act on this project once it is restored. **It will
not:** the standing rule is that SQL is drafted and the founder runs it. This file is for that.

## 3. What the founder does, literally

**Step 1 · Restore the project.** Open **`https://supabase.com/dashboard/project/xlqtveusyfpffaejegiq`** and
press **Restore project**. It takes a few minutes. ⚠ If there is **no** Restore button (Supabase offers one for a
limited time after pausing), stop and tell this session: the data could then only be downloaded, not restored.

**Step 2 · Copy the SQL.** One line in Terminal (the file holds no secret):
```
cd ~/Developer/Sasha-travel- && pbcopy < backend/booking_signer/sql/001_booking_storage.sql && echo copied
```

**Step 3 · Paste it whole and run it once.** Open
**`https://supabase.com/dashboard/project/xlqtveusyfpffaejegiq/sql/new`**, paste, press **Run**.
- **It is one block, 9 KB. Paste it whole; do not split it.** The preview is built in: it first checks that
  none of the six tables exists, and **stops with "STOP: … nothing was created"** if one does.
- **What it must show:** the result panel lists **six rows**: `booking_devices`, `booking_intents`,
  `booking_pairing_challenges`, `booking_reports`, `booking_tasks`, `reservations`, **each with `rowsecurity`
  = `true`**.
- **Any error at all means nothing was created**, because the script runs as one transaction. Tested three
  ways on a throwaway Postgres: a clean run gives six rows with RLS on; a second run is stopped by the guard;
  a failure partway leaves **zero** tables.

*(Optional, if he wants to look before running anything: this preview must return **no rows**.)*
```sql
select table_name from information_schema.tables where table_schema = 'public' and table_name in ('booking_pairing_challenges','booking_devices','booking_intents','booking_tasks','booking_reports','reservations');
```

**Step 4 · Give Railway the connection** (the founder sets it; its value never goes into chat).
In Supabase: **Project Settings → Database → Connection string → URI, "Transaction pooler"** (port 6543).
In Railway: service **`sasha-travel-production` → Variables → `DATABASE_URL`** = that URI.
- The pooler, because Supabase's direct address is IPv6-only on newer projects and Railway may not reach IPv6
  (as best I can tell). The store is configured for the pooler.
- Setting it changes nothing else that runs: only `db.py`, which is imported by nothing, and the hand-run
  `run_migration.py` read it.

**Step 5 · Rotate the committed service key**, in that project's **API** settings. Then:
- update **`SUPABASE_SERVICE_KEY`** on Railway;
- update the anon key on the Vercel projects, if rotation changes it too;
- replace the hard-coded value in `onboarding/save/route.ts` with an environment variable. That is a code
  change for a later ticket; this session made none.

**Step 6 · Probe** (after the S-17 push, which is **not** done yet):
`https://sasha-travel-production.up.railway.app/api/booking/health` must show, under `storage`,
`"configured": true` and `"provisioned": true`, and under `signer`, `"matches_pinned": true`.

## 4. What changed in the repo in this pass (uncommitted)

- **`backend/booking_signer/sql/001_booking_storage.sql`**: reshaped into the single paste. It has the guard
  first and the check last, and no explicit `BEGIN`/`COMMIT` (sent as one script it is already one
  transaction). **The tables are byte-identical** to the committed version. The full suite passes against it:
  63 tests, none skipped, Postgres half included.
- **This file**, replacing its first version.
