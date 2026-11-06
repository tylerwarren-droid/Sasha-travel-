"""Sasha 348 · ONE client for every request a page makes (docs/sasha/S-348-one-request-client.md).
    cd backend && python -m unittest tests.test_s348_one_request_client -v
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"
CHECK = FE / "scripts/check-outcome-surfaces.mjs"
HAS_NODE = bool(shutil.which("node") and (FE / "node_modules/typescript").exists())


class OneClient(unittest.TestCase):
    def test_the_client(self):
        lib = (FE / "lib/request.ts").read_text()
        for fn in ("export async function reach(", "export async function request(", "export function events(", "export function socket(",
                   "export function beacon(", "export const axios = {"):
            self.assertIn(fn, lib)
        self.assertEqual(lib.count("globalThis.fetch("), 1)                                   # THE one place a request leaves
        self.assertIn("toConsole(failed(`The request to ${where(input)}`, e))", lib)          # told before the caller sees it

    def test_axios_is_gone(self):
        self.assertNotIn('"axios"', json.loads((FE / "package.json").read_text()).get("dependencies", {}))
        self.assertNotIn("node_modules/axios", json.loads((FE / "package-lock.json").read_text())["packages"])

    @unittest.skipUnless(HAS_NODE, "node + the frontend's typescript")
    def test_zero_direct_requests(self):
        r = subprocess.run(["node", "scripts/one-client.mjs"], cwd=FE, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertIn("one-client: 0 direct request(s) in 0 file(s)", r.stdout)

    @unittest.skipUnless(HAS_NODE, "node + the frontend's typescript")
    def test_the_prebuild_passes(self):
        r = subprocess.run(["node", str(CHECK)], cwd=FE, capture_output=True, text=True, timeout=240)
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-3000:])
        self.assertIn("(every page that acts — no exceptions)", r.stdout)


class TheCheckRefusesTheWholeClass(unittest.TestCase):
    def test_the_rules_and_their_fixtures(self):
        chk = CHECK.read_text()
        self.assertIn("R1  a direct ${d.what}", chk)                                           # any direct request, anywhere
        self.assertIn('rule: "S4"', chk)                                                       # a catch that tells nobody
        self.assertIn('rule: "S5"', chk)                                                       # a press told only to the console
        for fx in ("a catch that tells nobody (Sasha 348)", "a press told only to the console (Sasha 348)", "the direct-request checker is broken"):
            self.assertIn(fx, chk)
        self.assertIn("ts.SyntaxKind.EqualsToken", chk)                                        # `x = p` stores it: not floating
        self.assertNotIn("NOT_YET_CLEAN", chk)

    def test_acting_is_found_not_listed(self):
        chk = CHECK.read_text()
        self.assertIn("if (rel !== \"app/api\") out.push(...actingPages(rel))", chk)          # every page and library, the server's routes aside
        self.assertIn("(request|booking-client)", chk)


class S2Tells(unittest.TestCase):
    def test_the_outcome_path(self):
        o = (FE / "lib/outcome.ts").read_text()
        self.assertIn("export const noted =", o)
        self.assertIn("export function announce(", o)
        self.assertIn("couldn’t reach Sasha — your connection seems to be off. Try again when it’s back.", o)

    def test_the_hello_and_the_mic(self):
        hello = (FE / "app/s2/S2Hello.tsx").read_text()
        self.assertIn("else announce(failed('Bringing her face up', e))", hello)
        self.assertIn("else announce(failed('Bringing her face back', e))", hello)
        mic = (FE / "app/components/VoiceButton.tsx").read_text()
        self.assertIn("observe(connect(), 'The microphone', (t: string) => reportMicError(t))", mic)
        self.assertIn("socket(", mic)
        self.assertNotIn("new WebSocket(", mic)

    def test_stage_b_moves_a_cto_drop(self):
        md = (ROOT / "CLAUDE.md").read_text()
        self.assertIn("node scripts/one-client.mjs --write && node scripts/one-client.mjs", md)


if __name__ == "__main__":
    unittest.main()
