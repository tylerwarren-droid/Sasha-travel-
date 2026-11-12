"""Sasha 230 · THE RESTAURANT LOOP (Tyler, /s2, 10 Oct): a pick must reach the read-back in ONE turn. The venue had one way to book
(its own form): the pick got the ladder's "I can book X directly — shall I?", the yes got the read-back's "shall I send it?" — the
same question twice. On /s2 one route is not a choice: straight to its read-back. A real choice still asks first; S1 unchanged.
Offline: the booking API is the venue suite's fake (nothing leaves the process).

    cd backend && python -m unittest tests.test_venue_pick_230 -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import date, timedelta
from unittest import mock

from app.agent import voice as V
from agapi import v0 as API, venues as VN
from booking_signer import guest_accounts as GA, guest_receipt as GR, guest_whatsapp as GW
from scripts.venue_suite import FakeApi

ACCT = "00000000-0000-4000-8000-000000000230"
run = asyncio.run
LATER = (date.today() + timedelta(days=6)).isoformat()


class FormApi(FakeApi):
    async def __call__(self, account, method, path, body=None, timeout=90.0):
        if path == "/api/booking/forms" and not (body or {}).get("handover"):
            self.calls.append((method, path, body))
            return 200, {"form_id": "f-9", "trip_item_id": "t-9", "read_back": {"lines": ["Casa Gate · 2 people · 21:00"], "sha256": "e" * 64}}
        if path == "/api/booking/forms/f-9/send":
            self.calls.append((method, path, body))
            return 200, {"status": "sent", "reading": {"result": "confirmed"}, "booking_reference": "TV-230"}
        return await super().__call__(account, method, path, body, timeout)


def reader(rungs):
    async def rd(ctx, a):
        return {"read_id": "r-1", "country": "ES", "venue": "Casa Gate", "facts": [], "rungs": rungs, "open_now": True,
                "opens_at": None, "say": "", "place_id": a.get("place_id") or "ChIJtest230"}   # Sasha 378 · its listing: AgAPI's venue.profile
    return rd


class APick(unittest.TestCase):
    def setUp(self):
        VN._HELD.pop(ACCT, None)
        self.api = FormApi()
        for p in (mock.patch.object(GW, "api", self.api), mock.patch.object(GA, "founder", lambda a: False),
                  mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="alex@example.test"))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(VN._HELD.pop, ACCT, None)

    def pick(self, surface, rungs, said=f"Casa Gate, please, for 2 on {LATER} at 21:00.", **extra):   # Sasha 381 · every term theirs
        ctx = API.Ctx(account=ACCT, mode="test", user_said=said, session="s230", surface=surface)
        from tests.test_s254_one_decider import engine_from   # Sasha 270 · MOVED: on the one path their form is the engine's read
        with mock.patch.object(VN, "_read", reader(rungs)), mock.patch.object(VN, "engine_channel", engine_from(rungs)):
            return run(VN.hold_venue(ctx, {"name": "Casa Gate", "city": "Madrid", "country": "ES", "what": "dinner", "party": 2,
                                           "day": LATER, "time": "21:00", **extra}))

    # Sasha 378 · CR 188 · AgAPI decides (venue.profile → handoff.decide; scripts/agapi_decides is its fake): a form is its send — the
    # read-back, the yes in a later turn books it; own channels before a platform
    def agapi(self, submit=None):
        """Sasha 270 · MOVED (CR 101: one form engine): on /s2 "Handle it" is AgAPI's send (venue.prepare_booking → the read-back →
        venue.submit_booking) — Sasha's own form sender is old S1's only. AgAPI faked as CR 90 answers (test_s254_handle_it_live)."""
        from agapi import venue_submit as VS
        from tests.test_s254_handle_it_live import FakeAgapi, signed_in
        self.fake = FakeAgapi()
        signed_in(self)   # Sasha 381 · their verified session: the instruction is the approval
        if submit:
            self.fake.submit.update(submit)
        VS._USERS.clear()
        for p in (mock.patch.object(VS, "CALL", self.fake), mock.patch.object(VS, "target", mock.AsyncMock(return_value="sandbox")),
                  mock.patch("agapi.s2_memory.put_kind", mock.AsyncMock(return_value=True)),
                  mock.patch("agapi.s2_memory.kind", mock.AsyncMock(return_value=None))):
            p.start()
            self.addCleanup(p.stop)

    def test_on_s2_a_form_is_agapis_send_on_the_instruction(self):
        # Sasha 381 · their own form → AgAPI's send_form → sent on the instruction: no card, no question of Sasha's own
        self.agapi()
        out = self.pick("s2", {"form": {}})
        self.assertEqual((out["status"], out["route"]), ("requested", "agapi"))
        self.assertNotIn("options", out)
        self.assertNotIn(ACCT, VN._HELD)                                         # nothing waits for a yes
        self.assertNotIn("/api/booking/forms", [c[1] for c in self.api.calls])

    def test_on_s2_their_own_email_comes_before_a_platform(self):
        self.agapi()   # Sasha 319 · the email request is AgAPI's send (Sasha's own email rung is gone)
        out = self.pick("s2", {"link": {"value": "TheFork"}, "email": {}, "phone": {"fact_index": 0}})
        self.assertEqual((out["status"], out["route"], out["rules"]["action"]), ("requested", "agapi", "request_email"))

    def test_old_s1_follows_the_same_decision(self):   # Sasha 378 · old S1 (parity off): AgAPI's decision too (its schema unchanged)
        self.agapi()
        with mock.patch.dict("os.environ", {"SASHA_S1_PARITY": "off"}):
            out = self.pick("s1", {"form": {}})
        self.assertEqual((out["status"], out["route"]), ("requested", "agapi"))

    def test_the_instruction_books_it(self):
        self.agapi({"status": "confirmed", "reference": "TV-230"})   # Sasha 270 · MOVED: AgAPI's send
        from booking_signer import wa_brain as WB
        with mock.patch.object(WB, "trip_day_words", mock.AsyncMock(return_value="It's in your bookings")), \
                mock.patch("agapi.v0.claim", mock.AsyncMock()):
            out = self.pick("s2", {"form": {}}, route="form")
        self.assertEqual((out["status"], out.get("reference")), ("confirmed", "TV-230"))
        tap = self.fake.body("approvals.in_app_tap")                              # the instruction binds the read-back (CR 196)
        self.assertEqual((tap["read_back_id"], tap["session"]["kind"]), ("rb_01JABCDEFGHJKMNPQRSTVWXYZ0", "in_app"))


if __name__ == "__main__":
    unittest.main()
