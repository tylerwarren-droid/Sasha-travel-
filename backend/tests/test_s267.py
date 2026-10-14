"""Sasha 267 · T49 — THE ONE AUDIO SESSION. Tyler's iPhone (14 Oct 20:01, /s2, her voice on) reported through the mic's own log:
getUserMedia refused 4 ms after "permission: prompt" — InvalidStateError "AudioSession category is not compatible with audio capture".
Her voice's unlock() set navigator.audioSession.type = "playback" on every tap (the mic's tap included). Now ONE owner
(lib/audio-session) holds "play-and-record" before her face or voice starts and before any mic request; nothing sets anything else.

    cd backend && python -m unittest tests.test_s267 -v
"""
from __future__ import annotations

import json
import pathlib
import re
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import voice_conductor as VC

FRONT = pathlib.Path(__file__).resolve().parents[2] / "frontend"


def _src(case, rel):
    f = FRONT / rel
    if not f.exists():
        case.skipTest("frontend/ is not in this checkout (a backend-only build)")
    return re.sub(r"//[^\n]*", "", f.read_text())


class OneAudioSession(unittest.TestCase):
    def test_gate_only_the_owner_touches_the_session_and_never_to_playback(self):
        if not FRONT.exists():
            self.skipTest("frontend/ is not in this checkout (a backend-only build)")
        users = [p.relative_to(FRONT).as_posix() for d in ("app", "lib") for p in (FRONT / d).rglob("*.ts*")
                 if re.search(r"audioSession\?*\s*[:?]|\.audioSession\b|\baudioSession\s*\?", re.sub(r"//[^\n]*|/\*[\s\S]*?\*/", "", p.read_text(errors="ignore")))]
        self.assertEqual(users, ["lib/audio-session.ts"])                              # one owner
        owner = _src(self, "lib/audio-session.ts")
        self.assertIn("export const PLAY_AND_RECORD = 'play-and-record'", owner)
        self.assertNotIn("'playback'", owner)

    def test_gate_held_before_any_mic_request_her_face_and_her_voice(self):
        mic = _src(self, "app/components/VoiceButton.tsx")
        body = mic[mic.index("const connect = useCallback(async () => {"):]
        self.assertLess(body.index("holdPlayAndRecord('the mic')"), body.index("await "))   # in the tap, before anything awaits
        self.assertLess(body.index("holdPlayAndRecord('the mic')"), body.index("getUserMedia("))
        self.assertIn("if (err.name === 'InvalidStateError') reportMicError(AUDIO_MODE)", mic)   # still refused: said, never "on"
        app = _src(self, "app/s2/S2App.tsx")
        self.assertIn("holdPlayAndRecord('her voice')", app)
        self.assertIn("holdPlayAndRecord('the page')", app)
        hello = _src(self, "app/s2/S2Hello.tsx")
        face = hello[hello.index("async function startFace"):hello.index("return {", hello.index("async function startFace"))]
        self.assertLess(face.index("holdPlayAndRecord('her face')"), face.index("new LiveAvatarSession"))
        self.assertGreater(face.index("holdPlayAndRecord('her face connected')"), face.index("await ready"))   # re-asserted after it connects

    def test_the_first_transcript_is_reported_without_words(self):
        mic = _src(self, "app/components/VoiceButton.tsx")
        self.assertIn("micLog('first_transcript', { ms:", mic)
        self.assertIn("'first_transcript'", _src(self, "lib/mic-log.ts"))


class TheKeepNeverAsksForWhatItHolds(unittest.TestCase):
    """Row 944 (Tyler, 19:01): his passport WAS saved, yet the add form opened with Passport preselected and Expires showing today."""

    def test_gate_closed_never_preselects_a_held_type_never_today(self):
        k = _src(self, "app/keep/KeepScreen.tsx")
        self.assertIn("const [open, setOpen] = useState(false)", k)                        # starts closed
        self.assertIn("＋ Add something", k)
        self.assertIn("Object.keys(types).find(k => !have.includes(k))", k)                # never a type he already has
        self.assertNotIn("useState('passport')", k)
        self.assertNotIn("'date' : 'text'", k)                                              # no date input (an iPhone shows today)
        self.assertIn("placeholder={DATE_FIELDS.has(f) ? 'YYYY-MM-DD' : undefined}", k)
        self.assertIn("yes: 'Saved, ready to use after your yes'", k)
        self.assertIn("{SAVED[it.tier]}", k)


class HerFrameNeverSwallowsATap(unittest.TestCase):
    def test_found_by_the_keep_proof(self):
        hello = _src(self, "app/s2/S2Hello.tsx")
        self.assertIn("pointerEvents: phase === 'faceAgain' ? 'auto' : 'none'", hello)   # her full-size frame: taps pass to the page
        self.assertEqual(hello.count("onClick={tapToHear} style={{ pointerEvents: 'auto'"), 2)   # except her own tap button
        self.assertIn("started={arrivalStarted(msgs) || tab !== 'sasha'}", _src(self, "app/s2/S2App.tsx"))   # another tab: the circle


class TheLogCarriesTheSession(unittest.TestCase):
    def test_the_session_state_and_who_set_it_are_kept(self):
        app = FastAPI()
        app.include_router(VC.router, prefix="/api")
        with self.assertLogs("sasha.mic", "WARNING") as logs:
            r = TestClient(app).post("/api/voice/mic-event", content=json.dumps({"ev": "audio_session", "state": "playback → play-and-record",
                                                                                "why": "the mic", "ua": "iPhone"}))
        self.assertEqual(r.status_code, 200)
        self.assertIn('"state": "playback → play-and-record"', "\n".join(logs.output))
        self.assertIn('"why": "the mic"', "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
