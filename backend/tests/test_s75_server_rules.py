"""S-75 steps 1–2 · the three rules the web used to own now live on the server (one sentence, one pick, one "yes"), and a
yes may arrive by WhatsApp's button or typed on WhatsApp — with its words. Offline.

    cd backend && python -m unittest tests.test_s75_server_rules -v
"""
from __future__ import annotations

import pathlib
import re
import unittest

from booking_signer import ranking as K, sentences as SN, yes as YS
from tests import test_booking_calls as BC   # a module, so its own test classes are not collected twice


def obj(name="Tyler Warren", count=2, unit="people", at="2026-10-03T21:00", ask=False):
    return {"who": {"name": name}, "how_many": {"count": count, "unit": unit},
            "when": {"mode": "venue_proposes"} if ask else {"mode": "at", "at": at}}


class OneSentence(unittest.TestCase):
    def test_the_words_the_web_used_to_build(self):
        """The exact strings ChatBookingCall.tsx built before S-75 (en-GB long date, surname only)."""
        cases = [
            (obj(), "Botavara Chamberí", "Book Botavara Chamberí for 2, Saturday 3 October at 21:00, under Warren?"),
            (obj(name="Ana", count=1), "Hanakura", "Book Hanakura for 1, Saturday 3 October at 21:00, under Ana?"),
            (obj(count=4, at="2026-12-31T13:30"), "Casa Lucio", "Book Casa Lucio for 4, Thursday 31 December at 13:30, under Warren?"),
            (obj(ask=True), "Sasha Test Kitchen", "Book Sasha Test Kitchen for 2, whenever they have space, under Warren?"),
            (obj(count=1, unit="hours", at="2026-10-05T10:00"), "Studio 9", "Book Studio 9 for 1 hours, Monday 5 October at 10:00, under Warren?"),
        ]
        for o, venue, want in cases:
            self.assertEqual(SN.confirm_sentence(o, venue), want)

    def test_the_cancel_sentence(self):
        self.assertEqual(SN.cancel_sentence(obj(), "Botavara"), "Cancel Botavara, Saturday 3 October at 21:00, for 2, under Tyler Warren?")
        self.assertEqual(SN.cancel_sentence({}, "Botavara"), "Cancel Botavara, no day set, for —, under —?")


class OnePick(unittest.TestCase):
    def c(self, pid, rating, open_=None):
        return {"place_id": pid, "rating": rating, "rating_count": 99, "price_level": None, "distance_m": None,
                "status": "OPERATIONAL", "open_at": {"known": open_ is not None, "open": open_, "words": "x"}}

    def test_exactly_one_pick_per_ordering_and_never_a_greyed_place(self):
        cs = [self.c("best_but_closed", 4.9, open_=False), self.c("open", 4.5, open_=True), self.c("unknown", 4.7)]
        r = K.rank(cs, open_at="2026-10-03T21:00", near_found=False)
        for chip, ids in r["orders"].items():
            self.assertIn(r["picks"][chip], ids)
            self.assertNotIn(r["groups"][r["picks"][chip]], ("closed_then", "closed_temporarily"))
        self.assertEqual(r["pick"], r["picks"]["rated"])
        self.assertNotEqual(r["pick"], "best_but_closed")

    def test_no_pick_when_everything_is_closed_then(self):
        r = K.rank([self.c("a", 4.9, open_=False)], open_at="2026-10-03T21:00", near_found=False)
        self.assertIsNone(r["pick"])


class OneYes(unittest.TestCase):
    def test_the_pattern_is_the_web_s_byte_for_byte(self):
        ts = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "lib" / "chat-booking-bus.ts").read_text(encoding="utf-8")
        m = re.search(r"^const YES = /(.*)/i$", ts, re.M)
        self.assertIsNotNone(m, "chat-booking-bus.ts no longer declares const YES = /…/i")
        self.assertEqual(m.group(1), YS.PATTERN, "the web's yes and the server's yes have drifted")

    def test_what_is_a_yes(self):
        for s in ("yes", "Yes please", "sí", "Si", "vale!", "ok", "okay then", "go ahead", "confirmed", "oui"):
            self.assertTrue(YS.is_yes(s), s)
        for s in ("yesterday", "no", "not yet", "okra", "", "maybe yes", "japan"):
            self.assertFalse(YS.is_yes(s), s)

    def test_how_a_yes_may_arrive(self):
        ok = [{"how": "button"}, {"how": "whatsapp_button"}, {"how": "whatsapp_text", "said": "vale"},
              {"how": "chat", "said": "yes"}, {"how": "voice", "said": "yes"}]
        bad = [{"how": "whatsapp_text"}, {"how": "whatsapp_text", "said": "  "}, {"how": "chat"}, {"how": "sms", "said": "yes"},
               {"how": "auto"}, None, "yes"]
        for a in ok:
            self.assertTrue(YS.approval_ok(a), a)
        for a in bad:
            self.assertFalse(YS.approval_ok(a), a)


class WhatsAppYes(unittest.TestCase):
    """S-75 step 2 · at the place route: the typed WhatsApp yes needs its words; WhatsApp's button does not."""
    make_store, setUp, tearDown, prepare = BC.OnMemory.make_store, BC.CallRoutes.setUp, BC.CallRoutes.tearDown, BC.CallRoutes.prepare

    def place(self, prep, approval):
        return self.c.post(f"/api/booking/calls/{prep['call_id']}/place",
                           json={"read_back_sha256": prep["read_back"]["sha256"], "approval": approval})

    def test_typed_on_whatsapp_needs_the_words(self):
        prep = self.prepare()
        r = self.place(prep, {"how": "whatsapp_text", "said": ""})
        self.assertEqual((r.status_code, r.json()["rule"]), (422, "approval_void"))
        self.assertEqual(self.place(prep, {"how": "whatsapp_text", "said": "vale"}).json()["status"], "placed")

    def test_the_whatsapp_button_is_a_yes(self):
        self.assertEqual(self.place(self.prepare(), {"how": "whatsapp_button", "said": "Yes, book it"}).json()["status"], "placed")


if __name__ == "__main__":
    unittest.main()
