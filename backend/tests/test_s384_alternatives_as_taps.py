"""Sasha 384 · CR 203's Sasha half — NO TABLE AT THE ASKED TIME → AgAPI's options as TAPS; ONE tap books it (KANOE_DECISIONS 13 Nov 18:44).

Found (Tyler, 13 Nov 18:42): Peñalver at 21:00 → "the only times they offer are 12:00–12:55 … Here's their page" + "Tap to finish". AgAPI's
venue.submit_booking now answers a slot with no table with `alternatives` (ranked, each bookable: `book` terms) and ONE sentence ending
"tap one and I'll book it" — and no hand_over while any remains (CR 203). Sasha's half:
  · venues._platform_result → _alternatives: AgAPI's sentence, word for word; its options as taps (exactly AgAPI's, in its rank — nothing
    re-ranked, added or filtered); NO page, link or "Tap to finish" while any remains (the true refusal keeps them).
  · the tap (S2 / /next: card_tap → answer_card "alt:<rank>"; WhatsApp: card:<id>:alt:<rank> → the same card_tap) IS the instruction:
    alternative_answer → hold_venue with THAT option's own `book` terms (the ONE act path: prepare → the instruction as approval, its proof
    the tap's door → submit) → "Booking now: …". Never a second card.
What Sasha read from venue.submit_booking BEFORE (venues._platform_result / VS.submit): status, say, act_id, venue, route, reference, ask
(a stop's question), instructed, and hand_over.link — the "Tap to finish". `alternatives` was never read.

    cd backend && python -m unittest tests.test_s384_alternatives_as_taps -v
"""
from __future__ import annotations

import inspect
import json
import re
import unittest
from datetime import datetime, timezone
from unittest import mock

from agapi import venues as VN
from app.agent import voice as V
from booking_signer import wa_agent as WAG
from tests.test_s329 import AgAPI, Base, CARD, Ctx, DEC, RD, RES, STANDIN, VENUE, run

SAY = (f"{VENUE} has no table at 22:00 on Fri 20 Nov. I can book that evening at 22:30 or 21:45; 22:00 on Sat 21 Nov; or Casa Vecina "
       "nearby at 22:00 — tap one and I'll book it.")
ALTS = [
    {"rank": 1, "kind": "same_venue_time", "venue": VENUE, "date": "2026-11-20", "time": "22:30", "reason": "30 min after",
     "book": {"place_id": "ChIJ329", "date": "2026-11-20", "time": "22:30", "party": 2}},
    {"rank": 2, "kind": "same_venue_time", "venue": VENUE, "date": "2026-11-20", "time": "21:45", "reason": "15 min before",
     "book": {"place_id": "ChIJ329", "date": "2026-11-20", "time": "21:45", "party": 2}},
    {"rank": 3, "kind": "same_time_other_day", "venue": VENUE, "date": "2026-11-21", "time": "22:00", "reason": "1 day later",
     "book": {"place_id": "ChIJ329", "date": "2026-11-21", "time": "22:00", "party": 2}},
    {"rank": 4, "kind": "nearby_venue", "venue": "Casa Vecina", "date": "2026-11-20", "time": "22:00", "reason": "300 m away",
     "book": {"place_id": "ChIJvecina", "url": "https://casavecina.example", "date": "2026-11-20", "time": "22:00", "party": 2}},
]


