"""Sasha 326 · S2 + WhatsApp: one conversation, the right channel (docs/sasha/S-326-one-conversation.md). Offline.

Root test: (1) THE ONE routing decision is booking_signer/channel.py — work in progress only where the request came from; outcomes on ONE
channel (S2 when he's on it now, else WhatsApp); the one record (trip items + AgAPI's acts) read the same from both. (2) No second copy:
the last channel (one value) and the open pages (live_events). (3) The class: a step can't reach the channel he isn't using; an outcome
can't reach both; a booking made on one is never invisible on the other.

    cd backend && python -m unittest tests.test_s326 -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from unittest import mock

from agapi import venue_submit as VS, venues as VN
from booking_signer import channel as CH, live_events as LE
from tests import test_s264 as P, test_s300 as R

BACKEND = pathlib.Path(__file__).resolve().parents[1]
run = asyncio.run


class Counted:
    """Every message that reaches him, by channel: S2 (an open page's events) and WhatsApp."""

    def __init__(self, account, page_open):
        self.account, self.page_open = account, page_open
        self.s2, self.wa = [], []

    def __enter__(self):
        CH._LAST.pop(self.account, None)
        LE._CLOSED.clear()
        self.q = type("Q", (), {"put_nowait": lambda _s, e: self.s2.append(e)})()
        if self.page_open:
            LE._SUBS.setdefault(self.account, []).append(self.q)

        async def wa(account, text):
            self.wa.append(text)
            return "sent"
        self.p = [mock.patch.object(LE, "WA_SEND", wa), mock.patch.object(LE, "SEND", mock.AsyncMock(return_value={"sent": True})),
                  mock.patch("booking_signer.guest_receipt.address_of", mock.AsyncMock(return_value="t@example.com")),
                  mock.patch.object(LE, "keep_news", mock.AsyncMock()), mock.patch.object(LE, "status_now", mock.AsyncMock(return_value=None)),
                  mock.patch("agapi.s2_memory.put_kind", mock.AsyncMock()), mock.patch("agapi.s2_memory.kind", mock.AsyncMock(return_value=None))]
        for x in self.p:
            x.start()
        return self

    def __exit__(self, *a):
        if self.q in LE._SUBS.get(self.account, []):
            LE._SUBS[self.account].remove(self.q)
        for x in self.p:
            x.stop()


class WaCtx(R.Ctx):
    via = "wa"


class TheRunAsTyler(unittest.TestCase):
    """Start a restaurant booking on S2 → nothing on WhatsApp during the form; it confirms → one notice, on S2 only (he's on it); later
    on WhatsApp "what time is my table tonight?" → the S2 booking's time; "cancel it" → the cancel flow on THAT booking. And with S2 closed
    the confirmation goes to WhatsApp."""

    def test_s2_open_then_whatsapp(self):
        A = R.ACCT
        counts = {}
        with Counted(A, page_open=True) as c:
            run(CH.used(A, CH.S2))
            # 1 · the form, asked on S2: their page (a platform), the prepared page, a draft — none reaches WhatsApp
            for rung, held in (("page", P.held_platform()), ("prepared", P.held_prepared())):
                with mock.patch.object(P, "Ctx", type("C", (P.Ctx,), {"via": "page"})):
                    out = P.book(rung, held, tap="sent", tell="sent")
                self.assertEqual(out["status"], "page_link", rung)   # the phone would have taken it ("sent"): S2's card, never WhatsApp
            self.assertEqual(c.wa, [])
            # 2 · the venue confirms: ONE notice, on S2 only
            run(LE.completed(A, "venue:act_mail", lead="✅ DiverXO confirmed your table.", lines=["DiverXO"], title="DiverXO"))
            counts["confirm"] = (len(c.s2), len(c.wa))
            self.assertEqual(counts["confirm"], (1, 0))
        # 3 · later, on WhatsApp: the S2 booking is the one he means — the ONE record, whatever channel made it
        t = R.Base("setUp")
        t.setUp()
        try:
            run(CH.used(A, CH.WA))
            rows = run(VN.venue_bookings(A))
            table = next(b for b in rows if b["venue"] == "DiverXO")
            self.assertEqual(table["time"], "21:00")                                   # "what time is my table?" → 21:00
            rb = mock.AsyncMock(return_value={"ok": True, "lines": ["Cancel DiverXO, 21:00 for 2?"], "read_back_id": "rb", "sha": "x"})
            with mock.patch.object(VS, "cancel_read_back", rb):
                out = run(VN.cancel_venue(WaCtx(said="cancel it"), {"venue": "DiverXO"}))
            self.assertEqual(rb.await_args.args[1], "act_mail")                           # the cancel flow, on THAT booking
            self.assertNotIn(out.get("status"), ("to_tyler", "booking_unknown"))
        finally:
            t.doCleanups()
        print(f"\n[s326 proof · S2 open] form: S2 card, WhatsApp 0 · confirmation: S2 {counts['confirm'][0]}, WhatsApp {counts['confirm'][1]}"
              f" · WhatsApp 'what time is my table' → {table['time']} · 'cancel it' → read-back for act_mail")

    def test_s2_closed_the_confirmation_goes_to_whatsapp(self):
        with Counted(R.ACCT, page_open=False) as c:
            run(CH.used(R.ACCT, CH.S2))
            run(LE.completed(R.ACCT, "venue:act_mail:2", lead="✅ DiverXO confirmed your table.", lines=["DiverXO"], title="DiverXO"))
        self.assertEqual((len(c.s2), len(c.wa)), (0, 1))
        print(f"\n[s326 proof · S2 closed] confirmation: S2 {len(c.s2)}, WhatsApp {len(c.wa)}")

    def test_s2_open_but_he_moved_to_whatsapp(self):
        with Counted(R.ACCT, page_open=True) as c:
            run(CH.used(R.ACCT, CH.WA))   # a page left open, but his last word was on WhatsApp: that's where he is
            run(CH.tell(R.ACCT, "No answer yet from DiverXO."))
        self.assertEqual((len(c.s2), len(c.wa)), (0, 1))


class TwoMatchOneQuestion(R.Base):
    def test_two_bookings_there_one_short_question(self):
        VS._ACTS[R.ACCT].append({"act_id": "act_mail2", "venue": "DiverXO", "when": f"{R.DAY}T14:00", "party": 2, "state": "sent",
                                 "channel": "email", "at": 9})
        from agapi.v0 import ToolError
        with self.assertRaises(ToolError) as e:
            run(VN.cancel_venue(WaCtx(said="cancel the DiverXO booking"), {"venue": "DiverXO"}))
        self.assertEqual(e.exception.code, "which_booking")
        self.assertIn("act_mail", e.exception.message)
        self.assertIn("act_mail2", e.exception.message)


class TheWholeClass(unittest.TestCase):
    def test_no_work_in_progress_send_without_the_gate(self):
        src = (BACKEND / "agapi/venues.py").read_text()
        for fn in ("async def _book_inner(", "async def _platform_handover("):
            body = src.split(fn)[1].split("\nasync def ")[0]
            for line in re.findall(r".*channel_of_account\(ctx\.account\).*", body):
                self.assertIn("wip_on_phone(ctx)", line, fn)
            self.assertIn("tap_platform(", body) if fn == "async def _book_inner(" else None
            for line in re.findall(r".*tap_platform\(.*", body):
                self.assertIn("wip_on_phone(ctx)", line + body.split(line)[1][:120], fn)

    def test_every_outcome_send_is_the_one_send(self):
        """No booking outcome is sent on WhatsApp AND published apart: _tell_whatsapp is called by channel.tell only (and the Gmail
        reconnect line, which isn't a booking's)."""
        hits = []
        for f in list((BACKEND / "agapi").glob("*.py")) + list((BACKEND / "booking_signer").glob("*.py")):
            for i, line in enumerate(f.read_text().splitlines(), 1):
                if "_tell_whatsapp(" in line and "def _tell_whatsapp" not in line:
                    hits.append(f"{f.name}:{line.strip()[:60]}")
        self.assertEqual(sorted({h.split(":")[0] for h in hits}), ["channel.py", "mailbox.py"], hits)   # 366: channel.progress too — still channel
        for f in ("agapi/venue_calls.py", "agapi/venue_submit.py", "booking_signer/paid_watch.py"):
            self.assertIn("CH.tell(", (BACKEND / f).read_text(), f)

    def test_the_one_entry_records_the_channel(self):
        src = (BACKEND / "app/agent/sasha.py").read_text()
        self.assertEqual(src.count("await _CH.used(account,"), 1)


if __name__ == "__main__":
    unittest.main()
