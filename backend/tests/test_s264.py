"""Sasha 264 · T46 — S2 FREEZE BUGS from Tyler's beta (14 Oct, ~09:30–10:40 UTC, /s2, /next and his phone). One gate per item; each
fails on 263's code. Offline.

  1 SILENCE   — after the holding line, a line every voice.PROGRESS_S from the step actually running (/s2, /next: the stream's hold
                event, shown and spoken; WhatsApp: a message). His turns ran 20–44 s with one line at 3 s.
  2 SPA FORM  — AgAPI's venue.prepare_booking gave no filled page (his spa: wellnessmadrid.com, every field empty) and she said "Done —
                it's on your screen". Not filled → said so, plainly, with the details to copy; the card says it too.
  3 TATTOO    — the platform page went to his phone by a send with no template while his last message there was over a day old:
                "not told: outside the 24-hour window", dropped. In the app the page is the card; the phone's failure is said.
  4 PAYMENT   — the charge is basket.trip_figures' to_pay_eur (the chat's and the Trip tab's), never a sum of the payment's own.
  5 VERBOSE   — at most voice.BRIEF_MAX sentences of her own; never one she said last reply, or one a card on screen says.

    cd backend && python -m unittest tests.test_s264 -v
"""
from __future__ import annotations

import asyncio
import inspect
import unittest
from contextlib import ExitStack
from unittest import mock

from app.agent import sasha as S, voice as V
from agapi import venue_submit as VS, venues as VN
from booking_signer import guest_whatsapp as GW, wa_agent as WA
from tests import test_guest_whatsapp_s75 as TG

ACCT = "00000000-0000-4000-8000-000000000264"
CLAIMS = ("found", "booked", "sent", "confirmed", "done", "ready")


def run(c):
    return asyncio.run(c)


async def collect(agen):
    return [e async for e in agen]


# ── 1 · SILENCE ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────
class NoSilence(unittest.TestCase):
    def slow_tool_turn(self, tool="search_flights", ms=0.75):
        async def turn():
            yield {"type": "tool_start", "name": tool}
            await asyncio.sleep(ms)   # the tool runs
            yield {"type": "tool", "name": tool, "ok": True}
            yield {"type": "text", "delta": "Here they are."}
            yield {"type": "done", "text": "Here they are."}
        return turn()

    def test_gate_a_long_tool_gets_progress_lines_from_that_step(self):
        """THE GATE (Tyler's /s2 and /next: 44 s, one line at 3 s, then nothing)."""
        with mock.patch.object(V, "PROGRESS_S", 0.2):
            evs = run(collect(S.with_holding(self.slow_tool_turn(), ACCT, after_s=0.05)))
        holds = [e["text"] for e in evs if e["type"] == "hold"]
        self.assertIn(holds[0], V.HOLDING)                                   # the holding line first, as before
        self.assertGreaterEqual(len(holds), 3)                               # then a line every PROGRESS_S while the tool ran
        self.assertTrue(set(holds[1:]) <= set(V._STEP["flights"]), holds)   # from the step actually running
        self.assertEqual([e["type"] for e in evs][-2:], ["text", "done"])

    def test_never_more_than_progress_s_of_silence(self):
        with mock.patch.object(V, "PROGRESS_S", 0.2):
            async def timed():
                loop, out, last = asyncio.get_running_loop(), [], None
                t0 = loop.time()
                async for e in S.with_holding(self.slow_tool_turn(ms=1.0), ACCT, after_s=0.05):
                    if e["type"] in ("hold", "text", "done"):
                        now = loop.time()
                        out.append(now - (last if last is not None else t0))
                        last = now
                return out
            gaps = run(timed())
        self.assertLess(max(gaps), 0.2 + 0.12, gaps)

    def test_the_lines_are_short_varied_and_never_a_claim(self):
        for step, lines in V._STEP.items():
            self.assertEqual(len(set(lines)), len(lines), step)
            for l in lines:
                self.assertLessEqual(len(l.split()), 8, l)
                self.assertFalse(any(c in l.lower() for c in CLAIMS), l)
        a = [V.progress_line("search_stays", "p") for _ in range(3)]
        self.assertEqual(len(set(a)), 3)
        self.assertIn(V.progress_line("propose_trip", "p"), V._STEP["trip"])
        self.assertIn(V.progress_line(None, "p"), V._STEP[None])

    def test_once_her_words_run_and_no_tool_does_none_is_said(self):   # T37 kept: never over her own words
        async def turn():
            yield {"type": "text", "delta": "Looking"}
            await asyncio.sleep(0.5)
            yield {"type": "done", "text": "Looking"}
        with mock.patch.object(V, "PROGRESS_S", 0.1):
            evs = run(collect(S.with_holding(turn(), ACCT, after_s=0.05)))
        self.assertNotIn("hold", [e["type"] for e in evs])

    def test_a_tool_after_her_words_still_gets_its_line(self):
        async def turn():
            yield {"type": "text", "delta": "Let me look."}
            yield {"type": "tool_start", "name": "search_stays"}
            await asyncio.sleep(0.45)
            yield {"type": "tool", "name": "search_stays", "ok": True}
            yield {"type": "done", "text": "Let me look. Three places."}
        with mock.patch.object(V, "PROGRESS_S", 0.2):
            evs = run(collect(S.with_holding(turn(), ACCT, after_s=0.05)))
        holds = [e["text"] for e in evs if e["type"] == "hold"]
        self.assertTrue(holds and set(holds) <= set(V._STEP["stays"]), holds)

    def test_steps_follow_tool_start_and_its_result(self):
        st = V.Steps()
        st.see({"type": "tool_start", "name": "read_booking_route"})
        st.see({"type": "tool_start", "name": "hold_venue"})
        self.assertEqual(st.now, "read_booking_route")
        st.see({"type": "tool", "name": "read_booking_route"})
        self.assertEqual(st.now, "hold_venue")
        st.see({"type": "tool", "name": "hold_venue"})
        self.assertIsNone(st.now)


