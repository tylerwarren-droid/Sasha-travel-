"""Sasha 254 · two defects found on production (cee7889), /s2, a test-mode account: "Book Hammam Al Ándalus in Madrid (Salesas) for two
on Thursday 29 October at 17:00."

  1 · THE RULES' WORDS ARE HEARD — hold_venue's rules said (say_key not_live) "This account is in test mode, so I won't contact a
      real venue." and she paraphrased it away. A booking rule's refusal or stop is told to the person: when a tool result carries
      one, sasha.turn puts the rules' sentence in front of her reply, once, whatever the model wrote (voice.told_prefix). S1 with
      parity off is untouched.
  2 · ONE TRUTH — hold_venue drew their prefilled page and said "It's in your bookings"; get_status then said "no booking or request
      … nothing was set up". The prepared page is now on the record get_status reads (venues.note_prepared → s2_status): said as
      prepared, waiting for them to book it on their page, not booked.

Offline: a scripted model, no network, no database."""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

import app.services.llm as LLM
from agapi import s2_status as ST, v0 as API, venues as VN
from agapi.booking_rules import booking_rules as BR
from app.agent import sasha as AG
from app.agent import voice as V
from app.agent.fakes import Block, client

ACCOUNT = "00000000-0000-4000-8000-000000000254"
NOT_LIVE = BR.PHRASES["not_live"]
FIRST = "This account is in test mode, so I won't contact a real venue."
HER = ("I've prefilled the Salesas booking page for two on Thursday 29 October at 17:00, and you book it yourself from there. "
       "Nothing is booked yet, and you can take it over at any point.")


def run(c):
    return asyncio.run(c)


def hold_result(key="not_live"):
    text = BR.PHRASES[key]
    say = text if "take it over" in text.lower() else f"{text} {BR.PHRASES['takeover']}"
    return {"ok": True, "result": {"status": "page_link", "venue": "Hammam Al Ándalus", "booked": False, "itinerary": "It's in your bookings",
                                   "prepared": {"venue": "Hammam Al Ándalus", "url": "https://example.test/prepared/x", "fields": []},
                                   "rules": {"action": "prepared_link", "say_key": key, "say": say, "refusals": [{"rule": "access"}],
                                             "takeover": {"say": BR.PHRASES["takeover"]}},
                                   "say": say, "how": "Say `say` exactly — never that it's booked."}}


def turn(reply, result, surface="s2", parity="on"):
    steps = [[Block(type="tool_use", id="t1", name="hold_venue",
                    input={"name": "Hammam Al Ándalus", "city": "Madrid", "day": "2026-10-29", "time": "17:00", "party": 2})],
             [Block(type="text", text=reply)]]

    async def call(ctx, name, args):
        r = result if name == "hold_venue" else {"ok": True, "result": {}}
        ctx.calls.append({"tool": name, "ok": r["ok"]})
        return r

    async def go():
        return [ev async for ev in AG.turn(ACCOUNT, "Book Hammam Al Ándalus in Madrid (Salesas) for two on Thursday 29 October at 17:00.",
                                           [], f"s254-{datetime.now().timestamp()}", surface=surface)]
    with mock.patch.object(LLM, "client", client(steps)), mock.patch.object(API, "call", call), \
            mock.patch.dict(os.environ, {"SASHA_S1_PARITY": parity}):
        evs = run(go())
    return evs, next(e["text"] for e in evs if e["type"] == "done")


class TheRulesWordsAreHeard(unittest.TestCase):
    def test_T30_a_not_live_hold_whose_reply_omits_the_line_carries_it_once(self):
        evs, text = turn(HER, hold_result("not_live"))
        self.assertTrue(text.startswith(FIRST), text)
        self.assertEqual(text.count(FIRST), 1)
        self.assertIn("Nothing is booked yet", text)                       # her own words stay
        self.assertEqual(text.lower().count("take it over"), 1)             # the take-over she said is never said twice
        rep = [e for e in evs if e["type"] == "replace"]
        self.assertEqual(len(rep), 1)
        self.assertTrue(rep[0]["speak"])
        self.assertIn("test mode", rep[0]["say"])                           # heard, not only shown
        done = next(e for e in evs if e["type"] == "done")
        self.assertTrue(any("rules' words put in front" in g for g in done["guard"]))

    def test_no_real_sends_too(self):
        _, text = turn(HER, hold_result("no_real_sends"))
        self.assertTrue(text.startswith("I can't contact venues for you yet on this account."), text)
        self.assertEqual(text.count("I can't contact venues for you yet"), 1)

    def test_said_already_nothing_is_added(self):
        reply = f"{NOT_LIVE} I've prefilled it for two on Thursday at 17:00. You can take it over at any point."
        evs, text = turn(reply, hold_result("not_live"))
        self.assertTrue(text.startswith(FIRST), text)   # said where she said it — never dropped as a "test" disclaimer
        self.assertEqual(text.count(FIRST), 1)
        self.assertFalse([e for e in evs if e["type"] == "replace"])

    def test_on_whatsapp_and_next_with_parity_too(self):
        for surface in ("wa", "s1"):
            _, text = turn(HER, hold_result("not_live"), surface=surface)
            self.assertEqual(text.count(FIRST), 1, surface)

    def test_old_s1_parity_off_is_untouched(self):
        evs, text = turn(HER, hold_result("not_live"), surface="s1", parity="off")
        self.assertEqual(text, HER)
        self.assertFalse([e for e in evs if e["type"] == "replace"])

    def test_a_result_with_nothing_to_tell_adds_nothing(self):
        r = hold_result("sent")
        r["result"]["rules"]["refusals"] = []
        self.assertEqual(V.told_line(r["result"]), "")
        self.assertEqual(V.told_line({"status": "awaiting_yes"}), "")

    def test_every_stop_and_refusal_key_is_a_rules_phrase(self):
        self.assertLessEqual(V.TOLD, set(BR.PHRASES))
        for k in ("not_live", "no_real_sends", "no_channel", "calls_cap", "too_soon", "stopped"):
            self.assertIn(k, V.TOLD)

    def test_the_prefix_is_once_across_many_results(self):
        line = V.told_line(hold_result("not_live")["result"])
        pre = V.told_prefix(HER, [line, line, line])
        self.assertEqual(pre.count(FIRST), 1)
        self.assertNotIn("take it over", pre.lower())


