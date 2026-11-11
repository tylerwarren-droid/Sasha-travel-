"""Sasha 368 · ONE ROUTE MAP decides what every URL on project.kanoe.ai serves; "/" is the Kanoe portal (its tabs + the collateral),
never a Sasha page.

Found (Tyler, 11 Nov 06:44): "project.kanoe.ai now goes directly to the Sasha video. It used to be the website with many tabs, including our
collateral. This happened one time before as well." — "/" was moved twice by a page edit (Sasha 123: the six-tab site; Sasha 142: the
Sasha Vietnam page), with nothing to say who owns it. Tyler chose (11 Nov): the original portal (Teaser · Investor Deck · Onboarding · TDM ·
Data Strategy · Demo), restored from git, at "/" — /archive only a redirect to it; every Sasha link inside it opens TODAY's Sasha (/s2).

    cd backend && python -m unittest tests.test_s368_one_route_map -v
"""
from __future__ import annotations

import json
import pathlib
import re
import unittest

FE = pathlib.Path(__file__).resolve().parents[2] / "frontend"
APP = FE / "app"


def _route_of(page: pathlib.Path) -> str:
    """app/(group)/x/page.tsx → "/x" (a route group's name is not in the URL)."""
    parts = [p for p in page.relative_to(APP).parent.parts if not (p.startswith("(") and p.endswith(")"))]
    return "/" + "/".join(parts)


class OneOwnerOfTheRoot(unittest.TestCase):
    def test_the_route_map_names_the_owner_and_the_root_is_the_portal(self):
        rm = (FE / "lib" / "routes.ts").read_text()
        self.assertIn("'/': 'the Kanoe portal", rm)                                             # ONE map, the root's owner named
        self.assertIn("export const SASHA = '/s2'", rm)
        home = (APP / "page.tsx").read_text()
        self.assertRegex(home, r"<PortalShell>\s*<Teaser />\s*</PortalShell>")                  # the portal's Teaser, as it was
        self.assertIn("title: 'Kanoe.ai — Investor Portal'", home)
        self.assertNotRegex(home, r"import [^\n]*(vietnam|s2|S2App|SashaChat|Sasha)|redirect\(")   # no Sasha page imported, no redirect

    def test_nothing_else_claims_the_root(self):
        roots = [str(p.relative_to(FE)) for p in APP.rglob("page.tsx") if _route_of(p) == "/"]
        self.assertEqual(roots, ["app/page.tsx"])                                               # no second home page (route groups too)
        cfg = (FE / "next.config.ts").read_text()
        for m in re.finditer(r"source:\s*'([^']*)'[^}]*destination:\s*'([^']*)'", cfg):
            self.assertNotEqual(m.group(1), "/", "a redirect or rewrite claims /")
        self.assertNotRegex(cfg, r"rewrites\s*\(")
        mw = (FE / "middleware.ts").read_text()
        self.assertNotRegex(mw, r"NextResponse\.(redirect|rewrite)")                            # the middleware serves, never moves "/"
        for vj in (FE / "vercel.json", FE.parent / "vercel.json"):
            if vj.exists():
                v = json.loads(vj.read_text())
                for k in ("redirects", "rewrites", "routes"):
                    self.assertFalse([r for r in v.get(k) or [] if r.get("source", r.get("src")) in ("/", "^/$")], (vj, k))

    def test_the_archive_is_only_a_redirect_to_the_root(self):
        self.assertFalse((APP / "archive").exists())
        self.assertIn("{ source: '/archive', destination: '/', permanent: false }", (FE / "next.config.ts").read_text())
        self.assertFalse((APP / "components" / "portal" / "ArchiveBanner.tsx").exists())       # the portal as it was: no archive banner
        self.assertIn("{ href: '/', label: 'Teaser' }", (APP / "components" / "portal" / "PortalNav.tsx").read_text())

    def test_every_sasha_link_in_the_portal_opens_todays_sasha(self):
        hits = []
        for f in sorted((APP / "components" / "portal").glob("*.tsx")) + [APP / p / "page.tsx" for p in ("deck", "demo", "tdm", "data-strategy", "walkthrough")]:
            s = f.read_text()
            for old in ("/vietnam", "/phuquoc", "/next", "/vietnam2", "demo.kanoe.ai", "/voice"):
                if re.search(r"['\"`]" + re.escape(old) + r"(?:['\"`/?#])", s) or (old == "demo.kanoe.ai" and old in s):
                    hits.append(f"{f.name}: {old}")
        self.assertEqual(hits, [])
        demo = (APP / "components" / "portal" / "DemoPortal.tsx").read_text()
        self.assertIn("src: SASHA", demo)                                                       # the Demo tab: the route map's Sasha


if __name__ == "__main__":
    unittest.main()