class NoSilenceOnWhatsApp(TG.Base):
    def setUp(self):
        super().setUp()
        self.link()

    def test_gate_whatsapp_gets_a_line_per_progress_s_from_the_running_step(self):
        async def agent(ch, body, payload, st, out, now, button_text="", voice_in=False):
            V.STEPS.get().see({"type": "tool_start", "name": "search_venues"})
            await asyncio.sleep(0.75)
            out.text("Here are three places near Sol.")
            return "x"
        with mock.patch.object(WA, "agent_turn", agent), mock.patch.object(V, "HOLD_AFTER_S", 0.05), mock.patch.object(V, "PROGRESS_S", 0.2):
            n = len(self.bodies())
            self.say("a table for two tonight near Sol")
            said = self.bodies()[n:]
        self.assertIn(said[0], V.HOLDING)
        self.assertGreaterEqual(len(said), 4, said)
        self.assertTrue(set(said[1:-1]) <= set(V._STEP["places"]), said)
        self.assertEqual(said[-1], "Here are three places near Sol.")

    def test_the_whatsapp_turn_reports_its_steps(self):
        src = inspect.getsource(WA.agent_turn)
        self.assertIn("steps = V.STEPS.get()", src)
        self.assertIn("steps.see(ev)", src)


# ── 2 · SPA FORM and 3 · TATTOO (the one booking path: venues._book_inner) ────────────────────────────────────────────────────
class Ctx:
    surface, session, mode = "s2", "s", "test"
    account, user_said, started = ACCT, "yes", None


def held_prepared():
    from datetime import datetime, timezone
    return {"id": "h1", "sha": "sha", "at": datetime.now(timezone.utc), "when": "2026-10-31T10:00", "summary": "Saturday 31 October at 10:00",
            "party": 2, "website": "https://wellnessmadrid.com/x", "place_id": "p", "url": "https://wellnessmadrid.com/x",
            "fields": [{"label": "Day", "value": "Sat 31 Oct"}, {"label": "Name", "value": "Test Person"}]}


spawned: list = []


def booking_world(prep=None, tell="sent", tap="sent", gmail=None):
    from agapi import venue_truth as VT
    from booking_signer import wa_brain as WB, slot_link as SL
    spawned.clear()
    store = mock.Mock()
    store.channel_of_account = mock.AsyncMock(return_value={"wa_id_sha256": "w"})

    class G:
        STORE = store

        @staticmethod
        async def _tell(ch, text, template=None):
            return tell

        @staticmethod
        async def tap_platform(*a, **k):
            return tap

        @staticmethod
        async def api(*a, **k):
            return 200, {"url": "https://booksy.com/es-es/1_sinkply"}

        @staticmethod
        def _spawn(coro):
            spawned.append(coro)
            coro.close()
    from booking_signer import mailbox as MB
    return [mock.patch.object(MB, "STORE", gmail), mock.patch.object(VN, "_API", lambda: G), mock.patch.object(VT, "prepare", mock.AsyncMock(return_value=prep)),
            mock.patch.object(VN, "note_prepared", mock.AsyncMock()), mock.patch.object(WB, "trip_day_words", mock.AsyncMock(return_value=None)),
            mock.patch.object(SL, "platform_message", lambda *a, **k: "their page")]


