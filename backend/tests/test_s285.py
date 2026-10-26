"""Sasha 285 · T65 — ONE WHATSAPP PATH: S2 sends and hears WhatsApp only through AgAPI (CR 118's Sasha half, row 1275 §3).

ROOT TEST (written before the code):
  (1) ONE truth: AgAPI's one send path (venue_submit._send_whatsapp, gated by venue_messages.kanoe_send_allowed) and its one inbound op
      (messages.whatsapp_inbound). Every place S2 talked to Twilio for WhatsApp before this ticket:
        · agapi/s2_whatsapp._twilio — a WhatsApp to a THIRD PARTY the person names, Sasha's own post, her own yes, her own STOP list
        · booking_signer/guest_whatsapp.Sender — the guest's OWN conversation with Sasha (and proactive.py / invitations.py through it)
        · booking_signer/inbound_phone /twilio/sms — every inbound WhatsApp; a non-guest's matched to the LAST CALL to that number
        · booking_signer/guest_whatsapp.dispatch → s2_whatsapp.on_contact_message — Sasha's own reply-matching for third parties
        · (SMS, not WhatsApp: guest_receipt.send_sms — named, out of this ticket)
  (2) A second copy of consent (S2's own post, yes, STOP list or reply matching for a third party) is a PATCH. So: (a) the person's
      end_user rides on venue.prepare_booking (AgAPI's gate reads THEIR access record); (b) a non-guest's WhatsApp goes to AgAPI's
      inbound op FIRST; (c) on the one path S2 never posts a third-party WhatsApp — their own WhatsApp, pre-filled, until AgAPI's path
      is wired. Old S1 (parity off) keeps its own path, byte for byte.
  (3) The class: no third-party WhatsApp leaves Kanoe's number from the one path without AgAPI; no reply from a number Kanoe wrote to
      lands anywhere but AgAPI's booking record. The ratchet: the closed list of Twilio senders, and the hand-off's place.
Offline: fakes only — nothing reaches Twilio, AgAPI or a phone.
    cd backend && python -m unittest tests.test_s285 -v
"""
from __future__ import annotations

import asyncio
import inspect
import os
import pathlib
import re
import unittest
from unittest import mock

from agapi import s2_records as REC, s2_whatsapp as WA, v0 as API, venue_submit as VS, venue_truth as VT
from booking_signer import guest_whatsapp as GW, inbound_phone as IP

run = asyncio.run
BACKEND = pathlib.Path(__file__).resolve().parents[1]
ACCT = "00000000-0000-4000-8000-000000000285"
VENUE = "+34611222333"


