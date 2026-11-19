"""Sasha 388 · ONE INBOUND = ONE ANSWER, in the person's words only.

Measured (Tyler's WhatsApp, 19 Nov 07:29–14:56): one booking message drew "Let me see what I can do." / "Setting up the booking." /
"They use CoverManager booking widget — I can book it directly once you confirm." / the no-table sentence TWICE / "On it — one moment." /
"Bear with me — still working." — up to five messages, the channel named, a second yes asked for.
Six senders made them (row 2049): the holding / first / progress lines, her text split per part, a card's own message, the voice note,
the reminders offer — each its own Twilio send; on /s2 and voice the holding wrapper and the quiver's fillers; the route lines
(voice.ROUTE_LINES) turned AgAPI's route and platform into words.

THE CLASS, made impossible:
  · WhatsApp: a brain turn × every booking outcome → exactly ONE send for the inbound, a second delivery for it refused;
  · /s2 and voice: no words before her answer — the "working" state only;
  · no platform / channel name and no "once you confirm" in any line Sasha's code says.

    cd backend && python -m unittest tests.test_s388_one_answer -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import re
import unittest
from datetime import datetime, timezone
from unittest import mock

from agapi import venue_submit as VS, venues as VN
from app.agent import sasha as AG, voice as V
from booking_signer import guest_whatsapp as GW, wa_agent as WA

BACKEND = pathlib.Path(__file__).resolve().parents[1]
ALT_SAY = ("La Taberna de Peñalver has no table at 21:30 on Thu 19 Nov. I can book that evening at 21:45 or 22:00 or 22:15 — tap one and "
           "I'll book it.")
#: every booking outcome as the brain's turn draws it on WhatsApp: (her words, the turn's render events)
OUTCOMES = {
    "confirmed": ("Booking now: La Taberna de Peñalver, 2 people, Thu 19 Nov at 21:45. Booked — reference CM48213.", []),
    "requested": ("Booking now: Casa Lucio, 2 people, Fri 20 Nov at 21:00. Requested — I'll tell you when they reply.", []),
    "alternatives": (ALT_SAY, [{"kind": "read_back", "ask": ALT_SAY, "read_back_id": "alt_" + "a" * 24, "read_back": [],
                                "choices": [{"title": f"{t} · Thu 19 Nov", "route": f"alt:{i}"}
                                            for i, t in enumerate(("21:45", "22:00", "22:15", "20:00"), 1)]}]),
    "a form question": ("Their booking asks for your Zona: Terraza 1, Terraza 2. Which one?",
                        [{"kind": "read_back", "ask": "Their booking asks for your Zona: Terraza 1, Terraza 2. Which one?",
                          "read_back_id": "q_" + "b" * 24, "read_back": [],
                          "choices": [{"title": "Terraza 1", "route": "pick:1"}, {"title": "Terraza 2", "route": "pick:2"}]}]),
    "refused": ("I couldn't book Casa Lucio from here — nothing was booked. Here's their page.", []),
}


class Sender:
    def __init__(self):
        self.sent = []

    async def send(self, frm, to, *, body="", media=None, content_sid=None, **k):
        self.sent.append(body or content_sid or media)
        return "SM" + str(len(self.sent))

    async def quick_reply(self, body, buttons):
        return "HXq"

    async def list_picker(self, body, button, rows):
        return "HXl"


class OneSendPerInbound(unittest.TestCase):
    def deliver_brain(self, words, renders, mid):
        out = GW.Out()
        for p in WA.split(words):
            out.text(p)
        for ev in renders:
            WA.render(ev, out, {}, datetime.now(timezone.utc))
        out.text(GW.REMINDERS_OFFER)   # the reminders offer joins the same answer
        out.one = True
        s = Sender()
        tok = VS.WA.set({"wa_id": "+12025550188", "message_id": mid})
        try:
            with mock.patch.object(GW, "SENDER", s), mock.patch.object(GW, "_record_out", mock.AsyncMock()):
                asyncio.run(GW.deliver({"number_e164": "+12025550188", "wa_id_sha256": "k388"}, "whatsapp:+14155238886", out,
                                       datetime.now(timezone.utc)))
                again = asyncio.run(GW.deliver({"number_e164": "+12025550188", "wa_id_sha256": "k388"}, "whatsapp:+14155238886",
                                               GW.Out().text("a second answer"), datetime.now(timezone.utc)))
        finally:
            VS.WA.reset(tok)
        return s.sent, again

    def test_every_booking_outcome_is_one_message(self):
        for i, (name, (words, renders)) in enumerate(OUTCOMES.items()):
            sent, again = self.deliver_brain(words, renders, f"SM388{i}")
            self.assertEqual(len(sent), 1, (name, sent))                                           # ONE send for the inbound
            self.assertEqual(again, ["not sent: this message was already answered"], name)         # nothing else can answer it

    def test_the_cards_sentence_is_said_once(self):
        out = GW.Out().text(ALT_SAY)
        WA.render(OUTCOMES["alternatives"][1][0], out, {}, datetime.now(timezone.utc))
        out.one = True
        out.compose()
        self.assertEqual(len(out.items), 1)
        self.assertEqual(out.items[0][1].count("has no table"), 1)

    def test_no_holding_first_or_progress_line_is_sent(self):
        src = inspect.getsource(GW._brain_turn)
        for gone in ("holding_line", "progress_line", "first_line", "progress=True", "progress_due"):
            self.assertNotIn(gone, src)
        self.assertNotIn("progress", inspect.signature(GW.deliver).parameters)


class NoWordsBeforeHerAnswer(unittest.TestCase):
    def test_s2_and_voice_say_nothing_before_the_answer(self):
        async def slow():
            await asyncio.sleep(0.05)
            yield {"type": "tool_start", "name": "hold_venue"}
            yield {"type": "filler", "text": "Let me look into that."}
            yield {"type": "say", "text": "Booking now: …"}
            yield {"type": "done", "text": "Booking now: …"}

        async def run():
            return [ev async for ev in AG.with_holding(slow(), "acct388", after_s=0.0, first="Let me see what I can do.")]
        evs = asyncio.run(run())
        self.assertFalse([e for e in evs if e.get("type") in ("hold", "filler")], evs)           # no words before her answer
        self.assertEqual([e.get("on") for e in evs if e.get("type") == "working" and "on" in e], [True, False])   # the ring only
        self.assertNotIn("first=_V.first_ack", inspect.getsource(AG))


class NoChannelNameNoSecondYes(unittest.TestCase):
    def test_the_route_lines_are_gone(self):
        for n in ("ROUTE_LINES", "route_line", "route_told", "is_route_line"):
            self.assertFalse(hasattr(V, n), n)
        self.assertFalse(hasattr(VN, "with_route_line"))

    def test_no_line_of_sashas_names_a_platform_or_asks_to_confirm(self):
        platforms = ("CoverManager", "TheFork", "OpenTable", "Zenchef", "DISH", "Resy", "SevenRooms", "Booksy", "Fresha", "Treatwell")
        said = re.compile(r"""^\s*[A-Z_]+\s*=\s*\(?["'](.+)["']""")
        hits = []
        for rel in ("app/agent/voice.py",):
            for i, line in enumerate((BACKEND / rel).read_text().splitlines(), 1):
                m = said.match(line)
                if line.lstrip().startswith("CHANNEL_NAMES"):   # the names she must never say (the guard's own list), not a line
                    continue
                if m and (any(p in m.group(1) for p in platforms) or re.search(r"once you confirm", m.group(1), re.I)):
                    hits.append(f"{rel}:{i}")
        self.assertEqual(hits, [])
        self.assertNotRegex((BACKEND / "app/agent/voice.py").read_text(), r"(?i)I can book it directly once you confirm")


if __name__ == "__main__":
    unittest.main()
