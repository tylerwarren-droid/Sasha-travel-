"""Sasha 279 · T59 — S2 BUGS FROM TYLER'S REAL USE (21 Oct 12:53, his iPhone on /s2). Each gate fails on 276's code. Offline.

  A PROGRESS TALK  — a line every 5 s while she worked (the logs: 7 in a 25-second trip). Now ONE line, a second only on a long wait,
                     never a third (voice.progress_due — read by the stream and by WhatsApp); the stream's {"type": "working", "on"}
                     is the same state, and /s2's ring pulses on it.
  B PAYMENT        — paid, back, waited, had to ask: the settle reached his page as `booked`, which /s2 wrote and never spoke. Now
                     live_events.completed says "Your payment for <item> went through — you're booked." first, on BOTH doors (the
                     page's event, spoken; WhatsApp), and keeps it for the return (said once).
  C CLOSING LINE   — after every completed booking (a payment settled, a venue confirmed in the turn, by its call, by a platform's
                     email): voice.closing_line, once per booking; "I've sent it to your email" only when the send result says so.

    cd backend && python -m unittest tests.test_s279 -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import re
import unittest
from unittest import mock

from app.agent import sasha as S, voice as V
from booking_signer import guest_receipt as GR, guest_whatsapp as GW, live_events as LE, paid_watch as PW, wa_agent as WA
from tests import test_guest_whatsapp_s75 as TG

BACKEND = pathlib.Path(__file__).resolve().parents[1]
FRONT = BACKEND.parent / "frontend"
ACCT = "00000000-0000-4000-8000-000000000279"


def run(c):
    return asyncio.run(c)


async def collect(agen):
    return [e async for e in agen]


def slow_tool(tool="propose_trip", s=1.0):
    async def turn():
        yield {"type": "tool_start", "name": tool}
        await asyncio.sleep(s)
        yield {"type": "tool", "name": tool, "ok": True}
        yield {"type": "text", "delta": "Here it is."}
        yield {"type": "done", "text": "Here it is."}
    return turn()


# ── A · SAY IT ONCE ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
class A_SayItOnce(unittest.TestCase):
    def test_the_rule(self):
        self.assertTrue(V.progress_due(0, 0))
        self.assertFalse(V.progress_due(1, V.LONG_WAIT_S - 1))
        self.assertTrue(V.progress_due(1, V.LONG_WAIT_S))
        self.assertFalse(V.progress_due(2, 10 * V.LONG_WAIT_S))   # never a third, however long
        self.assertEqual(V.PROGRESS_MAX, 2)

    def test_gate_a_long_trip_hears_two_lines_at_most_then_the_screen_shows_it(self):
        """THE GATE (21 Oct 10:40 UTC: propose_trip ran 25 s, a line every 5 s). Fails on 276: a line every PROGRESS_S."""
        with mock.patch.object(V, "LONG_WAIT_S", 0.15), mock.patch.object(V, "PROGRESS_S", 0.05):
            evs = run(collect(S.with_holding(slow_tool(s=1.0), ACCT, first=V.FIRST_LINE)))
        holds = [e["text"] for e in evs if e["type"] == "hold"]
        self.assertEqual(holds[0], V.FIRST_LINE)
        self.assertEqual(len(holds), 2, holds)                        # 1 s of work = ~7 long waits: still two
        work = [e["on"] for e in evs if e["type"] == "working" and "on" in e]
        self.assertEqual(work, [True, False])                         # on with her first line, off when her answer begins
        i_off = next(i for i, e in enumerate(evs) if e.get("type") == "working" and e.get("on") is False)
        self.assertEqual(evs[i_off + 1]["type"], "text")

    def test_a_slow_non_work_turn_too(self):
        with mock.patch.object(V, "LONG_WAIT_S", 0.15):
            evs = run(collect(S.with_holding(slow_tool("get_status", s=0.9), ACCT, after_s=0.05)))
        self.assertEqual(len([e for e in evs if e["type"] == "hold"]), 2)

    def test_a_fast_reply_is_never_working(self):
        async def fast():
            yield {"type": "text", "delta": "Hi"}
            yield {"type": "done", "text": "Hi"}
        evs = run(collect(S.with_holding(fast(), ACCT, after_s=0.5)))
        self.assertFalse([e for e in evs if e["type"] in ("hold", "working")])

    def test_both_doors_read_the_one_rule(self):
        self.assertIn("_V.progress_due(held_n", inspect.getsource(S.with_holding))
        wa = inspect.getsource(GW._brain_turn)
        self.assertIn("V.progress_due(said, V.LONG_WAIT_S)", wa)
        self.assertNotIn("timeout=V.PROGRESS_S", wa)
        self.assertNotIn("_V.PROGRESS_S", inspect.getsource(S.with_holding))


class A_WhatsApp(TG.Base):
    def setUp(self):
        super().setUp()
        self.link()

    def test_gate_whatsapp_a_long_wait_hears_two_lines_at_most(self):
        async def agent(ch, body, payload, st, out, now, button_text="", voice_in=False):
            V.STEPS.get().see({"type": "tool_start", "name": "propose_trip"})
            await asyncio.sleep(1.0)
            out.text("Here's your trip.")
            return "x"
        with mock.patch.object(WA, "agent_turn", agent), mock.patch.object(V, "HOLD_AFTER_S", 0.05), \
                mock.patch.object(V, "LONG_WAIT_S", 0.15), mock.patch.object(V, "PROGRESS_S", 0.05):
            n = len(self.bodies())
            self.say("plan me five days in Lisbon in May")
            said = self.bodies()[n:]
        self.assertEqual(said[0], V.FIRST_LINE)
        self.assertEqual(len(said), 3, said)   # the first line, one more on the long wait, her answer — nothing else for 1 s
        self.assertEqual(said[-1], "Here's your trip.")


@unittest.skipUnless(FRONT.exists(), "the frontend isn't beside the backend (Railway's image)")
class A_TheRing(unittest.TestCase):
    def test_the_ring_pulses_from_the_one_state(self):
        rule = (FRONT / "lib/presence-rule.mjs").read_text()
        self.assertIn("export function ring(look, talking = false, working = false)", rule)
        self.assertIn("const pulse = working && (look === 'listening' || look === 'idle') ? WORK_PULSE : null", rule)
        app = (FRONT / "app/s2/S2App.tsx").read_text()
        self.assertIn("if (ev.type === 'working' && typeof ev.on === 'boolean') setWorking(ev.on)", app)
        self.assertIn("working={working}\n    onBegin={beginNow}", app)   # Sasha 296 · MOVED: a tap before the sign-in check · Sasha 295 · MOVED: + the opening's moves
        hello = (FRONT / "app/s2/S2Hello.tsx").read_text()
        self.assertIn("const r = ring(p.look, talking, working)", hello)
        self.assertIn("data-sasha-working={r.pulse ? 'pulse' : undefined}", hello)


# ── B + C · A FINISHED BOOKING ──────────────────────────────────────────────────────────────────────────────────────────────────
class _World:
    """completed()'s edges, captured: the email's send result, WhatsApp, the page's events, the kept news."""

    def __init__(self, sent=True, to="scratch@example.com"):
        self.mails, self.wa, self.news = [], [], []
        self.sent, self.to = sent, to

    def __enter__(self):
        LE._CLOSED.clear()   # once per booking is per process too: an earlier test's same booking (test_s263's play) is not this one
        LE._RECENT.pop(ACCT, None)

        async def send(msg):
            self.mails.append(msg)
            return {"sent": self.sent, "why": None if self.sent else "not configured"}

        async def wa(account, text):
            self.wa.append(text)
            return "sent"

        async def addr(account):
            return self.to

        async def keep(account, key, text):
            self.news.append((key, text))

        async def st(account):
            return {"state": "booked", "line": "Booked: Kenya, 9 days."}
        self.p = [mock.patch.object(LE, "SEND", send), mock.patch.object(LE, "WA_SEND", wa), mock.patch.object(GR, "address_of", addr),
                  mock.patch.object(LE, "keep_news", keep), mock.patch.object(LE, "status_now", st)]
        for x in self.p:
            x.start()
        return self

    def events(self):   # what the open page hears (the same list a page that connects late replays)
        out = list(LE._RECENT.get(ACCT) or [])
        LE._RECENT.pop(ACCT, None)
        return out

    def __exit__(self, *a):
        for x in self.p:
            x.stop()


