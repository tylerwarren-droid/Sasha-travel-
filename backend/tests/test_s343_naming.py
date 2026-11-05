"""Sasha 343 · Sasha IS the assistant on every channel; the tools are things she does (docs/sasha/S-343-naming.md).
    cd backend && python -m unittest tests.test_s343_naming -v
"""
from __future__ import annotations

import pathlib
import re
import unittest

from products import tools as TL

ROOT = pathlib.Path(__file__).resolve().parents[1]
BRANDS = r"(?:CampusMe|RelocateMe|Espa[ñn]aMe)"   # the tools' old names (Kanoe is the company: "Sasha by Kanoe" is her)


class TheWords(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(TL.welcome_text(), "Hi, I'm Sasha. I can help you with: ✈️ Travel · 🔍 Due diligence · 🇪🇸 España · 🏠 Relocation · 🎓 Campus visits")
        self.assertEqual([r[0] for r in TL.tools_rows()], ["✈️ Travel", "🔍 Due diligence", "🇪🇸 España", "🏠 Relocation", "🎓 Campus visits"])   # taps
        self.assertEqual(TL.space_line("diligence", entering=True), "Sasha · 🔍 Due diligence — who should I investigate?")
        self.assertEqual(TL.space_line("diligence"), "Sasha · 🔍 Due diligence")
        self.assertEqual(TL.space_line(None, entering=True), "Sasha · ✈️ Travel — where would you like to go?")
        self.assertEqual((TL.BACK["title"], TL.BACK["id"]), ("← Everything I can do", "kanoe:tools"))
        self.assertLessEqual(max(len(TL.title(t)) for t in TL.TOOLS), 24)

    def test_every_name_is_the_registrys(self):
        from booking_signer import me3, switching as SW
        from products import space as SPC, web as WEB, whatsapp as PW
        for p in ("relocation", "campus", "health", "diligence"):
            self.assertEqual(SW.PRODUCT_LABEL[p], TL.name_of(p))
            self.assertTrue(SW.space_label(p).startswith("Sasha · " + TL.name_of(p)))
        self.assertEqual(set(SPC.NAME.values()), {TL.title(t) for t in TL.TOOLS})
        self.assertEqual(set(PW.PRODUCT_NAME.values()) | set(me3.NAME.values()) | set(WEB.SIGN_IN.values()),
                         {TL.name_of(p) for p in ("relocation", "campus", "health")})
        self.assertFalse(hasattr(SW, "SPACE_NAME"))                                           # the second list is gone


class TheScan(unittest.TestCase):
    """Every string Sasha can send: no "You're in", no word to type for a tool, no tool talking as someone other than Sasha."""

    BAD = [re.compile(r"You[’']re in\b(?! the)"),
           re.compile(r"(?i)\bsay\s+[“\"'‘]?\{?_?(?:RESUME_WORD|sasha|diligence|campus|relocat\w*|espa[ñn]a)"),
           re.compile(BRANDS + r"\s+(?:here|helps?|plans?|gets?|reads?|fills?|never|can't|cannot|needs?|starts?|will)\b"),
           re.compile(r"(?:read|one) by " + BRANDS),
           re.compile(r"""^\s*\w+\s*=\s*\(?\s*[f]?["']""" + BRANDS + r"\s*[🎓🇪🇸🏠:]"),
           re.compile(r"Hi, I'm (?!Sasha)")]

    def test_scan(self):
        import ast
        hits = []
        for d in ("products", "booking_signer", "agapi", "app"):
            for f in sorted((ROOT / d).rglob("*.py")):
                src = f.read_text()
                docs = set()   # docstring lines: prose about the code, never sent
                for node in ast.walk(ast.parse(src)):
                    if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body and \
                            isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant) and \
                            isinstance(node.body[0].value.value, str):
                        docs.update(range(node.body[0].lineno, node.body[0].end_lineno + 1))
                for i, line in enumerate(src.splitlines(), 1):
                    if i in docs:
                        continue
                    code = line.split("  #")[0]
                    if code.lstrip().startswith("#") or not re.search(r"[\"']", code):   # strings only: comments and docstring prose aren't sent
                        continue
                    for b in self.BAD:
                        if b.search(code):
                            hits.append(f"{f.relative_to(ROOT)}:{i}: {code.strip()[:120]}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
