"""Sasha 283 · T63 — FOUR S2 FIXES FROM TYLER'S REAL USE (23 Oct, 09:43–09:56, his iPhone). Offline: fakes only (no model, no
Duffel, no database, no venue, no WhatsApp).

  1 · THE TRIP CARD says what the trip is — from the Trip view's own record (plan_store.card over /plan's view + its one total);
      its title came from the event's KIND ("Flights to choose from" under six nights in Rio).
  2 · SHE ASKS whether they need flights — propose_trip's `flights` is their answer: false → stays and plans only (no flight
      searched, none chosen at the read-back, no home city told to the planner); true → from the origin they said.
  3 · (frontend/scripts/presence-rule.test.mjs) the mic, her sound and her corner are the shell's: no tab can unmount them.
  4c · THE WAY BACK: a page handed over → on his return ONE question ("Did it go through?") from its row, asked once — or what
      the confirmation watcher knows; the answer goes on that row (and a platform link's own record).

    cd backend && python -m unittest tests.test_s283 -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import s2_status as ST, v0 as API, venues as VN
from app.agent import s2 as S2, sasha as SA, voice as V
from booking_signer import basket as BK, basket_book as BB, plan_store as PS

run = asyncio.run
ACCT = "00000000-0000-4000-8000-000000000283"

RIO = {"title": "Six nights in Rio", "start": "2026-11-07", "end": "2026-11-13",
       "days": [{"day": 1, "date": "2026-11-07", "city": "Rio de Janeiro, Brazil",
                 "stay": {"name": "Copacabana Palace", "first_night": True}},
                {"day": 2, "date": "2026-11-08", "city": "Rio de Janeiro, Brazil", "stay": {"name": "Copacabana Palace"}}],
       "basket": {"flights": [{"owner": "Air Canada", "from": "YOW", "to": "GIG"}, {"owner": "Air Canada", "from": "GIG", "to": "YOW"}]}}


class TheTripCardIsTheTrip(unittest.TestCase):
    def test_rio_says_rio_its_nights_its_stay_its_flights_and_her_total(self):
        c = PS.card(RIO, {"total_eur": 1557.0})
        self.assertEqual(c["title"], "Rio de Janeiro · 6 nights")
        self.assertIn("Staying at Copacabana Palace", c["lines"])
        self.assertTrue(any(l.startswith("Flights: Air Canada YOW → GIG") for l in c["lines"]))
        self.assertEqual(c["total_eur"], 1557.0)   # the basket's one total — the figure she said
        self.assertNotIn("Flights to choose from", c["title"] + " ".join(c["lines"]))

    def test_a_trip_without_flights_says_so(self):
        c = PS.card({**RIO, "flights": False, "basket": {"flights": []}}, {"total_eur": 900.0})
        self.assertIn(PS.NO_FLIGHTS, c["lines"])

    def test_only_a_flight_list_says_flights_to_choose_from(self):
        c = PS.card({"title": "Madrid → Lisbon", "single": "flight", "days": [], "basket": {"flights": []}}, None)
        self.assertEqual(c["lines"], ["Flights to choose from"])
        self.assertIsNone(PS.card(None, None))

    def test_the_trip_views_record_carries_the_card(self):
        # Sasha 283b · the page's half (S2App reads r.json.card, never the event's kind) is frontend/scripts/presence-rule.test.mjs
        # "283 · item 1" — npm test; the backend gate never reads frontend source (Railway's image has none)
        src = inspect.getsource(__import__("booking_signer.ladder_routes", fromlist=["x"]).plan_view)
        self.assertIn('"card": PS.card(view, tt)', src)


class NoGateTestReachesIntoTheFrontend(unittest.TestCase):
    """Sasha 283b · a pin on frontend source belongs to the frontend's own run (npm test). Railway's backend image has no
    frontend/ folder, so a gate test that reads one either fails the deploy (a26a188, T63) or skips — and a skip proves nothing.
    LEGACY is the closed list of gate modules that already reach in (each behind a skip); it may only shrink."""
    REACH = re.compile(r"""["'](?:\.\./|/)*frontend["'/]""")
    LEGACY = {"test_s249_status_keep_caps", "test_s252_activities", "test_s253_gaps", "test_s264", "test_s265", "test_s266",
              "test_s267", "test_s268", "test_s269", "test_s271", "test_s273", "test_s274", "test_s276", "test_s279", "test_s281"}

    def _gate_files(self):
        from scripts import one_truth_suite as OT
        back = pathlib.Path(__file__).resolve().parents[1]   # backend/ here, the image root on Railway
        mods = {n.split(".")[1] for _, ns in OT.T.values() for n in ns}
        files = {m: back / "tests" / f"{m}.py" for m in mods}
        files.update({p.stem: p for p in (back / "scripts").glob("*_suite.py")})
        files["gate"] = back / "scripts" / "gate.py"
        return files

    def test_no_new_gate_module_reads_frontend_source(self):
        reach = {m for m, f in self._gate_files().items() if self.REACH.search(f.read_text())}
        self.assertEqual(reach - self.LEGACY, set(), "a gate test reads frontend/ — pin it in frontend/scripts (npm test)")
        self.assertEqual(self.LEGACY - reach, set(), "moved out — take it off LEGACY so the list only shrinks")

    def test_the_ratchet_sees_the_shape_that_broke_the_deploy(self):
        fe = "front" + "end"   # spelled apart, so this file is not itself a reach
        self.assertTrue(self.REACH.search(f'(ROOT / "{fe}" / "app" / "s2" / "S2App.tsx").read_text()'))
        self.assertTrue(self.REACH.search(f'os.path.join(here, "..", "..", "{fe}", "lib")'))
        self.assertFalse(self.REACH.search("is held by frontend/scripts/presence-rule.test.mjs"))   # a mention is not a read


class SheAsksAboutFlights(unittest.TestCase):
    def test_her_words(self):
        t = S2.s2_system()
        self.assertIn("whether they also need flights", t)
        self.assertIn("never assumes flights or a home city", t)
        self.assertNotIn("she has who, what, when and from where", t)
        from app.services import persona as P
        self.assertIn("whether they also need flights", S2.standalone(P.AGENT_SYSTEM))   # /next with parity: the same rule

    def test_the_schema_asks_flights_and_needs_no_origin(self):
        t = next(x for x in API.TOOLS if x["name"] == "propose_trip")
        s = S2.standalone_tool(t)["input_schema"]
        self.assertIn("flights", s["required"])
        self.assertNotIn("origin", s["required"])
        self.assertIn("origin", t["input_schema"]["required"])   # old S1's own schema: untouched

    def _propose(self, a):
        called = {"legs": 0}

        async def build(_a, _acct=None):
            called["asked"] = dict(_a)
            return {"itin": {"title": "Rio", "days": [{"day": 1, "city": "Rio de Janeiro"}, {"day": 2, "city": "Rio de Janeiro"}]}, "msg": "m"}

        async def legs(*_a, **_k):
            called["legs"] += 1
            raise AssertionError("a flight was searched")

        async def save(_acct, itin, _m, _now):
            called["saved"] = dict(itin)
            return "11111111-1111-4111-8111-111111111283"

        async def by_id(_a, tid):
            return {"trip_id": tid, "start": "2026-11-07", "end": "2026-11-13"}

        async def nothing(*_a, **_k):
            return None

        async def figs(*_a, **_k):
            return {"total_eur": 900.0, "breakdown": {"total_eur": 900.0}}
        ctx = API.Ctx(account=ACCT, surface="s2", user_said="plan me six nights in Rio, no flights")
        with mock.patch.object(API, "_build", build), mock.patch.object(API, "_search_legs", legs), mock.patch.object(PS, "save", save), \
                mock.patch.object(PS, "by_id", by_id), mock.patch.object(BK, "unchoose_flights", nothing), \
                mock.patch.object(BB, "store_prices", nothing), mock.patch.object(BK, "trip_figures", figs), \
                mock.patch.object(API, "_latest", nothing), mock.patch.object(API, "_s1_passport", nothing):
            return run(API.propose_trip(ctx, a)), called

    def test_no_flights_is_stays_and_plans_only(self):
        res, called = self._propose({"destination": "Rio de Janeiro", "start_date": "2026-11-07", "nights": 6, "party": 2, "flights": False})
        self.assertEqual(called["legs"], 0)
        self.assertIs(called["saved"]["flights"], False)          # on the trip record
        self.assertIs(called["asked"]["flights"], False)          # the planner is told no home city
        self.assertFalse(res["flight_options"])
        self.assertIs(res["flights_needed"], False)
        self.assertIn("no flights", res["total_is"])
        self.assertIsNotNone(SA.render("propose_trip", res, {}))  # its card still comes

    def test_a_yes_without_an_origin_asks_where_from(self):
        with self.assertRaises(API.ToolError) as e:
            run(API.propose_trip(API.Ctx(account=ACCT, surface="s2"), {"destination": "Rio", "start_date": "2026-11-07", "nights": 6,
                                                                      "party": 2, "flights": True}))
        self.assertEqual(e.exception.code, "origin_needed")

    def test_the_read_back_never_adds_flights_to_a_no_flights_trip(self):
        self.assertIn('(p.get("plan") or {}).get("flights") is not False', inspect.getsource(BB.refresh))

    def test_the_planner_hears_no_home_city(self):
        from app.services import world_itinerary as W
        self.assertIn('("." if a.get("flights") is False else f", flying from', inspect.getsource(W.build_world))


class Memory:
    def __init__(self):
        self.kinds = {}

    async def kind(self, _acct, name):
        return self.kinds.get(name)

    async def put_kind(self, _acct, name, value):
        self.kinds[name] = [dict(r) for r in value]
        return True


class TheWayBack(unittest.TestCase):
    def setUp(self):
        VN._PREPARED.pop(ACCT, None)
        self.mem = Memory()
        from agapi import s2_memory as M
        self.p = [mock.patch.object(M, "kind", self.mem.kind), mock.patch.object(M, "put_kind", self.mem.put_kind)]
        for p in self.p:
            p.start()
        from booking_signer import mailbox as MB
        self.p.append(mock.patch.object(MB, "STORE", None))
        self.p[-1].start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def _hand_over(self, link_id=None, at=None):
        run(VN.note_prepared(ACCT, "The India - Fleet Street", "2099-10-23T21:00", 2, "https://widget.thefork.com/x", link_id=link_id))
        if at:
            self.mem.kinds[VN.PREPARED_KIND][-1]["at"] = at

    def test_one_question_on_his_return_asked_once(self):
        self._hand_over()
        w = run(VN.awaiting_word(ACCT))
        self.assertEqual(w["ask"], V.DID_IT)
        self.assertEqual(w["venue"], "The India - Fleet Street")
        self.assertIsNone(run(VN.awaiting_word(ACCT)))   # never twice

    def test_an_old_hand_over_is_never_asked_about(self):
        self._hand_over(at=(datetime.now(timezone.utc) - timedelta(hours=VN.WORD_HOURS + 1)).isoformat())
        self.assertIsNone(run(VN.awaiting_word(ACCT)))

    def test_the_watcher_already_knows_so_she_says_it(self):
        self._hand_over(link_id="22222222-2222-4222-8222-222222222283")

        class Links:
            async def get_link(self, _a, _id):
                return {"status": "confirmed"}
        from booking_signer import ladder_routes as LR
        with mock.patch.object(LR, "LADDER_STORE", Links()):
            w = run(VN.awaiting_word(ACCT))
        self.assertNotIn("ask", w)
        self.assertEqual(w["said"], V.went_through("The India - Fleet Street"))

    def test_his_yes_goes_on_the_one_record(self):
        self._hand_over(link_id="22222222-2222-4222-8222-222222222283")
        calls = []

        class GW:
            @staticmethod
            async def api(account, method, path, body=None, **_k):
                calls.append((method, path, body))
                return 200, {}
        w = run(VN.awaiting_word(ACCT))
        with mock.patch.object(VN, "_API", lambda: GW):
            out = run(VN.answer_word(ACCT, w["key"], True, "voice"))
        self.assertEqual(out["say"], V.BOOKED_BY_YOU)
        self.assertEqual(calls, [("POST", "/api/booking/links/22222222-2222-4222-8222-222222222283/booked", {"how": "voice"})])
        row = self.mem.kinds[VN.PREPARED_KIND][-1]
        self.assertEqual(row["outcome"], "booked_by_you")
        self.assertIn("booked_by_you", VN.WORD_BOOKED)
        d = ST.decide({"by_you": ["The India - Fleet Street — 2099-10-23 21:00"]})
        self.assertEqual(d["state"], "by_you")
        self.assertIn(ST.WORDS["by_you"], d["line"])

    def test_not_yet_stays_not_booked(self):
        self._hand_over()
        w = run(VN.awaiting_word(ACCT))
        out = run(VN.answer_word(ACCT, w["key"], False))
        self.assertEqual(out["say"], V.NOT_YET)
        self.assertEqual(self.mem.kinds[VN.PREPARED_KIND][-1]["outcome"], "not_yet")
        self.assertNotIn("not_yet", VN.WORD_BOOKED)

    def test_every_page_hand_over_carries_the_way_back_and_writes_the_row(self):
        src = inspect.getsource(VN._book_inner)
        self.assertEqual(src.count("_V.way_back(WA.s2_link())"), 2)   # the copy card's text and a platform page's text
        # Sasha 300 · moved: each hand-over also names its route, platform and place ID for the ONE itinerary (agapi/itinerary.py)
        self.assertIn('await note_prepared(ctx.account, venue, held["when"], held["party"], url, link_id=held["id"], route="platform",', src)
        self.assertIn('await note_prepared(ctx.account, venue, held["when"], held["party"], held.get("url"), place_id=held.get("place_id"),', src)
        self.assertEqual(V.way_back("https://project.kanoe.ai/s2"), "Done? Back to Sasha: https://project.kanoe.ai/s2")
        from booking_signer import ladder_routes as LR
        paths = {getattr(r, "path", "") for r in LR.router.routes}
        self.assertTrue(any(p.endswith("/handover/word") for p in paths))


if __name__ == "__main__":
    unittest.main()
