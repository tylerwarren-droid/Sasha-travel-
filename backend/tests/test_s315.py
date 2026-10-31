"""Sasha 315 · a case question in travel goes to Applied Diligence on its own (Tyler: "the agent should know what I'm talking about").
Live 16:54: in travel he sent "what's the status of the Prada case?"; Sasha answered about money-back and card-insurance claims and said there
was no "Prada case". He has an AD case for Prada. He had to type "diligence" first.

ROOT TEST
(1) ONE truth: THE ROUTER — products/router.decide — picks the space for each WhatsApp message that no space's word or button claimed. It is
    called from ONE place, products/whatsapp.product_turn.
(2) No per-word hacks: AD's own list of the client's cases (AgAPI's door kind case_list, CR 139) decides whether a NAMED case exists; and
    investigation language as a class (case, investigate, due diligence / DD, questionnaire, interview, "add this to <case>") is AD's.
(3) The whole class, by meaning: clearly AD → handed to AD with ONE short line ("In Applied Diligence:"), never "switch"; clearly travel →
    travel; both at once → ONE question. Sasha's own detector of travel (for_sasha) works again: it read a pattern retired in Sasha 254 and,
    failing, said "travel" to every message.
Offline: AgAPI's op is stood in (agapi/venue_submit.whatsapp_inbound / ad_cases); the real WhatsApp turn runs.

    cd backend && python -m unittest tests.test_s315 -v
"""
from __future__ import annotations

import pathlib
import re
from datetime import datetime, timezone
from unittest import mock

from agapi import venue_submit as VS
from products import diligence as DG, router as RT, space as SPC, store as ST, whatsapp as PW
from tests import test_guest_whatsapp_s75 as TG

run = TG.run
ROOT = pathlib.Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 29, 16, 54, tzinfo=timezone.utc)
PRADA = [{"case_id": "af68eb09-0000-4000-8000-000000000315", "name": "Prada", "status": "open", "opened_at": "2026-10-28T10:00:00Z"},
         {"case_id": "53fc651b-0000-4000-8000-000000000315", "name": "Lehman Brothers Holdings Inc", "status": "open",
          "opened_at": "2026-10-27T10:00:00Z"}]
# Sasha 318 · AgAPI's answer (messages.ad_cases {from, text} → named), stood in as DATA — the message → the case_ids AD's door's reading names.
# Sasha has no matcher of its own to test: what the router does with AgAPI's answer is what is tested here.
AGAPI_NAMED = {"what's the status of prada?": [PRADA[0]["case_id"]], "any news on lehman brothers?": [PRADA[1]["case_id"]]}


def agapi(cases, text):
    """AgAPI's answer for this message, as the op returns it (each case with named)."""
    if cases is None:
        return None
    ids = AGAPI_NAMED.get(" ".join(str(text or "").lower().split()), [])
    return [{**c, "named": c["case_id"] in ids} for c in cases]


class TheRouterReadsMeaning(TG.unittest.TestCase):
    def d(self, text, cases=None):
        return RT.classify(text, [], NOW, cases)

    def test_a_tylers_message_is_ads(self):
        self.assertEqual(self.d("what's the status of the Prada case?"), "diligence")
        self.assertEqual(self.d("what's the status of the Prada case?", PRADA), "diligence")

    def test_b_a_named_case_from_ads_list_is_ads_without_the_word_case(self):
        self.assertEqual(self.d("what's the status of Prada?", agapi(PRADA, "what's the status of Prada?")), "diligence")
        self.assertEqual(self.d("any news on lehman brothers?", agapi(PRADA, "any news on lehman brothers?")), "diligence")
        self.assertEqual(self.d("what's the status of Prada?", PRADA), "sasha")           # AgAPI didn't read it: Sasha never guesses
        self.assertEqual(self.d("what's the status of Prada?", []), "sasha")              # no such case: travel, as before
        self.assertEqual(self.d("what's the status of Prada?", None), "sasha")            # AD gave no list: nothing guessed

    def test_c_investigation_language_is_a_class(self):
        for t in ("investigate Acme Holdings", "due diligence on Acme", "run DD on Acme", "send the questionnaire to Maria",
                  "invite John Smith to the interview", "add this to Lehman brothers: they filed late", "case 53fc651b",
                  "what's happening with my cases?", "any update on the Acme investigation?"):
            self.assertEqual(self.d(t), "diligence", t)

    def test_d_travel_stays_travel(self):
        for t in ("book dinner at Taverna Correo on Friday at 21:00 for 2", "where is my money-back claim?",
                  "status of my card insurance claim", "I need a phone case", "just in case, book a hotel in Madrid",
                  "hi", "yes", "a case of wine for the room", "ad hoc meeting tomorrow"):
            self.assertEqual(self.d(t), "sasha", t)

    def test_e_both_at_once_is_one_question(self):
        for t in ("book a flight to Milan for the Prada interview", "status of my compensation case"):
            self.assertEqual(self.d(t), "ask", t)

    def test_f_sashas_travel_detector_works_again(self):   # found while writing this: GW.COMBO was retired (Sasha 254); for_sasha raised → True
        self.assertFalse(PW.for_sasha("what's the status of the Prada case?", [], NOW))
        self.assertTrue(PW.for_sasha("book dinner at Taverna Correo on Friday at 21:00 for 2", [], NOW))