class NoTableAgAPI(AgAPI):
    """CR 203 as agapi cr/203 answers it: the asked slot (22:00 on the 20th) has no table → failed + alternatives + its say — and, to prove
    Sasha ignores it while options exist, a hand_over link too. Any other slot → booked."""

    def __init__(self, alts=ALTS, **k):
        super().__init__(**k)
        self.alts, self.when = alts, {}

    async def call(self, op, body, approval=None, account=None):
        if op == "venue.prepare_booking":
            got = await super().call(op, body, approval, account)
            self.when[got["result"]["prepared_id"]] = (body.get("date"), body.get("time"))
            return got
        return await super().call(op, body, approval, account)

    def _submit(self, body):
        pid = body["prepared_id"]
        if self.when.get(pid) == ("2026-11-20", "22:00") and self.alts is not None:
            self.n += 1
            aid = f"act_{self.n:03d}"
            self.acts[aid] = {"state": "failed"}
            out = {"prepared_id": pid, "status": "failed", "submitted": True, "how": "platform_form", "venue": VENUE, "act_id": aid,
                   "say": SAY if self.alts else f"{VENUE} has no table at 22:00 that day — here's their page: {STANDIN}",
                   "hand_over": {"link": STANDIN, "copy": [], "why": "time_unavailable"}}
            if self.alts:
                out["alternatives"] = [json.loads(json.dumps(x)) for x in self.alts]
            return out
        self.prepared[pid]["zona"] = "Salón Interior"   # no question for these: straight through
        d, t = self.when.get(pid) or ("2026-11-20", "22:00")
        self.n += 1
        aid = f"act_{self.n:03d}"
        self.acts[aid] = {"state": "confirmed"}
        return {"prepared_id": pid, "status": "confirmed", "submitted": True, "how": "platform_form", "venue": VENUE, "act_id": aid,
                "reference": f"SBX-{t.replace(':', '')}", "say": f"Booked: {VENUE}, {d} {t}, 2 people, ref SBX-{t.replace(':', '')}."}


class Base384(Base):
    ALTS = ALTS

    def setUp(self):
        super().setUp()
        self.ag = NoTableAgAPI(self.ALTS)
        p = mock.patch("agapi.venue_submit.CALL", self.ag.call)
        p.start()
        self.addCleanup(p.stop)
        self.holds = []

        async def hold_venue(ctx, a):   # THE ONE path, as the tap reaches it: the option's own terms → follow (prepare → instruction → submit)
            self.holds.append((ctx.user_said, dict(a)))
            at = f"{a['day']}T{a['time']}"
            res = {**RES, "when": {"at": at}, "how_many": {"count": int(a.get("party") or 2)}}
            rd = {**RD, "venue": a["name"], "place_id": a.get("place_id") or RD["place_id"]}
            return await VN.follow(ctx, {"name": a["name"], "city": "Madrid"}, rd, res, at, datetime.now(timezone.utc), CARD, DEC)
        p = mock.patch.object(VN, "hold_venue", hold_venue)
        p.start()
        self.addCleanup(p.stop)

    def options(self):
        return self.hold()


