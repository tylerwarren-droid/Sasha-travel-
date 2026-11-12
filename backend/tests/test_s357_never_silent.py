"""Sasha 357 · NO INBOUND MESSAGE IS EVER DROPPED SILENTLY: every WhatsApp message ends in ONE outcome (booking_signer/inbound_outcome) —
handled → its reply; refused → a reason the person reads; failed → "I couldn't take that just now — please send it again" (in their
language), recorded on the conversation record (349). Found: Sasha 355 failed CLOSED on a database error and the person heard nothing.

Every failure point is fed through the real webhook: the database (the message's steps; the guest's record), AgAPI down (in AD's
space), the model capped or refusing (no words), a tool error. Each must end in a message to the person, its cause named in the log,
and nothing reaches AgAPI twice (355 still holds).

    cd backend && python -m unittest tests.test_s357_never_silent -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from unittest import mock

from agapi import s2_memory as MEM
from booking_signer import guest_whatsapp as GW, inbound_outcome as OC, inbound_phone as IP
from booking_signer.store import StorageUnavailable
from tests import test_inbound_phone as TIP
from tests.test_guest_whatsapp_s75 import ACCOUNT, GUEST, SANDBOX, Base, run

ROOT = pathlib.Path(__file__).resolve().parents[1]
EN = OC.FAILED["en"]
ES = OC.FAILED["es"]


class Through(Base):
    """Through the real webhook (as test_guest_whatsapp_s75.Webhook, without its own tests)."""

    def setUp(self):
        super().setUp()
        TIP.InboundPhone.setUp(self)
        self.turns = []
        GW._spawn = lambda coro: self.turns.append(coro)        # the background turn: run here, after the webhook answers
        self.to_agapi = []
        self.agapi = {"matched": False, "why": "not_found"}

        async def inbound(sender, body, message_id=None, guest=False, twilio=None, **kw):
            self.to_agapi.append((message_id, body, kw.get("space")))
            return dict(self.agapi)
        self.p = [mock.patch("agapi.venue_submit.whatsapp_inbound", inbound)]
        for x in self.p:
            x.start()
        MEM._MEM.pop(ACCOUNT, None)

    def tearDown(self):
        for x in reversed(self.p):
            x.stop()
        MEM._MEM.pop(ACCOUNT, None)
        TIP.InboundPhone.tearDown(self)
        super().tearDown()

    def wa(self, sid, sender, body, to):
        form = {"MessageSid": sid, "From": f"whatsapp:{sender}", "To": f"whatsapp:{to}", "Body": body}
        return self.c.post("/api/booking/twilio/sms", data=form, headers={"X-Twilio-Signature": TIP.sign("sms", form)})

    def msg(self, sid, body):
        r = self.wa(sid, GUEST, body, SANDBOX)
        while self.turns:
            run(self.turns.pop(0))
        return r.text

    def heard(self, r: str) -> list:
        """What the person received for that message: the webhook's own reply, and what the background turn sent."""
        said = re.findall(r"<Message>(.*?)</Message>", r, re.S)   # Sasha 379a · always none now: Twilio is answered at once (empty), the rest by REST
        return [s.replace("&#x27;", "'").replace("&quot;", '"').replace("&amp;", "&") for s in said] + self.bodies()

    def brain(self, fn):
        from booking_signer import wa_agent as WA
        p = mock.patch.object(WA, "agent_turn", fn)
        p.start()
        self.addCleanup(p.stop)

    def recorded(self) -> list:
        return [m.get("text") for m in MEM.messages_of(MEM._MEM.get(ACCOUNT)) if m.get("dir") == "out"]


