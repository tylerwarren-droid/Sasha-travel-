# S-40 — The form measurement, built. Not run. Report before running

**Filed:** 30 September 2026. **Built and tested; not committed; not run.** SQL 005 is confirmed live (production
`/api/booking/links/<id>` → 404 `link_unknown`). The S-39 fixes are committed and pushed (AD `0a80615`).

## 0. Blunt answer

**The job reads about 1,020 venue own-domain sites:**
- 170 restaurants and 170 activities in each of Madrid, Lisbon and Berlin;
- **only as a one-off Railway service**. It refuses to start anywhere else, and **refused on this Mac even with Railway's
  variables faked**;
- robots first, own registrable domain only, public addresses only, served markup only;
- ⛔ **41 booking-platform patterns (restaurant and activity) are never fetched.**

**The scoring rules are frozen at AD `0a80615`.** The scorer refuses to run if the form reader differs by one byte.

**Before it can run, the founder:**
1. runs **SQL 006**;
2. creates **the one-off Railway service**;
3. then sets a **local `DATABASE_URL`** (name only) for the read-only export.

**Tests:**
- Sasha backend: **190 OK** (13 new, for the job);
- AD scorer: **PASS**;
- `tsc` 0; eslint clean on the new files.

AD's two failing tests at 12:50 were the US session's work in progress, resolved by its C-66 (§ at the end).

## 1. What was built

| file | what |
|---|---|
| `backend/booking_signer/measure_forms.py` | **the job.** `--plan` prints the plan and the SQL (no network). `--run` runs it, only on Railway. `--export PATH` is read-only, from the database, and fetches no web page |
| `backend/booking_signer/sql/006_measure_forms.sql` | `measure_runs`, `measure_hosts`, `measure_pages`, with RLS on. **For the founder to run**; it refuses if already applied |
| `backend/tests/test_measure_forms.py` | 13 offline tests: the Railway-only guard (Mac refused, `railway run` refused, switch required); platforms (restaurant **and** activity), social hosts and aggregators never fetched; a reproducible draw, one site per domain, own hosts only; robots disallow → nothing fetched; redirects to a platform or another domain refused; non-public hosts refused; what is kept |
| `backend/requirements.txt` | `duckdb` (the Overture query) |
| AD `scripts/measure-forms-score.ts` (+ test) | **the frozen scorer**, offline. It writes `forms.json`, `labelling.json` (one row per field, for a person to fill in the true role) and `summary.json`. It computes the roles-correct fraction **only from a person's labels**, never on its own |

## 2. How the job works

1. **The venue list.** Overture Places, release `2026-08-19.0` (the one the seeder read; it still has
   `categories.primary`, which Overture removes from September's release on). **Each city's box comes from Overture's
   own divisions data in the same release** (the `division_area` locality: Madrid, Lisboa, Berlin), recorded with its
   id: a box with provenance.
   - Restaurants: `restaurant / cafe / bar / bakery` (the seeder's list).
   - Activities: categories matching museum, gallery, tour, sightseeing, attraction, experience, excursion, cooking or
     culinary school, class, workshop, escape room, wine tasting, winery, boat, kayak, surf, climbing, dance or art
     school, pottery, yoga, bike rental, theme park, zoo, aquarium.
2. **Own hosts only.** Drop booking platforms (restaurant: TheFork, OpenTable, CoverManager, SevenRooms, DISH, UMAI,
   Spotlinker, Zenchef, Resy, Quandoo…; activity: FareHarbor, GetYourGuide, Viator, Tiqets, Bókun, Checkfront, Rezdy,
   Peek, Eventbrite, Klook, Civitatis, Musement, Headout, TrekkSoft, Regiondo, Fever…), social hosts, link hubs,
   delivery and aggregators. **One site per registrable domain.** A **seeded random draw** (seed `20260930`): 170 per
   kind per city.
3. **The read.**
   - `robots.txt` first; a disallow or an unreadable robots file means **not fetched**, and is recorded.
   - The home page, plus up to 4 **same-domain** pages whose link says reserv / book / contact / tickets / clases /
     workshop / Termin.
   - Every hop re-checked: **public IP, same registrable domain, never a platform**.
   - 10 hosts at once, 1 second between a host's pages, a 15-second timeout, a 2 MB cap, a user-agent naming Sasha.
4. **What is stored: not pages.** Per page: its `<form>` blocks, `<label>`s, iframe and script hosts, calendar markers
   and platforms seen, gzip'd, with URL, status, bytes and sha256. **About 30 MB for the run.** Never in a repo.
5. **The score** (offline, here), frozen at `0a80615`:
   - for every form: kind; the six found or missing; name parts; challenges; traps; each field's role;
   - `slot must be chosen first` pages;
   - **platform embeds per platform: the S-37 slot-link reach, measured at the same time.**
   - **The fraction of roles correct needs a truth file**: a person labels each field's true role from the markup, as
     in S-38. Without one, the scorer prints no fraction.

## 3. What the founder does, in order

1. **Run `backend/booking_signer/sql/006_measure_forms.sql`** in the Sasha Supabase SQL editor. The checklist row must
   say `ok = true`.
2. **Create the one-off service** in the Sasha Railway project:
   - New → GitHub repo (**Sasha-travel-**) → root directory **`backend`**;
   - start command **`python -m booking_signer.measure_forms --run`**;
   - variables: **`MEASURE_FORMS_RUN=1`**, and **`DATABASE_URL`** as a *reference* to the existing service's
     variable (never pasted);
   - Settings → **Restart policy: Never**. Deploy once.

   It prints each city's counts, then `run <id>: N hosts read`, and exits. Expect **20–40 minutes**. Afterwards,
   delete the service, or remove `MEASURE_FORMS_RUN`.
3. **For the export**, set `DATABASE_URL` for Sasha's database in a local `backend/.env` yourself (name only; I never
   see the value). I then run `--export` (read-only), score it offline, and label the truth.

**Commit first** (the job must be on `main` for Railway to build it). Say "commit" and "Push".

## 4. Cost and time

| | |
|---|---|
| Overture: three bounding-box queries from Railway | free; a few hundred MB of egress |
| the fetch: about 1,020 hosts × about 3 pages | ≈ **3,000 requests**, 20–40 min, **under $1** of Railway compute and egress |
| storage | about 30 MB in Sasha's database |
| scoring and labelling | minutes to score; **2–3 hours** to label 20–40 forms' true roles |

## The two AD failures, resolved

At 12:50 `npm test` failed in `lib/beta-gate-c62.test.ts` and `lib/coverage-agreement.test.ts`. On a clean
`origin/main`, with or without the S-40 scorer files, **both pass**, and they pass in the shared tree since C-66
(`f5b37ac`, 12:58). They were the US session's work in progress at that moment. Nothing to file.
