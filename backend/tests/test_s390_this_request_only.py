"""Sasha 390 · a venue booking uses only what the person chose THIS request, and the form's options by their identity.

Measured (Tyler's WhatsApp, 19 Nov; s2_memory, sasha_measures, agapi-live, Twilio — read-only):
  A · 09:14 Cava Baja (listing 3) was booked with no list: Tyler's conversation memory (13–14 Nov summary, decided, screen.focus) was
      restored into the cards "on his screen", search_venues' named_on_screen matched "La Taberna de Peñalver" inside "…Cava Baja | …"
      and refused to search ("that's their pick"); and the booking read asks Google for ONE listing by name (maxResultCount 1).
  B · the Zona question went as say:<label> taps cut at 20 ("Salón Interior Mesa…") — words for the model, never the option; typed
      "Mesa Alta" matched nothing (only a whole option inside the words counted) — asked again; the tap ended in a give-up with a phone.

THE CLASS, made impossible:
  A: three same-name venues × a new request with no location → the list, never a silent pick; a card restored from memory never picks.
  B: every field kind (2 options, more than 3, labels over 20 chars) × tap and typed → venue.submit_booking receives AgAPI's option.

    cd backend && python -m unittest tests.test_s390_this_request_only -v
"""
from __future__ import annotations

import asyncio
import re
import unittest
from unittest import mock

from agapi import venues as VN
from booking_signer import venue_read as VR, wa_agent as WA
from tests import test_s329 as T329
from tests.test_s329 import Ctx, run

ACCT = "00000000-0000-4000-8000-000000000390"
PENALVER = [{"id": "ChIJnx_fKOApQg0RlDK1xQwDUBI", "displayName": {"text": "La Taberna de Peñalver"}},
            {"id": "ChIJ99lSkHIpQg0RHt3kM8RiHO0", "displayName": {"text": "Taberna de Peñalver Callao"}},
            {"id": "ChIJvVxOe_cnQg0RgAIhtCFzZx4", "displayName": {"text": "La Taberna de Peñalver Cava Baja | Restaurante La Latina"}}]


def card(place):
    return {"name": place["displayName"]["text"], "place_id": place["id"]}


class WhichVenue(unittest.TestCase):
    def setUp(self):
        VN._SHOWN.pop(ACCT, None)
        VN._SHOWN_AT.pop(ACCT, None)

    def test_three_same_name_venues_are_the_list_never_a_silent_pick(self):
        """The booking read by name: Google's listings that answer to the name → refused as several places (they choose)."""
        class R:
            status_code = 200

            def json(self):
                return {"places": PENALVER}

        async def http(*a, **k):
            return R()
        with self.assertRaises(VR.ReadRefused) as e:
            run(VR.read_places(http, "key", "La Taberna de Peñalver", "Madrid", __import__("datetime").datetime.now()))
        self.assertEqual(e.exception.rule, "several_places")
        self.assertEqual(len(VR.named_alike("La Taberna de Peñalver", PENALVER)), 3)
        self.assertEqual(len(VR.named_alike("Casa Lucio", [{"displayName": {"text": "Casa Lucio"}},
                                                           {"displayName": {"text": "Sobrino de Botín"}}])), 1)   # one: not ambiguous

    def test_a_read_that_is_several_places_tells_the_model_to_show_the_list(self):
        async def api(account, method, path, body=None, timeout=90.0):
            return 422, {"rule": "several_places", "message": "3 places in Madrid are called “La Taberna de Peñalver”"}
        ctx = Ctx("Book dinner for 2 at La Taberna de Peñalver tonight at 21:30")
        ctx.account = ACCT
        with mock.patch("booking_signer.guest_whatsapp.api", api):
            with self.assertRaises(Exception) as e:
                run(VN._read(ctx, {"name": "La Taberna de Peñalver", "city": "Madrid"}))
        self.assertEqual(getattr(e.exception, "code", None), "choose_venue")
        self.assertIn("search_venues", str(e.exception))

    def test_a_card_restored_from_memory_never_picks(self):
        VN.remember_cards(ACCT, [card(PENALVER[2])], at=0)   # 13–14 Nov's Cava Baja, restored by s2_memory.recall
        self.assertIsNone(VN.named_on_screen(ACCT, "La Taberna de Peñalver"))
        self.assertIsNone(VN.card_of(ACCT, None, "La Taberna de Peñalver Cava Baja | Restaurante La Latina"))
        self.assertEqual(VN.card_of(ACCT, PENALVER[2]["id"])["place_id"], PENALVER[2]["id"])   # by its id: still its card (display)

    def test_this_requests_list_picks_only_an_unambiguous_name(self):
        VN.remember_cards(ACCT, [card(p) for p in PENALVER])   # this request's list
        self.assertIsNone(VN.named_on_screen(ACCT, "Peñalver"))   # all three answer: the list decides
        self.assertEqual(VN.named_on_screen(ACCT, "Taberna de Peñalver Callao")["place_id"], PENALVER[1]["id"])
        self.assertEqual(VN.named_on_screen(ACCT, "La Taberna de Peñalver")["place_id"], PENALVER[0]["id"])   # its exact name

    def test_recall_restores_history_never_a_pick(self):
        import inspect
        from agapi import s2_memory as MEM
        self.assertIn('remember_cards(account, scr["cards"], at=0)', inspect.getsource(MEM.recall))


