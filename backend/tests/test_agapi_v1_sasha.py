"""CR 61 · Sasha on AgAPI v1.0: the yes on EU's frozen lists (English and Spanish), the apostrophe errata, Sasha's deliberate additions,
and — when EU's frozen files are on this machine — the full conformance runner (scripts/agapi_v1_conformance.py).

    cd backend && python -m unittest tests.test_agapi_v1_sasha -v
"""
from __future__ import annotations

import hashlib
import os
import unittest
from pathlib import Path

from agapi import v0 as API, v1 as V1


class TheYes(unittest.TestCase):
    def test_apostrophes_never_turn_a_no_into_a_yes(self):
        for said in ("Yes, don't book it", "Yes, don’t book it", "yes, I don't want that", "Sure — don't send it yet"):
            self.assertFalse(API.explicit_yes(said), said)
            self.assertFalse(V1.explicit_yes(said, "en"), said)

    def test_lets_do_it_is_a_yes(self):
        for said in ("OK, let's do it", "Perfect, let’s do it", "let's book"):
            self.assertTrue(API.explicit_yes(said), said)

    def test_spanish(self):
        for said in ("Sí, adelante.", "vale", "Vale, hazlo", "de acuerdo"):
            self.assertTrue(API.explicit_yes(said), said)
        for said in ("sí, pero luego", "Vale, búscame opciones", "no", "espera"):
            self.assertFalse(API.explicit_yes(said), said)

    def test_sashas_deliberate_additions(self):
        self.assertTrue(API.explicit_yes("Perfect, book the whole trip"))          # an extra affirmative
        self.assertFalse(API.explicit_yes("yes, cancel it"))                       # 1.1: "cancel" vetoes a plain yes…
        self.assertTrue(API.yes_to_cancel("yes, cancel it"))                       # …but confirms a cancellation (act_kind)…
        self.assertFalse(API.yes_to_cancel("don't cancel it"))
        self.assertFalse(API.yes_to_book("yes, cancel it"))                        # …and never books
        for said in ("Yes, but what's the refund?", "Sure — what’s the total?"):    # 1.1: the apostrophe hole
            self.assertFalse(API.explicit_yes(said), said)
        self.assertTrue(API.explicit_yes("OK, let's do it"))
        self.assertFalse(API.explicit_yes("yes, but first the price"))             # an extra veto (stricter is safe)

    def test_the_pinned_language_file(self):
        raw = V1.LANGUAGE_FILE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), V1.LANGUAGE_SHA256)


FROZEN = Path(os.getenv("AGAPI_V1_DIR") or Path.home() / "Developer" / "Applied Diligence" / "docs" / "agapi" / "v1")


@unittest.skipUnless((FROZEN / "vectors" / "canonical.json").exists(), "EU's frozen v1.0 files aren't on this machine (set AGAPI_V1_DIR)")
class Conformance(unittest.TestCase):
    def test_the_runner_passes(self):
        from scripts import agapi_v1_conformance as RUN
        os.environ.setdefault("AGAPI_V1_DIR", str(FROZEN))
        self.assertEqual(RUN.main(), 0)


if __name__ == "__main__":
    unittest.main()
