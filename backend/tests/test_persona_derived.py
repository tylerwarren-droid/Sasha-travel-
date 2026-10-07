"""Sasha 201 · the charter, rule 1 — her words have ONE source (docs/sasha/sasha-persona.md). The derived files
(app/services/persona.py, frontend/lib/avatar-context.mjs) must be exactly what scripts/derive_persona.py writes from it."""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GEN = os.path.join(ROOT, "scripts", "derive_persona.py")


@unittest.skipUnless(os.path.exists(GEN), "the repo's docs/ and scripts/ are not in this checkout (a backend-only build)")
class PersonaIsDerived(unittest.TestCase):
    def test_the_derived_files_are_current(self):
        r = subprocess.run([sys.executable, GEN, "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_conductor_speaks_the_persona(self):
        from app.services import conductor as CD, persona as P
        self.assertEqual(CD.S199_OPEN, P.LINES["open"])
        self.assertEqual(CD.S199_FLIGHTS, P.LINES["flights"])
        self.assertIn(P.SERVER_VOICE_RULES.splitlines()[0][:40], P.SERVER_VOICE_RULES)

    def test_the_avatar_prompt_never_plans_or_books(self):
        from app.services import persona as P
        self.assertIn("Never plan", P.AVATAR_PROMPT)
        for q in P.QUIVER:
            self.assertIn(q, P.AVATAR_PROMPT)
        self.assertNotRegex(P.AVATAR_OPENING, r"(?i)plan|trip|book|itinerar")


if __name__ == "__main__":
    unittest.main()
