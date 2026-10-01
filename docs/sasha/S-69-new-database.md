# S-69 — Sasha's new database: a new Supabase project in the AppliedDiligence.AI organisation

*Sasha tab, 1 Oct 2026 (Sasha 68). **Plan only: nothing is created.** Chat creates the project after the founder approves
the cost. Every count and schema fact below was read today from the live project (read-only), not taken from files.*

> Numbering: the own-contact doc that held S-69 is now `docs/sasha/S-70-sasha-own-contact.md` (Sasha 69).

## 0. Why, and what moves

- **Why:** the founder can't log in to the current project, `xlqtveusyfpffaejegiq`. It is "tylerwarren@gmail.com's
  Project", region **eu-west-1**, Postgres **17.6**, created 14 May 2026. A project he can't reach can't have its keys
  rotated: that is S-62 step 0.
- **What moves:** Sasha's whole database: the schema, the data below, the demo auth user, and the auth settings.
- **What doesn't move:** the leaked service-role key. The new project has its own keys from day one, so **S-62 step 0's
  rotation happens by moving**. The old project's keys must still be made useless (§6).

**S-62's merge and deploy stay held** until the cut-over is done.

## 1. The schema: dump the live one, replay the files only as a check

**The files do NOT reproduce the live schema**, so they are not the source of truth (rule: verify against the live
database, never the files):

- **Live, but in no file:** `itineraries`, `itinerary_items`, `preferences`, `travellers`, `users` (public).
- **In a file, never applied live:** `booking_references` and `prompt_versions` (`backend/migrations/001_kanoe_schema.sql`).
  `app/services/prompts.py` reads `prompt_versions`, so that read already fails today and will still fail after the move.

**Method:**
1. `pg_dump --schema-only --schema=public` from the old database is the schema of record.
2. Apply it to the new project.
3. Check the result against the files in the order below. Any difference is listed before data moves.

