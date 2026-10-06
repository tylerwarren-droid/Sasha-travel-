"""CR 30 (1) · a photo uploaded in the WEB chat (laptop or phone) goes through the same reader as WhatsApp's: read once,
checked against its own check digits, read back for one yes, never kept. Specimen passport (tests' fake reader).

    cd backend && python -m unittest tests.test_web_media_cr30 -v
"""
from __future__ import annotations

from products import web as PWEB
from products.relocation import docread as DR
from tests import test_guest_whatsapp_s75 as TG
from tests import test_relocation_m3_cr1 as TR

run = TG.run
JPEG = b"\xff\xd8\xff\xe0 specimen passport photo page"


def web(t, message="", mode=None, payload=None, media=None):
    return run(PWEB.web_turn(TG.ACCOUNT, message, mode=mode, payload=payload, now=t.now, signed_in=True, media=media))


class WebPhoto(TR.Flow):
    def setUp(self):
        super().setUp()
        self.fetched = []
        saved_fetch = DR.FETCH

        async def fetch(url):          # a web upload must never be fetched: its bytes come with it
            self.fetched.append(url)
            return await saved_fetch(url)
        DR.FETCH = fetch

    def test_the_passport_photo_on_the_laptop_is_read_and_read_back(self):
        for t in ("relocation", "first", "me", "myself"):
            web(self, t)
        r = web(self, media=[{"bytes": JPEG, "content_type": "image/jpeg"}])
        self.assertEqual(self.reads, ["image/jpeg"])
        self.assertEqual(self.fetched, [])
        self.assertIn("AB1234567", r["response"])
        self.assertIn("Passport number", r["response"])
        self.assertEqual(r["quick_replies"][0]["payload"], "rx:doc:yes")   # one yes, as on WhatsApp

    def test_web_and_whatsapp_hold_the_same_file(self):
        for t in ("relocation", "first", "me", "myself"):
            web(self, t)
        web(self, media=[{"bytes": JPEG, "content_type": "image/jpeg"}])
        web(self, payload="rx:doc:yes")
        self.say("what's next for my application?")                       # the phone: the passport is not asked again
        self.assertNotIn("passport number", TG.GW.SENDER.contents[-1][0].lower() if TG.GW.SENDER.contents else "")
        self.assertIn("Back to your EX-01.", self.bodies()[-1])

    def test_what_is_not_a_photo_is_dropped_before_the_reader(self):
        self.assertEqual(PWEB.web_media([{"bytes": b"%PDF-1.7", "content_type": "application/pdf"}])[0]["type"], "application/pdf")
        self.assertEqual(PWEB.web_media([{"bytes": b"x" * (PWEB.WEB_MEDIA_MAX + 1), "content_type": "image/jpeg"}]), [])
        self.assertEqual(len(PWEB.web_media([{"bytes": b"a", "content_type": "image/png"}] * 9)), PWEB.WEB_MEDIA_COUNT)
        for t in ("relocation", "first", "me", "myself"):
            web(self, t)
        r = web(self, media=[{"bytes": b"%PDF-1.7", "content_type": "application/pdf"}])
        self.assertEqual(self.reads, [])
        self.assertIn("JPEG or PNG", r["response"])


if __name__ == "__main__":
    TG.unittest.main()


class NeverAskTwice(TR.Flow):
    """CR 30 (2) · about to repeat the last question with nothing learned → what's held, what's missing, once; "later" keeps."""

    def test_the_same_question_again_becomes_what_i_have_and_what_is_missing(self):
        self.start()
        self.say("hmm not sure")                               # not an answer: never stored, a gentle re-ask
        self.assertIn("No problem", self.bodies()[-1])
        self.say("hmm not sure")                               # the same reply would come again → what I have / what's missing
        guarded = self.bodies()[-1]
        self.assertIn("I asked that a moment ago", guarded)
        self.assertIn("Still missing:", guarded)
        self.assertIn("say “later”", guarded)
        self.say("hmm not sure")                               # once per question: no second lecture
        self.assertNotIn("I asked that a moment ago", self.bodies()[-1])
        a = TG.run(TG.GW.STORE.get_state(TG.GW.wa_key(TG.GUEST)))["pending"]["facts"].get("applicant", {})
        self.assertNotIn("passport_number", a)                 # never stored a non-answer

    def test_the_passport_number_said_in_a_sentence_is_taken_once(self):
        self.start()
        self.say("my passport number is AB1234567")
        self.assertIn("first surname", self.bodies()[-1].lower())       # moved on: never asked again

    def test_later_keeps_the_file_and_the_word_resumes_it(self):
        self.start()
        self.say("later")
        self.assertIn("Kept", self.bodies()[-1])
        self.assertIn("“relocation”", self.bodies()[-1])
        self.say("relocation")
        self.assertTrue(self.bodies()[-1].startswith("Back to your EX-01."))

    def test_held_never_says_a_health_identifier(self):
        from products import whatsapp as PW
        facts = {"applicant": {"passport_number": {"value": "AB1234567"}}, "health": {"tarjeta": {"value": "MDRD123"}},
                 "card_code": {"value": "X"}}
        self.assertEqual(PW.held(facts), ["Passport number: AB1234567"])
