"""Sasha 322 · the mic always says the truth, fast (docs/sasha/S-322-mic-truth.md).

Root test: (1) one truth — the audio pipeline (permission, track, audio, socket, frames, the speech service answering), read by
lib/mic-machine.mjs; (2) no label set on a timer; (3) never "Listening" while no audio reaches her, nor the reverse. The machine's own
tests are frontend/scripts/mic-machine-322.test.mjs; here: what the backend owes it — the mic's beacons never spend the key's budget,
and a socket's close code reaches the log. Offline.

    cd backend && python -m unittest tests.test_s322 -v
"""
from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class TheBeaconsNeverSpendTheKeysBudget(unittest.TestCase):
    def test_mic_event_takes_no_token(self):
        from app.middleware import ratelimit as RL
        self.assertIn("/api/voice/mic-event", RL._SELF_CAPPED)
        src = (ROOT / "backend/app/middleware/ratelimit.py").read_text()
        self.assertIn('or path in _SELF_CAPPED:', src)                       # before the secret, the per-IP and the global buckets
        self.assertTrue("/api/voice/deepgram-key".startswith(RL._PROTECTED_PREFIXES))   # the key itself stays limited
        self.assertNotIn("/api/voice/deepgram-key", RL._SELF_CAPPED)

    def test_the_close_code_is_kept(self):
        from app.api import voice_conductor as VC
        self.assertIn("code", VC.MIC_FIELDS)
        self.assertIn("'code'", (ROOT / "frontend/lib/mic-state.ts").read_text())


class TheMachineIsTheOneTruth(unittest.TestCase):
    def test_one_reader_everywhere(self):
        vb = (ROOT / "frontend/app/components/VoiceButton.tsx").read_text()
        self.assertIn("const st = readMic(snapshot()) as MicState", vb)
        self.assertEqual(vb.count("onConnectedChangeRef.current?.("), 1)     # on/off said in ONE place: the machine
        app = (ROOT / "frontend/app/s2/S2App.tsx").read_text()
        self.assertIn("speaking={speaking} thinking={busy || working} onState={setMicState}", app)
        self.assertIn("mic: micState", app)                                  # /s2's cue (and her face's micLive) from the same state
        for ev in ("'tap'", "'listening'", "'flushed'"):                     # tap → Listening reported from real phones (no words)
            self.assertIn(ev, (ROOT / "frontend/lib/mic-log.ts").read_text())

    def test_the_root_test_is_written(self):
        doc = (ROOT / "docs/sasha/S-322-mic-truth.md").read_text()
        for part in ("## Root test", "Listening ⇔ `hears()`", "## Before (measured 1 Nov 2026)"):
            self.assertIn(part, doc)


if __name__ == "__main__":
    unittest.main()
