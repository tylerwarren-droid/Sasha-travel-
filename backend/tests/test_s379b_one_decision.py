"""Sasha 379b · CR 192's Sasha half — ONE decision per inbound WhatsApp about which product it belongs to, and it is AgAPI's, on the FIRST
call (messages.whatsapp_inbound), from AD's own reading of THESE words (conversation_role.ad_intent, read with every question of AD's
still open). NO PATCHES.

Found (EU 285, 12 Nov 15:48 — Sasha 379, row 1920): Tyler's "es" (a yes to AD's offer) had two answers. The second came from a retired
service by Twilio's fallback (379a fixed that); and Sasha's own router still decided by its own memory — rule 2 `chose`, the ONE question
of her own, `space` (diligence.space_now) and a SECOND whatsapp_inbound (diligence.hand_over). All gone:
  matched → AD only (Sasha says nothing — AgAPI's answer is the one answer); unmatched → Sasha (her own tools by their word, else travel);
  AD's own word left unmatched → told, never travel's answer; an "ad" verdict left unmatched → logged loudly, never rerouted.
Was test_s361_one_router (the old router); test_cr128 / cr136 / cr142 (AD's space inside Sasha) retired with it.

    cd backend && python -m unittest tests.test_s379b_one_decision -v
"""
from __future__ import annotations

import pathlib
import re
import unittest
from unittest import mock

from booking_signer import guest_whatsapp as GW, inbound_outcome as OC
from products import diligence as DG, tools as TL
from tests import test_inbound_phone as TIP
from tests.test_guest_whatsapp_s75 import GUEST, SANDBOX, Base, run

ROOT = pathlib.Path(__file__).resolve().parents[1]
OGG = "https://api.twilio.com/2010-04-01/Accounts/AC1/Messages/MM1/Media/ME22"


class FakeAgAPI:
    """messages.whatsapp_inbound as AgAPI answers it after CR 192: AD's reading of THESE words decides — AD's words (or the answer to AD's
    open question) → matched, AD answers from Kanoe's number; anything else → unmatched, ad_intent "not_ad"."""

    def __init__(self):
        self.calls, self.open, self.down, self.closed = [], False, False, False

    async def __call__(self, sender, text, message_id=None, guest=False, twilio=None, **kw):
        self.calls.append({"text": text, "message_id": message_id, **kw})
        if self.down:
            return {"matched": False, "why": "unavailable"}
        ads = bool(re.match(r"(?i)\s*(diligence|do \d|investigate|show my cases)", text or "")) or (self.open and (text or "").strip().lower()
                                                                                                     in ("es", "yes", "2", "sí"))
        role = {"resolved": True, "reason": "one", "role": {"kind": "ad_user"}, "open": self.open, "ad_intent": "ad" if ads else "not_ad"}
        if ads:
            self.open = False
            return {"matched": True, "kept": True, "ad": "closed" if self.closed else "replied", "replied": True, "conversation_role": role}
        return {"matched": False, "why": "a guest of the product", "conversation_role": role}


class ThroughTheWebhook(Base):
    """The real webhook (signed as Twilio sends it); AgAPI's inbound stood in by FakeAgAPI; Sasha's brain stood in (records what reached it)."""

    def setUp(self):
        super().setUp()
        TIP.InboundPhone.setUp(self)
        self.turns, self.brain_saw = [], []
        GW._spawn = lambda coro: self.turns.append(coro)
        self.agapi = FakeAgAPI()

        async def brain(ch, body, payload, st, out, now, button_text="", voice_in=False):
            self.brain_saw.append(body)
            out.text(f"agent: {body}")
            return "x"
        from booking_signer import wa_agent as WA
        self.p = [mock.patch("agapi.venue_submit.whatsapp_inbound", self.agapi), mock.patch.object(WA, "agent_turn", brain),
                  mock.patch.object(DG, "_account_email", mock.AsyncMock(return_value="tyler@example.test"))]
        for x in self.p:
            x.start()
        self.link()
        self.n = 0

    def tearDown(self):
        for x in reversed(self.p):
            x.stop()
        TIP.InboundPhone.tearDown(self)
        super().tearDown()

    def msg(self, body, payload="", media=(), replied_to=None):
        self.n += 1
        form = {"MessageSid": "SM" + f"{self.n:032x}", "From": f"whatsapp:{GUEST}", "To": f"whatsapp:{SANDBOX}", "Body": body,
                "NumMedia": str(len(media))}
        for i, (u, t) in enumerate(media):
            form[f"MediaUrl{i}"], form[f"MediaContentType{i}"] = u, t
        if replied_to:
            form["OriginalRepliedMessageSid"] = replied_to
        if payload:
            form["ButtonPayload"] = payload
        n0 = len(GW.SENDER.sent)
        self.c.post("/api/booking/twilio/sms", data=form, headers={"X-Twilio-Signature": TIP.sign("sms", form)})
        while self.turns:
            run(self.turns.pop(0))
        return [s["body"] for s in GW.SENDER.sent[n0:]]

    def calls_for(self, n):
        return [c for c in self.agapi.calls if c["message_id"] == "SM" + f"{n:032x}"]


