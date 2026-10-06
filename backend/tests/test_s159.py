"""Sasha 159 · web photos to the products' reader, "send me the captcha test", the guest cap never on the founder's devices.

    cd backend && python -m unittest tests.test_s159 -v
"""
import asyncio
import base64
import os
import unittest
from unittest import mock

from booking_signer import captcha_test as CT, guest_accounts as GA, photo_turn as PT

JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 100).decode()


class Photos(unittest.TestCase):
    def test_decoded_and_bounded(self):
        got = PT.decode([{"content_type": "image/jpeg", "data_b64": JPEG}, {"content_type": "image/gif", "data_b64": JPEG},
                         {"content_type": "image/png", "data_b64": "not base64!"}] + [{"content_type": "image/png", "data_b64": JPEG}] * 9)
        self.assertEqual(len(got), 3)   # five looked at: the gif and the broken one dropped
        self.assertEqual(got[0]["content_type"], "image/jpeg")
        self.assertTrue(got[0]["bytes"].startswith(b"\xff\xd8"))

    def test_never_for_a_stranger_and_honest_until_the_reader_takes_photos(self):
        r = asyncio.run(PT.web(None, "📷 (photo)", PT.decode([{"content_type": "image/jpeg", "data_b64": JPEG}]), None, None, False))
        self.assertIn("Nothing was kept", r["response"])


class Captcha(unittest.TestCase):
    def test_the_words(self):
        self.assertTrue(CT.asked("send me the captcha test"))
        self.assertTrue(CT.asked("Send me the CAPTCHA test please"))
        self.assertFalse(CT.asked("what is a captcha?"))

    def test_founder_only(self):
        self.assertIn("founder's", asyncio.run(CT.send("someone-else")))


class GuestCap(unittest.TestCase):
    def setUp(self):
        GA._BY_IP.clear(); GA._DAY.clear(); GA._FOUNDER_IPS.clear()

    def test_the_founders_address_is_never_capped(self):
        for _ in range(8):
            GA._count("1.2.3.4")
        self.assertIsNotNone(GA.allowed("1.2.3.4"))
        GA.note_founder_ip("1.2.3.4")
        self.assertIsNone(GA.allowed("1.2.3.4"))
        self.assertIsNotNone(GA.allowed("5.6.7.8") if [GA._count("5.6.7.8") for _ in range(8)] else None)

    def test_a_listed_address_is_never_capped(self):
        for _ in range(8):
            GA._count("9.9.9.9")
        with mock.patch.dict(os.environ, {"SASHA_GUESTS_UNCAPPED_IPS": "9.9.9.9"}):
            self.assertIsNone(GA.allowed("9.9.9.9"))


class Greeting(unittest.TestCase):
    def test_hi_says_hello_and_names_the_open_item(self):
        from booking_signer import guest_whatsapp as GW
        for m in ("Hey Sasha", "hi", "Hola!", "hello there"):
            self.assertTrue(GW.GREETING.fullmatch(m), m)
        for m in ("hi, book dinner at 9", "highlight", "hey can you call them"):
            self.assertFalse(GW.GREETING.fullmatch(m), m)
        self.assertEqual(GW._open_item({"kind": "need", "read": {"venue": "Casa Lucio"}}), "We were in the middle of your booking at Casa Lucio.")
        self.assertIn("choosing", GW._open_item({"kind": "cards", "find": {"what": "restaurants", "where": "Madrid"}}))


class Sasha161(unittest.TestCase):
    def test_still_want(self):
        from booking_signer import guest_whatsapp as GW
        self.assertEqual(GW._still_want({"kind": "need", "read": {"venue": "Casa Lucio"}, "draft": {"when": {"mode": "at", "at": "2026-10-07T21:00"}}}),
                         "Still want Casa Lucio for Wednesday?")
        self.assertTrue(GW.RESUME.fullmatch("carry on"))
        self.assertTrue(GW.NO.fullmatch("no thanks"))

    def test_one_line_per_route(self):
        from booking_signer import decide as D
        v = D.Venue(phone=True, open_now=False, opens_at="13:00")
        self.assertEqual(D.line(v, D.decide(v), "Indian Accent"),
                         "There's no online booking for Indian Accent — they only take bookings by phone. They're closed now, so I'll call when they open at 13:00. Shall I?")
        v = D.Venue(email=True)
        self.assertIn("only email. I'll email them and tell you as soon as they reply. Shall I?", D.line(v, D.decide(v), "X"))
        v = D.Venue()
        self.assertIn("Want me to try somewhere similar nearby?", D.line(v, D.decide(v), "X"))


class Sasha162(unittest.TestCase):
    def test_what_sasha_starts_goes_from_the_number_they_wrote_to(self):
        from booking_signer import guest_whatsapp as GW
        with mock.patch.dict(os.environ, {"SASHA_GUEST_WHATSAPP_TO": "+447915914215,+14155238886"}):
            self.assertEqual(GW.sender_for({"last_to": "+14155238886"}), "+14155238886")   # wrote to the sandbox: from it
            self.assertEqual(GW.sender_for({"last_to": "+447915914215"}), "+447915914215")
            self.assertEqual(GW.sender_for({}), "+447915914215")                            # unknown: the permanent sender
            self.assertEqual(GW.sender_for({"last_to": "+999"}), "+447915914215")         # not ours: never used
        with mock.patch.dict(os.environ, {"SASHA_GUEST_WHATSAPP_TO": "+14155238886"}):
            self.assertEqual(GW.sender_for({}), "+14155238886")

    def test_outside_the_window_the_template_goes_and_only_then(self):
        from datetime import timedelta
        from booking_signer import guest_whatsapp as GW
        sent = []

        class S:
            async def send(self, frm, to, **kw):
                sent.append((frm, to, kw)); return "sent"

        class St:
            def __init__(self, last): self.last = last
            async def get_state(self, k): return {"last_inbound_at": self.last, "last_to": "+447915914215"}
        ch = {"wa_id_sha256": "k", "number_e164": "+34600000000"}
        with mock.patch.dict(os.environ, {"SASHA_GUEST_WHATSAPP_TO": "+447915914215,+14155238886"}), \
                mock.patch.object(GW, "SENDER", S()), mock.patch.object(GW, "STORE", St(GW.NOW() - timedelta(hours=30))):
            out = asyncio.run(GW._tell(ch, "hi", ("tap_to_finish", {1: "X", 2: "Tue", 3: "https://u"})))
            self.assertIn("template", out)
            self.assertEqual(sent[-1][2]["content_sid"], GW.TEMPLATES["tap_to_finish"][1])   # +34 → the Spanish one
            self.assertEqual(sent[-1][0], "+447915914215")
            self.assertTrue(asyncio.run(GW._tell(ch, "hi")).startswith("not told"))          # no template: nothing goes


if __name__ == "__main__":
    unittest.main()
