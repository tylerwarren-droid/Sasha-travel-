"""Sasha 376 · THE FINISH IS ONE CONVERSATION STATE that every channel renders whole and every form of yes answers. NO PATCHES.

Found (row 1901, the SME dry run): WhatsApp's card cut at 1,000 characters (the manager approving 5 people seeing 1); a typed "Yes, book
them" started a NEW instruction; the finish said "invoice €0.00" for a record that didn't answer; "Book Ana, Elena and Marta anyway" →
names not found; a named worker outside the mandate dropped ("not booked just now"); the model narrating its own double call.

ONE source each:
  · the OPEN CARD (group_book.open_card), read by sasha.turn BEFORE anything — any yes (booking_signer/yes.py) answers it via card_tap;
  · WhatsApp's ONE renderer (guest_whatsapp.fit): split into messages at line ends, the question + buttons last — never truncated;
  · the ONE person resolver (groups.pick → _by_name): full name, else the one person with that first/last name, two → asked;
  · AgAPI's record read through ONE reader (group_book._records): unread → Unread → said as unread, never €0.00 / nothing booked;
  · a named worker outside the mandate is ON the card (book_under_mandate: "item" and "outside" alike);
  · one start per (tool, arguments) per turn (v0.call · STARTS).

    cd backend && python -m unittest tests.test_s376_the_finish_is_one_state -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import time
import unittest
from unittest import mock

from agapi import v0 as API
from booking_signer import group_book as GB, groups as G, guest_whatsapp as GW, yes as YS
from tests import test_s365_mandate as T365, test_s367_mandate_at_agapi as T367

run = asyncio.run
ROOT = pathlib.Path(__file__).resolve().parents[2]
OWNER = T367.OWNER


class AnyYesAnswersTheOpenCard(unittest.TestCase):
    def _turn(self, said):
        from app.agent import sasha as AG
        cid = "grp_" + "a" * 20
        taps = []

        async def tap(account, session, surface, t, message):
            taps.append((account, t["read_back_id"], t["choice"], message))
            yield {"type": "done", "text": "Booking 3… 0 done."}

        async def nothing(*a, **k):
            return None
        with mock.patch.dict(GB._CARDS, {cid: {"account": OWNER, "action": "book", "items": [{}], "at": time.time(), "movement_id": "m"}}, clear=True), \
                mock.patch.object(AG, "card_tap", tap), mock.patch("booking_signer.channel.used", nothing), \
                mock.patch("agapi.person_access.warm", nothing):
            async def go():
                return [ev async for ev in AG.turn(OWNER, said, [], "conv-376", surface="wa")]
            evs = run(go())
        return cid, taps, evs

    def test_every_yes_form_answers_that_card(self):
        for said in ("Yes, book them", "yes", "sí", "ok book them", "OK", "vale"):
            cid, taps, evs = self._turn(said)
            self.assertEqual(taps, [(OWNER, cid, "group_yes", said)], said)                 # the card — never a new instruction
            self.assertEqual(evs[-1]["type"], "done")

    def test_no_card_no_capture_and_not_a_yes_never_captured(self):
        self.assertIsNone(GB.open_card("nobody"))
        self.assertFalse(YS.is_yes("Book all executives to Lisbon"))
        src = (ROOT / "backend" / "app" / "agent" / "sasha.py").read_text()
        i, j = src.index("_open = _GBo.open_card(account)"), src.index("remembered = _HANDOVER.pop(session")
        self.assertLess(i, j)                                                                   # BEFORE anything else in the turn


class TheReadBackReachesWhatsAppWhole(unittest.TestCase):
    def test_n_people_whole_question_and_buttons_last(self):
        people = [f"For Person {i}:\n" + "\n".join(f"Flight {k} for Person {i}: EUR 40.{k}. " + "Non-refundable: the fare's own conditions allow no refund. " * 3
                                                    for k in range(2)) + f"\nTotal EUR 362.8{i}." for i in range(7)]
        body = "\n\n".join(people) + "\n\nBook these 7 anyway?"
        out = GW.Out().ask(body, [("Yes, book them", "card:grp_x:group_yes"), ("No", "card:grp_x:group_no")])
        GW.fit(out)
        self.assertEqual(out.items[-1][0], "ask")
        self.assertTrue(out.items[-1][1].endswith("Book these 7 anyway?"))                   # the question LAST, with its buttons
        self.assertTrue(all(len(i[1]) <= (GW.ASK_MAX if i[0] == "ask" else GW.TEXT_MAX) for i in out.items))
        said = "\n".join(i[1] for i in out.items)
        for i in range(7):
            self.assertIn(f"For Person {i}:", said)
            self.assertIn(f"Total EUR 362.8{i}.", said)
        self.assertEqual(re.sub(r"\s+", "", said), re.sub(r"\s+", "", body))                 # every word, in order — nothing cut

    def test_no_cut_left_in_the_whatsapp_paths(self):
        src = (ROOT / "backend" / "booking_signer" / "wa_agent.py").read_text()
        self.assertNotRegex(src, r"out\.(ask|text|pick)\([^)]*\[:1[05]00\]")


class EveryNameTheFinishSpeaksResolves(unittest.TestCase):
    PEOPLE = [{"id": "1", "name": "Ana García"}, {"id": "2", "name": "Elena Ortega"}, {"id": "3", "name": "Marta Ruiz"},
              {"id": "4", "name": "Luis Pérez"}, {"id": "5", "name": "Luis Navarro"}]

    def test_first_names_full_names_and_two_asked(self):
        got, unknown, amb = G.pick(self.PEOPLE, ["Ana", "Elena", "marta ruiz"])
        self.assertEqual([p["name"] for p in got], ["Ana García", "Elena Ortega", "Marta Ruiz"])
        got, unknown, amb = G.pick(self.PEOPLE, ["Luis"])
        self.assertEqual((got, sorted(amb["Luis"])), ([], ["Luis Navarro", "Luis Pérez"]))   # two: asked, never guessed
        self.assertIn("Which Luis", G.ambiguous_words(amb))
        self.assertEqual(G.pick(self.PEOPLE, ["Zoe"])[1], ["Zoe"])

    def test_every_group_path_uses_the_one_resolver(self):
        for f in ("booking_signer/group_book.py", "booking_signer/group_outcome.py", "booking_signer/mandate.py"):
            src = (ROOT / "backend" / f).read_text()
            self.assertNotRegex(src, r'\["name"\]\.lower\(\) in \{|\["name"\] in set\(|by_name = \{', f)


class NoMoneySaidForAnUnreadRecord(unittest.TestCase):
    def test_the_invoice_and_the_finish_say_unread_never_zero(self):
        with T367.World() as w:
            T367._instruction(w)
            mv = run(G.store().movement(OWNER))
            real = w.agapi._do

            async def down(op, body, approval):
                if op == "group.bookings":
                    return {"ok": False, "error": {"code": "upstream_unreachable", "message": "AgAPI didn't answer"}}
                return await real(op, body, approval)
            with mock.patch.object(w.agapi, "_do", down):
                inv = run(GB.invoice(OWNER, mv["id"]))
                fin = run(GB.finish(OWNER, mv["id"], [], []))
        self.assertTrue(inv.get("unread"))
        self.assertNotIn("€0.00", fin["say"])
        self.assertEqual(fin["say"], GB.UNREAD_SAY)


class AWorkerOutsideTheMandateReachesTheCard(unittest.TestCase):
    def test_book_bruno_anyway_by_his_first_name_is_on_the_card(self):
        with T367.World(T367.MandateAgAPI(outside={"Bruno Example": "fare_not_refundable"})) as w:
            T367._instruction(w)
            mv = run(G.store().movement(OWNER))
            mid = mv["rules"]["mandate"]["agapi"]["mandate_id"]
            got = run(GB.book_under_mandate(OWNER, mid, ["Bruno"], mv["id"], over_ok=True))
        self.assertEqual([x["name"] for x in got["outside"]], ["Bruno Example"])            # ON the card …
        self.assertEqual(got["asks"], [])                                                     # … never dropped as "not booked just now"
        self.assertTrue(got["card"]["read_back_id"].startswith("grp_"))


class OneStartPerTurn(unittest.TestCase):
    def test_the_same_start_twice_in_a_turn_is_one_call(self):
        calls = []

        async def select(ctx, a):
            calls.append(a)
            return {"started": True, "say": "On it."}
        t = dict(API.BY_NAME["group_select"], fn=select)
        with mock.patch.dict(API.BY_NAME, {"group_select": t}):
            ctx = API.Ctx(account=OWNER, user_said="Book all executives", surface="s2", session="s")
            a = {"change": "new", "destination": "Lisbon", "starts_on": "2027-02-24", "ends_on": "2027-02-26", "roles": ["executives"]}
            r1, r2 = run(API.call(ctx, "group_select", dict(a))), run(API.call(ctx, "group_select", dict(a)))
        self.assertEqual(len(calls), 1)
        self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
