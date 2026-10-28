"""Sasha 266 · T48 — row 943 (Tyler, 14 Oct 18:59). Offline; each fails on 265's code.

  (a) THE MIC IS "ON" ONLY WHEN IT HEARS — his iPhone minted 16 keys (16:55–16:59Z), no socket reached Deepgram, the browser never
      asked for the microphone, and the page looked "on" (/s2's mic is drawn quiet: every failure lived only in a tooltip). Now the
      "on" look, "Listening" and onConnectedChange(true) come only from a live, unmuted track delivering frames; a blocked site is said on
      the page with the steps for that browser, before any key is minted; the mic reports its own state changes to the server.
  (b) ARRIVAL — she stays full size through her greeting AND his first reply; his first turn sends her to the circle, never a timer.

    cd backend && python -m unittest tests.test_s266 -v
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import re
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import voice_conductor as VC

BACKEND = pathlib.Path(__file__).resolve().parents[1]


def _tsx(case, rel):
    f = BACKEND.parent / "frontend" / rel
    if not f.exists():
        case.skipTest("frontend/ is not in this checkout (a backend-only build)")
    return re.sub(r"//[^\n]*", "", f.read_text())   # the code, never its comments


class OnOnlyWhenItHears(unittest.TestCase):
    def test_gate_the_on_look_and_the_live_signal_come_only_from_frames(self):
        src = _tsx(self, "app/components/VoiceButton.tsx")
        opened = src[src.index("ws.onopen = async () => {"):src.index("keepAliveIntervalRef.current = setInterval")]
        self.assertNotIn("onConnectedChangeRef.current?.(true)", opened)                 # an open socket is not "on"
        self.assertIn("if (!deafRef.current) reportMicError(null)", opened)              # nor does it clear "can't hear you"
        frame = src[src.index("node.port.onmessage = (e) => {"):src.index("if (deafRef.current) {")]
        self.assertIn("tr.readyState === 'live' && !tr.muted", frame)
        self.assertIn("onConnectedChangeRef.current?.(true)", frame)                    # ON = a live track's first frame
        self.assertEqual(src.count("onConnectedChangeRef.current?.(true)"), 1)
        self.assertIn(": hearing     ? 'bg-red-500 animate-pulse'", src)
        self.assertIn("hearing ? (isSpeaking ? 'Speaking'", src)
        self.assertNotIn("isConnected ? (isSpeaking ? 'Speaking'", src)

    def test_gate_a_blocked_site_is_said_with_its_steps_before_any_key(self):
        src = _tsx(self, "app/components/VoiceButton.tsx")
        body = src[src.index("const connect = useCallback(async () => {"):]
        self.assertLess(body.index("await micPermission()"), body.index("getDeepgramKey()"))   # no key minted for a blocked site
        self.assertIn("if (perm === 'denied') {", body)
        self.assertIn("reportMicError(BLOCKED)", body)
        app = _tsx(self, "app/s2/S2App.tsx")
        self.assertIn("onMicError={setMicNote}", app)                                     # /s2's quiet mic: said on the page
        self.assertIn("data-mic-stuck", app)
        self.assertIn("micNote === BLOCKED ? <div style={{ color: C.dim, marginTop: 4 }}>{stepsFor()}</div>", app)
        steps = _tsx(self, "lib/mic-state.ts")
        self.assertIn("Website Settings › Microphone › Allow", steps)                     # his browser: iPhone Safari

    def test_the_mic_reports_itself_without_words(self):
        app = FastAPI()
        app.include_router(VC.router, prefix="/api")
        c = TestClient(app)
        with self.assertLogs("sasha.mic", "WARNING") as logs:
            r = c.post("/api/voice/mic-event", content=json.dumps({"ev": "blocked", "name": "NotAllowedError", "perm": "denied",
                                                                  "text": "book a table for two", "ua": "iPhone"}))
        self.assertEqual(r.status_code, 200)
        line = "\n".join(logs.output)
        self.assertIn('"ev": "blocked"', line)
        self.assertIn('"perm": "denied"', line)
        self.assertNotIn("book a table", line)                                             # never a transcript

    def test_the_page_reports_the_states_that_say_why(self):
        self.assertIn("'hearing'", _tsx(self, "lib/mic-log.ts").replace('"', "'"))


class SheStaysThroughTheFirstExchange(unittest.TestCase):
    def test_gate_no_timer_sends_her_away(self):
        hello = _tsx(self, "app/s2/S2Hello.tsx")
        self.assertNotIn("setTimeout(handoff", hello)                                     # 265: ~1–2.5 s after her hello
        # Sasha 271 · MOVED (row 1008, Tyler): her arrival no longer stays full size through the first exchange — "Hey there" and the
        # camera-off line, then the corner AT ONCE (when said, never a timer); the live-face idle timer is only for a tap that
        # brought her back, and it lets her live face go (her still stays) — it never moves her
        voice = hello[hello.index("const speakVoice = async () => {"):hello.index("const capSay")]   # Sasha 303 · MOVED: lateFace is gone
        self.assertIn("await toCorner()", voice)
        self.assertNotIn("idleLive", hello)
        # Sasha 281 · MOVED (Tyler 21 Oct 17:58): her live face let go while full size takes her to the corner with it — her still
        # left full size had the next line said over it (a frozen face). Sasha 303 · MOVED: the quiet is the ONE gate's (server, 60 s);
        # its session's end is `ended` → collapse(), the same way — the page's FACE_IDLE_S timer is gone (tests.test_s303)
        self.assertNotIn("FACE_IDLE_S", hello)
        self.assertIn("const ended = () => { if (mine && face.current === mine) void collapse() }", hello)
        self.assertIn("if (!openingEnds(phaseRef.current, started)) return", hello)      # his first reply: then the circle
        self.assertIn("started={tab !== 'sasha'} ctlRef={helloCtl}", _tsx(self, "app/s2/S2App.tsx"))   # 268: small talk keeps her; his first request (bye) ends it


if __name__ == "__main__":
    unittest.main()
