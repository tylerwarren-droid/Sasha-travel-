"""Sasha 207 · THE REAL-POSTGRES HALF IN THE DEPLOY GATE — every unit-test module with a Postgres half (the stores as written in
sql/, run against a real Postgres: the guest WhatsApp store with 034, the booking/ladder/calls stores, the vault, retention…),
against BOOKING_TEST_DATABASE_URL — a THROWAWAY database: the tests drop and recreate schemas in it.

Refused (gate FAIL), never run: a URL whose database name does not contain "test", or that names production (the host of
DATABASE_URL / SUPABASE_URL, or sasha-prod's project ref). Not set: SKIPPED, said in the log — the gate still passes."""
from __future__ import annotations

import os
import sys
import time
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.flight_suite import RESULTS, ok  # noqa: E402
from scripts.whatsapp_suite import _RUNNER  # noqa: E402

MODULES = ["tests.test_booking_calls", "tests.test_booking_ladder", "tests.test_booking_routes", "tests.test_calendar_s79",
           "tests.test_contacts", "tests.test_followup", "tests.test_form_rung", "tests.test_guest_whatsapp_s75",
           "tests.test_inbound_phone", "tests.test_optin_page", "tests.test_proactive_s83", "tests.test_products_pg_cr1",
           "tests.test_places_terms", "tests.test_retention", "tests.test_stop", "tests.test_written_s118", "tests.test_vault_s78"]
PROD_REF = "yjafyzywzbmhlilxhzuz"   # sasha-prod


def refusal(url: str) -> str:
    """Why this URL must never be run against ('' = fine)."""
    u = urlsplit(url)
    if "test" not in u.path.lstrip("/"):
        return "its database name does not contain 'test'"
    if PROD_REF in url:
        return "it names sasha-prod"
    host = (u.hostname or "").lower()
    for k in ("DATABASE_URL", "SUPABASE_URL", "BOOKING_DATABASE_URL"):
        v = os.getenv(k, "")
        h = (urlsplit(v).hostname or "").lower() if v else ""
        if h and host and h == host:
            return f"it is on the same host as {k}"
    return ""


def main() -> int:
    import json
    import subprocess
    t0, start = time.time(), len(RESULTS)
    url = os.getenv("BOOKING_TEST_DATABASE_URL", "")
    if not url:
        print("   SKIPPED · POSTGRES — BOOKING_TEST_DATABASE_URL is not set: the real-Postgres half did NOT run", flush=True)
        return 0
    why = refusal(url)
    if why:
        ok("POSTGRES: the test database is a throwaway", False, f"refused — {why}")
        return 1
    keep = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "PYTHONPATH", "TZ", "TMPDIR")}
    keep["BOOKING_TEST_DATABASE_URL"] = url   # the only database the child can see
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "-W", "ignore", "-c", _RUNNER, *MODULES], cwd=here, env=keep, capture_output=True, text=True,
                       timeout=900)
    line = next((l for l in r.stdout.splitlines() if l.startswith("@@RESULT@@")), None)
    if line is None:
        ok("POSTGRES: the tests ran", False, (r.stderr or r.stdout)[-300:])
        res = {"ran": 0, "bad": [], "skipped": []}
    else:
        res = json.loads(line[len("@@RESULT@@"):])
    for tid, w in res["bad"]:
        ok(f"POSTGRES {tid.split('tests.')[-1]}", False, w[:180])
    pg_skips = [s for s in res["skipped"] if "BOOKING_TEST_DATABASE_URL" in s[1] or "refusing" in s[1]]
    for tid, w in pg_skips:   # with the URL set, a Postgres half that skips is a failure, never a quiet pass
        ok(f"POSTGRES {tid.split('tests.')[-1]} ran", False, w[:180])
    passed = res["ran"] - len(res["bad"]) - len(res["skipped"])
    ok(f"POSTGRES: {passed} tests passed against a real Postgres (the stores as written in sql/)", res["ran"] > 0 and not res["bad"],
       f"{res['ran']} run")
    for tid, w in res["skipped"]:
        if [tid, w] not in pg_skips:
            print(f"   SKIPPED · {tid.split('tests.')[-1]} — {w[:180]}", flush=True)
    mine = RESULTS[start:]
    failed = [n for n, p, _ in mine if not p]
    print(f"\npostgres suite: {len(mine) - len(failed)}/{len(mine)} passed in {time.time() - t0:.0f}s ({res['ran']} tests, "
          f"{len(res['skipped'])} skipped)" + (f" — FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
