"""CR 71 · S2 on AgAPI — SASHA_S2_VIA_AGAPI (0 · shadow · reads · 1), read ONLY at /s2's own tool selection. Offline: a scripted
model, a stand-in for agapi.v0.call and for AgAPI (no call leaves a test).

  S1 / /next   in EVERY mode (and an unrecognised one): byte-identical to the switch being unset, and ZERO AgAPI calls
  S2 0         exactly as today: zero AgAPI calls
  S2 shadow    Sasha's own answer is the one used; AgAPI is asked alongside, compared, logged; its failure changes nothing
  S2 reads     search_flights from AgAPI (the same Duffel offers), fed into the basket as her own search does; nothing from AgAPI →
               Sasha answers; search_venues stays Sasha's
  S2 1         acts stay on Sasha's engine (until AgAPI accepts S2's in-chat yes)
  token        each guest's own token goes with S2's AgAPI calls; /next never sets it

    cd backend && python -m unittest tests.test_s2_via_agapi -v
"""
from __future__ import annotations

import asyncio
import json
import os
import unittest
from unittest import mock

from agapi import v0 as API
from agapi import via_agapi as VIA
from app.agent.fakes import Block, client

ACCOUNT = "00000000-0000-4000-8000-000000000071"
FLIGHTS = {"origin": "Madrid", "destination": "London", "date": "2026-11-12", "passengers": 1}
SASHA_FLIGHTS = {"ok": True, "result": {"leg": "out", "date": "2026-11-12", "note": "Duffel TEST fares — nothing is held until book", "flights": [
    {"offer_id": "off_1", "airline": "Iberia", "flights": "IB 3166", "from": "MAD", "to": "LHR", "departs": "2026-11-12T07:30:00+01:00",
     "arrives": "2026-11-12T09:00:00+00:00", "stops": 0, "duration_minutes": 150, "price_eur": 98.4, "test": True}]}}
AGAPI_FLIGHTS = {"ok": True, "result": {"offers": [
    {"offer_ref": "off_1", "carrier": {"code": "IB", "name": {"text": "Iberia"}}, "flight_numbers": ["IB3166"], "from": "MAD", "to": "LHR",
     "departs": "2026-11-12T07:30:00+01:00", "arrives": "2026-11-12T09:00:00+00:00", "stops": 0, "duration_minutes": 150,
     "price": {"amount_minor": 9840, "currency": "EUR"}, "expires_at": "2026-11-01T10:00:00.000000Z"},
    {"offer_ref": "off_2", "carrier": {"code": "UX", "name": {"text": "Air Europa"}}, "flight_numbers": ["UX1013"], "from": "MAD", "to": "LGW",
     "departs": "2026-11-12T10:00:00+01:00", "arrives": "2026-11-12T11:30:00+00:00", "stops": 0, "duration_minutes": 150,
     "price": {"amount_minor": 12000, "currency": "EUR"}, "expires_at": "2026-11-01T10:00:00.000000Z"}]}}


def run(c):
    return asyncio.run(c)


class Recorder:
    """Stands in for agapi.v0.call (Sasha's own engine) and for AgAPI (VIA.CALL)."""

    def __init__(self, agapi=None):
        self.engine, self.agapi, self.tokens = [], [], []
        self.agapi_answer = agapi if agapi is not None else AGAPI_FLIGHTS

    async def call(self, ctx, name, args):
        self.engine.append((name, json.dumps(args, sort_keys=True)))
        if name == "search_flights":
            return json.loads(json.dumps(SASHA_FLIGHTS))
        if name == "search_venues":
            return {"ok": True, "result": {"venues": [{"name": "Casa Marea"}, {"name": "El Fogón Viejo"}]}}
        return {"ok": True, "result": {"status": "done", "tool": name}}

    async def via(self, op, body):
        self.agapi.append((op, body))
        self.tokens.append(VIA.GUEST_TOKEN.get())
        if isinstance(self.agapi_answer, Exception):
            raise self.agapi_answer
        if op == "venues.find_venues":
            return {"ok": True, "result": {"venues": [{"name": {"text": "Casa Marea"}}, {"name": {"text": "Bistró Salvia"}}]}}
        return self.agapi_answer


