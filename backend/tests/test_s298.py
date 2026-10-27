"""Sasha 298 · T76 — READY FOR TYLER'S THREE REAL BOOKINGS (Tyler, 27 Oct: "can she book me things now?").

ROOT TEST (written before the code): (1) ONE path a booking takes, his words → AgAPI's decision → what he sees (scratchpad
s298/root-test.md names the files). (2) A route-specific screen, a test-only shortcut, or S2 deciding what AgAPI decides = PATCH.
(3) No step on the email, platform or WhatsApp-only route where he wouldn't know what happens next, and nothing sent without his yes.
Also here: 297's question in Spanish, picked by the page's browser language (as "Aquí sigo." is).
    cd backend && python -m unittest tests.test_s298 -v
"""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from agapi import place_kind as PK, v0 as API, venue_submit as VS, venues as VN
from app.agent import voice as V

ACCT = "00000000-0000-4000-8000-000000002980"
run = asyncio.run


def ask_in(lang, said="find me a restaurant", what="restaurant", session="s298-a"):
    tok = API.PAGE_LANG.set(lang)
    try:
        ctx = API.Ctx(account=ACCT, mode="test", user_said=said, session=session, surface="s2", via="page")
        sent = []

        async def call(account, op, body, approval=None):
            sent.append(body)
            return {"ok": True, "result": {"options": [], "groups": []}}
        with mock.patch.object(VS, "_call", call), mock.patch("agapi.test_venues.search", mock.AsyncMock(return_value=None)), \
                mock.patch.object(VN, "named_on_screen", lambda *a: None), mock.patch("agapi.s2_memory._run", lambda: None):
            return run(API._search_venues(ctx, {"what": what, "where": "Madrid", "country": "ES"})), sent, ctx
    finally:
        API.PAGE_LANG.reset(tok)


class TheQuestionInSpanish(unittest.TestCase):
    def setUp(self):
        PK._HELD.clear()

    def test_picked_by_the_pages_language(self):
        out, _, ctx = ask_in("es-ES", said="busca un restaurante para cenar", what="restaurante")
        self.assertEqual(ctx.lang, "es-ES")
        self.assertEqual(out["kind_ask"], {"ask": V.KIND_ASK_ES, "choices": list(V.KIND_CHOICES_ES)})
        self.assertEqual(V.discover_line("search_venues", {"ok": True, "result": out}), V.KIND_ASK_ES)   # said and shown in Spanish
        PK._HELD.clear()
        out, _, _ = ask_in("en-GB")
        self.assertEqual(out["kind_ask"]["ask"], V.KIND_ASK)
        PK._HELD.clear()
        out, _, _ = ask_in("")   # no language sent (old pages, WhatsApp's brain): English
        self.assertEqual(out["kind_ask"]["ask"], V.KIND_ASK)

    def test_the_words(self):
        self.assertEqual(V.KIND_ASK_ES, "¿Algo especial, buena relación calidad-precio o para llevar?")
        self.assertEqual(len(V.KIND_CHOICES_ES), 3)
        for w in (V.KIND_ASK_ES, *V.KIND_CHOICES_ES):
            self.assertNotRegex(w, r"(?i)michelin|bib|repsol")   # 292: she names no guide, in either language

    def test_each_spanish_tap_and_their_own_words(self):
        for t, k in zip(V.KIND_CHOICES_ES, ("special", "value", "takeaway")):
            self.assertEqual(PK.tap_kind(t), k, t)
        for said, k in (("algo con estrella michelin", "special"), ("una cena de aniversario", "special"), ("algo barato", "value"),
                        ("buena relación calidad-precio", "value"), ("menú del día", "value")):
            self.assertEqual(PK.said_kind(said), k, said)
        for w in ("restaurante", "un sitio para cenar", "algo para comer esta noche"):
            self.assertTrue(PK.vague(w), w)
        for w in ("restaurante indio", "tapas", "Botín"):
            self.assertFalse(PK.vague(w), w)

    def test_a_spanish_answer_reaches_agapi_as_its_own_input(self):
        ask_in("es-ES", said="busca un restaurante", what="restaurante", session="s298-b")
        _, sent, _ = ask_in("es-ES", said="Para llevar / a domicilio", what="restaurante", session="s298-b")
        self.assertEqual(sent[0]["intent"], "takeaway")
        PK._HELD.clear()
        ask_in("es-ES", said="busca un restaurante", what="restaurante", session="s298-c")
        _, sent, _ = ask_in("es-ES", said="Buena relación calidad-precio", what="restaurante", session="s298-c")
        self.assertEqual(sent[0]["what"], "good value restaurante")   # AgAPI's value words lead its `what` (its BUDGET rule reads either language)


class TheHandOverIsShown(unittest.TestCase):
    """Found live (Taberna Las Sobrinas, WhatsApp-only; DiverXO as a guest): the hand-over card carries the picked venue's `focus`, and
    the turn turned EVERY such event into a bare highlight — she said "Tap the button and it goes from your phone" over a screen with no
    button. A venue pick is still only the highlight; a card of its own is highlighted AND shown."""

    def events(self, result, session="s298-handover"):
        import app.services.llm as LLM
        from app.agent import sasha as AG
        from app.agent.fakes import Block, client
        AG._SCREEN[session] = {"cards": [{"place_id": "PX", "name": "Taberna Prueba (test)"}], "ribbon": None}
        out = []

        async def call(ctx, name, args):
            return {"ok": True, "result": result}

        async def go():
            async for ev in AG.turn(ACCT, "book it for Friday at nine for two", [], session, None, "s2"):
                out.append(ev)
        steps = [[Block(type="tool_use", id="t1", name="hold_venue", input={"venue": "Taberna Prueba (test)", "when": "2026-10-30T21:00", "party": 2})],
                 [Block(type="text", text="Tap the button and it goes from your phone.")]]
        with mock.patch.object(LLM, "client", client(steps)), mock.patch.object(API, "call", call):
            run(go())
        AG._SCREEN.pop(session, None)
        return [e for e in out if e.get("type") == "render"]

    def test_their_whatsapp_button_reaches_the_screen(self):
        got = self.events({"status": "handed_over", "page_url": "https://wa.me/34600000000?text=Hola", "button": {"label": "Send on WhatsApp"},
                           "card": {"place_id": "PX", "name": "Taberna Prueba (test)"}})
        kinds = [e["kind"] for e in got]
        self.assertIn("focus", kinds)                                   # the picked venue, highlighted
        hand = [e for e in got if e["kind"] == "handover"]
        self.assertEqual(len(hand), 1, kinds)                           # …and its button, shown
        self.assertEqual((hand[0]["url"], hand[0]["label"]), ("https://wa.me/34600000000?text=Hola", "Send on WhatsApp"))

    def test_a_pick_alone_is_still_only_the_highlight(self):
        got = self.events({"card": {"place_id": "PX", "name": "Taberna Prueba (test)"}, "status": "picked"})
        self.assertTrue(all(e["kind"] != "handover" for e in got))


if __name__ == "__main__":
    unittest.main()