class EveryFailurePoint(Through):
    def test_a_the_database_refuses_the_messages_step(self):
        self.link()

        async def broken(fn):
            raise ConnectionError("the database is away")
        GW.STORE._run = broken
        with self.assertLogs("booking_signer.inbound_outcome", "ERROR") as logs:
            r = self.msg("SM" + "a1" * 16, "investigate Acme")
        self.assertIn(EN, self.heard(r))
        self.assertEqual(self.to_agapi, [])                                                 # failed CLOSED: never handed on (355)
        self.assertTrue(any("guest_message_steps" in l and "ConnectionError" in l for l in logs.output), logs.output)
        del GW.STORE._run
        self.msg("SM" + "a1" * 16, "investigate Acme")                                     # sent again, the DB back: it goes on
        n = len(self.to_agapi)
        self.assertGreater(n, 0)
        self.msg("SM" + "a1" * 16, "investigate Acme")                                     # a Twilio retry of it: never to AgAPI again
        self.assertEqual(len(self.to_agapi), n)

    def test_b_the_database_refuses_the_guests_record(self):
        self.link()
        with mock.patch.object(GW.STORE, "channel_for", mock.AsyncMock(side_effect=StorageUnavailable("db_down", "the database is away"))), \
                self.assertLogs("booking_signer.inbound_outcome", "ERROR") as logs:
            r = self.msg("SM" + "b2" * 16, "dinner for two tonight")
        self.assertIn(EN, self.heard(r))
        self.assertTrue(any("StorageUnavailable" in l for l in logs.output), logs.output)

    def test_c_agapi_down_for_ads_word(self):
        # Sasha 379b · CR 192: AD's word is AgAPI's to take on the ONE call — AgAPI unreachable → told, never travel's answer
        self.link()
        self.agapi = {"matched": False, "why": "unavailable"}                               # AgAPI can't be reached
        with self.assertLogs("booking_signer.inbound_outcome", "ERROR") as logs:
            r = self.msg("SM" + "c4" * 16, "diligence")
        self.assertIn(EN, self.heard(r))
        self.assertTrue(any("AgAPI" in l and "Applied Diligence" in l for l in logs.output), logs.output)
        self.assertIn(EN, self.recorded())                                                  # on the conversation record (349)

    def test_d_the_model_capped(self):
        self.link()
        from booking_signer import model_gateway as MG

        async def capped(*a, **k):
            raise MG.ModelBudgetExceeded("this account's daily model budget is reached")
        self.brain(capped)
        with self.assertLogs("booking_signer.inbound_outcome", "ERROR") as logs:
            r = self.msg("SM" + "d5" * 16, "find me a flight to Lisbon")
        self.assertIn(OC.CAPPED["en"], self.heard(r))                                       # refused: the reason, never "send it again"
        self.assertTrue(any("ModelBudgetExceeded" in l for l in logs.output))

    def test_e_the_model_refuses_no_words(self):
        self.link()

        async def silent(ch, body, payload, st, out, now, button_text="", voice_in=False):
            return ""                                                                      # a refusal: nothing to say
        self.brain(silent)
        with self.assertLogs("booking_signer.inbound_outcome", "ERROR") as logs:
            r = self.msg("SM" + "e6" * 16, "find me a flight to Lisbon")
        self.assertIn(EN, self.heard(r))
        self.assertTrue(any("without its reply" in l for l in logs.output))

    def test_f_a_tool_error(self):
        self.link()

        async def boom(*a, **k):
            raise RuntimeError("search_flights blew up")
        self.brain(boom)
        with self.assertLogs("booking_signer.inbound_outcome", "ERROR") as logs:
            r = self.msg("SM" + "f7" * 16, "find me a flight to Lisbon")
        self.assertEqual([b for b in self.heard(r) if b == EN], [EN])                       # exactly ONE line, not two
        self.assertTrue(any("RuntimeError" in l and "search_flights blew up" in l for l in logs.output))
        self.assertIn(EN, self.recorded())

    def test_g_in_their_language(self):
        self.link()

        async def boom(*a, **k):
            raise RuntimeError("x")
        self.brain(boom)
        with self.assertLogs("booking_signer.inbound_outcome", "ERROR"):
            r = self.msg("SM" + "g8" * 16, "¿Puedes reservar una mesa para dos esta noche?")
        self.assertIn(ES, self.heard(r))


class TheModelsFailureOnEverySurface(unittest.TestCase):
    """The brain's own failure (every surface: WhatsApp, /s2, voice) says the outcome's words — and never "send it again" after an act."""

    def events(self, err, message="find me a flight", calls=()):
        from app.agent import sasha as AG

        async def turn(account, message, history, session, voice, surface):
            from agapi import v0 as API
            voice["ctx"] = API.Ctx(account="a")
            voice["ctx"].calls.extend(calls)
            raise err
            yield  # pragma: no cover

        async def go():
            with mock.patch.object(AG, "turn", turn), self.assertLogs("booking_signer.inbound_outcome", "ERROR"):
                return [e async for e in AG.turn_with_quiver("a", message, [], None, surface="s2")]
        return [e for e in asyncio.run(go()) if e.get("type") == "error"]

    def test_failed_capped_and_after_an_act(self):
        from booking_signer import model_gateway as MG
        self.assertTrue(self.events(RuntimeError("x"))[0]["message"].startswith(EN))
        self.assertTrue(self.events(RuntimeError("x"), "¿me buscas un vuelo?")[0]["message"].startswith(ES))
        self.assertEqual(self.events(MG.ModelBudgetExceeded("cap"))[0]["message"], OC.CAPPED["en"])
        done = self.events(RuntimeError("x"), calls=[{"tool": "book_venue", "ok": True, "status": "placed"}])[0]["message"]
        self.assertNotIn("send it again", done)                                             # something was done: resending could repeat it
        self.assertIn("Before that", done)


class OneSource(unittest.TestCase):
    def test_no_failure_line_written_anywhere_else(self):
        """Whole class: the old one-place failure lines are gone — each failure point raises its cause to the ONE outcome."""
        old = ["Something went wrong on my side — nothing was sent to any venue", "I couldn't finish that one on my side",
               "Applied Diligence couldn't be reached just now", "Sorry — something went wrong on my side before I finished"]
        hits = []
        for d in ("booking_signer", "app/agent", "products"):
            for f in sorted((ROOT / d).rglob("*.py")):
                s = f.read_text(encoding="utf-8", errors="ignore")
                hits += [f"{f.relative_to(ROOT)}: {o}" for o in old if o in s]
        self.assertEqual(hits, [])

    def test_every_language_has_both_lines(self):
        self.assertEqual(set(OC.FAILED), set(OC.CAPPED))
        for k in ("en", "es", "fr", "it", "pt", "de"):
            self.assertIn(k, OC.FAILED)
        self.assertEqual(OC.lang_of("¿Puedes reservar una mesa?"), "es")
        self.assertEqual(OC.lang_of("Pouvez-vous réserver une table, s'il vous plaît ?"), "fr")
        self.assertEqual(OC.lang_of("book a table"), "en")
        self.assertEqual(OC.lang_of(""), "en")


if __name__ == "__main__":
    unittest.main()
