"""Sasha 203 · AgAPI v0 and the /next agent — every guard, offline (no network, no database, no model).

  · book needs the person's explicit yes — and the agent passes their REAL words, never the model's
  · v0 is TEST mode only; required inputs; Austen's idempotency keys replay, never repeat
  · the model never sees idempotency_key or approval
  · a reply that claims booked/paid/confirmed without Pacioli, or names a price no tool gave, is caught
"""
import asyncio
import types
import unittest

from agapi import v0 as API
from app.agent import sasha as AG


class Yes(unittest.TestCase):
    def test_explicit_yes(self):
        for t in ("Yes", "yes, book it", "Then book it.", "Go ahead", "OK, let's do it", "Sure", "Perfect, book the whole trip"):
            self.assertTrue(API.explicit_yes(t), t)
        for t in ("", "No", "No. What's the total with the flight and lodging?", "yes but wait", "not yet", "maybe",
                  "what does it cost?", "the BA one", "hold on, yes"):
            self.assertFalse(API.explicit_yes(t), t)


class Contract(unittest.TestCase):
    def ctx(self, **kw):
        return API.Ctx(account="00000000-0000-4000-8000-000000000001", **kw)

    def test_book_without_a_yes_is_refused_before_anything_moves(self):
        r = asyncio.run(API.call(self.ctx(), "book", {"read_back_sha256": "x" * 64, "idempotency_key": "k" * 12,
                                                      "approval": {"said": "what's the total?"}}))
        self.assertEqual(r["error"]["code"], "no_explicit_yes")

    def test_live_mode_is_refused(self):
        r = asyncio.run(API.call(self.ctx(mode="live"), "get_total", {}))
        self.assertEqual(r["error"]["code"], "mode_not_available")

    def test_missing_input_and_unknown_tool(self):
        self.assertEqual(asyncio.run(API.call(self.ctx(), "search_flights", {"origin": "MAD"}))["error"]["code"], "missing_input")
        self.assertEqual(asyncio.run(API.call(self.ctx(), "book", {"read_back_sha256": "x"}))["error"]["code"], "missing_input")   # no key
        self.assertEqual(asyncio.run(API.call(self.ctx(), "teleport", {}))["error"]["code"], "unknown_tool")

    def test_austen_replays_an_idempotency_key(self):
        n = {"calls": 0}

        async def act(ctx, a):
            n["calls"] += 1
            return {"done": n["calls"]}
        API.BY_NAME["_t_idem"] = {"name": "_t_idem", "agent": "Austen", "fn": act, "idempotent": True,
                                  "input_schema": {"type": "object", "properties": {}, "required": ["idempotency_key"]}}
        try:
            a = asyncio.run(API.call(self.ctx(), "_t_idem", {"idempotency_key": "same-key-1"}))
            b = asyncio.run(API.call(self.ctx(), "_t_idem", {"idempotency_key": "same-key-1"}))
        finally:
            API.BY_NAME.pop("_t_idem")
        self.assertEqual(n["calls"], 1)
        self.assertEqual(a["result"], b["result"])
        self.assertTrue(b.get("replayed"))

    def test_the_model_never_sees_the_key_or_the_approval(self):
        for t in API.TOOLS:
            s = API.schema_for_model(t)["input_schema"]
            self.assertNotIn("idempotency_key", s["properties"], t["name"])
            self.assertNotIn("approval", s["properties"], t["name"])
        self.assertEqual({t["agent"] for t in API.TOOLS}, {"Magellan", "Sherlock", "Austen", "Pacioli"})
        self.assertTrue(all(t["idempotent"] == (t["agent"] == "Austen") for t in API.TOOLS))


