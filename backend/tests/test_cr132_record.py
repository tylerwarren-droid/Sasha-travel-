"""CR 132 · AgAPI's booking record holds every route (Sasha 300's asks, built in AgAPI v1.43.0): the ONE itinerary reads it once
(venue.bookings) and a hand-over with a prepared booking goes on it (venue.handed_over, after her answer). An AgAPI without the ops:
everything as before. A cancellation booked by his own WhatsApp: AgAPI's words, for HIM to send.

    cd backend && python -m unittest tests.test_cr132_record -v
"""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from agapi import itinerary as IT, venue_submit as VS, venues as VN
from tests import test_s300 as T

ACCT, DAY = T.ACCT, T.DAY


class Record(T.AgAPI):
    """AgAPI v1.43.0: venue.bookings answers with its record; venue.handed_over puts a hand-over on it."""

    def __init__(self, bookings):
        super().__init__(True)
        self.bookings = bookings

    async def __call__(self, op, body, approval=None, account=None):
        if op == "venue.bookings":
            self.calls.append((op, dict(body), approval))
            return {"ok": True, "result": {"bookings": self.bookings}}
        if op == "venue.handed_over":
            self.calls.append((op, dict(body), approval))
            return {"ok": True, "result": {"act_id": "act_handed", "state": "handed_over"}}
        return await super().__call__(op, body, approval, account)


RECORD = [{"act_id": "act_mail", "state": "confirmed", "route": "email", "venue": {"name": "DiverXO", "place_id": "ChIJ-diverxo",
           "maps_url": "https://www.google.com/maps/search/?api=1&query=DiverXO&query_place_id=ChIJ-diverxo", "address": "Calle de Padre Damián, 23"},
           "at": f"{DAY}T21:30", "party": 2, "manage": {"change": "message", "cancel": "message", "late": "message"}, "external_ref": "trip:trip-9",
           "venue_words": {"untrusted_text": "Sí, a las 21:30 os esperamos.", "at": "x"}},
          {"act_id": "act_handed", "state": "handed_over", "route": "platform", "platform": "CoverManager", "venue": {"name": "La Mi Venta"},
           "at": f"{DAY}T21:30", "party": 2, "manage": {"change": "their_page", "cancel": "their_page", "late": "their_page"},
           "manage_url": "https://www.covermanager.com/r/lamiventa"}]


class ReadsTheRecord(T.Base):
    def setUp(self):
        super().setUp()
        self.api = Record([dict(b) for b in RECORD])
        p = mock.patch.object(VS, "CALL", self.api)
        p.start()
        self.addCleanup(p.stop)

    def test_a_agapis_record_is_the_truth_for_every_booking_on_it(self):
        r = self.rows()
        d = r["DiverXO"]
        self.assertEqual((d["status"], d["route"], d["time"], d["trip_id"]), ("confirmed", "email", "21:30", "trip-9"))   # moved by its reply
        self.assertEqual(d["address"], "Calle de Padre Damián, 23")
        self.assertIn("query_place_id=ChIJ-diverxo", d["map_url"])
        self.assertEqual(d["venue_said"]["untrusted_text"], "Sí, a las 21:30 os esperamos.")
        m = r["La Mi Venta"]
        self.assertEqual((m["source"], m["act_id"], m["status"], m["route"], m["manage"]), ("act", "act_handed", "handed_over", "platform", "their_page"))
        self.assertEqual(len([x for x in run_rows() if x["venue"] == "La Mi Venta"]), 1)   # its hand-over row isn't a second one

    def test_b_the_rest_as_before(self):
        r = self.rows()
        self.assertEqual(r["Casa Lucio"]["route"], "kanoe_whatsapp")      # an act not on the list (an older AgAPI's): as before
        self.assertEqual(r["Bar Tomate"]["source"], "handover")            # a hand-over with no prepared booking: its own row


class OlderAgAPI(T.Base):
    def test_without_the_op_nothing_changes(self):
        r = self.rows()   # test_s300's AgAPI raises on venue.bookings, like an AgAPI without it answering an error
        self.assertEqual((r["DiverXO"]["route"], r["La Mi Venta"]["source"]), ("email", "handover"))


class HandOverOnTheRecord(T.Base):
    def setUp(self):
        super().setUp()
        self.api = Record([])
        p = mock.patch.object(VS, "CALL", self.api)
        p.start()
        self.addCleanup(p.stop)

    def test_a_after_her_answer_with_its_prepared_booking(self):
        async def go():
            await VN.note_prepared(ACCT, "Taberna El Sur", f"{DAY}T21:00", 2, "https://wa.me/34600?text=x", route="your_whatsapp",
                                   prepared_id="vpr_" + "a" * 32)
            sent_at_once = [c for c in self.api.calls if c[0] == "venue.handed_over"]
            await asyncio.gather(*list(VS._LATER_HANDED))
            return sent_at_once
        at_once = asyncio.run(go())
        self.assertEqual(at_once, [])                                          # never awaited by her answer
        got = [c[1] for c in self.api.calls if c[0] == "venue.handed_over"]
        self.assertEqual([(g["prepared_id"], g["how"]) for g in got], [("vpr_" + "a" * 32, "whatsapp_person")])
        self.assertNotIn("link", got[0])                                       # a wa.me link carries his words; only an https page is passed

    def test_b_no_prepared_booking_nothing_is_written(self):
        asyncio.run(VN.note_prepared(ACCT, "Bar Tomate", f"{DAY}T13:00", 2, "https://bartomate.test/reservas", route="their_page"))
        self.assertEqual([c for c in self.api.calls if c[0] == "venue.handed_over"], [])

    def test_c_the_route_names(self):
        async def go(route, platform):
            await VN.note_prepared(ACCT, "X", f"{DAY}T13:00", 2, "https://x.test/p", route=route, platform=platform, prepared_id="vpr_" + "b" * 32)
            await asyncio.gather(*list(VS._LATER_HANDED))
        for route, platform, how in (("platform", None, "platform"), (None, "CoverManager", "platform"), ("their_page", None, "their_page")):
            self.api.calls.clear()
            asyncio.run(go(route, platform))
            self.assertEqual([c[1]["how"] for c in self.api.calls if c[0] == "venue.handed_over"], [how], (route, platform))


class CancelByHisOwnWhatsApp(T.Base):
    def test_the_words_for_him_to_send(self):
        async def cancel_submit(account, held, said):
            return {"ok": True, "status": "person_sends", "say": "Here's the message for Taberna — send it from your WhatsApp.",
                    "message": {"text": "Hola, … cancélenla.", "link": "https://wa.me/34611222333?text=Hola"}}
        held = {"act_id": "act_wa", "at": T.datetime.now(T.timezone.utc) - T.timedelta(minutes=1), "venue": "Taberna"}
        with mock.patch.object(VS, "cancel_submit", cancel_submit):
            out = asyncio.run(VN._cancel_act(T.Ctx("yes, cancel it", ago=0), {"act_id": "act_wa"}, held, "yes, cancel it", lambda s: True))
        self.assertEqual((out["status"], out["sent"]), ("yours_to_send", False))
        self.assertEqual(out["button"]["link"], "https://wa.me/34611222333?text=Hola")


def run_rows():
    return asyncio.run(IT.venue_rows(ACCT))


if __name__ == "__main__":
    unittest.main()