class Base(TG.Base):
    def setUp(self):
        super().setUp()
        self.saved_st = ST.STORE
        ST.STORE = ST.MemoryCaseStore()
        self.addCleanup(lambda: setattr(ST, "STORE", self.saved_st))
        self.answer = {"matched": True, "kept": True, "ad": "door", "replied": True}
        self.ad = mock.AsyncMock(side_effect=lambda *a, **k: dict(self.answer))
        self.cases = mock.AsyncMock(side_effect=lambda number, text=None: agapi(PRADA, text))
        for p in (mock.patch.object(VS, "whatsapp_inbound", self.ad), mock.patch.object(VS, "ad_cases", self.cases)):
            p.start()
            self.addCleanup(p.stop)
        RT._CASES.clear()
        self.link()
        TG.stand_in_brain(self)

    def sent_to_ad(self):
        return [(c.args[1], c.kwargs.get("space"), c.kwargs.get("guest")) for c in self.ad.call_args_list]

    def space(self):
        return run(SPC.current_space(TG.ACCOUNT))


class InTravelTheCaseQuestionGoesToAD(Base):
    def test_a_no_diligence_needed_one_line_no_switch(self):
        self.say("what's the status of the Prada case?")
        self.assertEqual(self.sent_to_ad(), [("what's the status of the Prada case?", "diligence", True)])
        self.assertEqual(self.bodies()[-1], RT.LINE)                       # the ONE line; AD's reply is AgAPI's, sent from Kanoe's number
        self.assertNotRegex(self.bodies()[-1].lower(), r"switch|diligence”|say “")
        self.assertEqual(self.brain_saw, [])                               # Sasha's travel brain never saw it
        self.assertEqual(self.space(), "sasha")                            # he never moved: travel is still where he is

    def test_b_travel_still_goes_to_travel(self):
        self.say("what's the status of the Prada case?")
        self.say("book dinner at Taverna Correo on Friday at 21:00 for 2")
        self.assertEqual(self.brain_saw, ["book dinner at Taverna Correo on Friday at 21:00 for 2"])
        self.assertEqual(len(self.sent_to_ad()), 1)

    def test_c_ads_answer_is_answered_to_ad(self):   # AD asked last ("Send me a contact…"): his reply is AD's, unless it is travel
        self.say("what's the status of the Prada case?")
        self.say("yes")
        self.assertEqual([t for t, _, _ in self.sent_to_ad()], ["what's the status of the Prada case?", "yes"])
        self.say("book dinner at Taverna Correo on Friday at 21:00 for 2")
        self.say("yes")                                                    # Sasha asked last now: hers
        self.assertEqual(self.brain_saw, ["book dinner at Taverna Correo on Friday at 21:00 for 2", "yes"])

    def test_d_unclear_is_one_question_and_the_answer_routes_it(self):
        self.say("book a flight to Milan for the Prada interview")
        self.assertEqual(self.sent_to_ad(), [])
        self.assertEqual(GW_sent_buttons(), [RT.ASK_AD, RT.ASK_TRAVEL])
        self.say("", payload="rt:ad")
        self.assertEqual(self.sent_to_ad(), [("book a flight to Milan for the Prada interview", "diligence", True)])

    def test_e_unclear_answered_travel(self):
        self.say("book a flight to Milan for the Prada interview")
        self.say("", payload="rt:sasha")
        self.assertEqual(self.brain_saw, ["book a flight to Milan for the Prada interview"])
        self.assertEqual(self.sent_to_ad(), [])

    def test_f_ad_down_is_said(self):
        self.answer = {"matched": False, "why": "upstream_unreachable"}
        self.say("what's the status of the Prada case?")
        self.assertTrue(self.bodies()[-1].endswith(DG.DOWN))

    def test_g_the_named_case_is_asked_of_ads_list(self):
        self.say("what's the status of Prada?")
        self.cases.assert_awaited()
        self.assertEqual(self.cases.await_args.args[0], TG.GUEST)
        self.assertEqual([t for t, _, _ in self.sent_to_ad()], ["what's the status of Prada?"])


def GW_sent_buttons():
    from booking_signer import guest_whatsapp as GW
    body, buttons = GW.SENDER.contents[-1]   # the fake sender's quick-reply content: (its text, its buttons)
    assert body.endswith(RT.ASK), body
    return [b[0] if isinstance(b, (list, tuple)) else b for b in buttons]


class OneRouter(TG.unittest.TestCase):
    def test_a_one_place_calls_it(self):
        users = sorted(str(f.relative_to(ROOT)) for f in ROOT.rglob("*.py")
                       if "tests" not in f.parts and re.search(r"\bRT\.decide\(|router\.decide\(", f.read_text()))
        self.assertEqual(users, ["products/whatsapp.py"])

    def test_b_ads_door_is_still_reached_from_its_module_only(self):   # CR 128's pin holds: space="diligence" in products/diligence.py
        users = sorted(str(f.relative_to(ROOT)) for f in ROOT.rglob("*.py")
                       if "tests" not in f.parts and re.search(r'space\s*=\s*"diligence"', f.read_text()))
        self.assertEqual(users, ["products/diligence.py"])

    def test_c_the_case_list_is_ads_never_a_copy(self):
        src = (ROOT / "products" / "router.py").read_text()
        self.assertIn("VS.ad_cases(", src)
        self.assertNotRegex(src, r"put_kind|STORE\.put|s2_memory")


if __name__ == "__main__":
    TG.unittest.main()