TRIP = {"status": "booked", "say": "✅ Booked — everything's in your itinerary.", "booked": ["Flight IB1 MAD → NBO · ref X1", "Hotel A · ref H1"],
        "failed": []}


class B_PaymentSaidFirst(unittest.TestCase):
    def test_gate_paid_she_says_so_first_on_both_doors(self):
        """THE GATE (21 Oct 10:47:57 UTC: settled, his page heard `booked` — written, never spoken; WhatsApp had its own words)."""
        with _World() as w:
            run(LE.on_settled(ACCT, TRIP, "Kenya, 9 days", key="cs_test_279"))
            ev = w.events()
        line = f"{V.paid_line('Kenya, 9 days')} {V.CLOSING}"
        self.assertEqual(line, "Your payment for Kenya, 9 days went through — you're booked. You'll find your itinerary here, and I've "
                               "sent it to your email. If you want to change anything, I'm here 24 hours a day, 7 days a week.")
        self.assertEqual([(e["type"], e["text"], e["key"]) for e in ev], [("booked", line, "pay:cs_test_279")])
        self.assertEqual(len(w.wa), 1)
        self.assertTrue(w.wa[0].startswith(line))                    # the same words on WhatsApp (+ the itinerary link)
        self.assertEqual(w.news, [("pay:cs_test_279", line)])      # kept for a return later than the replay
        self.assertEqual(len(w.mails), 1)

    def test_said_once_however_many_see_the_payment(self):
        with _World() as w:
            run(LE.on_settled(ACCT, TRIP, "Kenya", key="cs_test_once"))
            again = run(LE.on_settled(ACCT, TRIP, "Kenya", key="cs_test_once"))
            self.assertEqual(len(w.events()), 1)
            self.assertEqual((len(w.wa), len(w.mails)), (1, 1))
        self.assertTrue(again.get("already"))

    def test_a_flight_is_named(self):
        self.assertEqual(LE.item_of({"card": {"owner": "Iberia", "flights": "IB3166"}}, None), "the Iberia IB3166 flight")
        self.assertEqual(LE.item_of({}, None), "your trip")

    def test_partly_booked_is_never_youre_booked(self):
        with _World() as w:
            run(LE.on_settled(ACCT, {**TRIP, "failed": ["Hotel B — refused"]}, "Kenya", key="cs_test_part"))
            text = w.events()[0]["text"]
        self.assertNotIn("you're booked", text)
        self.assertIn("not everything", text)

    def test_failed_is_said_as_before_with_no_closing(self):
        with _World() as w:
            run(LE.on_settled(ACCT, {"status": "failed", "failed": ["the airline refused"]}, "Kenya", key="cs_test_fail"))
            ev = w.events()
        self.assertEqual(ev[0]["type"], "booking_failed")
        self.assertNotIn("24 hours a day", ev[0]["text"])

    def test_the_settle_hands_both_doors_to_completed(self):
        src = inspect.getsource(PW.settle)
        self.assertIn('if r.get("status") != "booked":', src)          # its own WhatsApp line only when NOT booked
        self.assertIn("key=sid", src)

    def test_the_return_takes_the_kept_news_once(self):
        kept = {"news": {"key": "pay:x", "text": "Your payment for X went through — you're booked.", "at": __import__("time").time()}}

        async def kind(account, name):
            return kept.get(name)

        async def put(account, name, value):
            if value is None:
                kept.pop(name, None)
            else:
                kept[name] = value
            return True
        from agapi import s2_memory as M
        with mock.patch.object(M, "kind", kind), mock.patch.object(M, "put_kind", put):
            first, second = run(LE.take_news(ACCT)), run(LE.take_news(ACCT))
        self.assertEqual(first["key"], "pay:x")
        self.assertIsNone(second)
        self.assertIn("news = await LE.take_news(account)", inspect.getsource(S.s2_memory))

    @unittest.skipUnless(FRONT.exists(), "the frontend isn't beside the backend (Railway's image)")
    def test_the_page_speaks_it_and_says_it_once(self):
        app = (FRONT / "app/s2/S2App.tsx").read_text()
        self.assertIn("if (!held && said) speaker.say(String(ev.spoken || said))", app)
        self.assertIn("if (ev.type === 'booked' && ev.key && newsSaid(ev.key)) return", app)
        self.assertIn("if (j?.news?.text && !newsSaid(j.news.key)) {", app)