def book(rung, held, in_app=True, **world):
    async def go():
        tok = VS.TAP.set("their-session") if in_app else None
        try:
            return await VN._book_inner(Ctx(), held, {"said": "yes"}, "Wellness Boutique Experience", rung)
        finally:
            if tok is not None:
                VS.TAP.reset(tok)
    with ExitStack() as st:
        for p in booking_world(**world):
            st.enter_context(p)
        return run(go())


class ANotFilledFormIsSaidAsIt(unittest.TestCase):
    def test_gate_no_prepared_page_is_never_called_filled(self):
        """THE GATE (his spa): venue.prepare_booking gave no link → their own page, empty — "Done — it's on your screen" was said."""
        out = book("prepared", held_prepared(), prep=None)
        self.assertIs(out["prepared"]["filled"], False)
        self.assertNotIn(V.DONE_FORM, out["say"])
        self.assertTrue(out["say"].startswith(V.NOT_FILLED))
        self.assertEqual(V.page_line("book_venue", {"ok": True, "result": out}), V.NOT_FILLED)
        ev = S.render("book_venue", out, {})
        self.assertEqual((ev["kind"], ev["filled"]), ("prepared", False))   # the card says it too (S2Cards: "Not filled in")

    def test_a_filled_page_is_as_it_was(self):
        out = book("prepared", held_prepared(), prep={"link": "https://agapi.example/p/1", "human_step": None})
        self.assertIs(out["prepared"]["filled"], True)
        self.assertTrue(out["say"].startswith(V.DONE_FORM))
        self.assertEqual(V.page_line("book_venue", {"ok": True, "result": out}), "")

    def test_the_rules_never_say_filled_in_over_an_empty_page(self):
        src = inspect.getsource(VN._prepared_now)
        self.assertIn('if (out.get("prepared") or {}).get("filled") is False:', src)
        self.assertIn('line = V.not_filled_line(d.get("say") == "prepared_link_captcha")', src)
        self.assertIn('out["rules"] = {**out["rules"], "say": line}', src)   # the rules' told words too: never "filled in for you"

    def test_the_card_names_it(self):
        import pathlib
        tsx = (pathlib.Path(__file__).resolve().parents[2] / "frontend/app/components/cards/S2Cards.tsx").read_text()
        self.assertIn("ev.filled === false ? 'Not filled in — copy your details' : 'Ready to book'", tsx)


def held_platform():
    return {"id": "l1", "sha": "sha", "when": "2026-10-31T14:00", "summary": "Saturday 31 October at 14:00", "party": 1, "platform": "Booksy",
            "url": "https://booksy.com/es-es/1_sinkply"}


