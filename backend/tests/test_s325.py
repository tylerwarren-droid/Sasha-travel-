"""Sasha 325 · no display mark is ever spoken (Bug A: "star 1 person" — the trip line's "·" read aloud) and one booking read per refresh
(Bug B: 2 Nov 14:52–14:54 UTC, ~280 AgAPI calls in two minutes, all 429). docs/sasha/S-325-voice-and-reads.md. Offline.

    cd backend && python -m unittest tests.test_s325 -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import re
import unittest

from app.agent import spoken as SP

BACKEND = pathlib.Path(__file__).resolve().parents[1]
FRONT = BACKEND.parent / "frontend"

SAMPLE = {"venue": "Casa Lucio · Madrid", "when": "Mon 2 Nov · 15:30", "ref": "X7K2PQ", "day": "Mon 2 Nov", "hhmm": "15:30", "n": 2,
          "party": 2, "date": "2026-11-20", "words": "*yes* · 2 people", "text": "**1 person** · 15:30", "message": "- refused", "what": "website",
          "tool": "book_venue", "masked": "+34 ··· 123", "figures": {"total": "€42"}, "r": {"venue": "Botín · Madrid", "when": "15:30"},
          "channel": {"kind": "email"}, "result": {"say": "✅ Booked · ref X7K2PQ"}}


def _strings(obj, out, depth=0):
    if depth > 3:
        return
    if isinstance(obj, str):
        if len(obj) > 3 and " " in obj:
            out.append(obj)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for x in obj:
            _strings(x, out, depth + 1)
    elif isinstance(obj, dict):
        for x in obj.values():
            _strings(x, out, depth + 1)


class NoMarkIsEverSpoken(unittest.TestCase):
    def test_the_train_test_lines(self):
        for line in ("Madrid → Barcelona · Mon 2 Nov · 13:00 · 1 passenger", "*1 person* at **15:30**", "• Casa Lucio\n• Botín",
                     "Book [here](https://x.y/z) now", "## Your trip\n1. Hanoi · 2 nights", "`ref` X7K2PQ — my_plans", "✅ Booked · ref X7K2PQ"):
            out = SP.speakable(line)
            self.assertIsNone(SP.NEVER_SPOKEN.search(out), (line, out))
        self.assertNotIn("star", SP.speakable("Mon 2 Nov · 1 person").lower())
        self.assertIn("one person", SP.speakable("· 1 person").lower())                  # the words are kept

    def test_every_template_she_can_speak(self):
        from app.agent import voice as V, sasha, s2
        lines = []
        for mod in (V, sasha, s2):
            for name, val in vars(mod).items():
                if not name.startswith("__") and not inspect.ismodule(val) and not callable(val):
                    _strings(val, lines)
        said = 0
        for name, fn in vars(V).items():
            if not (callable(fn) and name.endswith("_line") and inspect.isfunction(fn)):
                continue
            ps = inspect.signature(fn).parameters
            try:
                args = {k: SAMPLE.get(k, "Casa · Lucio") for k, p in ps.items() if p.default is inspect._empty}
                out = fn(**args)
            except Exception:
                continue
            if isinstance(out, str):
                lines.append(out)
                said += 1
        self.assertGreater(said, 8)
        self.assertGreater(len(lines), 100)
        for line in lines:
            out = SP.speakable(line)
            self.assertIsNone(SP.NEVER_SPOKEN.search(out), (line[:120], out[:120]))


class OneSpeechEngine(unittest.TestCase):
    def test_every_audio_passes_speakable(self):
        vc = (BACKEND / "app/api/voice_conductor.py").read_text()
        body = vc.split("async def text_to_speech(")[1].split("\n@router")[0]
        self.assertIn("SP.speakable(text)", body)
        self.assertIn('"linear16"', body)                                                  # her face's lip-sync audio, same engine
        self.assertEqual(vc.count("DEEPGRAM_TTS_URL,"), 1)                                 # one call to the speech engine
        self.assertIn("SP.speakable(text)", (BACKEND / "app/api/heygen_chat.py").read_text())   # HeyGen's avatar speaks it too

    def test_no_second_engine(self):
        hits = []
        for root in (BACKEND, FRONT):
            if not root.exists():
                continue
            for f in root.rglob("*"):
                if f.suffix not in (".py", ".ts", ".tsx", ".mjs", ".js") or "node_modules" in f.parts or ".next" in f.parts or "tests" in f.parts:
                    continue
                if "/v1/speak" in f.read_text(errors="ignore"):
                    hits.append(str(f.relative_to(root.parent)))
        self.assertEqual(hits, ["backend/app/api/voice_conductor.py"])
        if FRONT.exists():
            self.assertFalse((FRONT / "app/api/s2-voice/pcm/route.ts").exists())
            hello = (FRONT / "app/s2/S2Hello.tsx").read_text()
            self.assertIn("apiUrl('/api/voice/tts')", hello)
            self.assertIn("format: 'pcm'", hello)
            self.assertNotIn("/api/s2-voice/pcm'", hello)


if __name__ == "__main__":
    unittest.main()


# ── Bug B · one read per refresh ────────────────────────────────────────────────────────────────────────────────────────────
from unittest import mock   # noqa: E402

from agapi import agapi_health as AH, agapi_route as AR, itinerary as IT, person_access as PA, venue_submit as VS, venues as VN   # noqa: E402
from agapi import s2_memory as M   # noqa: E402

ACCT = "acct-325"
DAY = "2026-12-01"
N = 12   # Tyler's My bookings with 10+ items


class Record:
    """agapi-live as Sasha sees it: venue.bookings (every act, one call) and venue.booking_status (one act). Counts every call."""

    def __init__(self):
        self.calls = []
        self.state = {f"act_{i}": ("confirmed" if i % 3 == 0 else "sent") for i in range(N)}

    async def __call__(self, op, body, approval=None, account=None):
        self.calls.append(op)
        if op == "users.register":
            return {"ok": True, "result": {"end_user_id": "usr_325"}}
        if op == "venue.bookings":
            return {"ok": True, "result": {"bookings": [
                {"act_id": a, "state": st, "route": "email", "venue": {"name": f"Venue {a}"}, "at": f"{DAY}T21:00", "party": 2,
                 **({"venue_words": {"untrusted_text": "Sí.", "at": "t1"}} if st == "confirmed" else {})} for a, st in self.state.items()]}}
        if op == "venue.booking_status":
            st = self.state[body["act_id"]]
            return {"ok": True, "result": {"act_id": body["act_id"], "state": st,
                                           **({"venue_words": {"untrusted_text": "Sí."}} if st == "confirmed" else {})}}
        raise AssertionError(op)


def acts():
    return [{"act_id": f"act_{i}", "venue": f"Venue act_{i}", "when": f"{DAY}T21:00", "party": 2, "channel": "email", "at": 0,
             "state": "confirmed" if i % 3 == 0 else "sent", "words": "Sí." if i % 3 == 0 else None} for i in range(N)]


class OneReadPerRefresh(unittest.TestCase):
    def setUp(self):
        self.api = Record()
        self.t = [1_000_000.0]

        async def gw_api(account, method, path, body=None, timeout=None):
            return 200, {"reservations": []}
        from booking_signer import guest_whatsapp as GW
        for p in (mock.patch.object(VS, "CALL", self.api), mock.patch.dict(VS._ACTS, {ACCT: acts()}, clear=True),
                  mock.patch.dict(VS._USERS, {}, clear=True), mock.patch.dict(VS._RECORD, {}, clear=True),
                  mock.patch.object(VS, "target", mock.AsyncMock(return_value="live")),
                  mock.patch.object(M, "put_kind", mock.AsyncMock(return_value=True)), mock.patch.object(M, "kind", mock.AsyncMock(return_value=None)),
                  mock.patch.object(GW, "api", gw_api), mock.patch("agapi.s2_outcomes.sync", mock.AsyncMock()),
                  mock.patch.object(VS.time, "time", lambda: self.t[0])):
            p.start()
            self.addCleanup(p.stop)

    def refresh(self):
        """One 6-s tick of the trip screen as it was on 2 Nov: Plan (venue_rows, venue_bookings, trip_status's venue_bookings) and
        Journeys (venue_rows, agapi_rows) — every reader that reached AgAPI."""
        from booking_signer import journeys as JN

        async def tick():
            await IT.venue_rows(ACCT)
            await VN.venue_bookings(ACCT, include_cancelled=True)
            await VN.venue_bookings(ACCT, include_cancelled=True)
            await IT.venue_rows(ACCT)
            return await JN.agapi_rows(ACCT)
        return asyncio.run(tick())

    def test_two_minutes_of_the_train_test_is_a_handful_of_calls(self):
        rows = None
        for _ in range(20):   # two minutes: a refresh every 6 s
            rows = self.refresh()
            self.t[0] += 6
        self.assertEqual(len(rows), N)
        n = {op: self.api.calls.count(op) for op in set(self.api.calls)}
        # a refresh every 6 s, the record read at most once per RECORD_S (10 s): every other refresh → 10 reads in two minutes; nothing
        # changed on the record, so no act is read on its own
        self.assertEqual(n.get("venue.bookings"), 10, n)
        self.assertEqual(n.get("venue.booking_status", 0), 0, n)
        self.assertLessEqual(len(self.api.calls), 12, n)   # was 20 refreshes × (5 readers × 8 open acts + venue.bookings ×2) ≈ 840
        print(f"\n[s325 proof] 2 min of the trip screen, {N} bookings: {n} — {len(self.api.calls)} AgAPI calls in all")

    def test_a_venue_reply_is_read_once(self):
        self.refresh()
        before = self.api.calls.count("venue.booking_status")
        self.api.state["act_1"] = "confirmed"            # the venue said yes
        self.t[0] += VS.RECORD_S + 1
        rows = {r["id"]: r for r in self.refresh()}
        self.assertEqual(rows["act_1"]["status"], "confirmed")
        self.assertEqual(self.api.calls.count("venue.booking_status") - before, 1)   # that one act, once
        for _ in range(5):
            self.t[0] += VS.RECORD_S + 1
            self.refresh()
        self.assertEqual(self.api.calls.count("venue.booking_status") - before, 1)   # nothing changed: never asked again

    def test_readers_at_the_same_moment_share_one_call(self):
        async def many():
            return await asyncio.gather(*(VS.bookings(ACCT) for _ in range(6)))
        asyncio.run(many())
        self.assertEqual(self.api.calls.count("venue.bookings"), 1)

    def test_a_429_is_never_answered_by_reading_each_act(self):
        async def limited(op, body, approval=None, account=None):
            self.api.calls.append(op)
            if op == "users.register":
                return {"ok": True, "result": {"end_user_id": "usr_325"}}
            return {"ok": False, "error": {"code": "rate_limited"}}
        with mock.patch.object(VS, "CALL", limited):
            rows = asyncio.run(VS.bookings(ACCT))
        self.assertEqual(len(rows), N)                                        # as last known — never "no bookings"
        self.assertNotIn("venue.booking_status", self.api.calls)


class AgapisRetryAfter(unittest.TestCase):
    def test_nothing_sent_to_that_key_until_it_passes(self):
        import httpx
        sent = []

        class Resp:
            def __init__(self, code):
                self.status_code, self.headers = code, {"retry-after": "30"}

            def json(self):
                return {"ok": False, "error": {"code": "rate_limited"}} if self.status_code == 429 else {"ok": True, "result": {}}

        class C:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, headers, content):
                sent.append(url)
                return Resp(429 if len(sent) == 1 else 200)
        t = [5000.0]
        AR._WAIT.clear()
        self.addCleanup(AR._WAIT.clear)
        with mock.patch.object(httpx, "AsyncClient", C), mock.patch.object(AH, "note", mock.AsyncMock()), \
                mock.patch.object(AR, "time", create=True), mock.patch("time.time", lambda: t[0]):
            post = lambda: asyncio.run(AR.post("https://agapi.test", "k", "venue.bookings", {}, {}, 5.0))   # noqa: E731
            self.assertEqual(post()["error"]["code"], "rate_limited")
            held = post()
            self.assertEqual((len(sent), held["error"]["details"]["held"]), (1, True))   # not sent: AgAPI asked to wait
            t[0] += 31
            self.assertTrue(post()["ok"])
            self.assertEqual(len(sent), 2)


class AccessOncePerSession(unittest.TestCase):
    def test_one_read_for_every_request_of_the_session(self):
        calls = []

        async def wire(op, body):
            calls.append(op)
            await asyncio.sleep(0.01)
            return {"ok": True, "result": {"end_user_id": "usr_x"}} if op == "users.register" else \
                {"ok": True, "result": {**PA.CLOSED, "mode": "live", "source": "person_access"}}
        PA.clear()
        self.addCleanup(PA.clear)

        async def session():
            await asyncio.gather(*(PA.get("acct-s325") for _ in range(8)))   # a page load's requests, together
            for _ in range(20):
                await PA.get("acct-s325")                                     # every call after
        with mock.patch.object(PA, "CALL", wire), mock.patch.object(PA, "RESOLVER", None):
            asyncio.run(session())
        self.assertEqual(calls, ["users.register", "access.get"])
        self.assertGreaterEqual(PA.TTL_S, 15 * 60)


class TheHealthEmailSaysWhichItWas(unittest.TestCase):
    def mail(self, code):
        got = []

        async def send(m):
            got.append(m)
            return {"sent": True}
        AH._LAST.clear()
        with mock.patch.object(AH, "SEND", send), mock.patch("app.services.model_health._founder_address", mock.AsyncMock(return_value="t@x")):
            asyncio.run(AH.note(AH.LIMIT, "venue.booking_status", "https://agapi-live.x/v1", "k", code=code))
        AH._LAST.clear()
        return got[0]

    def test_429_is_the_rate_limit_in_one_sentence(self):
        m = self.mail("rate_limited")
        line = m["text"].splitlines()[0]
        self.assertIn("rate limit (429)", line)
        self.assertIn("budget is fine", line)
        self.assertNotIn("402", m["text"] + m["subject"])
        self.assertIn("429", m["subject"])

    def test_402_is_the_budget(self):
        m = self.mail("budget_exhausted")
        self.assertIn("monthly budget is spent (402)", m["text"].splitlines()[0])
        self.assertNotIn("429", m["text"] + m["subject"])
