"""Sasha 206 (EU 186 R4) · WHATSAPP IN THE DEPLOY GATE — offline, the real WhatsApp turn (fake sender, memory stores, no model):
the strict spaces on WhatsApp (14 tests un-skipped and rewritten to the strict rule — two still skipped for a REAL defect,
listed here), the payment result reaching the phone (R1), no turn twice for one MessageSid (R2), and the core guest pipeline.
Any failure fails the gate; skips are listed, never hidden."""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.flight_suite import RESULTS, ok  # noqa: E402

MODULES = ["tests.test_one_sasha_cr10", "tests.test_trip_cr13", "tests.test_cross_channel_cr20", "tests.test_finder_cr35",
           "tests.test_whatsapp_r1_r2_s206", "tests.test_guest_whatsapp_s75"]


_RUNNER = """
import json, sys, unittest, io
suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
print("@@RESULT@@" + json.dumps({"ran": res.testsRun,
    "bad": [[t.id(), w.strip().splitlines()[-1][:300]] for t, w in res.failures + res.errors],
    "skipped": [[t.id(), w[:300]] for t, w in res.skipped]}))
"""


def main() -> int:
    """The tests run in THEIR OWN process with a clean environment (no database URL, no production keys): offline, as unit tests
    are meant to — inside the gate's process they would meet its live stores, its env and its running loop. The child reports
    its results as data (never parsed from text)."""
    import json
    import subprocess
    t0, start = time.time(), len(RESULTS)
    keep = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "PYTHONPATH", "TZ", "TMPDIR")}
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "-c", _RUNNER, *MODULES], cwd=here, env=keep, capture_output=True, text=True, timeout=600)
    line = next((l for l in r.stdout.splitlines() if l.startswith("@@RESULT@@")), None)
    if line is None:
        ok("WHATSAPP: the tests ran", False, (r.stderr or r.stdout)[-300:])
        res = {"ran": 0, "bad": [], "skipped": []}
    else:
        res = json.loads(line[len("@@RESULT@@"):])
    for tid, why in res["bad"]:
        ok(f"WHATSAPP {tid.split('tests.')[-1]}", False, why[:180])
    passed = res["ran"] - len(res["bad"]) - len(res["skipped"])
    ok(f"WHATSAPP: {passed} tests passed (spaces on WhatsApp, the payment result to the phone, one turn per MessageSid, the guest "
       f"pipeline)", res["ran"] > 0 and not res["bad"], f"{res['ran']} run")
    for tid, why in res["skipped"]:
        print(f"   SKIPPED · {tid.split('tests.')[-1]} — {why[:180]}", flush=True)
    mine = RESULTS[start:]
    failed = [n for n, p, _ in mine if not p]
    print(f"\nwhatsapp suite: {len(mine) - len(failed)}/{len(mine)} passed in {time.time() - t0:.0f}s ({res['ran']} tests, "
          f"{len(res['skipped'])} skipped)" + (f" — FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
