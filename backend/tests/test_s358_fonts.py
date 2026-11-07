"""Sasha 358 · NO BUILD DEPENDS ON THE NETWORK. Found 7 Nov: every Vercel build of the frontend failed — next/font/google couldn't reach
Google Fonts from the builder ("Can't resolve '@vercel/turbopack-next/internal/font/google/font'"), so nothing could deploy.

One source: the font files IN the repo (frontend/app/fonts, each family's OFL licence beside it), served through ONE module (fonts.ts,
next/font/local). This fails on any next/font/google, any next/font/local outside that module, a font file it names that isn't there, a
family without its licence, and any build-time fetch of an asset from the network (a stylesheet's remote @import or url(), a remote font).

    cd backend && python -m unittest tests.test_s358_fonts -v
"""
from __future__ import annotations

import pathlib
import re
import unittest

FE = pathlib.Path(__file__).resolve().parents[2] / "frontend"
FONTS = FE / "app" / "fonts"
SKIP = ("node_modules", ".next", ".vercel")


def sources(*exts):
    for f in sorted(FE.rglob("*")):
        if f.is_file() and f.suffix in exts and not any(p in f.parts for p in SKIP) and "public" not in f.relative_to(FE).parts[:1]:
            yield f


def code(f: pathlib.Path) -> str:   # comments out: a comment that names a thing is not a use of it
    s = f.read_text(encoding="utf-8", errors="ignore")
    return re.sub(r"/\*[\s\S]*?\*/|(^|[^:'\"])//[^\n]*", r"\1", s)


class NoBuildNeedsTheNetwork(unittest.TestCase):
    def test_every_font_comes_from_the_repo_through_one_module(self):
        google, local_elsewhere = [], []
        for f in sources(".ts", ".tsx", ".js", ".jsx", ".mjs"):
            s = code(f)
            if "next/font/google" in s:
                google.append(str(f.relative_to(FE)))
            if "next/font/local" in s and f != FONTS / "fonts.ts":
                local_elsewhere.append(str(f.relative_to(FE)))
        self.assertEqual(google, [], "a font fetched from Google at build time")
        self.assertEqual(local_elsewhere, [], "fonts come from app/fonts/fonts.ts only")

    def test_each_file_it_names_is_there_with_its_licence(self):
        mod = (FONTS / "fonts.ts").read_text()
        files = set(re.findall(r"['\"]\./([\w.-]+\.(?:ttf|otf|woff2?))['\"]", mod))
        self.assertTrue(files)
        for name in files:
            f = FONTS / name
            self.assertTrue(f.is_file() and f.stat().st_size > 10_000, name)
            self.assertIn(f.read_bytes()[:4], (b"\x00\x01\x00\x00", b"OTTO", b"wOFF", b"wOF2"), f"{name} is not a font file")
        for fam in ("Geist", "GeistMono", "DMSans", "DMSerifDisplay"):
            lic = FONTS / f"OFL-{fam}.txt"
            self.assertTrue(lic.is_file(), lic.name)
            self.assertIn("SIL OPEN FONT LICENSE", lic.read_text(errors="ignore").upper())

    def test_no_stylesheet_or_page_fetches_an_asset_at_build_time(self):
        hits = []
        remote = re.compile(r"@import\s+(?:url\()?\s*['\"]?https?://|url\(\s*['\"]?https?://[^)]*\.(?:woff2?|ttf|otf|css)|"
                            r"fonts\.googleapis\.com|fonts\.gstatic\.com|use\.typekit\.net", re.I)
        for f in sources(".css", ".scss", ".ts", ".tsx", ".mjs", ".js"):
            for i, line in enumerate(code(f).splitlines(), 1):
                if remote.search(line):
                    hits.append(f"{f.relative_to(FE)}:{i}: {line.strip()[:100]}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
