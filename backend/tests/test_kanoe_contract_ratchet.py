"""CR 186 · THE RATCHET (agapi cr/186 docs/agapi/cr186-sasha-half.md §2): fails on any hand-written copy of AgAPI's contract — an operation name
or an AgAPI error code written as a string instead of kanoe_contract.OP / ERR.

    cd backend && python -m unittest tests.test_kanoe_contract_ratchet -v
"""
import pathlib
import subprocess
import sys
import unittest

BACKEND = pathlib.Path(__file__).resolve().parents[1]


class Ratchet(unittest.TestCase):
    def test_no_hand_written_copy(self):
        r = subprocess.run([sys.executable, "-m", "kanoe_contract.ratchet", str(BACKEND), "--exclude", str(BACKEND / "tests")],
                           cwd=BACKEND, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:])


if __name__ == "__main__":
    unittest.main()
