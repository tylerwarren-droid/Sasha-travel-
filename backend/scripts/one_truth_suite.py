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
    # Sasha 253 · live vs the sandbox only in client_for, by the person's mode: the gate and every scratch guest never touch live
    # Sasha 254 · AgAPI's booking rules, vendored byte-identical — every vector (R1–R14 + access) holds in Sasha's gate
    "T26": ("the booking rules: vendored byte-identical, every vector holds", ["tests.test_cr91_vendored_rules_and_invite.VendoredRules"]),
    "T23": ("a test person never touches live (the gate included)", ["tests.test_s253_gate_never_live.PersonMode",
                                                                      "tests.test_s253_gate_never_live.SuiteGuestsAreTest"]),
    # Sasha 253 · G5: a booking that needs a name and mobile asks once (with the consent), saves them on the one person record
    "T20": ("booking contact asked once and kept",
            ["tests.test_s253_contact.AskedOnceAndKept", "tests.test_s253_contact.WhatsAppThisNumber",
             "tests.test_s253_contact.OnlyWhereTheBrainIs", "tests.test_s253_contact.BrainPath"]),
    # Sasha 253 · EU S2 item 11: every time she names (departure or landing) resolves to a stored fare; a fare gone is said with
    # what's there now (stored first); a time never offered is "not one of the options", with the options
    "T21": ("every time she offers can be booked", ["tests.test_s253_offered.EveryOfferedTimeBooks",
                                                    "tests.test_s253_offered.AFareThatWentAway",
                                                    "tests.test_s253_offered.ATimeNeverOffered"]),
    # Sasha 253 · item 4 (part 1): the WhatsApp old flow's capabilities in the one brain, each capability test moved to its path
    "T22": ("the WhatsApp capabilities live in the brain",
            ["tests.test_s253_gaps.TheToolsAreTheBrains", "tests.test_s253_gaps.G1ForwardedConfirmation",
             "tests.test_s253_gaps.G2ResultsPushed", "tests.test_s253_gaps.G4RelocationOnTheBrain",
             "tests.test_s253_gaps.G4CampusOnTheBrain", "tests.test_s253_gaps.G9TimeQuestion", "tests.test_s253_gaps.G10AddToTrip",
             "tests.test_s253_gaps.G13SaveForLater", "tests.test_s253_gaps.G15OpsConsole", "tests.test_s253_gaps.G16RemindersOffer", "tests.test_s253_gaps.BookIsNeverParked"]),
    # Sasha 253 · item 4 (part 2): the old flow's VENUE capabilities in the one engine path — no slot (G7), a hotel stay on the
    # ladder (G8), a Keep loyalty number and "luxury" €€€ first (G14); old S1 untouched
    "T24": ("the venue capabilities live in the one path",
            ["tests.test_s253_venue_gaps.TheSchemaOnTheOnePath", "tests.test_s253_venue_gaps.G7NoSlot",
             "tests.test_s253_venue_gaps.G8HotelOnTheLadder", "tests.test_s253_venue_gaps.G8OnWhatsApp",
             "tests.test_s253_venue_gaps.G14Loyalty", "tests.test_s253_venue_gaps.G14Luxury",
             "tests.test_s253_venue_gaps.OldS1Untouched"]),
    # Sasha 253 · item 5 (Tyler, mailbox 807/809): every account's WhatsApp to the one brain, no switch; an unlinked number gets one
    # /you line and no guest account; STOP / reminders / spaces / invites / LINK / G3 / the demos (until G11) stay in front; the
    # old flow's capability tests moved onto the brain
    "T25": ("WhatsApp: the one brain for everyone, the old flow retired",
            ["tests.test_s253_one_brain_all.EveryAccountEveryMessage", "tests.test_s253_one_brain_all.Unlinked",
             "tests.test_s253_one_brain_all.InFront", "tests.test_s253_wa_caps.Cancel", "tests.test_s253_wa_caps.TheList",
             "tests.test_s253_wa_caps.Tonight", "tests.test_s253_wa_caps.Cuisine", "tests.test_s253_wa_caps.Receipts",
             "tests.test_s253_wa_caps.VoiceNote", "tests.test_s253_wa_caps.Rehearsal"]),
    # Sasha 254 · item 2: every venue booking chooser (/s2, WhatsApp, /next, old S1, the old flow, the sweep) asks the vendored booking
    # rules through ONE adapter (agapi/booking_decide); each rule end to end; the retired deciders and env vars read nowhere
    "T27": ("every booking decision from the one rules file",
            ["tests.test_s254_one_decider.R1ChannelOrder", "tests.test_s254_one_decider.R2TheOneQuestion",
             "tests.test_s254_one_decider.R3R4FortyEightHours", "tests.test_s254_one_decider.R4CallsOff",
             "tests.test_s254_one_decider.R6Hotel", "tests.test_s254_one_decider.R5HotelNoReplySweep",
             "tests.test_s254_one_decider.R7R8R9TheCall", "tests.test_s254_one_decider.R8DepositAsked",
             "tests.test_s254_one_decider.R10Limits", "tests.test_s254_one_decider.R10CallRoutes",
             "tests.test_s254_one_decider.R11R12", "tests.test_s254_one_decider.R13R14",
             "tests.test_s254_one_decider.AccessTest", "tests.test_s254_one_decider.AccessSendsOff",
             "tests.test_s254_one_decider.AccessOf", "tests.test_s254_one_decider.EverySurface",
             "tests.test_s254_one_decider.Retired"]),
    # Sasha 254 · item 3: "I'll handle it" live — the rules' send is AgAPI's venue.submit_booking (read-back first, sent on their yes,
    # said in her voice; not_allowed kindly with their page), and venue.booking_status feeds get_status
    "T28": ("\"I'll handle it\" sends through AgAPI, read back first, said in her voice",
            ["tests.test_s254_handle_it_live.TheSend", "tests.test_s254_handle_it_live.Live",
             "tests.test_s254_handle_it_live.TheStatus", "tests.test_s254_handle_it_live.TheRoute"]),
    # Sasha 254 · item 5: every founder / calls / mailbox / demo / real-venue / mode decision reads AgAPI's person_access record
    # (access.get, ≤ 60 s, closed on failure); no env person list is read; SASHA_SWITCHING a kill switch only
    "T29": ("access from the one record",
            ["tests.test_s254_access.TheRecordGrantsEachPower", "tests.test_s254_access.ClosedOnFailure",
             "tests.test_s254_access.TheCache", "tests.test_s254_access.WarmAtEntry", "tests.test_s254_access.TheRulesAccess",
             "tests.test_s254_access.PlatformCheckIsAFixture", "tests.test_s254_access.NoEnvListDecidesAccess",
             "tests.test_s249_identity.OneFounderDecision", "tests.test_s253_gate_never_live.PersonMode"]),
    # Sasha 254 · found on production (cee7889): the booking rules' refusal ("This account is in test mode, …") paraphrased away —
    # and dropped as a "test" disclaimer. A told say_key's sentence is in her reply, once, on every surface S2 runs (S1 off untouched)
    "T30": ("the booking rules' refusals and stops are heard in the rules' words, once",
            ["tests.test_s254_said_and_status.TheRulesWordsAreHeard"]),
    # Sasha 254 · found on production: hold_venue drew a prepared page ("It's in your bookings") and get_status said "no booking or
    # request … nothing was set up". The prepared page is on the record get_status reads: prepared, waiting for them, not booked
    "T31": ("a prepared page is on the one status: prepared, not booked — never \"nothing\"",
            ["tests.test_s254_said_and_status.OneTruthPreparedPage"]),
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