class APlatformPageIsNeverStranded(unittest.TestCase):
    def test_gate_the_phone_failed_and_she_says_so_with_the_card_on_screen(self):
        """THE GATE (his tattoo link): the send met "outside the 24-hour window", nothing said, nothing arrived."""
        out = book("page", held_platform(), tap="not told: outside the 24-hour window")
        self.assertEqual(out["page_url"], "https://booksy.com/es-es/1_sinkply")                 # the card, always, in the app
        self.assertEqual(S.render("book_venue", out, {})["kind"], "handover")
        line = V.page_line("book_venue", {"ok": True, "result": out})
        self.assertTrue(line.startswith(out["page_says"]), line)
        self.assertIn("I couldn't send it to your phone — you haven't messaged me there in the last day", line)
        self.assertEqual(V.channel_words(line), [])

    def test_sent_to_the_phone_too(self):
        out = book("page", held_platform(), tap="sent")
        self.assertEqual(V.page_line("book_venue", {"ok": True, "result": out}), out["page_says"])   # nothing about the phone: it arrived

    def test_gate_item_8_one_line_one_button_never_an_internal_address(self):
        """Row 929 (Ichikani Madrid): "Shall I send this?" on a platform she never sends on, and a card telling him to forward the
        confirmation to act-…@booking.kanoe.ai. Now one line over the one button; the confirmation from his Gmail when it's linked."""
        mb = mock.Mock()
        mb.get_link = mock.AsyncMock(return_value={"vault_item_id": "v"})
        out = book("page", held_platform(), tap="not told: outside the 24-hour window", gmail=mb)
        line = V.page_line("book_venue", {"ok": True, "result": out})
        self.assertTrue(line.startswith("Wellness Boutique Experience books on their own booking page — pick Saturday 31 October at 14:00 "
                                        "for 1 person there. Tap to book there; I'll pick up their confirmation from your email."), line)
        self.assertNotIn("Shall I send", line)
        self.assertNotIn("@", line)
        self.assertEqual(V.channel_words(line), [])
        self.assertEqual(len(spawned), 1)   # the Gmail watch, though the phone didn't get it
        self.assertEqual(S.render("book_venue", out, {})["kind"], "handover")   # the ONE button: "Open their booking page"

    def test_no_gmail_one_plain_ask_never_an_address(self):
        out = book("page", held_platform(), tap="sent")
        self.assertIn("forward me the confirmation when it arrives", V.page_line("book_venue", {"ok": True, "result": out}))

    def test_filled_only_when_the_link_carries_the_slot(self):
        self.assertIn("it's filled in for 2 people", V.platform_line("X", 2, "tonight at 21:00", True, False))
        self.assertNotIn("filled", V.platform_line("X", 2, "tonight at 21:00", False, False))

    def test_in_the_app_a_platform_is_handed_over_at_once_no_read_back_no_yes(self):
        src = inspect.getsource(VN._execute)
        self.assertIn('out = _said(await _finish(ctx, _HELD[ctx.account]), d)', src)
        self.assertIn('out["rules"] = {**out["rules"], "say": line}', src)

    def test_whatsapp_and_old_s1_are_as_they_were(self):
        out = book("page", held_platform(), in_app=False, tap="not told: outside the 24-hour window")
        self.assertNotIn("in_app", out)
        self.assertEqual(V.page_line("book_venue", {"ok": True, "result": out}), "")

    def test_every_reason_is_plain_words(self):
        for why in ("not sent: no WhatsApp linked to this account", "not told: WhatsApp for guests is off", "not sent: opted out", "boom"):
            l = V.phone_line(False, why)
            self.assertTrue(l.startswith("I couldn't send it to your phone"), l)
            self.assertEqual(V.channel_words(l), [], l)
        self.assertEqual(V.phone_line(True, "sent"), "")

    def test_the_turn_says_it_and_ends_on_it(self):
        self.assertIn("_V.read_back_line(u.name, r) or _V.yes_line(u.name, r) or _V.page_line(u.name, r)", inspect.getsource(S.turn))

    def test_she_is_told_the_page_is_on_screen(self):
        self.assertIn("A booking page is always on their screen as a card they tap", V.RULES)


# ── 7 · VOICE NOT HEARD (row 929: his phone, /s2, "Voice on", the mic showing as working, she never heard him) ──────────────────
def _tsx(rel):
    import pathlib
    return (pathlib.Path(__file__).resolve().parents[2] / "frontend" / rel).read_text()


class TheMicIsNeverDeafWhileItShowsWorking(unittest.TestCase):
    def test_gate_the_gate_is_closed_only_when_someone_owns_it(self):
        """THE GATE: useRef(true) with no owner on /s2 — an auto-started mic dropped every frame (only a 45 s watchdog reopened it)."""
        vb = _tsx("app/components/VoiceButton.tsx")
        self.assertIn("const micGatedRef = useRef(!!onSetGate)", vb)
        self.assertNotIn("const micGatedRef = useRef(true)", vb)

    def test_gate_s2_owns_it_with_her_own_voice(self):
        app = _tsx("app/s2/S2App.tsx")
        self.assertIn("onSetGate={g => { micGate.current = g; g(false) }}", app)
        self.assertIn("speaker.onSpeaking(b => micGate.current?.(b))", app)

    def test_gate_deaf_is_said_never_listening(self):
        """A phone's audio started without a tap stays suspended (no frame ever) — said, and the tap turns it on (not off)."""
        vb = _tsx("app/components/VoiceButton.tsx")
        self.assertIn("if (ctx.state !== 'running') { deafRef.current = true; reportMicError(DEAF_TAP)", vb)
        self.assertIn("now - Math.max(lastFrameRef.current, lastAliveRef.current) > DEAF_AFTER_MS", vb)
        self.assertIn("if (connectedRef.current && deafRef.current) {", vb)
        self.assertLess(vb.index("if (connectedRef.current && deafRef.current) {"), vb.index("if (connectedRef.current) { stopAll(); return }"))
        self.assertIn("const stateWords = micError ||", vb)   # the error is what the mic says first


# ── 4 · PAYMENT ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def rows():
    return [{"id": "s1", "kind": "stay", "state": "suggested", "price_amount": 1380.00, "price_currency": "EUR", "day": "2026-11-15"},
            {"id": "f1", "kind": "flight", "state": "chosen", "price_amount": 666.86, "price_currency": "EUR", "day": "2026-11-15"},
            {"id": "f2", "kind": "flight", "state": "chosen", "price_amount": 727.72, "price_currency": "EUR", "day": "2026-11-27"}]


