"""S-52 · who Sasha says she is: "an AI concierge operated by Kanoe Technologies SL", first, everywhere.

    cd backend && python -m unittest tests.test_wordings -v
"""
import json
import pathlib
import re
import unittest

from booking_signer import wordings as W

FRONTEND_TEMPLATE = pathlib.Path(__file__).parents[2] / "frontend" / "lib" / "whatsapp-template.ts"


class Wordings(unittest.TestCase):
    def test_no_current_wording_says_assistant(self):
        current = [*W.DISCLOSURE.values(), *W.WHATSAPP_TEMPLATE_V2.values()]
        current += [t for ch in W.OPTIN_WORDINGS.values() for t in ch[W.CURRENT_OPTIN_VERSION].values()]
        for t in current:
            self.assertNotRegex(t.lower(), r"assistant|asistente|assistente|asistanı", t[:60])
            self.assertIn("Kanoe Technologies SL", t)

    def test_the_disclosure_comes_first_in_the_whatsapp_text(self):
        for lang, t in W.WHATSAPP_TEMPLATE_V2.items():
            self.assertLess(t.index("Kanoe Technologies SL"), t.index("{who}"), lang)

    def test_the_frontend_mode_a_text_is_the_backends_byte_for_byte(self):
        src = FRONTEND_TEMPLATE.read_text(encoding="utf-8")
        found = dict(re.findall(r'^\s+(en|es|pt|tr): ("(?:[^"\\]|\\.)*"),$', src, re.M))
        self.assertEqual({k: json.loads(v) for k, v in found.items()}, W.WHATSAPP_TEMPLATE_V2)

    def test_opt_in_wordings_are_versioned_and_v1_is_kept_as_it_was(self):
        self.assertIn("an AI assistant", W.OPTIN_WORDINGS["whatsapp"]["v1"]["en"])   # stored v1 consents stay checkable
        w = W.optin_wording("web_submit", "es", url="https://v.test/reservas")
        self.assertEqual((w["version"], w["lang"]), ("v2", "es"))
        self.assertIn("https://v.test/reservas", w["text"])
        self.assertEqual(len(w["sha256"]), 64)
        self.assertEqual(W.optin_wording("whatsapp", "xx")["lang"], "en")


if __name__ == "__main__":
    unittest.main()
