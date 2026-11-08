"""Sasha 336 · the group demo fixes from SASHA 335 (docs/sasha/S-336-group-demo-fixes.md), items 2–5. Item 1 (the vault owner) is proved on
REAL Postgres in tests/test_s336_keep_owners.py.
    cd backend && python -m unittest tests.test_s336_group_fixes -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest

from agapi import s2_keep as KEEP
from booking_signer import group_book as GB, groups as G
from tests import test_s334 as W334

run = asyncio.run
OWNER = W334.OWNER
ROOT = pathlib.Path(__file__).resolve().parents[2]


def _lum(h: str) -> float:
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class ReadableOnTheDarkTheme(unittest.TestCase):
    """2 · /group and /vault: ONE palette, every pair AA, real buttons."""

    def test_every_pair_is_aa(self):
        src = (ROOT / "frontend/lib/group-theme.ts").read_text()
        body = src[src.index("export const T = {"):src.index("} as const")]
        T = dict(re.findall(r"(\w+): '(#[0-9a-fA-F]{6})'", body))
        pairs = re.findall(r"\['(\w+)', '(\w+)'\]", src[src.index("export const PAIRS"):src.index("export const TONE")])
        self.assertGreaterEqual(len(pairs), 12)
        low = [(f, b, round(ratio(T[f], T[b]), 2)) for f, b in pairs if ratio(T[f], T[b]) < 4.5]
        self.assertEqual(low, [], "below WCAG AA (4.5:1)")
        for tone in ("over", "vault", "planned", "booked", "idle"):                       # every status colour is in a checked pair
            self.assertIn((tone, "bg"), pairs)

    def test_the_pages_draw_from_it_with_real_buttons(self):
        for rel in ("frontend/app/components/group/GroupView.tsx", next((ROOT / "frontend/app/vault").glob("*/page.tsx")).relative_to(ROOT).as_posix()):
            src = (ROOT / rel).read_text()
            self.assertIn("from '@/lib/group-theme'", src, rel)
            self.assertEqual(re.findall(r"#[0-9a-fA-F]{6}\b", src), [], f"{rel}: a colour outside the palette")
            buttons = [b.split("</button>")[0] for b in src.split("<button")[1:]]   # each button up to its close (an onClick's => is not its end)
            self.assertTrue(buttons, rel)
            self.assertEqual([b for b in buttons if "style=" not in b], [], f"{rel}: a button the base reset leaves as plain text")


class BookAllSaysAShortList(unittest.TestCase):
    """3 · nothing bookable → a short list with taps, never a paragraph per worker."""

    def test_the_taps(self):
        sk = [{"name": f"W{i}", "member_id": f"m{i}", "kind": "over_limit", "why": "over"} for i in range(18)] + \
             [{"name": "V1", "member_id": "v1", "kind": "needs_vault", "why": "no passport"}, {"name": "V2", "member_id": "v2", "kind": "needs_vault", "why": "x"}]
        taps = GB.summary_taps(sk)
        # Sasha 346 · each tap: why (say, from the record) + its button (label)
        self.assertEqual([(t["say"], t["label"]) for t in taps], [("18 over the limit", "Book anyway"), ("2 are waiting for their passport", "Invite")])
        self.assertEqual((taps[0]["act"]["over_ok"], len(taps[0]["act"]["who"]), taps[1]["invite"]), (True, 18, ["v1", "v2"]))
        self.assertEqual(GB.summary_taps(sk[-1:])[0]["say"], "1 is waiting for their passport")

    def test_on_the_list(self):
        with W334.World() as w:
            hanna = next(m for m in w.members() if m["name"] == "Hanna Dummy")
            run(KEEP.delete(hanna["person_id"]))   # Sasha 351 · the vault is the PERSON's                                                      # her vault empty again
            out = run(GB.prepare(OWNER, "book", ["Rania Mithal", "Hanna Dummy"]))
            self.assertEqual(out["status"], "nothing")
            self.assertEqual(out["say"], "0 can be booked: 1 over the limit; 1 is waiting for their passport.")   # Sasha 346
            self.assertLess(len(out["say"]), 80)                                               # a line, not a paragraph
            anyway = out["taps"][0]["act"]                                                     # the tap: the SAME card and Yes, over_ok
            card = run(GB.prepare(OWNER, anyway["action"], anyway["who"], over_ok=anyway["over_ok"]))
            self.assertEqual(card["status"], "awaiting_yes")
            self.assertTrue(any("OVER the group's limit" in l for l in card["read_back"]))
            self.assertEqual(out["taps"][1]["invite"], [hanna["id"]])


class SwapAddsTheNewcomer(unittest.TestCase):
    """4 · a newcomer not on the list: the swap adds them (city, grade) and invites them to their vault — one flow."""

    def test_the_flow(self):
        with W334.World() as w:
            card = run(GB.prepare(OWNER, "book"))
            run(w.tap(card["read_back_id"]))
            ask = run(GB.prepare(OWNER, "swap", ["Bruno Example"], "Zoe Newhire"))
            self.assertEqual((ask["status"], ask["need"]), ("needs_details", ["city", "grade"]))
            self.assertFalse(any(m["name"] == "Zoe Newhire" for m in w.members()))           # nothing added without the details
            out = run(GB.prepare(OWNER, "swap", ["Bruno Example"], "Zoe Newhire", newcomer={"city": "Seville", "grade": "worker"}))
            self.assertEqual((out["status"], out["added"]), ("needs_vault", "Zoe Newhire"))
            self.assertTrue(out["say"].startswith("Zoe Newhire is on the list now."))
            self.assertEqual([l["name"] for l in out["links"]], ["Zoe Newhire"])              # her secure link (no email on the list)
            zoe = next(m for m in w.members() if m["name"] == "Zoe Newhire")
            self.assertEqual((zoe["home_city"], zoe["grade"]), ("Seville", "worker"))
            w.fill(zoe, 19)
            again = run(GB.prepare(OWNER, "swap", ["Bruno Example"], "Zoe Newhire", newcomer={"city": "Seville", "grade": "worker"}))
            self.assertEqual(again["status"], "awaiting_yes")                                  # once her vault is filled: the swap's card
            self.assertEqual(sum(1 for m in w.members() if m["name"] == "Zoe Newhire"), 1)     # never added twice


class S2TakesTheList(unittest.TestCase):
    """5 · S2's 📎 takes a group list through the SAME reader as /group, and S2 links to /group."""

    def test_the_clip_and_the_link(self):
        s2 = (ROOT / "frontend/app/s2/S2App.tsx").read_text()
        clip = s2[s2.index("async function pickedGroup"):s2.index("async function picked(")]
        self.assertIn("bookingReq('/api/booking/group/upload'", clip)                         # the one reader (groups.read_csv / xlsx / photo)
        self.assertIn('accept=".csv,.xlsx,image/*"', s2)
        self.assertIn("A group list (csv, xlsx or a photo)", s2)
        self.assertIn("<GroupView embedded />", s2)                                            # Sasha 359 · the Group tab: the one view
        self.assertNotIn("read_csv", s2)                                                       # no second reader in the page


if __name__ == "__main__":
    unittest.main()