class OneTruthPreparedPage(unittest.TestCase):
    def setUp(self):
        VN._PREPARED.pop(ACCOUNT, None)
        self.day = (date.today() + timedelta(days=16)).isoformat()

    def tearDown(self):
        VN._PREPARED.pop(ACCOUNT, None)

    def _hold_and_draw(self):
        """hold_venue's prepared rung, drawn at once (_finish, as _prepared_now does): their page, prefilled; their tap pending."""
        from agapi import s2_outcomes as OC, venue_truth as VT
        from booking_signer import wa_brain as WB
        held = {"rung": "prepared", "id": "prep-254", "sha": "x" * 64, "at": datetime.now(timezone.utc), "venue": "Hammam Al Ándalus",
                "summary": "Thursday 29 October at 17:00 for 2", "when": f"{self.day}T17:00", "party": 2, "place_id": "p254",
                "url": "https://example.test/book", "fields": [{"label": "People", "value": "2"}], "website": "https://example.test"}
        with mock.patch.object(VT, "prepare", mock.AsyncMock(return_value=None)), \
                mock.patch.object(WB, "trip_day_words", mock.AsyncMock(return_value="It's in your bookings")), \
                mock.patch.object(OC, "booked", mock.AsyncMock()), mock.patch.object(VN._API(), "STORE", None):
            return run(VN._finish(API.Ctx(account=ACCOUNT, surface="s2"), held))

    def _status(self, venues=()):
        from agapi import s2_outcomes as OC

        async def vb(account, include_cancelled=False):
            return list(venues)
        with mock.patch.object(VN, "venue_bookings", vb), mock.patch.object(API, "_latest", mock.AsyncMock(return_value=None)), \
                mock.patch.dict(OC._OPEN, {}, clear=True):
            return run(API.get_status(API.Ctx(account=ACCOUNT), {}))

    def test_T31_a_prepared_page_held_is_named_by_get_status_as_prepared_not_booked(self):
        out = self._hold_and_draw()
        self.assertEqual(out["status"], "page_link")
        self.assertEqual(out["itinerary"], "It's in your bookings")
        st = self._status()
        self.assertEqual(st["state"], "prepared")
        self.assertIn("Prepared, not booked", st["line"])
        self.assertIn("waiting for you to book it there", st["line"])
        self.assertIn(f"Hammam Al Ándalus — {self.day} 17:00", st["line"])
        self.assertFalse(st["anything_booked"])
        self.assertNotEqual(st["line"], ST.WORDS["nothing"])
        self.assertNotIn("Booked:", st["line"])

    def test_prepared_again_is_one_line_not_three(self):
        for _ in range(3):   # found live: the same page drawn three times
            self._hold_and_draw()
        self.assertEqual(len(self._status()["prepared"]), 1)

    def test_beside_another_venue_it_is_still_said(self):
        self._hold_and_draw()
        st = self._status([{"venue": "Taberna del Olivo", "date": self.day, "time": "21:00", "status": "link_sent"}])
        self.assertEqual(st["state"], "requested")
        self.assertIn("Taberna del Olivo", st["line"])
        self.assertIn("Prepared, not booked", st["line"])
        self.assertIn("Hammam Al Ándalus", st["line"])

    def test_once_it_is_on_the_record_it_is_said_from_there(self):
        self._hold_and_draw()
        st = self._status([{"venue": "Hammam Al Ándalus", "date": self.day, "time": "17:00", "status": "confirmed"}])
        self.assertNotIn("prepared", st)
        self.assertEqual(st["state"], "booked")

    def test_kept_in_the_memory_table_when_there_is_one(self):
        from agapi import s2_memory as M
        kept = {}

        async def put_kind(account, name, value):
            kept[name] = value
            return True

        async def kind(account, name):
            return kept.get(name)
        with mock.patch.object(M, "put_kind", put_kind), mock.patch.object(M, "kind", kind):
            self._hold_and_draw()
            VN._PREPARED.clear()   # a restart, or another worker: the table still answers
            st = self._status()
        self.assertEqual(kept[VN.PREPARED_KIND][0]["venue"], "Hammam Al Ándalus")
        self.assertEqual(st["state"], "prepared")

    def test_a_past_day_is_no_longer_said(self):
        VN._PREPARED[ACCOUNT] = [{"venue": "Old Place", "date": "2020-01-01", "time": "12:00", "party": 2}]
        self.assertEqual(self._status()["state"], "nothing")


if __name__ == "__main__":
    unittest.main()
