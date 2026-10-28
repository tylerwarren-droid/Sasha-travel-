"""Sasha 302 · T80 — THE FINE PRINT, SAID AS IT IS, ON AgAPI'S RECORD.

Root test (written before code): (1) booking_fine_print's and keep_note's `say` is said BY CODE, word for word, and the turn ends on
it — the model never paraphrases the venue's terms (found live on 301: markdown "**…**" on the phone); (2) a term on AgAPI's record
(venue.bookings, CR 132) is read from the venue's words IN FULL — the record's 160-character display line never cuts a term into
something they didn't say; (3) a hotel stay booked as an act is a HOTEL on the itinerary, so his hotel programme's line shows on it
and nowhere else.

    cd backend && python -m unittest tests.test_s302 -v
"""
from __future__ import annotations

import inspect
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from agapi import booking_terms as BT, itinerary as IT
from app.agent import voice as V

DAY = (datetime.now(ZoneInfo("Europe/Madrid")) + timedelta(days=3)).date().isoformat()
LONG = ("Hola, confirmamos la mesa para el viernes a las 21:00 para dos personas, en la terraza que pedisteis, junto a la ventana "
        "grande del fondo. Pedimos una señal de 20€ por persona para confirmar la reserva. "
        "Las cancelaciones con menos de 24 horas de antelación no se reembolsan.")


class SaidByCode(unittest.TestCase):
    def test_the_fine_print_and_the_keep_line_are_said_as_given(self):
        r = {"ok": True, "result": {"say": "DiverXO, Friday 30 October 21:00: Deposit: they said “Pedimos una señal…”"}}
        self.assertEqual(V.fine_print_line("booking_fine_print", r), r["result"]["say"])
        self.assertEqual(V.fine_print_line("keep_note", {"ok": True, "result": {"say": "Saved your Marriott Bonvoy number in your Keep."}}),
                         "Saved your Marriott Bonvoy number in your Keep.")
        self.assertEqual(V.fine_print_line("my_plans", r), "")
        self.assertEqual(V.fine_print_line("booking_fine_print", {"ok": False, "error": {"code": "date_invalid"}}), "")

    def test_the_turn_says_it_by_code_and_ends_on_it(self):
        from app.agent import sasha as S
        src = inspect.getsource(S)
        self.assertIn("_V.discover_line(u.name, r) or _V.fine_print_line(u.name, r)", src)   # the read-back chain: said by code, then break


class OnTheRecord(unittest.TestCase):
    def record(self, words):
        return {"act_id": "act_1", "state": "confirmed", "route": "whatsapp", "venue": {"name": "Taverna"}, "at": f"{DAY}T21:00",
                "party": 2, "venue_words": {"untrusted_text": words}}

    def test_a_term_is_read_from_their_words_in_full_never_the_160_cut(self):
        self.assertGreater(len(LONG), 160)
        row = IT._from_record(self.record(LONG))
        self.assertEqual(len(row["venue_said"]["untrusted_text"]), 160)   # the line shown
        t = IT.row_terms(row)
        self.assertEqual([x["kinds"] for x in t], [["deposit"], ["cancellation"]])
        self.assertTrue(all(x["quote"] in LONG for x in t))
        self.assertTrue(t[1]["by"])

    def test_a_stay_act_is_a_hotel_and_his_programme_shows_on_it_only(self):
        row = IT._from_record({**self.record("Confirmed."), "venue": {"name": "Marriott Test Hotel (sandbox)"}}, {"stay": {"nights": 2}})
        self.assertEqual(row["type"], "hotel")
        self.assertEqual(IT._venue_kind(row["type"]), "hotel")
        wallet = [{"item_id": "k1", "type": "loyalty", "masked": "Marriott Bonvoy ••••001", "program": "Marriott Bonvoy"}]
        self.assertEqual([p["line"] for p in BT.perks_for("hotel", "Marriott Test Hotel (sandbox)", wallet)],
                         ["Use your Marriott Bonvoy number (••••001)."])
        self.assertEqual(BT.perks_for(IT._venue_kind("restaurant"), "Taverna Correo", wallet), [])



class HisYesCarriesTheAsk(unittest.TestCase):
    """Found on the v1.43 sandbox walk (CR 132 venue_manage._ask): the approved venue.change_booking is read AGAIN — a change without
    its new time, a "running late" without its arrive, is refused. His yes sends what the read-back asked, nothing less."""

    def go(self, kind, ask):
        import asyncio
        from unittest import mock
        from agapi import venue_submit as VS
        sent = []

        async def call(op, body, approval=None, account=None):
            sent.append((op, dict(body), approval))
            return {"ok": True, "result": {"status": "sent", "change_act_id": "act_chg"}}

        async def approval(account, rid, said):
            return "apv_1"
        held = {"read_back_id": "rb_1", "act_id": "act_1", "end_user": "eu_1", "kind": kind, "ask": ask, "venue": "Taverna Correo"}
        with mock.patch.object(VS, "CALL", call), mock.patch.object(VS, "_approval", approval), \
                mock.patch.object(VS, "acts_of", mock.AsyncMock(return_value=[])), mock.patch.object(VS, "_remember", mock.AsyncMock()):
            r = asyncio.run(VS.change_submit("acct", held, "yes"))
        self.assertTrue(r["ok"])
        return sent[-1]

    def test_a_change_goes_with_its_new_time(self):
        op, body, apv = self.go("change", {"at": f"{DAY}T21:30"})
        self.assertEqual((op, apv, body["kind"], body["at"]), ("venue.change_booking", "apv_1", "change", f"{DAY}T21:30"))

    def test_running_late_goes_with_when_they_arrive(self):
        _, body, _ = self.go("late", {"arrive": "21:45"})
        self.assertEqual((body["kind"], body["arrive"]), ("late", "21:45"))

    def test_the_held_yes_keeps_the_ask(self):
        from agapi import s2_manage as SM
        self.assertIn("ask=args", inspect.getsource(SM._act_notice))


from tests.test_s300 import Base as S300Base, Ctx, run   # noqa: E402


class OnTheCard(S300Base):
    def test_the_plans_card_carries_the_fine_print(self):
        from agapi import s2_manage as SM
        self.assertIn('"terms", "perks"', inspect.getsource(SM.my_plans))   # found live: the card never got them (301)
        self.api.states["act_mail"] = "confirmed"
        out = run(SM.my_plans(Ctx(), {}))
        self.assertTrue(all("venue_said" not in i for i in out["items"] if i["title"] in ("Casa Lucio", "Botín")))   # not answered yet

    def test_a_sent_requests_note_is_never_their_words(self):
        from agapi import venue_submit as VS
        orig = VS.CALL

        async def call(op, body, approval=None, account=None):
            r = await orig(op, body, approval, account)
            if op == "venue.booking_status" and body["act_id"] == "act_wa":
                r["result"]["venue_words"] = {"untrusted_text": "Emailed Casa Lucio (x@y.test) — sandbox: captured, never sent."}
            return r
        from unittest import mock
        with mock.patch.object(VS, "CALL", call):
            r = {x["venue"]: x for x in run(IT.venue_rows("00000000-0000-4000-8000-000000000300"))}
        self.assertEqual(r["Casa Lucio"]["status"], "asked")
        self.assertNotIn("venue_said", r["Casa Lucio"])


if __name__ == "__main__":
    unittest.main()
