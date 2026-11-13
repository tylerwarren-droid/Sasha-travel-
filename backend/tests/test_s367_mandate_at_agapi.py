"""Sasha 367 · the manager's instruction registered ONCE at AgAPI as a signed mandate (CR 182, mailbox 1866); every worker booked under it
with their OWN contact; no per-item yes inside the limits. Tyler 11 Nov: a non-refundable fare is ALWAYS asked (fare_not_refundable).

ONE source: the mandate at AgAPI + its id on the trip record. Never the instruction's text sent as a yes; never a made-up contact.

    cd backend && python -m unittest tests.test_s367_mandate_at_agapi -v
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import pathlib
import unittest
from unittest import mock

from agapi import v0 as API
from booking_signer import agapi_mandate as AM, groups as G, live_events as LE, mandate as M
from tests import test_s339_book_all as W339, test_s365_mandate as T365

run = asyncio.run
OWNER = W339.OWNER
ROOT = pathlib.Path(__file__).resolve().parents[2]
SECRET = "test-tap-secret-367"
SAID = "Book all executives to London 15–17 December"
PHONES = {n: f"+3461{i:07d}" for i, n in enumerate(T365.SIX)}   # valid-format Spanish mobiles: fictional, never texted


MandateAgAPI = W339.PricedAgAPI   # CR 182's contract lives in the group world's AgAPI (tests/test_s339_book_all.PricedAgAPI)


class World(W339.World):
    def __init__(self, agapi=None, phones=True):
        super().__init__(agapi or MandateAgAPI())
        self.phones = phones

    def __enter__(self):
        super().__enter__()

        async def codes(city):
            return ["LON", "LHR", "LGW"]
        for p in (mock.patch.object(G, "HOTELS", G._hotel_search), mock.patch.dict(os.environ, {"SASHA_AGAPI_TAP_SECRET": SECRET}),
                  mock.patch.object(AM, "PLACE", codes), mock.patch.dict(M._RUNS, {}, clear=True)):
            p.start()
            self.p.append(p)
        T365._executives(T365.SIX)
        roster = {p["name"]: p for p in run(G.roster(OWNER))["people"]}
        for n in T365.SIX:   # the demo's executives: their own mobile and email (fictional, never texted)
            fields = {"email": f"{n.split()[0].lower()}@lusaobras.example", "phone": PHONES[n] if self.phones is True or n in (self.phones or ()) else ""}
            run(G.edit_person(OWNER, roster[n]["id"], fields))
        return self


def _instruction(w):
    async def go():
        from agapi import venue_submit as VS
        VS.TAP.set(T365.S2_SESSION)   # Sasha 381e · the S2 door, as its entry point records it
        q = LE.subscribe(OWNER)
        ctx = API.Ctx(account=OWNER, user_said=SAID, surface="s2", session="s367-session")
        r = await API.call(ctx, "group_select", {"change": "new", "destination": "London", "starts_on": "2026-12-15", "ends_on": "2026-12-17",
                                                 "roles": ["executives"]})
        await M.finished(OWNER)
        evs = []
        while not q.empty():
            evs.append(q.get_nowait())
        LE.unsubscribe(OWNER, q)
        return r, evs
    return run(go())


def _finish(evs):
    return [e for e in evs if e.get("type") == "group_done"][-1]


class InsideTheLimits(unittest.TestCase):
    def test_one_mandate_every_worker_booked_zero_questions(self):
        with World() as w:
            r, evs = _instruction(w)
            mv = run(G.store().movement(OWNER))
            view = run(G.view(OWNER))
        self.assertTrue(r["ok"], r)
        fin = _finish(evs)["text"]
        self.assertTrue(fin.startswith("All 6 booked (TEST)."), fin)
        self.assertNotIn("?", fin)                                                            # zero questions
        calls = w.agapi.calls
        mand = [b for op, b in calls if op == "approvals.mandate"]
        self.assertEqual(len(mand), 1)                                                        # ONE mandate
        self.assertEqual(mand[0]["words"], SAID)                                              # the words, as given
        self.assertEqual(mand[0]["scope"]["destination"], ["LGW", "LHR", "LON"])
        self.assertEqual((mand[0]["scope"]["from"], mand[0]["scope"]["to"]), ("2026-12-15", "2026-12-17"))
        self.assertEqual(len(mand[0]["scope"]["workers"]), 6)
        pw = mand[0]["limits"]["per_worker"]                                                  # Sasha 371b · CR 184: EACH worker's own
        self.assertEqual(set(mand[0]["limits"]), {"per_worker"})
        self.assertEqual(sorted(x["worker"] for x in pw), sorted(mand[0]["scope"]["workers"]))
        for x in pw:                                                                          # … from the ONE rules record, never a max
            lim = G.limit_for(mv.get("rules") or {}, {"id": x["worker"], "grade": next(r["grade"] for r in view["rows"] if r["member_id"] == x["worker"])})
            self.assertEqual(x["flight_return_max"], {"amount_minor": round(lim["flight_return_eur"] * 100), "currency": "EUR"})
            self.assertEqual(x["stay_night_max"], {"amount_minor": round(lim["hotel_night_eur"] * 100), "currency": "EUR"})
        self.assertEqual(mand[0]["scope"]["movement_id"], str(mv["id"]))
        self.assertEqual(mand[0]["proof"]["kind"], "in_app")
        mid = (mv["rules"]["mandate"].get("agapi") or {}).get("mandate_id")
        self.assertEqual(mid, w.agapi.mandates and next(iter(w.agapi.mandates)))           # its id on the trip record (never a token)
        books = [b for op, b in calls if op == "group.book"]
        self.assertTrue(books and all(b.get("mandate_id") == mid for b in books))
        self.assertEqual(sorted(b["worker"]["phone"] for b in books), sorted(PHONES.values()))   # each traveller's OWN mobile
        self.assertTrue(all(b["worker"]["email"].endswith("@lusaobras.example") for b in books))
        self.assertEqual([op for op, _ in calls if op == "sandbox.simulate_approval"], [])  # never the text as a yes
        self.assertEqual(sorted(r["status"] for r in view["rows"]), ["booked"] * 6)


class OutsideIsAskedOnce(unittest.TestCase):
    def test_a_non_refundable_fare_is_asked_named_with_its_tap(self):
        with World(MandateAgAPI(outside={"Bruno Example": "fare_not_refundable"})) as w:
            r, evs = _instruction(w)
        done = _finish(evs)
        self.assertTrue(done["text"].startswith("5 of 6 booked (TEST)."), done["text"])
        self.assertIn("Bruno Example: their fare can't be refunded", done["text"])
        self.assertEqual(done["text"].count("?"), 1, done["text"])                          # the ONE grouped question
        self.assertTrue(done["card"]["read_back_id"].startswith("grp_"))                    # … with its explicit tap
        self.assertEqual([c["route"] for c in done["card"]["choices"]], ["group_yes", "group_no"])

    def test_a_missing_mobile_is_asked_before_any_order(self):
        with World(phones=T365.SIX[1:]) as w:                                              # Amara: no mobile on the roster
            r, evs = _instruction(w)
        fin = _finish(evs)["text"]
        self.assertIn("Amara Sample: no mobile on their profile", fin)
        self.assertNotIn("Amara", " ".join(w.agapi.supplier))                              # nothing ordered for her
        self.assertEqual(fin.count("?"), 1, fin)


class TheMissingFactAndTheProof(unittest.TestCase):
    def test_no_limits_on_the_record_is_asked_and_nothing_is_registered(self):
        with World() as w:
            mv = run(G.store().movement(OWNER))
            with mock.patch.object(G, "limit_for", lambda rules, m: {}):
                r, evs = _instruction(w)
        self.assertIn("I need the company's limits", r["result"]["say"])
        self.assertEqual([op for op, _ in w.agapi.calls if op in ("approvals.mandate", "group.book")], [])

    def test_the_limits_given_carry_the_instruction_on(self):
        with World() as w:
            gone = mock.patch.object(G, "limit_for", lambda rules, m: {})
            gone.start()
            r, _ = _instruction(w)
            self.assertEqual(run(G.store().movement(OWNER))["rules"]["mandate"]["state"], "waiting")
            gone.stop()                                                                        # the manager gives the limits …
            ctx = API.Ctx(account=OWNER, user_said="limits: 900 a return flight and 140 a hotel night", surface="s2", session="s367-session-2")
            out = run(T365.s2(API.call(ctx, "group_limits", {"by_grade": {"worker": {"flight_return_eur": 900, "hotel_night_eur": 140},
                                                                  "supervisor": {"flight_return_eur": 900, "hotel_night_eur": 140}}})))
            run(M.finished(OWNER))
            mv = run(G.store().movement(OWNER))
        self.assertIn("carrying on with your instruction", out["result"]["say"])           # … and it carries on, no second instruction
        self.assertEqual(mv["rules"]["mandate"]["state"], "done")
        self.assertEqual(len([op for op, _ in w.agapi.calls if op == "approvals.mandate"]), 1)

    def test_the_proof_is_signed_as_agapi_checks_it(self):
        with mock.patch.dict(os.environ, {"SASHA_AGAPI_TAP_SECRET": SECRET}):
            p = AM.sign({"kind": "whatsapp", "wa_id": "34611000000", "message_id": "SM1"}, OWNER, "ab" * 32, t=1700000000, nonce="n" * 16)
        want = hmac.new(SECRET.encode(), f"1700000000.{'n' * 16}.mandate.whatsapp.SM1.34611000000.{'ab' * 32}".encode(), hashlib.sha256).hexdigest()
        self.assertEqual(p["signature"], want)
        self.assertEqual(set(p), {"kind", "t", "nonce", "wa_id", "message_id", "signature"})


class FoundOnTheIphone(unittest.TestCase):
    def test_each_reason_named_once_and_one_planner(self):
        """Found by the iPhone proof (11 Nov): "their fare can't be refunded and their fare can't be refunded" (both legs); and the limits'
        planning ran beside the mandate's (a second registry), leaving a person "not planned"."""
        from booking_signer import group_book as GB
        q = GB.one_question([{"name": "Elena Ortega", "outside": ["fare_not_refundable", "fare_not_refundable"]}])
        self.assertEqual(q.count("can't be refunded"), 1, q)
        v0 = (ROOT / "backend" / "agapi" / "v0.py").read_text()
        self.assertIn("G._plan_later(account, mv[\"id\"], ids)", v0)
        self.assertNotIn("_GROUP_PLANS", v0)


class OneSource(unittest.TestCase):
    def test_no_text_as_yes_and_no_made_up_contact(self):
        src = (ROOT / "backend" / "booking_signer" / "mandate.py").read_text()
        self.assertIn("GB.book_under_mandate(", src)
        self.assertNotIn("GB.confirm(", src)                                                  # no per-item yes inside the mandate
        book = (ROOT / "backend" / "booking_signer" / "group_book.py").read_text()
        self.assertIn('"worker": {**w, **contact_of(m)}', book)
        self.assertNotIn("+34600000000", book)


if __name__ == "__main__":
    unittest.main()
