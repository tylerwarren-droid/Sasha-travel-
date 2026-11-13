"""Sasha 383 · THE GATE'S PASS MARK IS WRITTEN — found by 383's push build (b57218d8): ReplayMissing on keys the recording build 55551406
had recorded and passed. 381f wrote the mark with kind 'gate_pass'; sasha_measures' CHECK (sasha_measures_kind_check) refused it
(the gate logged "pass not marked (CheckViolationError)"), so no build was ever marked passed and no recording since 381f could be
replayed. Now the mark is a replay-store record (kind 'model_replay', id gate_pass:<build>), and every kind any code writes to the
table is one the database accepts.

    cd backend && python -m unittest tests.test_s383_gate_pass_mark -v
"""
from __future__ import annotations

import inspect
import pathlib
import re
import unittest

from booking_signer import model_gateway as MG

BACKEND = pathlib.Path(__file__).resolve().parents[1]


class TheMark(unittest.TestCase):
    def test_the_pass_mark_is_an_accepted_kind(self):
        src = inspect.getsource(MG._PgReplays.mark_passed)
        self.assertIn("'model_replay'", src)
        self.assertNotIn("values ($1, 'gate_pass'", src)
        self.assertIn('f"gate_pass:{build}"', src)
        self.assertIn('f"gate_pass:{build}"', inspect.getsource(MG._PgReplays.passed))   # the reader reads the same id

    def test_every_kind_written_to_sasha_measures_is_accepted(self):
        bad = []
        for f in BACKEND.rglob("*.py"):
            rel = f.relative_to(BACKEND).as_posix()
            if rel.startswith(("tests/", "venv/", ".venv/")):
                continue
            src = f.read_text(errors="ignore")
            for m in re.finditer(r"insert into sasha_measures \([^)]*\)\s*\"?\s*\"?values \(\$1, '([a-z_]+)'", src):
                if m[1] not in MG.MEASURE_KINDS:
                    bad.append(f"{rel}: {m[1]}")
        self.assertEqual(bad, [])
        from agapi import measure as ME   # the measures writer passes its row's kind: each one it makes is accepted
        kinds = set(re.findall(r'"kind": "([a-z_]+)"', inspect.getsource(ME)))
        self.assertTrue(kinds and kinds <= set(MG.MEASURE_KINDS), kinds)


if __name__ == "__main__":
    unittest.main()