class TheOptionsAreTaps(Base384):
    def test_agapis_sentence_and_its_options_exactly(self):
        q = self.options()
        self.assertEqual((q["status"], q["ask"], q["say"]), ("awaiting_yes", SAY, SAY))           # AgAPI's sentence, word for word
        self.assertEqual([c["route"] for c in q["choices"]], ["alt:1", "alt:2", "alt:3", "alt:4"])   # its rank: nothing re-ranked/added/cut
        self.assertEqual([c["title"] for c in q["choices"]],
                         ["22:30 · Fri 20 Nov", "21:45 · Fri 20 Nov", "22:00 · Sat 21 Nov", "Casa Vecina · 22:00"])
        self.assertEqual(V.read_back_line("hold_venue", {"ok": True, "result": q}), SAY)          # said by code

    def test_no_page_while_options_exist(self):
        q = self.options()
        flat = json.dumps({k: v for k, v in q.items() if k != "card"}, ensure_ascii=False)   # the venue's place card (every answer has it)
        for gone in ("open", "page_url", "no_page", "hand_over"):
            self.assertNotIn(gone, q)
        self.assertNotIn("http", flat)                                                           # no link of any kind on the card
        self.assertNotIn("Tap to finish", flat)

    def test_one_tap_books_it_through_the_one_path(self):
        q = self.options()
        done = run(VN.answer_card(Ctx("21:45 · Fri 20 Nov"), q["read_back_id"], "alt:2"))
        self.assertEqual(done["status"], "confirmed", done)
        self.assertTrue(done["line"].startswith("Booking now:"), done["line"])
        prep = self.ag.bodies("venue.prepare_booking")[-1]                                      # CR 203's SEAM: the option's own terms
        self.assertEqual((prep["date"], prep["time"], prep["party"], prep["place"]["place_id"], prep["person"]["name"]),
                         ("2026-11-20", "21:45", 2, "ChIJ329", "Tyler Warren"))                     # … for the SAME person
        self.assertEqual(self.holds, [])                                                         # no second search: straight to the act
        self.assertIn(f"Book {VENUE} on 2026-11-20 at 21:45 for 2", json.dumps(self.ag.mandates[-1], ensure_ascii=False))   # the tap's words
        self.assertEqual(self.ag.mandates[-1]["scope"]["booking"]["time"], "21:45")               # CR 196: the tap IS the approval
        self.assertNotIn(ALTS[0]["book"]["time"], json.dumps(self.ag.mandates[-1]))
        self.assertEqual(VN._HELD.get("00000000-0000-4000-8000-000000000329"), None)              # no second card held

    def test_a_nearby_venue_is_its_own_booking(self):
        q = self.options()
        run(VN.answer_card(Ctx("Casa Vecina · 22:00"), q["read_back_id"], "alt:4"))
        prep = self.ag.bodies("venue.prepare_booking")[-1]
        self.assertEqual((prep["place"]["name"], prep["place"]["place_id"], prep["place"]["website"], prep["time"]),
                         ("Casa Vecina", "ChIJvecina", "https://casavecina.example", "22:00"))

    def test_typed_words_naming_one_option(self):
        self.options()
        done = run(VN.book_venue(Ctx("the 21:45 please"), {"approval": {"said": "the 21:45 please"}}))
        self.assertEqual(done["status"], "confirmed", done)
        self.assertEqual(self.ag.bodies("venue.prepare_booking")[-1]["time"], "21:45")

    def test_a_stale_or_other_card_books_nothing(self):
        self.options()
        self.assertEqual(run(VN.answer_card(Ctx("x"), "alt_not_this_card", "alt:1"))["status"], "nothing_waiting")


class WhatsApp(Base384):
    def test_taps_are_card_taps_and_no_link(self):
        q = self.options()

        class Out:
            def __init__(self):
                self.asked, self.picked, self.texts = [], [], []

            def ask(self, text, buttons):
                self.asked.append((text, buttons))

            def pick(self, text, label, rows):
                self.picked.append((text, label, rows))

            def text(self, t):
                self.texts.append(t)
        out = Out()
        WAG._read_back(q, out)
        self.assertEqual(out.asked, [])
        (text, _label, rows), = out.picked                                                        # 4 options → the list
        self.assertEqual(text, SAY)
        self.assertEqual([r[2] for r in rows], [f"card:{q['read_back_id']}:alt:{n}" for n in (1, 2, 3, 4)])
        self.assertFalse(any("http" in str(x) for x in (text, rows, out.texts)))


class TheTrueRefusal(Base384):
    ALTS = []

    def test_no_options_their_page(self):
        q = self.options()
        self.assertEqual(q["status"], "not_booked")
        self.assertTrue(str(q.get("open") or "").startswith("https://"))                          # only then: their page


class TheRatchet(unittest.TestCase):
    def test_an_answer_with_alternatives_never_reaches_a_link(self):
        src = inspect.getsource(VN._platform_result)
        self.assertLess(src.index("alternatives_of(r)"), src.index("_link_out(link)"))           # options first: the page is after them
        alt = inspect.getsource(VN._alternatives).split('"""')[2]   # its code, not its docstring
        for gone in ("_link_out", "hand_over", "open", "page_url", "Tap to finish"):
            self.assertNotIn(gone, alt)
        self.assertIsNone(re.search(r"sorted\(|\.sort\(|reverse", inspect.getsource(VN.alternatives_of).split(chr(34) * 3)[2]))   # nothing re-ranked
        self.assertIn('"alt:"', inspect.getsource(VN.answer_card))


if __name__ == "__main__":
    unittest.main()