class ReplyGuard(unittest.TestCase):
    def test_a_claim_without_pacioli_is_caught(self):
        self.assertTrue(AG.guard_check("Lovely — it's all booked!", set(), anything_booked=False))
        self.assertFalse(AG.guard_check("Lovely — it's all booked!", set(), anything_booked=True))
        self.assertFalse(AG.guard_check("Nothing's booked yet — tap to pay on your phone.", set(), anything_booked=False))

    def test_a_price_no_tool_gave_is_caught(self):
        self.assertTrue(AG.guard_check("The whole trip comes to about €1,999.", {1468.14}, False))
        self.assertFalse(AG.guard_check("The whole trip comes to about €1,468.", {1468.14}, False))
        self.assertFalse(AG.guard_check("Your total is €1,468.14.", {1468.14}, False))

    def test_fillers_never_carry_a_fact_and_never_repeat(self):
        used = []
        for line in ("Ooh, Hoi An at lantern time — let me see what's around then.", "Right, let me see."):
            self.assertTrue(AG.filler_ok(line, used), line)
            used.append(line)
        self.assertFalse(AG.filler_ok("Right, let me see.", used))                       # never twice
        for bad in ("That's about €1,468.", "I've booked it!", "Your payment went through.", "Prices are great in May.",
                    "Flights from 300 euros.", "I'll confirm it now.", "Shall I look?", "I promise it's lovely."):
            self.assertFalse(AG.filler_ok(bad, []), bad)                                  # never a fact or a question

    def test_s210_the_acknowledgement_fits_what_she_does_and_is_never_said_twice(self):
        lines = [asyncio.run(AG.make_filler("Vietnam!", "propose_trip", "t-dup")) for _ in range(12)]
        AG._USED.pop("t-dup", None)
        AG._OPENERS.pop("t-dup", None)
        self.assertEqual(lines[0], "Let me put that together.")
        said = [x for x in lines if x]
        self.assertEqual(len(said), len({AG._norm(x) for x in said}))                   # never twice
        self.assertTrue(all(AG.filler_ok(x, []) for x in said))                         # never a fact, never an answer's opener
        self.assertEqual(lines[-1], "")                                                  # every fitting line spent: silence

    def test_s210_the_model_never_sees_test_notes_or_disclaimers(self):
        r = AG.clean_for_model({"read_back": ["⚠ TEST bookings — no hotel or airline is contacted, nothing is reserved and nothing is charged. For 2.",
                                              "Total €1468.14 (TEST) — ONE tap to pay on your phone: Apple Pay or a saved card on Stripe's TEST page.",
                                              "Each goes in your itinerary on its day, marked TEST, with its reference."],
                                "note": "Duffel TEST fares — nothing is held until book", "total_eur": 1468.14})
        self.assertNotIn("note", r)
        self.assertEqual(len(r["read_back"]), 2)
        self.assertNotIn("TEST", " ".join(r["read_back"]))
        self.assertIn("€1468.14", r["read_back"][0])
        self.assertEqual(r["total_eur"], 1468.14)

    def test_s210_openers_and_internals(self):
        self.assertEqual(AG.opener_of("Lovely — Vietnam in November!"), "lovely")
        self.assertEqual(AG.opener_of("Great choice! It's swapped."), "great")
        self.assertIsNone(AG.opener_of("Lovely to meet you."))                 # a word, not an interjection: kept
        self.assertEqual(AG.strip_openers("Ooh, lovely — let me look."), "Let me look.")
        self.assertEqual(AG.drop_internal("I don't want to pass on bad info. That flight's gone — here's the closest one."),
                         "That flight's gone — here's the closest one.")
        for bad in ("Just so you know, these aren't real bookings.", "It's a test, so nothing is charged.", "My search tool timed out.",
                    "The demo spa is ours."):
            self.assertEqual(AG.drop_internal(bad), "", bad)

    def test_the_last_resort_strips_only_the_bad_sentence(self):
        out = AG.guard_strip("Good choice. The total is €9,999. Shall I book it?", ["price: €9,999 did not come from a tool"])
        self.assertNotIn("9,999", out)
        self.assertIn("Shall I book it?", out)


class _Block(types.SimpleNamespace):
    def model_dump(self, exclude_none=True):
        return {k: v for k, v in self.__dict__.items() if v is not None}


class _Stream:
    def __init__(self, final):
        self.final = final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        async def gen():
            for b in self.final.content:
                if b.type == "text":
                    yield types.SimpleNamespace(type="text", text=b.text)
        return gen()

    async def get_final_message(self):
        return self.final


class TheAgentPassesTheRealWords(unittest.TestCase):
    def test_book_gets_the_persons_words_never_the_models(self):
        """The model calls book with its own approval "yes" while the person asked a question: book is refused."""
        steps = [types.SimpleNamespace(content=[_Block(type="tool_use", id="t1", name="book",
                                                       input={"read_back_sha256": "a" * 64, "approval": {"said": "yes"}})]),
                 types.SimpleNamespace(content=[_Block(type="text", text="Not booked — I need your yes first.")])]
        seen = []

        class Msgs:
            def stream(self, **kw):
                return _Stream(steps.pop(0))

            async def create(self, **kw):
                return types.SimpleNamespace(content=[_Block(type="text", text="ok")])
        import app.services.llm as LLM
        real_client, real_call = LLM.client, API.call

        async def spy(ctx, name, args):
            seen.append((name, dict(args)))
            if name == "book":
                return await real_call(ctx, name, args)
            return {"ok": True, "result": {"anything_booked": False}}
        LLM.client, API.call = types.SimpleNamespace(messages=Msgs()), spy
        try:
            async def run():
                return [ev async for ev in AG.turn("00000000-0000-4000-8000-000000000001", "What's the total?", [], "t")]
            evs = asyncio.run(run())
        finally:
            LLM.client, API.call = real_client, real_call
        book = next(a for n, a in seen if n == "book")
        self.assertEqual(book["approval"]["said"], "What's the total?")
        tool_ev = next(e for e in evs if e["type"] == "tool")
        self.assertEqual((tool_ev["ok"], tool_ev.get("error")), (False, "no_explicit_yes"))


class NeverSilent(unittest.TestCase):
    def test_quiver_timing(self):
        from app.agent.fakes import quiver_checks
        for name, (good, detail) in asyncio.run(quiver_checks()).items():
            self.assertTrue(good, f"{name}: {detail}")


class EveryResultIsRendered(unittest.TestCase):
    def test_each_tools_result_type_has_a_renderer(self):
        import os
        from agapi import v0 as API
        self.assertEqual(set(AG.RENDER), set(API.BY_NAME) - {n for n in API.BY_NAME if n.startswith("_t_")}, "a tool without a renderer")
        self.assertTrue(set(AG.RENDER.values()) <= AG.KINDS)
        chat = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "app", "components", "SashaChat.tsx")
        if os.path.exists(chat):
            src = open(chat, encoding="utf-8").read()
            for kind in AG.KINDS - {"inline"}:
                self.assertIn(f"ev.kind === '{kind}'", src, f"the /next UI doesn't render '{kind}'")


class TheDocIsTheContract(unittest.TestCase):
    def test_api_v0_md_is_generated_from_the_module(self):
        import os
        from scripts import agapi_doc
        if not os.path.exists(agapi_doc.OUT):
            self.skipTest("docs/ is not in this checkout (a backend-only build)")
        self.assertEqual(open(agapi_doc.OUT, encoding="utf-8").read(), agapi_doc.render(),
                         "docs/agapi/api-v0.md is stale — run: python -m scripts.agapi_doc")


if __name__ == "__main__":
    unittest.main()
