"""Sasha 281 · T61 — HER LIPS MOVE ON EVERY LINE SHE SAYS WITH HER FACE ON SCREEN (Tyler's real use, 21 Oct 17:58: on his return she
said she was turning off her camera and the avatar's mouth didn't move). Offline: source and words only (no avatar, no browser).

THE ONE PLACE a line reaches her lips: frontend/app/s2/S2Hello.tsx startFace() → Face.say → /api/s2-voice/pcm → repeatAudio. The
lines that went around it (all fixed by one rule, S2Hello speak(), not by the camera line): the return's voice-alone line under a face
that came LATE (phase faceLate: her live face full size, muted, lips still — Tyler's case); the voice-alone arrival drawn over her big
still; bye and every reply after a tap's face was let go (120 s, or a dropped session) with her still left full size; page lines during
the arrival's live face (no route); a failed face line reported as said. THE RULE: on her live lips, or said with her in the corner —
never a line over a big still or a frozen face; the camera words only when her live face says them, in ONE short line.
The frontend half is held by frontend/scripts/presence-rule.test.mjs (281 · …); this holds the words and the wiring.

    cd backend && python -m unittest tests.test_s281 -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest

from app.agent import voice as V

BACKEND = pathlib.Path(__file__).resolve().parents[1]
FRONT = BACKEND.parent / "frontend"
run = asyncio.run


def _front(case, rel):
    f = FRONT / rel
    if not f.exists():
        case.skipTest("frontend/ is not in this checkout (a backend-only build)")
    return re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", f.read_text())   # code only: a comment never satisfies a pin


class TheCameraLine(unittest.TestCase):
    def test_one_short_line(self):
        self.assertEqual(V.CAMERA_OFF, "I'm turning my camera off — just talk, or tap to see me.")
        self.assertEqual(len(re.findall(r"[.!?](?:\s|$)", V.CAMERA_OFF)), 1)   # one sentence (was two)
        self.assertLess(len(V.CAMERA_OFF), 60)

    def test_the_page_reads_it_from_voice_py(self):
        from app.agent import sasha as S
        self.assertEqual(run(S.first_line_rule())["camera_off"], V.CAMERA_OFF)

    def test_said_only_with_a_camera(self):
        fl = _front(self, "lib/first-line.ts")
        self.assertIn("export async function arrivalLine(name: string | null | undefined, back: boolean, live = true)", fl)
        self.assertIn("export async function newsLine(news: string, live = true)", fl)
        rule = _front(self, "lib/presence-rule.mjs")
        self.assertIn("return live && cameraOff ? (said ? `${said} ${cameraOff}` : cameraOff) : said", rule)


class OneWayToHerLips(unittest.TestCase):
    def setUp(self):
        self.hello = _front(self, "app/s2/S2Hello.tsx")
        self.speak = self.hello[self.hello.index("const speak = async"):self.hello.index("const speakRef")]

    def test_every_voice_and_face_line_is_inside_speak(self):
        self.assertEqual(self.hello.count("talker.sayNow("), 1)
        self.assertIn("return talker.sayNow(plain)", self.speak)
        self.assertEqual(len(re.findall(r"\bf\.say\(|face\.current\.say\(", self.hello)), 1)
        self.assertIn("const said = await f.say(t)", self.speak)   # Sasha 295 · MOVED: her face's line is the page's "speaking" too
        self.assertIn("if (said) return 'face'", self.speak)
        self.assertIn("if (bigNow()) await collapse()", self.speak)   # the corner before her voice: never over her big still

    def test_the_page_speaks_through_it_her_whole_visit(self):
        self.assertIn("talker.setRoute(async t => { await speakRef.current(t) })", self.hello)
        self.assertNotIn("talker.setRoute(async t => { arm(); await f.say(t) })", self.hello)   # 273's route, only while a tap held her face

    def test_a_late_face_is_never_shown_mid_line(self):
        self.assertNotIn("'faceLate')", self.hello)
        self.assertIn("if (now === 'tap' && tapForRef.current === 'voice')", self.hello)

    def test_face_let_go_while_big_goes_to_the_corner(self):
        self.assertIn("idle.current = setTimeout(() => { if (phaseRef.current === 'faceAgain') void collapse() }", self.hello)
        self.assertIn("const ended = () => { if (mine && face.current === mine) void collapse() }", self.hello)
        self.assertIn("if (phaseRef.current !== 'faceAgain') { letGo(f); return }", self.hello)

    def test_a_face_line_says_whether_it_reached_her_lips(self):
        self.assertIn("say: (text: string) => Promise<boolean>", self.hello)
        self.assertIn("if (!a || gone) return false", self.hello)

    def test_the_page_asks_for_the_camera_line_only_with_her_live_face(self):
        app = _front(self, "app/s2/S2App.tsx")
        self.assertIn("const onCamera = leaving && !!helloCtl.current?.live()", app)
        self.assertIn("const l = helloCtl.current.live() ? cameraOffLine() : ''", app)
        self.assertIn("if (loud && lineToSay && !asleepRef.current) await speak(lineToSay, '')", self.hello)

    def test_her_voice_alone_is_drawn_in_the_corner(self):
        gr = _front(self, "lib/greeting-rule.mjs")
        self.assertIn("if (phase === 'voice') return null", gr)


if __name__ == "__main__":
    unittest.main()