def scripted_turn(surface, tool, args, rec, env_mode=None, token=None):
    """One turn with a scripted model that calls `tool` once, then speaks. → (events, model calls)."""
    import app.services.llm as LLM
    from app.agent import sasha as AG
    steps = [[Block(type="tool_use", id="t1", name=tool, input=args)], [Block(type="text", text="Here's what I found.")]]
    evs = []

    async def go():
        if token:
            VIA.GUEST_TOKEN.set(token)
        async for e in AG.turn(ACCOUNT, "find me a flight", [], f"via-{surface}-{tool}", None, surface):
            evs.append(e)
        if VIA.SHADOW_TASKS:
            await asyncio.gather(*list(VIA.SHADOW_TASKS))
    env = {"SASHA_S2_VIA_AGAPI": env_mode} if env_mode is not None else {}
    with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(LLM, "client", client(steps)), \
            mock.patch.object(API, "call", rec.call), mock.patch.object(VIA, "CALL", rec.via), \
            mock.patch.object(API, "_latest", mock.AsyncMock(return_value=None)):
        if env_mode is None:
            os.environ.pop("SASHA_S2_VIA_AGAPI", None)
        run(go())
    return [e for e in evs if e.get("type") in ("text", "tool", "done", "render", "say")]


def norm(evs):
    """Events, without timings (the only field that may differ between two identical runs)."""
    out = []
    for e in evs:
        e = {k: v for k, v in e.items() if k not in ("ms", "steps", "step_ms", "timing", "first_text_ms")}
        out.append(json.dumps(e, sort_keys=True, default=str))
    return out