class ThePaymentChargesTheOneFigure(unittest.TestCase):
    def pay(self, figure):
        from booking_signer import basket_book as BB, basket as BK, test_deposit as TD, paid_watch as PWT
        cur = {"rows": rows(), "party": 2, "trip_id": "t", "title": "13 Days in Argentina & Chile"}
        sha = __import__("hashlib").sha256("\n".join(BB.lines_of(cur["rows"], 2)).encode()).hexdigest()
        checkout = mock.AsyncMock(return_value={"id": "cs_test_x", "url": "https://checkout.stripe.com/x"})
        with mock.patch.object(BB, "in_progress", mock.AsyncMock(return_value=None)), mock.patch.object(BB, "current", mock.AsyncMock(return_value=cur)), \
                mock.patch.object(BK, "trip_figures", mock.AsyncMock(return_value={"to_pay_eur": figure, "breakdown": {}})), \
                mock.patch.object(TD, "checkout", checkout), mock.patch.object(BK, "hold", mock.AsyncMock()), \
                mock.patch.object(PWT, "remember", mock.AsyncMock(return_value=True)), \
                mock.patch.object(GW, "tap_to_pay", mock.AsyncMock(return_value="sent")):
            got = run(BB.pay(ACCT, sha, "phone"))
        return got, checkout

    def test_gate_the_charge_is_the_trips_figure(self):
        got, checkout = self.pay(2774.58)
        self.assertEqual(checkout.await_args.args[0], "2774.58")   # lodging AND flights: the one figure
        self.assertEqual(got["eur"], 2774.58)

    def test_gate_a_payment_that_isnt_the_figure_is_never_made(self):
        got, checkout = self.pay(1394.58)   # e.g. the flights alone
        self.assertIn("isn't the trip's total", got["why"])
        checkout.assert_not_awaited()

    def test_pay_reads_trip_figures(self):
        from booking_signer import basket_book as BB
        self.assertIn("await charge_of(account, cur)", inspect.getsource(BB.pay))
        self.assertIn("BK.trip_figures(account, cur[\"trip_id\"])", inspect.getsource(BB.charge_of))
        self.assertIn('BK.total(rows)["amount"]', inspect.getsource(BB._moved))   # never raw amounts in any currency


# ── 5 · VERBOSE / REPEATS ───────────────────────────────────────────────────────────────────────────────────────────────────────
class ShortNeverTwice(unittest.TestCase):
    def test_gate_her_long_repeat_is_cut(self):
        """THE GATE (his tattoo turn): five sentences, a status recital and the same question again."""
        said = ["The booking page can only go to your phone.", "I can't open it on this screen, because you have to press Book yourself.",
                "It would be set for Saturday 31 October at 14:00.", "Your flights and all seven hotel stays are booked.",
                "The Madrid spa isn't booked yet.", "Shall I send the tattoo page to your phone now?"]
        kept, n, asked = V.brief(said, [], [], 0, False)
        self.assertEqual(len(kept), V.BRIEF_MAX + 1)          # three of hers, and the question she was asking
        self.assertEqual(kept[-1], said[-1])
        self.assertNotIn("Your flights and all seven hotel stays are booked.", kept)

    def test_never_what_she_said_last_reply_or_a_card_says(self):
        last = "Their page is on this screen now, Tyler. Tap it to open it, then press Book there."
        kept, _, _ = V.brief(["Their page is on this screen now, Tyler.", "Saturday 31 October at 14:00, for 1."], [last],
                             ["Saturday 31 October at 14:00, for 1."], 0, False)
        self.assertEqual(kept, [])

    def test_the_rules_words_are_not_put_in_front_twice_running(self):
        told = ["They book on Booksy: their page is ready for you — you press Book there. I never book on a platform for you."]
        self.assertTrue(V.told_prefix("Shall I send this?", told))
        last = "They book on Booksy: their page is ready for you — you press Book there. I never book on a platform for you. Shall I?"
        self.assertEqual(V.told_prefix("Shall I send this? " + last, told), "")

    def test_the_turn_holds_it_in_code_and_tells_her(self):
        src = inspect.getsource(S.turn)
        self.assertIn('_V.brief([x], [last_reply], tstate["seen"], tstate["brief_n"], tstate["asked"])', src)
        self.assertIn('_V.told_prefix(f"{text} {last_reply}" if honest else text, told)', src)
        self.assertIn("Short: two or three sentences at most", V.RULES)


if __name__ == "__main__":
    unittest.main()