**The files, in order** (each one's tables, read today):

| # | File | Creates or changes | Replay? |
|---|---|---|---|
| A1 | `backend/migrations/001_initial_schema.sql` | user_profiles, organizations, traveler_profiles, trips, trip_items, booking_attempts, documents, escalations, conversations, calendar_events; their RLS policies; `set_updated_at` | yes (in the dump) |
| A2 | `backend/migrations/001_kanoe_schema.sql` | booking_references, prompt_versions | **apply (Sasha 69)**: `prompts.py` reads prompt_versions. ⚠ **Without its seed INSERT**: the seed marks May-era prompts *active* ("Maximum 3 sentences"), and `prompts.py` overlays active rows onto its newer static prompts, which would quietly change how Sasha speaks. The tables are created empty; the static registry stays authoritative until a prompt is deliberately activated. booking_references: nothing in code reads it (one docstring mentions it) |
| A3 | `backend/migrations/002_clients_schema.sql` | clients, client_api_keys | yes |
| 001 | `booking_signer/sql/001_booking_storage.sql` | booking_pairing_challenges, booking_devices, booking_intents, booking_tasks, booking_reports; **the demo auth user `11111111-1111-4111-8111-111111111111`** (no email, no password) | yes. The demo user must exist before any data (FKs) |
| 002 | `002_prepared_status.sql` | trip_items status gains "prepared" | yes |
| 003 | `003_phone_calls.sql` | booking_calls | yes |
| 004 | `004_ladder.sql` | venue_reads, booking_emails, booking_email_replies, booking_email_quarantine | yes |
| 005 | `005_slot_links.sql` | booking_links, booking_link_confirmations | yes |
| 006 | `006_measure_forms.sql` | measure_runs, measure_hosts, measure_pages | yes |
| 007 | `007_retention_log.sql` | retention_log | yes |
| 008 | `008_venue_optins.sql` | venue_optins, the append-only trigger | yes |
| 009 | `009_venue_optin_requests.sql` | venue_optin_requests | yes |
| 010 | `010_withdrawal_channels.sql` | widens venue_optins' channels | yes |
| 011 | `011_reservation_request.sql` | `request`, `request_sha256`, `request_schema` on trip_items and the channel tables | yes |
| 012 | `012_backfill_request.sql` | a data backfill | **no**: the copied rows already carry it (10/10 trip_items have a request hash) |
| 013 | `013_purge_places_content.sql` | a data purge | **no**: copied after the purge, so nothing is left to purge |
| 014 | `014_dialled_number_hash.sql` | dialled_number may hold `sha256:` | yes |
| 015 | `015_guest_contacts.sql` (branch `s62-guest-accounts`) | guest_contacts | **after** the move, with S-62, on approval |

**Also on the live database, to carry over:**
- extensions: `pgcrypto`, `uuid-ossp` (plus Supabase's own);
- functions: `set_updated_at`, `venue_optins_append_only`, `rls_auto_enable`;
- triggers: updated_at on clients, traveler_profiles, trip_items and trips; append-only on venue_optins;
- RLS is **on for every public table**. The policies are those listed in A1; booking_signer's tables have none (backend
  only).

## 2. The data to copy (exact row counts, 1 Oct 2026)

| Table | Rows | Copy? | Note |
|---|---:|---|---|
| auth.users | 4 | **the demo user only, by 001** | **Decided (Sasha 69): the other 3 are NOT copied.** They are e-mail sign-ups from May (gmail.com, kanoe.ai, medpark.us) that no row references; they can sign in again by magic link. |
| trips | 1 | yes | the demo account's "Bookings" trip |
| **trip_items** | **10** | yes | **includes Calma**: confirmed, request_sha256 `bfe605709212edd7c52060a8376266728b67124e8e52a1a12e9ba7807b769c00`. The others: 5 restaurant (4 pending, 1 prepared, 1 unclear) and 4 beauty pending |
| booking_calls | 8 | yes | already purged (013): numbers hashed, each with its place_id |
| booking_attempts | 2 | yes | |
| venue_reads | 23 | yes | purged: place_id plus own-site facts only |
| booking_intents | 2 | yes | |
| booking_tasks | 1 | yes | |
| booking_reports | 1 | yes | |
| booking_devices | 1 | yes | the paired helper device |
| booking_pairing_challenges | 1 | **no** | single-use and expired |
| clients | 3 | yes | onboarded businesses |
| measure_runs / measure_hosts / measure_pages | 2 / 1,021 / 1,411 | yes | the S-40 form measurement (research data) |
| retention_log | 676 | yes | the audit of what retention deleted |
| booking_emails, booking_email_replies, booking_email_quarantine, booking_links, booking_link_confirmations, venue_optins, venue_optin_requests, client_api_keys, itineraries, itinerary_items, conversations, documents, escalations, calendar_events, organizations, preferences, traveler_profiles, travellers, user_profiles, users | 0 each | schema only | |
| storage buckets and objects | 0 | nothing | no edge functions or storage in use |

**Method:**
- `pg_dump --data-only` per table, in FK order: trips → trip_items → booking_* → venue_reads → clients → measure_* →
  retention_log.
- It runs from this machine, old URL → new URL. Neither URL is ever printed: both are read inside `railway run`, and the
  new one as an env value the founder sets.
- Calls are **off** during the copy (`SASHA_CALLS_ENABLED=0`, as now) and the sweeper is idle, so nothing writes
  meanwhile.

**Verify, old against new, per table:**
- row count;
- `md5(string_agg(t::text, '' order by <pk>))`. **They must be identical.**
- Plus the spot check: Calma's trip_item reads `confirmed`, with request_sha256 `bfe60570…c00`.

## 3. The environment to swap (names only; the founder sets every value, rule 17)

Read from the code today. The founder confirms each name is set where listed (the Vercel API lookup returned 404 here).

**Railway, the backend service (`6b2d42a0…`):**

| Variable | Read by | New value |
|---|---|---|
| `DATABASE_URL` | booking_signer (every store, retention), `app/db.py` | the new project's **session pooler** URL |
| `SUPABASE_URL` | `app/services/tenant.py`, `prompts.py` | `https://<new-ref>.supabase.co` |
| `SUPABASE_SERVICE_KEY` | `tenant.py`, `prompts.py` | the new secret key, see ⚠ below |
| `SASHA_SUPABASE_URL` | `booking_signer/identity.py` (S-62 branch) | `https://<new-ref>.supabase.co`. The code's default (the old ref) changes too, §5 |
| `FOUNDER_ACCOUNT_ID` | identity (S-62) | unchanged: ids are copied |

**Railway, the measure-forms service (`b1f4dac4…`, disconnected):** `DATABASE_URL`, the same new URL.

**Vercel: project.kanoe.ai is served by `sasha-heygen`** (team applied-diligence), found with the CLI on 1 Oct:
`vercel inspect project.kanoe.ai` names `sasha-heygen`, production, Ready. Its production env holds the names below
plus a `DATABASE_URL` (swap it too). sasha-travel and sasha-travel-hdyp do not serve the site.

| Variable | Read by | New value |
|---|---|---|
| `SUPABASE_SERVICE_ROLE_KEY` | `app/api/onboarding/save/route.ts` | the new secret key |
| `NEXT_PUBLIC_SUPABASE_URL` | `lib/auth.ts`, `lib/supabase.ts`, S-62 guest session | `https://<new-ref>.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | the same | the new **publishable** key |
| `DATABASE_URL` | set on sasha-heygen (production) | the new pooler URL |

⚠ **A new project issues `sb_publishable_…` / `sb_secret_…` keys.** An `sb_secret_` key is refused as a Bearer token:
- `onboarding/save` already sends it as `apikey` only;
- **`app/services/tenant.py` and `prompts.py` send it as Bearer too**, so they would fail.

Either enable the legacy JWT keys on the new project, or patch those two files to send `apikey` only for an
`sb_secret_` key (§5). **Patching is recommended**, because legacy keys are being retired.

## 4. Auth settings on the new project (founder, dashboard)

- **JWT signing:** asymmetric (ES256), the default for a new project. `identity.py` verifies ES256 against the JWKS.
  Confirm after creation: `/auth/v1/.well-known/jwks.json` lists `alg: ES256`.
- **Site URL:** `https://project.kanoe.ai`. **Redirect URLs:** `https://project.kanoe.ai/auth/callback`.
- **SMTP: Resend, once `booking.kanoe.ai` verifies in Resend.**
  - Host `smtp.resend.com`, port 465, user `resend`, password = a Resend API key (the founder enters it).
  - Sender `sasha@booking.kanoe.ai`, name "Sasha (Kanoe)".
  - Until it verifies, **guest sign-in stays closed**. Supabase's built-in mailer is for testing only.
- **The magic-link email** names Sasha and Kanoe Technologies SL and links `/sasha-privacy`.
- **Email sign-ups on; other providers off.** Rate limits at Supabase's defaults.

## 5. Code changes before the cut-over (Sasha tab, through the full gate)

**Built and tested, 1 Oct (Sasha 69); held on branches until the cut-over:**
- branch `s69-pre-cutover`: items 1 and 3, plus the prompt_versions read now logs a refusal instead of reading it as
  "no prompts" (465 pass, build clean);
- branch `s62-guest-accounts`: item 2 (461 pass).

1. `frontend/app/api/onboarding/save/route.ts`: the project URL is **hardcoded** to the old ref. Read
   `NEXT_PUBLIC_SUPABASE_URL` instead, and refuse (503, said) if it is missing.
2. `booking_signer/identity.py` (branch): no old-ref default. `SASHA_SUPABASE_URL` is required; without it, guest tokens
   refuse (fail closed).
3. `app/services/tenant.py`, `prompts.py`: an `sb_secret_` key goes as `apikey` only.
4. Tests for each; then the gate.

## 6. The cut-over, in order

1. **Founder approves the cost.** Chat creates the project in the AppliedDiligence.AI organisation: region
   **eu-west-1** (as now: EU data stays in the EU), Postgres 17.
2. Sasha tab: §5's code changes, pushed through the gate. They work against the **old** project, so nothing breaks yet.
3. Sasha tab: the schema (§1) and the copy (§2) into the new project. Then the verify: every count and hash matches,
   and Calma checks out.
4. Founder: the new env values on Railway (§3). Railway redeploys. Then the new values on Vercel, and Vercel redeploys.
   **Calls stay off throughout.**
5. Sasha tab, live:
   - `/api/booking/health` shows storage provisioned;
   - `/reservations` lists the same 10 items, Calma confirmed;
   - a venue read and a prepared call land in the **new** database (checked there), then are removed with every
     `.error` checked;
   - an onboarding save works (founder session) and is removed.
6. **Copy any rows the old database got since step 3** (there should be none: calls off, no traffic). Compare counts again.
7. **Retire the old project:** in an incognito window, check the anon URL still answers, then the founder (or whoever
   owns that login) pauses it.
   - **Until it is paused, the leaked service-role key still opens it.** It must not hold anything live after the cut-over.
   - If no one can log in to pause it, ask Supabase support to pause or delete it as the account owner.
8. Then S-62: 015 on the new project (approved), auth settings (§4), the merge (S-62-build-and-merge.md), and the proof.

## 7. Rollback

- **Until step 4:** nothing has changed for users. Delete the new project.
- **After step 4, if any step-5 check fails:** the founder sets the **old** env values back on Railway and Vercel and
  redeploys. The old project is untouched (it was only read), so Sasha is back exactly as before.
  - Rows written to the new project during the failed window are listed from there and re-entered by hand if any matter.
    With calls off, there should be none.
- **After step 7, the old project is paused, not deleted:** it can be resumed for 90 days. That is the last-resort rollback.

## TO DO, by whom

- **Founder:**
  - approve the cost;
  - confirm which Vercel projects serve project.kanoe.ai;
  - decide on the 3 May email users and on `001_kanoe_schema.sql`;
  - set the env values;
  - pause the old project.
- **Chat:** create the project.
- **Sasha tab:** §5, the schema and copy, the verification, the live checks.
