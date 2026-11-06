"""Sasha 353 · THE MODEL GATEWAY (docs/sasha/S-353-model-gateway.md): every model call through ONE place — caps refused loudly, only what a
turn needs, the fixed parts cached, the gate on recorded replies. The SDK's own client runs here against a mock transport (nothing sent).

    cd backend && python -m unittest tests.test_s353_gateway -v
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import pathlib
import re
import unittest
from unittest import mock

import anthropic
import httpx

import booking_signer  # noqa: F401 — installs the gateway, as the service does (app.main mounts booking_signer)
from booking_signer import model_gateway as MG
from app.agent import tool_need as TN

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPLY = {"id": "msg_test", "type": "message", "role": "assistant", "model": "claude-haiku-4-5", "stop_reason": "end_turn",
         "stop_sequence": None, "content": [{"type": "text", "text": "Hello."}],
         "usage": {"input_tokens": 1000, "output_tokens": 50, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 9000}}


def client(sent: list):
    def handler(req: httpx.Request):
        sent.append(json.loads(req.content))
        return httpx.Response(200, json=REPLY)
    return anthropic.AsyncAnthropic(api_key="test-key", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


class Mem:
    def __init__(self, kept=None):
        self.kept, self.saved = kept, []

    async def load(self, day):
        return self.kept

    async def save(self, day, data):
        self.saved.append(data)


class Replays:
    def __init__(self):
        self.d = {}

    async def get(self, k):
        return self.d.get(k)

    async def put(self, k, v):
        self.d[k] = v


def fresh(kept=None):
    MG._DAY.update(day=None, total=0, accounts={}, models={}, callers={}, loaded=False)
    MG.STORE = Mem(kept)
    return MG.STORE


def run(c):
    return asyncio.run(c)


class EveryCallPassesHere(unittest.TestCase):
    def test_the_sdk_itself_is_the_gateway(self):
        """Whatever else wraps the SDK (the gate's own meter), a call passes the gateway: over its cap, it is refused and never sent."""
        fresh()
        sent = []
        try:
            with mock.patch.dict(os.environ, {"SASHA_MODEL_DAILY_TOKENS": "0", "SASHA_MODEL_REPLAY": ""}), \
                    self.assertLogs("booking_signer.model_gateway", "ERROR"), self.assertRaises(MG.ModelBudgetExceeded):
                run(client(sent).messages.create(model="claude-haiku-4-5", max_tokens=1, messages=[{"role": "user", "content": "x"}]))
        finally:
            MG.STORE = None
        self.assertEqual(sent, [])
        self.assertTrue(MG._INSTALLED["on"])

    def test_the_service_installs_it_where_it_starts(self):
        main = (ROOT / "app" / "main.py").read_text()
        self.assertIn("from booking_signer.routes import router as booking_signer_router", main)   # importing booking_signer installs it
        self.assertIn("_MG.install()", (ROOT / "booking_signer" / "__init__.py").read_text())
        self.assertIn("_MG.install()", (ROOT / "scripts" / "gate.py").read_text())

    def test_nothing_reaches_the_api_another_way(self):
        hits = []
        for d in ("app", "agapi", "booking_signer", "products", "scripts"):
            for f in (ROOT / d).rglob("*.py"):
                s = f.read_text(encoding="utf-8", errors="ignore")
                if re.search(r"api\.anthropic\.com/v1|x-api-key|anthropic-version", s):   # a host ping (perf_ops) is no model call
                    hits.append(str(f.relative_to(ROOT)))
        self.assertEqual(hits, [])


class TheCaps(unittest.TestCase):
    def setUp(self):
        fresh()

    def tearDown(self):
        MG.STORE = None
        fresh()

    def test_metered_then_refused_loudly_per_account(self):
        sent = []
        c = client(sent)

        async def go():
            tok = MG.ACCOUNT.set("acct-1")
            try:
                await c.messages.create(model="claude-haiku-4-5", max_tokens=10, messages=[{"role": "user", "content": "hi"}])
                with self.assertRaises(MG.ModelBudgetExceeded) as e:
                    await c.messages.create(model="claude-haiku-4-5", max_tokens=10, messages=[{"role": "user", "content": "again"}])
                return str(e.exception)
            finally:
                MG.ACCOUNT.reset(tok)
        with mock.patch.dict(os.environ, {"SASHA_MODEL_ACCOUNT_DAILY_TOKENS": "5000", "SASHA_MODEL_REPLAY": ""}), self.assertLogs("booking_signer.model_gateway", "ERROR"):
            said = run(go())
        self.assertEqual(len(sent), 1)                                                   # the refused call was never sent
        self.assertIn("this account's daily model budget is reached (10,050 of 5,000", said)
        self.assertEqual(MG.today()["total"], 10050)

    def test_the_global_cap_and_a_restart_never_resets_it(self):
        fresh(kept={"total": 999_000, "accounts": {}, "models": {}, "callers": {}})   # what the day's record already holds
        sent = []

        async def go():
            await client(sent).messages.create(model="claude-haiku-4-5", max_tokens=5, messages=[{"role": "user", "content": "x"}])
        with mock.patch.dict(os.environ, {"SASHA_MODEL_DAILY_TOKENS": "1000000", "SASHA_MODEL_REPLAY": ""}):
            run(go())
            self.assertEqual(MG.today()["total"], 1_009_050)
            with self.assertRaises(MG.ModelBudgetExceeded):
                run(go())
        self.assertEqual(len(sent), 1)

    def test_a_stream_is_capped_and_metered_too(self):
        def handler(req):
            body = ("event: message_start\ndata: " + json.dumps({"type": "message_start", "message": {**REPLY, "content": [],
                    "usage": {"input_tokens": 700, "output_tokens": 1}}}) + "\n\n"
                    "event: message_delta\ndata: " + json.dumps({"type": "message_delta", "delta": {"stop_reason": "end_turn"},
                                                                  "usage": {"output_tokens": 3}}) + "\n\n"
                    "event: message_stop\ndata: {\"type\": \"message_stop\"}\n\n")
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
        c = anthropic.AsyncAnthropic(api_key="k", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

        async def go():
            async with c.messages.stream(model="claude-sonnet-5-5", max_tokens=5, messages=[{"role": "user", "content": "x"}]) as s:
                await s.get_final_message()
        with mock.patch.dict(os.environ, {"SASHA_MODEL_REPLAY": ""}):
            run(go())
        self.assertGreaterEqual(MG.today()["total"], 703)


class OnlyWhatItNeeds(unittest.TestCase):
    def test_history_is_the_recent_turns_and_never_splits_a_tool_pair(self):
        msgs = []
        for i in range(12):
            msgs += [{"role": "user", "content": f"q{i}"},
                     {"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": "get_trip", "input": {}}]},
                     {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": "ok"}]},
                     {"role": "assistant", "content": f"a{i}"}]
        out = MG.trim_history(msgs, 8)
        self.assertEqual(out[0], {"role": "user", "content": "q4"})                      # a turn's start: their words
        self.assertEqual(len(out), 32)
        self.assertEqual(MG.trim_history(msgs[:8], 8), msgs[:8])                        # short: untouched

    def test_the_fixed_parts_are_cached_and_opus_is_sonnet(self):
        kw = MG.prepare({"model": "claude-opus-5-5", "system": "S" * 5000, "tools": [{"name": "a"}, {"name": "b"}],
                         "messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(kw["model"], MG.SONNET)
        self.assertEqual(kw["tools"][-1]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(kw["system"][0]["cache_control"], {"type": "ephemeral"})
        with mock.patch.dict(os.environ, {"SASHA_MODEL_ALLOW_OPUS": "1"}):
            self.assertEqual(MG.choose_model("claude-opus-5-5"), "claude-opus-5-5")
        marked = MG.with_cache({"system": [{"type": "text", "text": "x", "cache_control": {"type": "ephemeral"}}],
                                "tools": [{"name": "a", "cache_control": {"type": "ephemeral"}}]})
        self.assertEqual(json.dumps(marked).count("cache_control"), 2)                 # the caller's marks kept, none added

    def test_a_turn_offers_only_the_families_its_words_and_record_ask_for(self):
        fam = TN.families
        self.assertEqual(fam("Hi Sasha!"), {"core", "find"})
        self.assertIn("plan", fam("Two of us, flying from Madrid for 5 nights"))
        self.assertNotIn("group", fam("Two of us, flying from Madrid for 5 nights"))
        self.assertEqual(fam("Book it.", [], trip=True, places=False), {"core", "book"})       # the trip waiting on it
        self.assertEqual(fam("Yes.", [], trip=False, places=True), {"core", "reserve", "find"})   # the place on their screen (found first)
        self.assertTrue({"book", "reserve"} <= fam("Book it."))                                # unknown: either booking
        self.assertIn("group", fam("Book all", []))
        venue = fam("Uh, a table for two at the Sasha Test Venue in Madrid, Saturday at nine at night, please.")
        self.assertTrue({"reserve", "find"} <= venue)
        self.assertNotIn("plan", venue)                                                      # "nine at night" is a time, not a trip's nights
        self.assertIn("plan", fam("Five nights in Lisbon"))
        self.assertIn("plan", fam("Yes", [{"role": "assistant", "content": "Do you need flights as well?"}]))   # her last line
        tools = [{"name": n} for ns in TN.FAMILIES.values() for n in ns] + [{"name": "a_new_tool"}]
        got = {t["name"] for t in TN.select(tools, "Hi Sasha!")}
        self.assertIn("a_new_tool", got)                                                     # never dropped by omission
        self.assertNotIn("group_book", got)
        self.assertIn("hold_booking", {t["name"] for t in TN.select(tools, "Hi", keep=["hold_booking"])})

    def test_a_rule_about_a_tool_not_offered_is_left_out(self):
        text = "## Rules\n\n- **To book:** call `hold_booking` then `book`.\n- **Places:** `search_venues` first.\n- **Tone.** Warm.\n"
        out = TN.system_for(text, {"search_venues"})
        self.assertNotIn("hold_booking", out)
        self.assertIn("`search_venues` first", out)
        self.assertIn("Tone", out)

    def test_the_turn_offers_what_its_code_calls(self):
        src = (ROOT / "app" / "agent" / "sasha.py").read_text()
        self.assertIn("tools = _TN.select(tools, message, history,", src)
        self.assertIn('_by_code = {u.name for u in tap_uses} - {x["name"] for x in tools}', src)
        self.assertIn("base = _TN.system_for(base, offered)", src)
        self.assertIn("if account and _VNh._HELD.get(account):", src)                     # what's waiting for their yes decides
        self.assertIn("_MG.ACCOUNT.set(account or None)", src)


class TheGateReplays(unittest.TestCase):
    def setUp(self):
        fresh()
        MG.REPLAYS = Replays()

    def tearDown(self):
        MG.REPLAYS = None
        MG.STORE = None

    def test_recorded_once_then_replayed_without_the_api_dates_and_ids_aside(self):
        sent = []
        c = client(sent)
        ask = lambda day, oid: {"model": "claude-haiku-4-5", "max_tokens": 20, "messages": [
            {"role": "user", "content": f"Flights on {day} December 2026, offer {oid}"}]}

        async def go():
            with mock.patch.dict(os.environ, {"SASHA_MODEL_REPLAY": "record"}):
                await c.messages.create(**ask("21", "off_0000AbCdEfGhIjKlMn"))
            with mock.patch.dict(os.environ, {"SASHA_MODEL_REPLAY": "replay"}):
                r = await c.messages.create(**ask("29", "off_0000ZzYyXxWwVvUuTt"))   # another day, another offer id: the same ask
                with self.assertRaises(MG.ReplayMissing):
                    await c.messages.create(model="claude-haiku-4-5", max_tokens=5, messages=[{"role": "user", "content": "something new"}])
            return r
        r = run(go())
        self.assertEqual(r.content[0].text, "Hello.")
        self.assertEqual(len(sent), 1)                                                  # only the recording went to the API

    def test_recording_fills_only_whats_missing_and_alike_requests_share_one_call(self):
        sent = []
        c = client(sent)
        ask = {"model": "claude-haiku-4-5", "max_tokens": 5, "messages": [{"role": "user", "content": "Two of us, Vietnam"}]}

        async def go():
            with mock.patch.dict(os.environ, {"SASHA_MODEL_REPLAY": "record"}):
                await asyncio.gather(*[c.messages.create(**ask) for _ in range(3)])   # the loops start alike, at once
                await c.messages.create(**ask)                                       # recorded: answered from it
        run(go())
        self.assertEqual(len(sent), 1)

    def test_a_tools_output_never_changes_the_key_its_call_and_outcome_do(self):
        def msgs(out, err=False, arg="LIS"):
            return {"model": "m", "messages": [{"role": "user", "content": "flights to Lisbon"},
                    {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "search_flights", "input": {"to": arg}}]},
                    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": out, "is_error": err}]}]}
        k = MG.replay_key
        self.assertEqual(k(msgs("checked under two minutes ago, offer A")), k(msgs("searched just now, offer B")))
        self.assertNotEqual(k(msgs("x")), k(msgs("x", err=True)))
        self.assertNotEqual(k(msgs("x")), k(msgs("x", arg="OPO")))

    def test_the_gate_replays_and_its_one_live_check_is_the_haiku_preflight(self):
        gate = (ROOT / "scripts" / "gate.py").read_text()
        self.assertIn('os.environ["SASHA_MODEL_REPLAY"] = "record" if os.getenv("SASHA_GATE_RECORD", "").strip() == "1" else "replay"', gate)
        self.assertEqual(MG.LIVE_IN_REPLAY, ("app.services.model_health",))
        self.assertIn('max_tokens=1', inspect.getsource(__import__("app.services.model_health", fromlist=["x"]).preflight))


if __name__ == "__main__":
    unittest.main()
