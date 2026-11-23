"""Sasha 396 · D0 · ONE ENGINE, THREE DOORS: /next = S2's desktop layout (EU 288 §5.2; KANOE "three doors, one product"). Root test: row 2080.

Measured: /next mounted the old SashaChat in agent mode → /api/sasha-agent → surface "s1" (its own turn route, memory, cards and taps);
draws() counted EVERY card kind as drawn on WhatsApp and on s1 ("it's on your screen" with nothing drawn); and S2's history was its page
session only, so desktop and phone never shared one conversation.

THE CLASS: every door × every card kind → "drawn" only where that door's own renderer draws it; /next is <S2App layout="desktop"/>; no page
runs SashaChat's agent mode; /api/sasha-agent (the turn) and its /memory are gone; one conversation per account (test_s249d).

    cd backend && python -m unittest tests.test_s396_three_doors -v
"""
from __future__ import annotations

import pathlib
import re
import unittest

from app.agent import sasha as AG
from booking_signer import wa_agent as WA

FE = pathlib.Path(__file__).resolve().parents[2] / "frontend"


class EveryDoorEveryKind(unittest.TestCase):
    def test_drawn_only_where_the_doors_own_renderer_draws_it(self):
        kinds = set(AG.RENDER.values()) | set(AG.S2_DRAWS) | set(WA.KIND_MAP) | set(getattr(AG, "KINDS", set())) | {"focus", "nonsense"}
        for k in sorted(kinds):
            # Sasha 402 · a kind outside a door's renderer is never drawn there; inside it, only an event its renderer draws (its payload:
            # tests/test_s402_cards_drawn runs the real renderers on the stream's own events)
            if k not in AG.S2_DRAWS:
                self.assertFalse(AG.draws("s2", {"kind": k}), ("s2", k))                       # /s2 and /next (S2's page)
            if k not in WA.KIND_MAP:
                self.assertFalse(AG.draws("s2", {"kind": k}, wa=True), ("wa", k))              # WhatsApp: wa_agent's renderers
            for door in ("s1", "next", None):                                                   # no page renders these: nothing drawn
                self.assertFalse(AG.draws(door, {"kind": k}), (door, k))

    def test_a_card_not_drawn_is_told_to_her_as_not_shown(self):
        src = (pathlib.Path(AG.__file__)).read_text()
        self.assertIn('mr["on_screen"] = "nothing from this result was shown on their screen', src)


class OnePage(unittest.TestCase):
    def test_next_is_s2s_desktop_layout(self):
        nxt = (FE / "app/next/page.tsx").read_text()
        self.assertIn('<S2App layout="desktop" />', nxt)
        self.assertNotRegex(nxt, r"import .*SashaChat")
        s2 = (FE / "app/s2/S2App.tsx").read_text()
        self.assertIn("layout = 'phone'", s2)
        self.assertIn("data-s2-trip-pane", s2)                                                    # the permanent trip pane
        self.assertIn("`/sign-in?next=${home}`", s2)                                              # back to the page they were on
        self.assertNotIn("window.location.href = '/sign-in?next=/s2'; return }\n      const rd", s2)

    def test_no_page_runs_the_old_agent_path(self):
        self.assertFalse((FE / "app/api/sasha-agent/route.ts").exists())
        self.assertFalse((FE / "app/api/sasha-agent/memory").exists())
        for p in (FE / "app").rglob("*.tsx"):
            if "node_modules" in p.parts:
                continue
            for m in re.finditer(r"<SashaChat\b[^>]*>", p.read_text(), re.S):
                self.assertNotRegex(m.group(0), r"\bagent\b(?!\w)", str(p))                       # SashaChat (the CTO's) only in conductor mode
        for kept in ("timing", "events", "activity", "keep"):                                     # S2's and the Keep's: kept
            self.assertTrue((FE / "app/api/sasha-agent" / kept / "route.ts").exists(), kept)


if __name__ == "__main__":
    unittest.main()
