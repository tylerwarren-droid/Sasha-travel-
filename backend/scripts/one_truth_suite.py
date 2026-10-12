"""Sasha 249 · THE CONSISTENCY TEST IN THE DEPLOY GATE (EU 245, docs/sasha/one-truth-spec.md §3) — T1–T15, offline (no model, no
Places, no AgAPI, no production database), in a clean process with a stripped environment (as the safety suite runs). One line per
invariant; any T with a failing test fails the gate, and so does a T with no test at all.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

T = {   # invariant → (what it holds, the test classes that hold it)
    "T1": ("badge = acting", ["tests.test_s249_identity.T1OneResolver"]),
    "T2": ("no demo leak", ["tests.test_s249_identity.T2NoDemoLeak", "tests.test_s249_identity.OneFounderDecision"]),
    "T3": ("trips belong to the actor", ["tests.test_s249_identity.T3TripsBelongToTheActor"]),
    "T4": ("one total", ["tests.test_s249_total_options.OneTotal", "tests.test_s249_total_options.TheGuardChecksTheTotalExactly",
                         "tests.test_s249_total_options.HoldBookingSaysWhenTheTotalMoved"]),
    "T5": ("one currency", ["tests.test_s249_total_options.OneRate", "tests.test_s249_total_options.OneCurrency"]),
    "T6": ("one party", ["tests.test_s249_total_options.OneParty"]),
    "T7": ("offered = bookable", ["tests.test_s249_total_options.OfferedIsBookable"]),
    "T8": ("one status", ["tests.test_s249_status_keep_caps.Decide", "tests.test_s249_status_keep_caps.EverySurfaceReadsIt",
                          "tests.test_s249_status_keep_caps.GetStatusIsTheOneSource", "tests.test_s249_status_keep_caps.TheFrontReadsIt",
                          "tests.test_s249_status_keep_caps.BasketBookingsInTheLedger"]),
    "T9": ("WhatsApp reaches the brain", ["tests.test_one_truth.T9_WhatsAppReachesTheBrain", "tests.test_wa_one_brain.Routing"]),
    "T10": ("one capability list", ["tests.test_s249_status_keep_caps.OneCapabilityList"]),
    "T11": ("one space", ["tests.test_s249d.OneSpace", "tests.test_s249d.Names"]),
    "T12": ("one route", ["tests.test_s249d.OneRoute"]),
    "T13": ("no fixed examples", ["tests.test_s249_status_keep_caps.NoFixedExamples"]),
    "T14": ("durable claims and outcomes", ["tests.test_s249d.DurableClaims", "tests.test_s249d.DurableOutcomes"]),
    # Sasha 251 · the trip's dates from the one trip record (no "evening before"), and the read-back carries the one total
    "T15": ("right dates + one total in the read-back", ["tests.test_s251_dates.RightDates", "tests.test_s251_dates.ReadBackCarriesTheTotal"]),
    # Sasha 251 · every venue booking through the one engine path (D4: the one question word for word); "under <name>" to its person
    "T16": ("one booking path + book under another name", ["tests.test_s251_one_path.OnePath", "tests.test_s251_one_path.UnderAnotherName"]),
    # Sasha 252 · G3: Sasha's own WhatsApp questions answered on the one brain — one resolver before the model, tap or typed; the
    # brain's state in its own key, so a message in between never drops the open question
    "T17": ("Sasha's own questions answered on the brain, tap or typed",
            ["tests.test_s252_g3.Payment", "tests.test_s252_g3.Mailbox", "tests.test_s252_g3.NoReplyCall",
             "tests.test_s252_g3.TheirPageSent", "tests.test_s252_g3.Invitations", "tests.test_s252_g3.TheSlot",
             "tests.test_s252_g3.ProductsSeeNoQuestionAfterABrainTurn"]),
    # Sasha 252 · EU 251 FAIL 5: things to do are places — the one place card, photos from venue.profile (ActivityCard retired)
    "T18": ("activities are places (one card, their own photos)", ["tests.test_s252_activities.ThingsToDoArePlaces"]),
    # Sasha 252 · the Trip tab's flights from the one trip record, never "ask for flights" while they're chosen
    "T19": ("the Trip tab's flights from the trip record", ["tests.test_s252_activities.TripTabReadsTheTrip"]),
    # Sasha 253 · EU S2 item 11: every time she names (departure or landing) resolves to a stored fare; a fare gone is said with
    # what's there now (stored first); a time never offered is "not one of the options", with the options
    "T21": ("every time she offers can be booked", ["tests.test_s253_offered.EveryOfferedTimeBooks",
                                                    "tests.test_s253_offered.AFareThatWentAway",
                                                    "tests.test_s253_offered.ATimeNeverOffered"]),
}

_RUNNER = """
import json, sys, unittest, io
out = {}
for name in sys.argv[1:]:
    suite = unittest.defaultTestLoader.loadTestsFromName(name)
    res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    bad = [(str(t), tb.strip().splitlines()[-1][:160]) for t, tb in res.failures + res.errors]
    out[name] = {"ran": res.testsRun, "bad": bad, "skipped": len(res.skipped)}
print("@@RESULT@@" + json.dumps(out))
"""


def main() -> int:
    names = [n for _, ns in T.values() for n in ns]
    keep = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "PYTHONPATH", "TZ", "TMPDIR")}
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "-c", _RUNNER, *names], cwd=here, env=keep, capture_output=True, text=True, timeout=300)
    line = next((l for l in r.stdout.splitlines() if l.startswith("@@RESULT@@")), None)
    print(f"ONE TRUTH — the consistency test, T1–T{len(T)} (Sasha 249; Sasha 251 · T15)", flush=True)
    if line is None:
        print(f"  ✗ the tests did not run — {(r.stderr or r.stdout)[-300:]}", flush=True)
        return 1
    res = json.loads(line[len("@@RESULT@@"):])
    failed = []
    for t, (what, ns) in T.items():
        ran = sum(res[n]["ran"] - res[n]["skipped"] for n in ns)
        bad = [b for n in ns for b in res[n]["bad"]]
        ok = ran > 0 and not bad
        if not ok:
            failed.append(t)
        print(f"  {'✓' if ok else '✗'} {t} {what} ({ran} tests)" + ("" if ok else f" — {bad[:2] if bad else 'no test ran'}"), flush=True)
    print(f"ONE TRUTH: {len(T) - len(failed)}/{len(T)} hold" + (f" — FAILED: {failed}" if failed else ""), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
