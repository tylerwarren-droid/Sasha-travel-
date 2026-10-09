"""CR 56 · THE DEMO SAFETY BEATS IN THE DEPLOY GATE — offline (scripted model, recorded venue API, no keys, 0 live calls):
"what are my cancellation terms?" and "find me dinner options" never cancel, book, pay or send, whatever the model does
(tests/test_demo_safety_cr56.py). Any failure fails the gate. The KNOWN GAPS (expected failures) are listed, never hidden;
one that starts passing fails the gate too, so its decorator is removed the day it's fixed and it guards from then on.

Wire into scripts/gate.py (docs/sasha/robustness-review.md §4): `from scripts import demo_safety_suite as DS` and
`s = await asyncio.to_thread(DS.main)`, with `s` in the PASS/FAIL line."""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.flight_suite import RESULTS, ok  # noqa: E402

MODULES = ["tests.test_demo_safety_cr56", "tests.test_robustness_cr56", "tests.test_safety_215",
           "tests.test_s2_powers", "tests.test_s2_216"]   # Sasha 216 · an email is never sent on a question   # Sasha 215 · the safety items too

_RUNNER = """
import json, sys, unittest, io
suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
print("@@RESULT@@" + json.dumps({"ran": res.testsRun,
    "bad": [[t.id(), w.strip().splitlines()[-1][:300]] for t, w in res.failures + res.errors],
    "gaps": [t.id() for t, _ in res.expectedFailures],
    "fixed": [t.id() for t in res.unexpectedSuccesses],
    "skipped": [[t.id(), w[:300]] for t, w in res.skipped]}))
"""


def main() -> int:
    import json
    import subprocess
    t0, start = time.time(), len(RESULTS)
    keep = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "PYTHONPATH", "TZ", "TMPDIR")}
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "-c", _RUNNER, *MODULES], cwd=here, env=keep, capture_output=True, text=True, timeout=300)
    line = next((l for l in r.stdout.splitlines() if l.startswith("@@RESULT@@")), None)
    if line is None:
        ok("DEMO SAFETY: the tests ran", False, (r.stderr or r.stdout)[-300:])
        res = {"ran": 0, "bad": [], "gaps": [], "fixed": [], "skipped": []}
    else:
        res = json.loads(line[len("@@RESULT@@"):])
    for tid, why in res["bad"]:
        ok(f"DEMO SAFETY {tid.split('tests.')[-1]}", False, why[:180])
    for tid in res["fixed"]:
        ok(f"DEMO SAFETY {tid.split('tests.')[-1]}: a known gap now PASSES — remove its @expectedFailure so it guards", False, "")
    passed = res["ran"] - len(res["bad"]) - len(res["gaps"]) - len(res["fixed"]) - len(res["skipped"])
    ok(f"DEMO SAFETY: {passed} tests passed — cancellation terms and dinner options never act", res["ran"] > 0 and not res["bad"],
       f"{res['ran']} run")
    for tid in res["gaps"]:
        print(f"   KNOWN GAP · {tid.split('tests.')[-1]} (fix before the demo: docs/sasha/robustness-review.md)", flush=True)
    mine = RESULTS[start:]
    failed = [n for n, p, _ in mine if not p]
    print(f"\ndemo safety suite: {len(mine) - len(failed)}/{len(mine)} passed in {time.time() - t0:.0f}s ({res['ran']} tests, "
          f"{len(res['gaps'])} known gaps)" + (f" — FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
