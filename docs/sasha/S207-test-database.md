# Sasha 207 · a throwaway Postgres for the deploy gate

## What it is for

The gate (`backend/scripts/gate.py`, Railway `preDeployCommand`) gained a POSTGRES step (`scripts/postgres_suite.py`).
The step runs the 17 test modules that have a real-Postgres half: 434 tests in about 12 s. These are the stores exactly as
written in `booking_signer/sql/`: the guest WhatsApp store with 034 (`last_to`, one turn per MessageSid), plus bookings,
ladder, calls, vault, retention, contacts and opt-in.

The tests **drop and recreate schemas** in the database they are given. So:
- The step refuses (gate FAIL) any URL whose database name lacks `test`.
- It refuses any URL that names sasha-prod, or that sits on the same host as `DATABASE_URL` / `SUPABASE_URL`.
- While `BOOKING_TEST_DATABASE_URL` is unset, it prints `SKIPPED` and the gate still passes. That is today's state.
- Once the URL is set, a Postgres half that skips counts as a failure; it is never a quiet pass.

Verified on 8 Oct 2026 against a local Postgres 16 (embedded, `pgserver`): 434 run, 0 failed, 4 skipped. The 4 skips are
pinned conversations superseded in Sasha 195, not Postgres tests. The refusals were checked with a prod-ref URL and a
same-host URL.

## The options

Prices are as known to the tab, not re-checked on the vendors' pages today.

| Option | Cost | Clicks for the founder | Catch |
|---|---|---|---|
| **Neon free project** (recommended) | €0 | sign up, create 1 project, paste 1 string | Suspends when idle and wakes in about 1 s on the next connection. Nothing to un-pause. 0.5 GB, far more than the tests use. |
| Supabase free project (SASHA org: 1 project, paused) | €0 | none: the tab can create it | **Pauses after 7 days without use**, and only a dashboard click restores it. A quiet week would block every deploy. Its direct host is IPv6-only, so it needs the pooler. |
| Supabase branch of sasha-prod | Pro plan ($25/mo) + about $0.013/h per branch (about $10/mo if kept) | upgrade, enable branching | The branch's database is named `postgres` (the guard refuses it), it starts from prod's migrations, and it sits one setting away from production. **No.** |
| Railway Postgres service in the Sasha project | about $1–3/mo, billed by usage | none: the tab can add it | Lives next to production in the same project. Small, but not free. |
| Postgres inside the gate (`pgserver` wheel) | €0 | none | No URL at all, so it can never point anywhere. But it adds about 40 MB to the production image, and Railway runs as root, which Postgres refuses without a workaround. Untested on Railway. |

## Recommended: Neon free. What the founder clicks

1. Go to **neon.tech → Sign up** (GitHub or Google). No card is asked for on the free plan.
2. **Create project**:
   - name `sasha-gate`;
   - Postgres version: the default;
   - region: **AWS Europe (Frankfurt)**;
   - **Database name: `sasha_test`** (it must contain "test").
3. On the project dashboard, open **Connect**:
   - database `sasha_test`;
   - **turn "Connection pooling" OFF** (the tests use prepared statements);
   - copy the connection string.
4. Paste it into the Sasha tab.

The tab then:
- strips `channel_binding=require`, which asyncpg does not accept;
- runs the 434 tests against it from the laptop;
- sets `BOOKING_TEST_DATABASE_URL` on Railway with the CLI, never printing it;
- redeploys, and confirms the gate log shows `POSTGRES: 4xx tests passed`.

Nothing to pay.
