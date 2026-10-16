"""Sasha 274 · S2 beta fixes from Tyler's iPhone (16 Oct 14:48–14:53, mailbox rows 1061/1062), after Sasha 273 went live.
    1  never a greeting under her own unanswered booking question (rule 4: mid_booking); an open page picks up a new release at a
       safe moment (version check on a return / a turn's end, the conversation carried across, never mid-sentence or mid-booking)
    2  a place card is its content: no name → no card (reported); a failed photo hidden; its own layer (WebKit paint)
    3  /s2's mic icon is drawn from `hearing`, as its label and its ring — never a crossed-out mic beside "Voice on"
    4  New chat / a chip start listening inside the tap when the mic is already granted; refused → the mic pulses ("Tap to talk")
Frontend source pins (the node suite holds rule 4 itself: scripts/presence-rule.test.mjs).
    cd backend && python -m unittest tests.test_s274 -v
"""
from __future__ import annotations

import pathlib
import unittest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
FRONT = BACKEND.parent / "frontend"


def _front(case, rel):
    f = FRONT / rel
    if not f.exists():
        case.skipTest("frontend/ is not in this checkout (a backend-only build)")
    return f.read_text(encoding="utf-8")


class Greeting(unittest.TestCase):
    def test_rule4_mid_booking(self):
        rule = _front(self, "lib/presence-rule.mjs")
        self.assertIn("if (s.midFlow) return { greet: false, lead: null, why: 'mid_booking' }", rule)
        self.assertIn("export function midFlow(msgs)", _front(self, "lib/greeting-rule.mjs"))
        app = _front(self, "app/s2/S2App.tsx")
        self.assertIn("midFlow: mid ?? midFlow(msgsRef.current)", app)
        self.assertIn("const r = rule4(mid)", app)
        import re
        self.assertEqual(re.findall(r"['`]Hey[^'`\n]*what can I help you with", app), [])   # the greeting's words: the backend's, never the page's


class NewRelease(unittest.TestCase):
    def test_version_check_and_safe_reload(self):
        self.assertIn("NEXT_PUBLIC_BUILD: process.env.VERCEL_GIT_COMMIT_SHA || 'dev'", _front(self, "next.config.ts"))
        self.assertIn("build: process.env.VERCEL_GIT_COMMIT_SHA || 'dev'", _front(self, "app/api/version/route.ts"))
        app = _front(self, "app/s2/S2App.tsx")
        self.assertIn("if (!stale.current || busyRef.current || speakingRef.current || queued.current.length || midFlow(msgsRef.current) || helloCtl.current?.big()) return", app)
        self.assertIn("putCarry(msgsRef.current, histRef.current)", app)
        self.assertIn("const carried = takeCarry()", app)
        self.assertIn("c.k !== 'pay'", app)                                  # a payment card never crosses
        self.assertNotIn("setInterval(() => checkRelease", app)              # never a timer: a return, a turn's end, her silence


class Cards(unittest.TestCase):
    def test_never_empty(self):
        pc = _front(self, "app/components/cards/PlaceCard.tsx")
        self.assertIn("if (!named) return null", pc)
        self.assertIn("report('card_empty'", pc)
        self.assertIn("onError={() => { setPhotoOk(false); report('card_photo_failed'", pc)
        self.assertIn("isolation: 'isolate', transform: 'translateZ(0)'", pc)


class MicAgrees(unittest.TestCase):
    def test_icon_from_hearing(self):
        vb = _front(self, "app/components/VoiceButton.tsx")
        self.assertIn(": hearing && strict ? <Mic className=\"w-4 h-4 text-white\" />", vb)
        self.assertIn(": hearing && strict ? 'bg-emerald-600'", vb)
        self.assertIn(": isConnected && !strict ? <Loader2", vb)

    def test_tap_starts_listening(self):
        app = _front(self, "app/s2/S2App.tsx")
        self.assertIn("<button onClick={() => { listenOnTap(); void newChat() }}", app)
        self.assertIn("speaker.unlock(); listenOnTap(); send(c)", app)
        self.assertIn("if (voiceCtl.current?.granted()) { micUsed.current = true; voiceCtl.current.tap() }", app)
        self.assertIn("data-cue={!vo.live && !asleep && !!micNote ? '1' : '0'}", app)
        self.assertIn("granted: () => permRef.current === 'granted'", _front(self, "app/components/VoiceButton.tsx"))

    def test_one_account_control(self):
        # rows 1063/1064: tapping "Signed in as …" → Sign out / Switch account; a guest → "Guest — Sign in to book for real"; a guest's
        # booking offers sign-in in the conversation; signing in keeps the conversation (the guest's own, read once)
        sil = _front(self, "app/components/SignedInLine.tsx")
        self.assertIn("export function AccountControl(", sil)
        self.assertIn(">Guest — Sign in to book for real</button>", sil)
        self.assertIn(">Sign out</button>", sil)
        self.assertIn("Switch account</button>", sil)
        self.assertIn("await ensureGuest()   // back to a private guest", sil)
        self.assertIn("if (carry) sessionStorage.setItem(SIGN_IN_CARRY, carry)", sil)          # the one hand-off survives the change of person
        app = _front(self, "app/s2/S2App.tsx")
        self.assertIn("<AccountControl style={{ padding: '0 16px 8px', textAlign: 'right' }} onSignIn={() => putCarry(msgsRef.current, histRef.current, SIGN_IN_CARRY)} />", app)
        self.assertNotIn("<WhoLine", app)
        self.assertIn("if (ACTING === 'guest' && ['read_back', 'prepared', 'wa_open', 'handover', 'pay'].includes(c.k)) add0({ k: 'sign_in' })", app)
        self.assertIn("const signIn = sessionStorage.getItem(SIGN_IN_CARRY)", app)
        self.assertIn("onClick={() => { setOpen(false); if (acting === 'user') void signOut('sign_in'); else signIn(false) }}", sil)   # switching never carries

    def test_in_the_gate(self):
        self.assertIn('["tests.test_s274"]', (BACKEND / "scripts" / "one_truth_suite.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
