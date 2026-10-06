"""CR 40 · the reliability sweep as a test: 15 natural phrasings per environment (CampusMe, RelocateMe, EspañaMe) through the
WhatsApp turn, each checked for a reply, no error, no loop, and its own expected answer. See tests/sweep_cr40.py.

    cd backend && python -m unittest tests.test_sweep_cr40 -v
"""
from __future__ import annotations

import unittest

from tests import sweep_cr40 as W


class Sweep(unittest.TestCase):
    def _env(self, which, scenarios):
        res = W.sweep(which, scenarios)
        bad = [f"{n}: {' | '.join(p)}" for n, ok, p in res if not ok]
        self.assertEqual(bad, [], "\n".join(bad))

    def test_campus(self):
        self._env(W.classes()[0], W.CAMPUS)

    def test_relocate(self):
        self._env(W.classes()[1], W.RELOCATION)

    def test_espana(self):
        self._env(W.classes()[2], W.ESPANA)


if __name__ == "__main__":
    unittest.main()
