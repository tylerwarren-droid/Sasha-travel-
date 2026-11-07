"""Sasha 347 · every page that acts answers — NOT_YET_CLEAN cleared and deleted (docs/sasha/S-347-every-page-answers.md).
    cd backend && python -m unittest tests.test_s347_every_page_answers -v
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"
CHECK = FE / "scripts/check-outcome-surfaces.mjs"


def code(rel: str) -> str:
    """the file as written (a regex comment-strip is the very bug 347 found: it ate the code after accept="image/*")"""
    return (FE / rel).read_text()


def sources():
    for d in ("app", "lib", "scripts"):
        for p in (FE / d).rglob("*"):
            if p.suffix in (".ts", ".tsx", ".mjs", ".js") and "node_modules" not in p.parts:
                yield p


class TheDebtIsGone(unittest.TestCase):
    def test_no_exception_list_anywhere(self):
        self.assertEqual([p.relative_to(FE).as_posix() for p in sources() if "NOT_YET_CLEAN" in p.read_text()], [])

    def test_every_acting_page_is_checked(self):
        chk = CHECK.read_text()
        self.assertIn("const surfaces = [...new Set([...OUTCOME_SURFACES, ...actingPages()])];", chk)
        self.assertIn("floatingPromises(surfaces)", chk)                                      # the type pass covers every surface too

    @unittest.skipUnless(shutil.which("node") and (FE / "node_modules/typescript").exists(), "node + the frontend's typescript")
    def test_the_prebuild_passes_with_no_exceptions(self):
        r = subprocess.run(["node", str(CHECK)], cwd=FE, capture_output=True, text=True, timeout=180)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertIn("(every page that acts — no exceptions)", r.stdout)


class TheCheckSeesTheWholeClass(unittest.TestCase):
    """the holes the old checker had, each now a fixture the checker must catch before it vouches for anything"""

    def test_parsed_not_regexed(self):
        chk = CHECK.read_text()
        self.assertIn('ts.createSourceFile("surface.tsx"', chk)                                # comments and syntax from TypeScript
        self.assertNotIn(r'src.replace(/\/\*[\s\S]*?\*\//g, "")', chk)                        # the regex that ate code after accept="image/*"
        for fixture in ('a \\"/*\\" inside a string hides no code', "a bare disabled", "a long chain that ends in .catch passes",
                        "an awaited .then is its caller's"):
            self.assertIn(fixture, chk)
        self.assertIn("the floating-promise checker is broken", chk)                          # the type pass is proven on fixtures too
        self.assertIn("given where a void callback goes", chk)                                # `send={send}` into a `=> void` prop


class OneOutcomePath(unittest.TestCase):
    def test_one_reader(self):
        lib = (FE / "lib/outcome.ts").read_text()
        for fn in ("export function heard(", "export function failed(", "export const needs", "export const stillGoing", "export const again",
                   "export function observe<T>("):
            self.assertIn(fn, lib)
        # the fallback words live in ONE place: no page keeps its own copy (that would be a second reader)
        own = [p.relative_to(FE).as_posix() for p in sources() if "didn’t answer — nothing was changed" in p.read_text()]
        self.assertEqual(own, ["lib/outcome.ts"])

    def test_the_pages_use_it(self):
        for rel in ("app/components/group/GroupView.tsx", "app/s2/S2App.tsx", "app/components/ChatBookingDo.tsx", "app/components/TripBookTest.tsx",
                    "app/booking-helper/OutlookConnect.tsx", "app/booking-helper/MailboxConnect.tsx"):
            self.assertIn("from '@/lib/outcome'", (FE / rel).read_text(), rel)

    def test_s2_presses_answer(self):
        s2 = code("app/s2/S2App.tsx")
        self.assertNotRegex(s2, r"<[^<>]*\sdisabled(=|\s|>)")                                 # nothing greyed out on S2 (the prebuild: by AST)
        self.assertIn("tell(needs('Send', ['a message — type one, or tap the mic to talk']))", s2)   # empty Send: said
        self.assertIn("tell(stillGoing(clearing ? 'Clearing the conversation' : 'Sasha’s reply', 'New chat'))", s2)
        self.assertIn("say(stillGoing(working ? 'The upload' : 'Sasha’s reply', '📎'))", s2)
        self.assertEqual(s2.count("setTwice(again("), 2)                                       # a card's second press: told, never sent twice
        self.assertIn("<Clip busy={busy} send={sendNow} say={tell}", s2)
        self.assertNotRegex(s2, r"(?m)^[^/\n]*\bvoid\s+[\w.?]+\(")                                # nothing launched and forgotten

    def test_continue_names_what_it_needs(self):
        do = code("app/components/ChatBookingDo.tsx")
        self.assertIn("setNeed(needs('Continue', missing))", do)
        for words in ("the date", "the time", "how many people", "the name it goes under", "a mobile number they can reach you on"):
            self.assertIn(f"'{words}'", do)


if __name__ == "__main__":
    unittest.main()
