"""Sasha 312 · a cancelled (or changed) booking updates the calendar: the SAME event (one UID per booking), a higher SEQUENCE, METHOD:CANCEL
(STATUS:CANCELLED) or METHOD:REQUEST at its new time — validated with a standard iCalendar parser (icalendar). Offline.

    cd backend && python -m unittest tests.test_s312 -v
"""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

import icalendar

from agapi import powers as P, s2_tools as S2T

ACCT = "acct-312"
EV = P.event_for_table("act_312@sasha.kanoe", "DiverXO", "Calle de Padre Damián 23, Madrid", "2026-11-13T21:00:00+01:00", 2, "DX-312")


def run(c):
    return asyncio.run(c)


def parse(text: str):
    cal = icalendar.Calendar.from_ical(text)
    [ev] = [c for c in cal.walk("VEVENT")]
    return cal, ev


class TheFiles(unittest.TestCase):
    def test_publish_then_cancel_the_same_event_parse_as_standard_icalendar(self):
        first = P.ics(EV, "20261029T110000Z", sequence=0)
        cancel = P.ics_cancel(EV, "20261029T120000Z", "2026-10-29T12:00:00Z")
        c1, e1 = parse(first)
        c2, e2 = parse(cancel)
        self.assertEqual((str(c1["METHOD"]), str(c2["METHOD"])), ("PUBLISH", "CANCEL"))
        self.assertEqual(str(e1["UID"]), str(e2["UID"]))                                  # the SAME event
        self.assertGreater(int(e2["SEQUENCE"]), int(e1["SEQUENCE"]))                       # a later version of it
        self.assertEqual(str(e2["STATUS"]), "CANCELLED")
        self.assertIn("mailto:sasha@booking.kanoe.ai", str(e2["ORGANIZER"]))              # RFC 5546: a CANCEL names its organizer
        self.assertTrue(first.endswith("\r\n") and "\r\n" in first)

    def test_a_change_is_a_request_at_the_new_time_with_a_higher_sequence(self):
        moved = {**EV, "starts_at": "2026-11-13T20:30:00Z", "ends_at": "2026-11-13T22:30:00Z"}
        a = P.ics_update(moved, "20261029T120000Z", "2026-10-29T12:00:00Z")
        b = P.ics_update(moved, "20261029T130000Z", "2026-10-29T13:00:00Z")   # a second change, later
        _, ea = parse(a)
        cal_b, eb = parse(b)
        self.assertEqual(str(cal_b["METHOD"]), "REQUEST")
        self.assertEqual(ea["DTSTART"].dt.isoformat(), "2026-11-13T20:30:00+00:00")
        self.assertGreater(int(eb["SEQUENCE"]), int(ea["SEQUENCE"]))

    def test_the_default_file_is_byte_for_byte_as_before(self):   # AgAPI's conformance cases (test_s2_powers) pin it
        self.assertNotIn("SEQUENCE", P.ics(EV, "20261029T110000Z"))
        self.assertIn("METHOD:PUBLISH", P.ics(EV, "20261029T110000Z"))


class OnlyWhatWentInTheirCalendar(unittest.TestCase):
    def acts(self, extra=()):
        return [{"kind": "calendar", "state": "done", "proof": {"booking_id": "act_312", "uid": EV["uid"], "event": EV}}, *extra]

    def test_a_booking_in_their_calendar_gets_its_cancel_once(self):
        rec = mock.AsyncMock()
        with mock.patch("agapi.s2_records.acts", mock.AsyncMock(return_value=self.acts())), mock.patch("agapi.s2_records.record", rec):
            u = run(S2T.calendar_update(ACCT, ["act_312"], "cancel", "2026-10-29T12:00:00Z"))
        self.assertEqual((u["kind"], u["uid"]), ("cancel", EV["uid"]))
        self.assertIn("/api/agent/ics/", u["url"])
        self.assertEqual(rec.call_args.args[2], "cancelled")
        sent = {"kind": "calendar", "state": "cancelled", "proof": {"uid": EV["uid"], "sequence": u["sequence"]}}
        with mock.patch("agapi.s2_records.acts", mock.AsyncMock(return_value=self.acts([sent]))), mock.patch("agapi.s2_records.record", rec):
            self.assertIsNone(run(S2T.calendar_update(ACCT, ["act_312"], "cancel", "2026-10-29T12:00:00Z")))   # once per version

    def test_never_in_their_calendar_nothing_is_sent(self):
        with mock.patch("agapi.s2_records.acts", mock.AsyncMock(return_value=[])):
            self.assertIsNone(run(S2T.calendar_update(ACCT, ["act_312"], "cancel", "2026-10-29T12:00:00Z")))

    def test_the_whole_class_reads_the_record(self):   # a table / stay on AgAPI's record, cancelled or changed by its route
        rows = [{"source": "act", "id": "act_312", "act_id": "act_312", "venue": "DiverXO", "status": "cancelled",
                 "cancelled_at": "2026-10-29T12:00:00Z"},
                {"source": "act", "id": "act_ST", "venue": "Hotel WhatsApp", "status": "confirmed", "date": "2026-11-15", "time": "15:00",
                 "party": 1, "change_answer": {"state": "confirmed"}, "changed_at": "2026-10-29T10:46:00Z",
                 "stay": {"check_in": "2026-11-15", "check_out": "2026-11-18", "nights": 3, "arrival": "15:00"}}]
        seen = []

        async def upd(account, ids, kind, changed_at, ev_now=None):
            seen.append((ids[0], kind, changed_at, (ev_now or {}).get("ends_at")))
            return {"kind": kind, "uid": f"{ids[0]}@sasha.kanoe", "line": "x", "url": "u"}
        with mock.patch("agapi.itinerary.venue_rows", mock.AsyncMock(return_value=rows)), mock.patch.object(S2T, "calendar_update", upd):
            out = run(S2T.calendar_updates_due(ACCT))
        self.assertEqual([x[:3] for x in seen], [("act_312", "cancel", "2026-10-29T12:00:00Z"), ("act_ST", "change", "2026-10-29T10:46:00Z")])
        self.assertTrue(seen[1][3].startswith("2026-11-18"))   # the stay's new check-out, from the record's own nights
        self.assertEqual(len(out), 2)


class EverySurfaceShowsIt(unittest.TestCase):
    def test_the_card_and_whatsapp(self):
        from app.agent import sasha as SA
        from booking_signer import wa_agent as WA, guest_whatsapp as GW
        res = {"flight": True, "status": "cancelled", "say": "…", "calendar_update": {"kind": "cancel", "line": S2T.CAL_CANCEL_LINE, "url": "https://x/a.ics"}}
        ev = SA.render("cancel_booking", res, {})
        self.assertEqual((ev["kind"], ev["update"], ev["links"]), ("calendar", "cancel", {"apple": "https://x/a.ics"}))
        out = GW.Out()
        WA._calendar(ev, out)
        self.assertEqual(out.items[0][1], f"{S2T.CAL_CANCEL_LINE}\nhttps://x/a.ics")


if __name__ == "__main__":
    unittest.main()