class S1Untouched(unittest.TestCase):
    def test_s1_fingerprint_is_identical_in_every_mode_with_zero_agapi_calls(self):
        base_rec = Recorder()
        base = norm(scripted_turn("s1", "search_flights", FLIGHTS, base_rec))
        self.assertEqual(base_rec.engine[0][0], "search_flights")
        for m in ("0", "shadow", "reads", "1", "garbage"):
            rec = Recorder()
            got = norm(scripted_turn("s1", "search_flights", FLIGHTS, rec, env_mode=m, token="guest-token-x"))
            self.assertEqual(got, base, m)                                                   # byte-identical to the switch unset
            self.assertEqual(rec.engine, base_rec.engine, m)                                 # the same tool calls, through v0.call
            self.assertEqual(rec.agapi, [], m)                                               # ZERO AgAPI calls

    def test_next_never_reads_the_switch_nor_sets_a_token(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.agent import sasha as AG
        seen = []

        async def fake(account, message, history, session, surface="s1"):
            seen.append((surface, VIA.GUEST_TOKEN.get()))
            yield {"type": "done", "text": "ok", "guard": [], "tools": []}
        app = FastAPI()
        app.include_router(AG.router)
        c = TestClient(app)
        with mock.patch("app.services.chat_account.chat_account", mock.AsyncMock(return_value=ACCOUNT)), \
                mock.patch("app.services.chat_account.signed_in", lambda a: True), mock.patch.object(AG, "turn_with_quiver", fake), \
                mock.patch.object(AG, "over_budget", mock.AsyncMock(return_value=None)):
            for m in ("0", "shadow", "reads", "1"):
                with mock.patch.dict(os.environ, {"SASHA_S2_VIA_AGAPI": m}):
                    c.post("/api/agent/turn", json={"message": "hi"}, headers={"authorization": "Bearer guest-token-next"})
            c.post("/api/agent/turn", json={"message": "hi"}, headers={"authorization": "Bearer guest-token-s2", "x-sasha-surface": "s2"})
        self.assertEqual(seen[:4], [("s1", None)] * 4)                                       # /next: no token, whatever the mode
        self.assertEqual(seen[4], ("s2", "guest-token-s2"))                                   # /s2: this guest's own token

    def test_the_switch_is_read_only_in_s2s_block(self):
        import inspect
        from app.agent import sasha as AG
        src = inspect.getsource(AG)
        self.assertEqual(src.count("VIA.runner("), 1)
        i = src.index("VIA.runner(")
        block = src[src.rindex('if surface == "s2":', 0, i):i]
        self.assertIn("S2.S2_TOOLS", block)                                                   # inside /s2's own tool selection
        self.assertNotIn("SASHA_S2_VIA_AGAPI", src.replace("# CR 71 · SASHA_S2_VIA_AGAPI", ""))   # never read in the shared path


class S2Modes(unittest.TestCase):
    def test_mode_0_is_exactly_today(self):
        base = Recorder()
        b = norm(scripted_turn("s2", "search_flights", FLIGHTS, base))
        rec = Recorder()
        self.assertEqual(norm(scripted_turn("s2", "search_flights", FLIGHTS, rec, env_mode="0")), b)
        self.assertEqual(rec.agapi, [])

    def test_shadow_uses_sashas_answer_and_logs_the_difference(self):
        base = norm(scripted_turn("s2", "search_flights", FLIGHTS, Recorder(), env_mode="0"))
        VIA.SHADOW_LOG.clear()
        rec = Recorder()
        got = norm(scripted_turn("s2", "search_flights", FLIGHTS, rec, env_mode="shadow", token="guest-token-1"))
        self.assertEqual(got, base)                                                           # nothing from AgAPI is shown
        self.assertEqual([op for op, _ in rec.agapi], ["travel.find_flights"])
        self.assertEqual(rec.tokens, ["guest-token-1"])                                       # as this guest
        e = VIA.SHADOW_LOG[-1]
        self.assertEqual((e["tool"], e["same"], e["sasha_n"], e["agapi_n"]), ("search_flights", False, 1, 2))
        self.assertTrue(any("UX1013" in x for x in e["only_agapi"]))

    def test_shadow_survives_agapi_failing(self):
        base = norm(scripted_turn("s2", "search_flights", FLIGHTS, Recorder(), env_mode="0"))
        VIA.SHADOW_LOG.clear()
        rec = Recorder(agapi=ConnectionError("down"))
        self.assertEqual(norm(scripted_turn("s2", "search_flights", FLIGHTS, rec, env_mode="shadow")), base)
        self.assertEqual(VIA.SHADOW_LOG[-1]["same"], False)

    def test_reads_serves_flights_from_agapi_into_the_basket(self):
        rec = Recorder()
        fed = []

        async def suggest(ctx, trip_id, cards, *a):
            fed.append([c["id"] for c in cards])
            return []
        with mock.patch.object(API, "_suggest_flights", suggest), mock.patch.object(API, "_latest", mock.AsyncMock(return_value={"trip_id": "t1"})):
            ctx = API.Ctx(account=ACCOUNT, surface="s2")
            with mock.patch.object(VIA, "CALL", rec.via):
                r = run(VIA.runner(rec.call, "reads")(ctx, "search_flights", FLIGHTS))
        self.assertEqual([f["offer_id"] for f in r["result"]["flights"]], ["off_1", "off_2"])  # AgAPI's offers, Sasha's card shape
        self.assertEqual(r["result"]["flights"][1]["price_eur"], 120.0)
        self.assertEqual(fed, [["off_1", "off_2"]])                                            # the basket gets them, as her search does
        self.assertEqual(rec.engine, [])                                                       # Sasha's engine wasn't needed

    def test_reads_falls_back_to_sasha_when_agapi_has_nothing(self):
        rec = Recorder(agapi={"ok": True, "result": {"offers": []}})
        ctx = API.Ctx(account=ACCOUNT, surface="s2")
        with mock.patch.object(VIA, "CALL", rec.via), mock.patch.object(API, "_latest", mock.AsyncMock(return_value=None)):
            r = run(VIA.runner(rec.call, "reads")(ctx, "search_flights", FLIGHTS))
        self.assertEqual(r["result"]["flights"][0]["offer_id"], "off_1")
        self.assertEqual([n for n, _ in rec.engine], ["search_flights"])

    def test_venues_stay_sashas_in_reads_and_acts_stay_sashas_in_1(self):
        for m in ("reads", "1"):
            rec = Recorder()
            ctx = API.Ctx(account=ACCOUNT, surface="s2")

            async def go():
                runner = VIA.runner(rec.call, m)
                v = await runner(ctx, "search_venues", {"what": "dinner", "where": "Madrid"})
                b = await runner(ctx, "book_venue", {"approval": {"said": "yes"}})
                await asyncio.gather(*list(VIA.SHADOW_TASKS))
                return v, b
            with mock.patch.object(VIA, "CALL", rec.via), mock.patch.dict(os.environ, {"SASHA_S2_SHADOW_TOOLS": "search_flights,search_venues"}):
                v, b = run(go())   # Sasha 225 · venues compared only when listed (SASHA_S2_SHADOW_TOOLS)
            self.assertEqual(v["result"]["venues"][0]["name"], "Casa Marea")                   # Sasha's own cards
            self.assertEqual(b["result"]["tool"], "book_venue")
            self.assertEqual([n for n, _ in rec.engine], ["search_venues", "book_venue"])
            self.assertEqual([op for op, _ in rec.agapi], ["venues.find_venues"])               # venues compared; the act never sent to AgAPI

    def test_by_default_only_flights_are_shadowed(self):   # Sasha 225 · venue shadowing would spend Places calls
        rec = Recorder()
        ctx = API.Ctx(account=ACCOUNT, surface="s2")

        async def go():
            await VIA.runner(rec.call, "shadow")(ctx, "search_venues", {"what": "dinner", "where": "Madrid"})
            await asyncio.gather(*list(VIA.SHADOW_TASKS))
        with mock.patch.object(VIA, "CALL", rec.via), mock.patch.dict(os.environ, {"SASHA_S2_SHADOW_TOOLS": ""}):
            os.environ.pop("SASHA_S2_SHADOW_TOOLS", None)
            run(go())
        self.assertEqual(rec.agapi, [])
        self.assertEqual([n for n, _ in rec.engine], ["search_venues"])

    def test_modes_and_the_flip_back(self):
        for raw, want in (("", "0"), ("0", "0"), ("shadow", "shadow"), ("READS", "reads"), ("1", "1"), ("yes", "0")):
            with mock.patch.dict(os.environ, {"SASHA_S2_VIA_AGAPI": raw}):
                self.assertEqual(VIA.mode(), want, raw)
        base = object()
        with mock.patch.dict(os.environ, {"SASHA_S2_VIA_AGAPI": "0"}):
            self.assertIs(VIA.runner(base), base)                                               # 0: v0.call itself — nothing wrapped


class Client(unittest.TestCase):
    def test_the_guest_token_and_the_key_go_with_each_call(self):
        sent = []

        class R:
            def json(self):
                return {"ok": True, "result": {}}

        class C:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def post(self, url, headers=None, content=None):
                sent.append((url, dict(headers)))
                return R()

        async def go():
            VIA.GUEST_TOKEN.set("guest-token-7")
            return await VIA._agapi("travel.find_flights", {})
        with mock.patch("httpx.AsyncClient", C), mock.patch.dict(os.environ, {"SASHA_AGAPI_KEY": "agp_live_" + "x" * 32,
                                                                              "SASHA_AGAPI_URL": "https://agapi-live.example"}):
            run(go())
        url, h = sent[0]
        self.assertEqual(url, "https://agapi-live.example/v1/travel.find_flights")
        self.assertEqual((h["X-Sasha-Guest-Token"], h["Authorization"][:16]), ("guest-token-7", "Bearer agp_live_"))
        with mock.patch.dict(os.environ, {"SASHA_AGAPI_KEY": ""}):
            self.assertEqual(run(VIA._agapi("x", {}))["error"]["code"], "not_configured")


if __name__ == "__main__":
    unittest.main()