class OneDecision(ThroughTheWebhook):
    def test_the_ad_offer_then_es_is_one_answer_ads(self):
        """THE REPLAY (EU 285): AD's offer is open; "es" → AgAPI takes it on the first call → AD's answer is the ONE outbound."""
        self.agapi.open = True
        said = self.msg("es")
        self.assertEqual(said, [])                                                        # nothing of Sasha's — AD's (sent by AgAPI) only
        self.assertEqual(self.brain_saw, [])
        self.assertEqual(len(self.calls_for(self.n)), 1)                                  # ONE call for the message

    def test_book_a_table_with_nothing_open_is_travel_only(self):
        said = self.msg("book a table for 2 tonight")
        self.assertEqual(self.brain_saw, ["book a table for 2 tonight"])                  # travel answers …
        self.assertEqual(said, ["agent: book a table for 2 tonight"])                     # … once
        self.assertEqual(len(self.calls_for(self.n)), 1)                                  # AD silent: unmatched on the one call

    def test_no_memory_of_a_choice(self):
        """An AD message, then a travel one: each decided on its own words by AgAPI — never by what was "chosen" before."""
        self.msg("diligence")
        self.msg("do 1-3 on Halfords")
        self.msg("a table for two tonight")
        self.assertEqual(self.brain_saw, ["a table for two tonight"])

    def test_the_due_diligence_row_reaches_agapi_as_ads_word(self):
        said = self.msg(TL.title(TL.BY_ID["diligence"]), payload=TL.TOOL_ID + "diligence")
        self.assertEqual([c["text"] for c in self.calls_for(self.n)], [TL.BY_ID["diligence"]["word"]])
        self.assertEqual((said, self.brain_saw), ([], []))                                # AD asks its own question (from Kanoe's number)

    def test_sashas_own_rows_never_reach_agapi(self):
        self.msg(TL.title(TL.BY_ID["travel"]), payload=TL.TOOL_ID + "travel")
        self.assertEqual(self.calls_for(self.n), [])

    def test_ads_word_left_unmatched_is_told_never_travels_answer(self):
        self.agapi.down = True
        with self.assertLogs("booking_signer.inbound_outcome", "ERROR"):
            said = self.msg("diligence")
        self.assertEqual(self.brain_saw, [])
        self.assertEqual(said, [OC.FAILED["en"]])

    def test_ad_closed_is_said_once(self):
        self.agapi.closed = True
        self.assertEqual(self.msg("investigate Acme Ltd"), [DG.CLOSED])

    def test_everything_ad_may_need_is_on_the_one_call_and_never_a_space(self):
        self.msg("", media=[(OGG, "audio/ogg")], replied_to="SM" + "a" * 32)
        c = self.calls_for(self.n)[0]
        self.assertEqual((c["media"], c["replied_to"], c["account_email"]),
                         ([{"url": OGG, "type": "audio/ogg"}], "SM" + "a" * 32, "tyler@example.test"))
        self.assertNotIn("space", c)
        self.assertTrue(all("space" not in x for x in self.agapi.calls))

    def test_a_voice_note_not_ads_is_heard_as_words(self):
        with mock.patch.object(GW, "voice_text", mock.AsyncMock(return_value="a table for two tonight")) as vt:
            self.msg("", media=[(OGG, "audio/ogg")])
        vt.assert_called_once()                                                           # AgAPI didn't take it: Sasha hears it
        self.assertEqual(self.brain_saw, ["a table for two tonight"])

    def test_an_ad_verdict_left_unmatched_is_logged_never_rerouted(self):
        with self.assertLogs("products.tools", "ERROR"):
            self.assertEqual(TL.route("anything", {"ad_intent": "ad"}), "sasha")
        self.assertEqual(TL.route("campus", None), "sasha")                              # Sasha's own tool: hers (her own switch picks it)
        self.assertEqual(TL.route("diligence", None), "diligence")                        # AD's word, if it ever reaches here: told
        self.assertEqual(TL.route("book a table", {"ad_intent": "not_ad"}), "sasha")


class TheRatchet(unittest.TestCase):
    def test_no_decider_of_sashas_own_and_one_call(self):
        for gone in ("recalled", "remember", "ask_which", "roles"):
            self.assertFalse(hasattr(TL, gone), gone)
        for gone in ("space_now", "hand_over"):
            self.assertFalse(hasattr(DG, gone), gone)
        sites, hits = [], []
        for d in ("products", "booking_signer", "agapi", "app"):
            for f in sorted((ROOT / d).rglob("*.py")):
                s = f.read_text(encoding="utf-8", errors="ignore")
                rel = str(f.relative_to(ROOT))
                sites += [rel for _ in re.finditer(r"VS\.whatsapp_inbound\(", s)]
                if re.search(r"set_agent_state\([^)]*\bchose\b|\bchose_now\b|route_held", s):
                    hits.append(rel)
                if re.search(r"whatsapp_inbound\([^)]*\bspace\s*=", s):
                    hits.append(rel + ": space")
        self.assertEqual(sites, ["booking_signer/inbound_phone.py"])                     # ONE call site: the webhook's first call
        self.assertEqual(hits, [])
        self.assertNotIn("space", __import__("inspect").signature(__import__("agapi.venue_submit", fromlist=["x"]).whatsapp_inbound).parameters)


if __name__ == "__main__":
    unittest.main()