class TheOnePathNeverPostsAThirdPartyWhatsApp(unittest.TestCase):
    def _send(self, surface, live=True, window=True, parity="on"):
        contact = {"last_inbound_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()} if window else None
        tw = mock.AsyncMock(return_value={"sid": "SMx"})
        ctx = API.Ctx(account=ACCT, user_said="yes send it", surface=surface)
        with mock.patch.object(REC, "contact", mock.AsyncMock(return_value=contact)), mock.patch("agapi.s2_tools.live_for", lambda a: live), \
                mock.patch.object(WA, "_twilio", tw), mock.patch.dict(os.environ, {"SASHA_S1_PARITY": parity}):
            out = run(WA.send_whatsapp(ctx, {"to": {"number": "+447700900123", "name": "Marta"}, "text": "Running late"}))
        return out, tw

    def test_founder_live_inside_the_window_is_their_whatsapp(self):
        for surface in ("s2", "s1"):   # /s2, and /next or WhatsApp with parity (the one path)
            out, tw = self._send(surface)
            self.assertEqual(out["status"], "open_in_their_whatsapp", surface)
            self.assertFalse(out["sent_by_sasha"])
            self.assertEqual(out["why"], WA.WHY_THEIRS["agapi_only"])
            self.assertEqual(tw.await_count, 0)   # Sasha's own Twilio post: never on the one path

    def test_a_stop_still_stops_it(self):
        ctx = API.Ctx(account=ACCT, surface="s2")
        with mock.patch.object(REC, "contact", mock.AsyncMock(return_value={"opted_out_at": "2026-10-01T00:00:00Z"})):
            with self.assertRaises(API.ToolError) as e:
                run(WA.send_whatsapp(ctx, {"to": {"number": "+447700900123"}, "text": "x"}))
        self.assertEqual(e.exception.code, "recipient_opted_out")

    def test_old_s1_keeps_its_own_path(self):
        out, _ = self._send("s1", parity="off")
        self.assertEqual(out["status"], "awaiting_yes")   # its read-back, as before (CR 62) — parity off only

    def test_the_tool_says_so_on_the_one_path(self):
        from app.agent import s2 as S2
        t = next(x for x in API.TOOLS if x["name"] == "send_whatsapp")
        d = S2.standalone_tool(t)["description"]
        self.assertIn("THEIR OWN WhatsApp", d)
        self.assertIn("never sends it from her number", d)
        self.assertIn("FROM SASHA'S NUMBER", t["description"])   # old S1's own words: untouched


class Params(dict):
    pass


class VenueRepliesLandOnAgAPIsRecord(unittest.TestCase):
    def _inbound(self, sender, body="Sí, confirmado para las 21:00", matched=True, linked=False, sid="SM285"):
        p = {"From": f"whatsapp:{sender}", "To": "whatsapp:+447700900000", "Body": body, "MessageSid": sid}
        handed, called = [], []

        async def inbound(s, t, **kw):
            handed.append((s, t))
            return {"matched": matched}

        class Store:
            async def call_for_number(self, n, since):
                called.append(n)
                return None

            async def put(self, row):
                called.append(("put", row["provider_id"]))
                return True
        with mock.patch.object(IP, "_verified", mock.AsyncMock(return_value=p)), mock.patch.object(IP, "STORE", Store()), \
                mock.patch.object(VS, "whatsapp_inbound", inbound), mock.patch.object(GW, "linked", mock.AsyncMock(return_value=linked)), \
                mock.patch.object(GW, "first_time", mock.AsyncMock(return_value=True)), \
                mock.patch.object(GW, "dispatch", mock.AsyncMock(return_value=None)):
            r = run(IP.sms(None))
        return r, handed, called

    def test_a_venues_reply_goes_to_agapi_first_and_nowhere_else(self):
        r, handed, called = self._inbound(VENUE)
        self.assertEqual(handed, [(VENUE, "Sí, confirmado para las 21:00")])
        self.assertEqual(called, [])   # never matched to the last call, never filed here
        self.assertIn(b"<Response></Response>", r.body)   # never answered

    def test_unmatched_runs_the_old_path(self):
        _, handed, called = self._inbound(VENUE, matched=False)
        self.assertEqual(len(handed), 1)
        self.assertEqual(called[0], VENUE)   # then the call match, as before

    def test_a_guest_talking_to_sasha_is_handed_over_first_and_kept_when_unmatched(self):   # Sasha 294 reverses 285's skip
        _, handed, called = self._inbound("+447700900111", linked=True, matched=False)
        self.assertEqual(len(handed), 1)   # AgAPI's ONE classifier first, for every sender (CR 127: the AD door)

    def test_the_hand_off_calls_agapis_one_op(self):
        got = []

        async def call(op, body, approval=None, account=None):
            got.append((op, body, account))
            return {"ok": True, "result": {"matched": True, "kept": True}}
        with mock.patch.object(VS, "CALL", call):
            self.assertEqual(run(VS.whatsapp_inbound(VENUE, "STOP"))["matched"], True)
        self.assertEqual(got, [("messages.whatsapp_inbound", {"from": VENUE, "text": "STOP"}, None)])

    def test_agapi_down_never_loses_it(self):
        async def call(op, body, approval=None, account=None):
            return {"ok": False, "error": {"code": "upstream_unreachable"}}
        with mock.patch.object(VS, "CALL", call):
            self.assertEqual(run(VS.whatsapp_inbound(VENUE, "hola")), {"matched": False, "why": "upstream_unreachable"})


class ThePersonRidesOnPrepare(unittest.TestCase):
    def setUp(self):
        VS._USERS.clear()

    def test_venue_submit_prepare_carries_end_user(self):
        seen = []

        async def call(op, body, approval=None, account=None):
            seen.append((op, body))
            if op == "users.register":
                return {"ok": True, "result": {"end_user_id": "eu_285"}}
            return {"ok": True, "result": {"prepared_id": "vpr_285", "submitted": False}}
        with mock.patch.object(VS, "CALL", call):
            run(VS.prepare(ACCT, {"name": "Casa"}, {"name": "T", "phone": "+447700900000"}, "2099-11-01", "21:00", 2))
        self.assertEqual(seen[-1][0], "venue.prepare_booking")
        self.assertEqual(seen[-1][1]["end_user"], "eu_285")

    def test_venue_truth_prepare_registers_on_its_own_agapi(self):
        seen = []

        async def call(op, body):
            seen.append((op, body))
            if op == "users.register":
                return {"ok": True, "result": {"end_user_id": "eu_vt"}}
            return {"ok": True, "result": {"link": "https://agapi.test/prepared/x", "submitted": False}}
        with mock.patch.object(VT, "CALL", call):
            run(VT.prepare({"name": "Casa"}, {"name": "T", "phone": "+447700900000"}, "2099-11-01", "21:00", 2, account=ACCT))
        self.assertEqual([o for o, _ in seen], ["users.register", "venue.prepare_booking"])   # the same transport, the same AgAPI
        self.assertEqual(seen[-1][1]["end_user"], "eu_vt")

    def test_the_hand_over_passes_the_account(self):
        from agapi import venues as VN
        self.assertIn("int(held[\"party\"]), account=ctx.account)", inspect.getsource(VN._book_inner))


class NoSecondTwilioSender(unittest.TestCase):
    """THE RATCHET (3): the closed list of places that post to Twilio's Messages API, and the one path's guard before Sasha's own."""
    ALLOWED = {
        "booking_signer/guest_whatsapp.py": "the guest's OWN conversation with Sasha (Sender)",
        "booking_signer/guest_receipt.py": "SMS (send_sms) — not WhatsApp",
        "agapi/s2_whatsapp.py": "OLD S1 only (parity off): _twilio, behind the one path's return",
    }

    def test_only_these_post_to_twilio(self):
        found = set()
        for f in list(BACKEND.glob("agapi/*.py")) + list(BACKEND.glob("booking_signer/*.py")) + list(BACKEND.glob("app/**/*.py")) \
                + list(BACKEND.glob("products/**/*.py")):
            if "Messages.json" in f.read_text(encoding="utf-8"):
                found.add(str(f.relative_to(BACKEND)))
        self.assertEqual(found, set(self.ALLOWED))

    def test_the_one_path_returns_before_sashas_own_post(self):
        src = inspect.getsource(WA.send_whatsapp)
        self.assertLess(src.index('if one_path(ctx):'), src.index("await _twilio("))
        self.assertIn('return _in_their_whatsapp(number, to.get("name"), a.get("text"), "agapi_only")',
                      src[src.index('if one_path(ctx):'):src.index("await _twilio(")])

    def test_whatsapp_through_the_guest_sender_goes_only_to_people_talking_to_sasha(self):
        users = set()
        for f in list(BACKEND.glob("agapi/*.py")) + list(BACKEND.glob("booking_signer/*.py")) + list(BACKEND.glob("products/**/*.py")):
            if re.search(r"SENDER\.send\(", f.read_text(encoding="utf-8")):
                users.add(str(f.relative_to(BACKEND)))
        # guest_whatsapp / proactive: a linked guest's own chat; invitations: an invitee who opted in by writing to Sasha (S-80) —
        # each answers a STOP. A new caller must be added here on purpose (or go through AgAPI).
        self.assertEqual(users, {"booking_signer/guest_whatsapp.py", "booking_signer/proactive.py", "booking_signer/invitations.py"})

    def test_the_hand_off_sits_before_the_call_match(self):
        src = inspect.getsource(IP.sms)
        self.assertLess(src.index("VS.whatsapp_inbound(sender, body"), src.index("GW.dispatch("))   # Sasha 294 · + message_id, guest
        self.assertLess(src.index("VS.whatsapp_inbound(sender, body"), src.index("STORE.call_for_number(sender"))


if __name__ == "__main__":
    unittest.main()