class C_TheClosingLine(unittest.TestCase):
    def test_emailed_only_when_the_send_result_says_so(self):
        with _World(sent=False) as w:
            out = run(LE.completed(ACCT, "venue:t1", lines=["Casa X — Thu 21:00"], title="Casa X", push=False))
        self.assertEqual(out["text"], V.CLOSING_LATER)
        self.assertNotIn("I've sent it", out["text"])
        self.assertEqual(len(w.mails), 1)
        with _World(sent=True, to=None):
            out = run(LE.completed(ACCT, "venue:t2", lines=["Casa X"], push=False))
        self.assertEqual(out["text"], V.CLOSING_LATER)   # no address on record: nothing went
        with _World(sent=True):
            out = run(LE.completed(ACCT, "venue:t3", lines=["Casa X"], push=False))
        self.assertEqual(out["text"], V.CLOSING)

    def test_once_per_booking(self):
        with _World():
            a = run(LE.completed(ACCT, "venue:once", lines=["Casa X"], push=False))
            b = run(LE.completed(ACCT, "venue:once", lines=["Casa X"], push=False))
        self.assertTrue(a["said"])
        self.assertEqual((b["said"], b["text"]), (False, ""))

    def test_gate_a_venue_confirmed_in_the_turn_ends_with_it(self):
        """In the turn (both doors say book_venue's `line` word for word): the closing line follows the booked sentence."""
        from tests import test_s263 as T263
        with _World():
            w, out = T263.play(T263.ITEM_7[:1] + [("Handle it", "book_venue", T263.booking("21:15")), ("Yes, send it.", "book_venue", {})])
        line = out[2]["line"]
        self.assertTrue(line.startswith("✅ Booked: Sasha Test Venue, 2026-10-22 at 21:15 — reference TV-263."), line)
        self.assertTrue(line.endswith(V.CLOSING), line)

    def test_never_after_a_quote_a_hold_or_a_request(self):
        from tests import test_s263 as T263
        with _World():
            w, out = T263.play(T263.ITEM_7[:1] + [("Handle it", "book_venue", T263.booking("21:15"))])
        self.assertNotIn("24 hours a day", str(out))   # the read-back card: not past "book it"
        src = inspect.getsource(__import__("agapi.venues", fromlist=["x"])._finish)
        self.assertIn('if out.get("status") == "confirmed" and out.get("line"):', src)

    def test_a_venue_confirmed_by_its_call(self):
        from agapi import venue_calls as VC, venue_submit as VS

        async def attempt(account, act_id, outcome, words, by):
            return {"ok": True, "result": {"state": "confirmed" if outcome == "confirmed" else "proposed",
                                           "say": "They said yes — Casa X, Thursday at 21:00 is booked."}}
        told = []

        async def tell(account, text, card=None, wa_text=None):
            told.append(text)
            return "sent"
        reading = type("R", (), {"state": "reached", "outcome": "yes", "venue_words": "yes", "why": ""})()
        with _World(), mock.patch.object(VS, "call_attempt", attempt), mock.patch.object(VC, "tell", tell), \
                mock.patch.object(VC, "act_of", lambda call: "act_279"):
            run(VC.after_call({"account_id": ACCT, "venue": "Casa X"}, reading))
            reading.outcome = "unclear"
            run(VC.after_call({"account_id": ACCT, "venue": "Casa X"}, reading))
        self.assertTrue(told[0].endswith(V.CLOSING), told)
        self.assertNotIn("24 hours a day", told[1])   # another time offered: not a booking

    def test_every_completion_goes_through_the_one_trigger(self):
        callers = {}
        for p in BACKEND.rglob("*.py"):
            if "tests" in p.parts or "node_modules" in p.parts or ".venv" in p.parts:
                continue
            n = len(re.findall(r"\bLE\.completed\(|\bawait completed\(", p.read_text(errors="ignore")))
            if n:
                callers[str(p.relative_to(BACKEND))] = n
        self.assertEqual(callers, {"agapi/venues.py": 1, "agapi/venue_calls.py": 1, "booking_signer/mailbox.py": 1,
                                   "booking_signer/live_events.py": 1})
        voice_words = [p for p in BACKEND.rglob("*.py") if "tests" not in p.parts and ".venv" not in p.parts
                       and "24 hours a day" in p.read_text(errors="ignore")]
        self.assertEqual(sorted(str(p.relative_to(BACKEND)) for p in voice_words), ["app/agent/voice.py", "booking_signer/live_events.py"])


if __name__ == "__main__":
    unittest.main()
