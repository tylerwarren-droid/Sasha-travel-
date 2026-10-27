"""Sasha 268 · T50 — HER ARRIVAL, SHE TRIES FIRST, ONE PAUSE (rows 951–955, Tyler 14 Oct 20:46–21:00). Offline; each fails on 267's code.

  (1–6) ONE FRAMING: the first image on load is her half-body still (/sasha-half.webp), drawn with the live video's own crop, scale and
        position, so the live face takes over without a jump; the face close-up is gone. She stays full size through greetings and
        small talk; his first real REQUEST makes her say voice.CAMERA_OFF (by code) and go to the corner circle; a tap brings her back.
  (7)   SHE TRIES FIRST: "Can you find a dog walker and schedule one?" → "I can't do that yet, but I've noted it". Her first answer to
        any request for a service is voice.TRY_FIRST; "I can't" only after a tool actually tried (note_not_yet refuses otherwise).
  (8)   ONE PAUSE: "Pause Sasha" / "Wake" in words; it stops listening, stops her voice mid-sentence, lets go of her live face, and says
        plainly that she's paused — on /s2 and /next.

    cd backend && python -m unittest tests.test_s268 -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from unittest import mock

from agapi import s2_home as HOME, v0 as API
from app.agent import s2 as S2, sasha as S, voice as V

FRONT = pathlib.Path(__file__).resolve().parents[2] / "frontend"
ACCT = "00000000-0000-4000-8000-000000000268"
GATE = ["Can you find a dog walker and schedule one?", "I want a tattoo this week", "I need a dentist tomorrow morning",
        "Get me a plumber, my sink is leaking", "Send flowers to my mum on Friday"]


def run(c):
    return asyncio.run(c)


def _src(case, rel):
    f = FRONT / rel
    if not f.exists():
        case.skipTest("frontend/ is not in this checkout (a backend-only build)")
    return re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", f.read_text())   # the code, never its comments


class SheTriesFirst(unittest.TestCase):
    def test_gate_every_service_request_starts_with_the_try(self):
        for m in GATE:
            self.assertEqual(V.first_line(m), V.TRY_FIRST, m)
        self.assertEqual(V.TRY_FIRST, "Let me see what I can do.")
        self.assertEqual(V.first_line("Book a table for two tonight in Madrid"), V.FIRST_LINE)   # a table: 265's line, unchanged
        for m in ("Hi", "How are you?", "Can you hear me?", "Thanks!"):
            self.assertIsNone(V.first_line(m), m)                                           # small talk: no line, she stays full size

    def test_gate_nothing_tells_her_to_refuse_first(self):
        for text in (S2.S2_WHO, V.RULES, S2.S2_SEARCH, str(HOME.tools()[1]["description"])):
            self.assertNotIn("I can't do that yet", text)
            self.assertNotIn("noted it", text)
        self.assertIn(f'her first answer — "{V.TRY_FIRST}" or a short acknowledgement — is said for her by code', V.RULES.replace("\n  ", " "))   # Sasha 273 · moved: once per request, by code
        self.assertIn("\"I can't\" is never her first answer", S2.S2_WHO)
        self.assertIn("a dog walker", S2.S2_SEARCH)                                        # /s2's search: any business
        self.assertIn('{**t, "description": S2.S2_SEARCH, "input_schema": S2.search_schema(t["input_schema"])} if t["name"] == "search_venues"',
                      pathlib.Path(S.__file__).read_text())   # 276: + venue.discover's dates / when_words / near

    def test_gate_cant_only_after_a_tool_tried(self):
        HOME._MEM.clear()
        with mock.patch("booking_signer.plan_store._run", lambda: None):
            first = run(HOME.note_not_yet(API.Ctx(account=ACCT, surface="s2"), {"asked": "a dog walker"}))
            self.assertFalse(first["noted"])                                                # no try this turn: refused, nothing noted
            self.assertIn("Let me see what I can do", first["how"])
            self.assertEqual(list(HOME._MEM), [])
            tried = API.Ctx(account=ACCT, surface="s2", calls=[{"tool": "search_venues", "ok": False}])
            after = run(HOME.note_not_yet(tried, {"asked": "a dog walker"}))
        self.assertTrue(after["noted"])
        self.assertEqual(after["tried"], ["search_venues"])

    def test_the_page_says_the_try_from_the_one_rule(self):
        got = run(S.first_line_rule())
        self.assertEqual((got["try"], got["trip"], got["camera_off"]), (V.TRY_FIRST, V._TRIP.pattern, V.CAMERA_OFF))
        fl = _src(self, "lib/first-line.ts")
        self.assertIn("rule.trip.test(text || '') ? rule.line : rule.tryLine", fl)
        self.assertNotIn("Let me see what I can do", fl)                                    # the words live in voice.py only


class OneFraming(unittest.TestCase):
    def test_gate_one_half_body_still_in_the_live_framing(self):
        hello = _src(self, "app/s2/S2Hello.tsx")
        self.assertIn("export const FACE_STILL = '/sasha-half.webp'", hello)
        self.assertTrue((FRONT / "public" / "sasha-half.webp").exists())
        for gone in ("sasha-face.jpg", "s2_face", "still(", "keptFace"):
            self.assertNotIn(gone, hello)                                                   # the close-up and kept snapshots: gone
        self.assertEqual(hello.count("background: `${FRAMING} url(${img})`"), 1)           # Sasha 271 · MOVED: ONE element, ONE still (full and corner)
        self.assertIn("objectPosition: 'center 18%'", hello)                                 # the live canvas: the same framing
        self.assertIn("export const FRAMING = 'center 18% / cover no-repeat'", hello)
        self.assertIn("transition: big ? 'none' : 'left .45s ease, top .45s ease", hello)   # she appears full size at once: no grow-in
        # Sasha 271 · MOVED: from first paint — presence()'s own clause (lib/presence-rule.mjs)
        self.assertIn("(s.signedIn === true || (s.signedIn === null && !!s.soon))", _src(self, "lib/presence-rule.mjs"))
        self.assertIn("presence({ phase, tapFor, started, signedIn, soon, asleep, dormant, reduced: reducedMotion(), micLive, arrive })", hello)   # Sasha 273 · moved: + the mic's truth, rule 4


class LeavesOnHisFirstRequest(unittest.TestCase):
    def test_gate_said_by_code_then_the_circle_and_back_on_a_tap(self):
        hello = _src(self, "app/s2/S2Hello.tsx")
        self.assertIn("export type HelloCtl = { big: () => boolean; bye: (line: string, speak: boolean) => Promise<void>; again: (news?: string | null) => boolean; live: () => boolean\n  waiting: () => boolean", hello)   # Sasha 296 · MOVED: + returned, settleLine · Sasha 295 · MOVED: + waiting (the opening)   # Sasha 273 · moved: + again (rule 4) · Sasha 281 MOVED: + live
        # Sasha 271 · MOVED (row 1008): her arrival goes to the corner as its own lines end; bye is for a tap that brought her back
        self.assertIn("if (phaseRef.current !== 'faceAgain' || byeing.current) return", hello)
        self.assertIn("await collapse()\n  }", hello)
        app = _src(self, "app/s2/S2App.tsx")
        self.assertIn("const leaving = isRequest && !!helloCtl.current?.big()", app)
        self.assertIn("const said1 = onCamera ? (helloCtl.current?.settleLine() || null)", app)   # Sasha 296 · MOVED: settle's line (camera words once a session) · Sasha 281 · MOVED: the camera line only on her live lips
        self.assertIn("ev.type === 'tool_start' && helloCtl.current?.big()", app)            # a request only the server saw
        self.assertIn("started={tab !== 'sasha'} ctlRef={helloCtl}", app)                       # small talk never ends her arrival
        self.assertNotIn("arrivalStarted", app)
        self.assertIn('"camera_off": _V.CAMERA_OFF', pathlib.Path(S.__file__).read_text())


class OnePause(unittest.TestCase):
    def test_gate_words_release_and_said_plainly(self):
        rule = _src(self, "lib/sleep-rule.mjs")
        self.assertIn("export const buttonLabel = (asleep) => (asleep ? 'Wake' : 'Pause Sasha')", rule)
        self.assertIn("stopAudio: true, micOff: true, dim: true, releaseFace: true", rule)
        btn = _src(self, "app/components/SleepButton.tsx")
        self.assertIn("showLabel = true", btn)
        self.assertIn("{showLabel ? <span>{label}</span> : null}", btn)
        self.assertIn("data-sasha-paused", _src(self, "app/s2/S2App.tsx"))
        self.assertIn("if (busy || asleep || !queued.current.length) return", _src(self, "app/s2/S2App.tsx"))   # a queued message never undoes it
        nxt = _src(self, "app/next/page.tsx")
        self.assertIn("if (r.effects.releaseFace) handleEndSession()", nxt)


if __name__ == "__main__":
    unittest.main()