LONG = ["Terraza 6", "Salón Interior Mesa Alta", "Salón Interior Mesa Baja", "Barra de la entrada principal"]


class TheFormsQuestion(T329.Base):
    """B · every field kind × tap and typed → venue.submit_booking receives AgAPI's option exactly."""
    OPTIONS = ["Terraza 6", "Salón Interior Mesa Alta"]

    def setUp(self):
        p = mock.patch.object(T329, "ASK", {"choice": "zona", "label": "Zona", "options": list(self.OPTIONS)})
        p.start()
        self.addCleanup(p.stop)
        super().setUp()

    def chosen(self):
        return (self.ag.bodies("venue.submit_booking")[-1].get("choices") or {}).get("zona")

    def test_two_options_tap_by_identity(self):
        q = self.hold()
        self.assertEqual([c["route"] for c in q["choices"]], ["pick:1", "pick:2"])
        run(VN.answer_card(Ctx("Salón Interior Mesa…"), q["read_back_id"], "pick:2"))   # the cut title never matters: its identity
        self.assertEqual(self.chosen(), "Salón Interior Mesa Alta")

    def test_typed_words_naming_one_option(self):
        self.hold()
        got = run(VN.platform_answer(Ctx("Mesa Alta"), "Mesa Alta"))   # Tyler, 09:16:04 — was asked again
        self.assertIsNotNone(got)
        self.assertEqual(self.chosen(), "Salón Interior Mesa Alta")

    def test_on_whatsapp_each_tap_carries_the_options_identity(self):
        q = self.hold()
        out = WA_out()
        WA._read_back({"kind": "read_back", **q}, out)
        ids = [i for _, i in out.items[0][2]]
        self.assertTrue(all(re.fullmatch(r"card:q_[0-9a-f]{24}:pick:\d", i) for i in ids), ids)
        self.assertFalse(any(i.startswith("say:") for i in ids))


class MoreThanThreeLongLabels(TheFormsQuestion):
    OPTIONS = LONG

    def test_two_options_tap_by_identity(self):
        q = self.hold()
        out = WA_out()
        WA._read_back({"kind": "read_back", **q}, out)
        self.assertEqual(out.items[0][0], "list")   # more than three: a list, its rows by identity
        run(VN.answer_card(Ctx("Barra de la entrada…"), q["read_back_id"], "pick:4"))
        self.assertEqual(self.chosen(), "Barra de la entrada principal")

    def test_typed_words_naming_one_option(self):
        self.hold()
        self.assertIsNone(run(VN.platform_answer(Ctx("Salón Interior"), "Salón Interior")))   # two options answer: never a guess
        self.assertIsNotNone(run(VN.platform_answer(Ctx("mesa baja"), "mesa baja")))
        self.assertEqual(self.chosen(), "Salón Interior Mesa Baja")

    def test_on_whatsapp_each_tap_carries_the_options_identity(self):
        q = self.hold()
        out = WA_out()
        WA._read_back({"kind": "read_back", **q}, out)
        ids = [r[2] for r in out.items[0][3]]
        self.assertEqual(len(ids), 4)
        self.assertTrue(all(re.fullmatch(r"card:q_[0-9a-f]{24}:pick:\d", i) for i in ids), ids)


def WA_out():
    from booking_signer import guest_whatsapp as GW
    return GW.Out()


if __name__ == "__main__":
    unittest.main()
