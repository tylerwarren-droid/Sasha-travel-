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


if __name__ == "__main__":
    unittest.main()
