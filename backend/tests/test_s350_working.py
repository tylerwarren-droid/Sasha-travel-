"""Sasha 350 · every WhatsApp message shows it's being worked on, from its arrival until its reply leaves (booking_signer/wa_working).

    cd backend && python -m unittest tests.test_s350_working -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import re
import unittest
from unittest import mock

from booking_signer import guest_whatsapp as GW, inbound_phone as IP, wa_working as WK

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Calls:
    def __init__(self, not_found_first=0, refuse=None):
        self.calls, self.nf, self.refuse = [], not_found_first, refuse

    async def __call__(self, sid):
        self.calls.append(sid)
        if self.refuse:
            return {"ok": False, "error": {"code": self.refuse, "message": "Twilio said no"}}
        if len(self.calls) <= self.nf:
            return {"ok": False, "error": {"code": "not_found"}}
        return {"ok": True, "status": 200}


def go(coro):
    return asyncio.run(coro)


class TheHold(unittest.TestCase):
    def setUp(self):
        WK._HOLDS.clear()
        self.p = [mock.patch.object(WK, "REFRESH_S", 0.05), mock.patch.object(WK, "FIRST_TRIES", (0.0, 0.01, 0.01, 0.01)),
                  mock.patch.object(WK, "CAP_S", 0.5)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        WK._HOLDS.clear()
        WK.CALL = None

    def test_at_once_refreshed_and_ended_by_the_webhooks_answer(self):
        c = WK.CALL = Calls()

        async def run():
            self.assertTrue(WK.start("k1", "SMa"))
            await asyncio.sleep(0)                                   # at once: the first call, before anything else is awaited
            await asyncio.sleep(0.01)
            first = len(c.calls)
            await asyncio.sleep(0.13)                                # refreshed (every REFRESH_S) while the message is worked on
            refreshed = len(c.calls)
            WK.settle("SMa")                                         # the webhook's answer left
            await asyncio.sleep(0.12)
            return first, refreshed, len(c.calls)
        first, refreshed, after = go(run())
        self.assertEqual(first, 1)
        self.assertGreaterEqual(refreshed, 3)
        self.assertEqual(after, refreshed)                           # nothing after its reply
        self.assertEqual(set(c.calls), {"SMa"})                      # tied to THAT message

    def test_a_background_turn_holds_until_its_reply_leaves(self):
        c = WK.CALL = Calls()

        async def run():
            WK.start("k2", "SMb")
            WK.keep("k2")                                            # the guest's turn answers in the background
            WK.settle("SMb")                                         # the webhook returns "" — the dots stay
            await asyncio.sleep(0.12)
            held = WK.holding("k2")
            WK.stop_for("k2")                                        # deliver: the reply leaves
            n = len(c.calls)
            await asyncio.sleep(0.1)
            return held, n, len(c.calls)
        held, n, after = go(run())
        self.assertEqual(held, 1)
        self.assertGreaterEqual(n, 2)
        self.assertEqual(after, n)

    def test_retried_until_agapi_has_seen_it(self):
        c = WK.CALL = Calls(not_found_first=2)                      # AgAPI's inbound op records it a moment later

        async def run():
            WK.start("k3", "SMc")
            await asyncio.sleep(0.05)
            WK.settle("SMc")
        go(run())
        self.assertGreaterEqual(len(c.calls), 3)

    def test_a_refusal_is_logged_and_never_retried_forever(self):
        c = WK.CALL = Calls(refuse="twilio_refused")

        async def run():
            WK.start("k4", "SMd")
            await asyncio.sleep(0.2)
        with self.assertLogs("booking_signer.wa_working", "INFO") as logs:
            go(run())
        self.assertEqual(len(c.calls), 1)
        self.assertTrue(any("refused (twilio_refused: Twilio said no)" in l for l in logs.output))

    def test_a_retry_is_the_same_hold_and_a_newer_message_supersedes(self):
        WK.CALL = Calls()

        async def run():
            self.assertTrue(WK.start("k5", "SMe"))
            self.assertFalse(WK.start("k5", "SMe"))                 # Twilio's retry of the same message
            self.assertTrue(WK.start("k5", "SMf"))                  # a newer one from the same person
            out = (WK.holding("k5"), "SMe" in WK._HOLDS)
            WK.stop_for("k5")
            return out
        self.assertEqual(go(run()), (1, False))

    def test_never_longer_than_the_cap(self):
        c = WK.CALL = Calls()

        async def run():
            WK.start("k6", "SMg")
            WK.keep("k6")
            await asyncio.sleep(0.8)                                 # no reply ever: the cap ends it
            return len(c.calls), WK.holding("k6")
        n, left = go(run())
        self.assertLessEqual(n, 12)
        self.assertEqual(left, 0)


class TheAcknowledgementIsNotTheReply(unittest.TestCase):
    """Sasha 350 (close) · Tyler, 7 Nov 06:10: "find me a dinner in Madrid tonight for two" → "Let me see what I can do", and no dots —
    the holding line went through the same deliver() as a reply and ended the hold 0.6 s in (Twilio's log), before its retry showed them."""

    def setUp(self):
        WK._HOLDS.clear()
        self.p = [mock.patch.object(WK, "REFRESH_S", 5), mock.patch.object(WK, "FIRST_TRIES", (0.0,)), mock.patch.object(WK, "CAP_S", 10)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        WK._HOLDS.clear()
        WK.CALL = None

    def test_a_holding_line_keeps_the_dots_and_shows_them_again_the_result_ends_them(self):
        c = WK.CALL = Calls()
        ch = {"wa_id_sha256": "kA", "number_e164": "+15005550100"}

        async def run_():
            with mock.patch.object(GW, "_send", mock.AsyncMock(return_value=["ok"])):
                WK.start("kA", "SMx"); WK.keep("kA")
                await asyncio.sleep(0.01)
                await GW.deliver(ch, "f", GW.Out().text("Let me see what I can do."), None, progress=True)
                await asyncio.sleep(0.01)
                held = WK.holding("kA")
                n = len(c.calls)
                await GW.deliver(ch, "f", GW.Out().text("Here are three places for tonight…"), None)
                return held, n, WK.holding("kA")
        held, n, after = go(run_())
        self.assertEqual(held, 1)                                                       # the acknowledgement is not the reply
        self.assertEqual(n, 2)                                                          # shown at once, and again right after it
        self.assertEqual(after, 0)                                                      # the result ends them

    def test_a_turn_that_never_replies_is_told_as_a_failure(self):
        sent = []
        ch = {"wa_id_sha256": "kB", "number_e164": "+15005550101", "account_id": "a"}

        async def silent_turn(ch_, frm, p):
            return None                                                                 # its work ended, no reply ever left

        async def run_():
            WK.CALL = Calls()
            store = mock.Mock(get_state=mock.AsyncMock(return_value={"last_inbound_at": None}))
            with mock.patch.object(GW, "turn", silent_turn), mock.patch.object(GW, "STORE", store), \
                    mock.patch.object(GW, "_send", mock.AsyncMock(side_effect=lambda ch_, frm, out, last: sent.append(out.said()) or ["ok"])):
                WK.start("kB", "SMy"); WK.keep("kB")
                await GW._turn(ch, "f", {})
            return WK.holding("kB")
        from booking_signer import inbound_outcome as OC
        with self.assertLogs("booking_signer.inbound_outcome", "ERROR"):                 # Sasha 357 · the ONE outcome names it, and
            left = go(run_())
        self.assertEqual(sent, [OC.FAILED["en"]])                                        # tells it (their language)
        self.assertEqual(left, 0)

    def test_the_holding_line_is_sent_as_progress(self):
        src = inspect.getsource(GW)
        self.assertIn("await deliver(ch, frm, hold, now, progress=True)", src)


class OnePlace(unittest.TestCase):
    def test_every_whatsapp_message_starts_its_hold_where_it_arrives(self):
        src = inspect.getsource(IP.sms)   # Sasha 379a · the hold starts where it arrives; the work (and its settle) runs after Twilio's ack
        self.assertLess(src.index("WK.start(_GWk.wa_key(sender), sid)"), src.index("_whatsapp(p, channel, sender, body, sid, held)"))
        bg = inspect.getsource(IP._whatsapp)
        self.assertIn("WK.settle(held)", bg[bg.index("finally:"):])
        body = inspect.getsource(IP._sms)
        self.assertLess(body.index("TL.switch_tap(p)"), body.index("VS.whatsapp_inbound(sender, "))

    def test_the_reply_ends_it(self):
        self.assertIn('_WK.stop_for(ch.get("wa_id_sha256") or "")', inspect.getsource(GW.deliver))
        turn = inspect.getsource(GW._turn)
        self.assertIn("await _told(", turn[turn.index("finally:"):])                     # Sasha 357 · no reply: told through deliver,
        self.assertIn('_WK.stop_for(ch["wa_id_sha256"])', inspect.getsource(GW._told))   # and the dots end even if that can't be sent
        disp = inspect.getsource(GW.dispatch)
        self.assertLess(disp.index("_WK.keep(key)"), disp.index("_spawn(_turn(ch, to, p))"))

    def test_no_second_sender_no_per_tool_call_no_working_text(self):
        hits = []
        for f in list(ROOT.glob("booking_signer/**/*.py")) + list(ROOT.glob("agapi/**/*.py")) + list(ROOT.glob("products/**/*.py")) \
                + list(ROOT.glob("app/**/*.py")):
            s = f.read_text(encoding="utf-8")
            if f.name != "wa_working.py" and re.search(r"messages\.typing|Indicators/Typing", s):
                hits.append(f.name)
            wa = f.name in ("guest_whatsapp.py", "wa_agent.py", "inbound_phone.py") or "products" in f.parts   # what WhatsApp sends
            if wa and re.search(r"""["'](?:working on it|one moment|give me a (?:sec|moment))[.…]""", s, re.I):
                hits.append(f"{f.name} (a working text)")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
