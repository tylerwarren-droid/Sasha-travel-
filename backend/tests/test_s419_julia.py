"""Sasha 419 · JULIA, THE LUXURYOFFSEASON VOICE (DESIGN §5, R8, R13; KANOE B3 11:03 and "LUXURYOFFSEASON — Julia" 13:29).

ROOT TEST: (1) the ONE source of every figure she says is offseason.deltas, read through Sasha's one route with Sasha's own key;
(2) her prompt and code hold no figure or decision of their own; (3) no figure reaches her voice without its observation ids — the
post-check (R8) replaces any reply holding a %, amount or date the turn's OBSERVED items don't hold.

The items below are TEST VECTORS shaped as the published contract types them (every field present): fictional places, never shown.

    cd backend && python -m unittest tests.test_s419_julia -v
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import re
import types
import typing
import unittest
from unittest import mock

import kanoe_contract as KC
from products.luxury import julia as J, postcheck as PC, reader as R


def run(c):
    return asyncio.run(c)


MEDIAN = {"kind": "gap", "destination_key": "seed:t1", "destination_name": "Testisle", "hotel_id": None, "hotel_name": None,
          "windows": {"high": {"label": "July", "from": "2037-07-05", "to": "2037-07-26"},
                      "low": {"label": "November", "from": "2037-11-01", "to": "2037-11-22"}},
          "gap_percent": 40, "gap_basis": "median_of_hotels", "hotels_counted": 7, "hotels_closed": None, "stay": None, "closure": None,
          "observation_ids": {"high": ["rob_h1"], "low": ["rob_l1"]}, "measured_at": {"high": "2037-06-01T10:00:00Z", "low": "2037-06-02T10:00:00Z"},
          "freshness": {"state": "fresh", "age_days": 3, "shown_until": "2037-07-01T10:00:00Z"}, "last_measured_at": None}
HOTEL = {**MEDIAN, "hotel_id": "h9", "hotel_name": "Four Seasons Testisle", "gap_basis": "same_room", "gap_percent": 33, "hotels_counted": None,
         "stay": {"room_name": "Deluxe King", "board": "breakfast", "refundable": "yes", "nights": 3, "check_in_weekday": "Sunday",
                  "adults": 2, "children": 0, "rooms": 1, "high_check_in": "2037-07-12", "low_check_in": "2037-11-08"}}
NO_IDS = {**MEDIAN, "destination_key": "seed:t2", "destination_name": "Nowhere", "gap_percent": 61, "observation_ids": None}
OUT = [{"level": "destination", "as_of": "2037-06-05T00:00:00Z", "items": [MEDIAN, NO_IDS]},
       {"level": "hotel", "as_of": "2037-06-05T00:00:00Z", "items": [HOTEL]}]


def ok(text, out=OUT):
    return PC.check(text, out)


class R8ThePostCheck(unittest.TestCase):
    def test_a_supported_figure_with_its_measured_date_is_spoken(self):
        for t in ["Five-star rooms in Testisle started a median 40% lower in November than in July, across 7 hotels, measured on 1 June and 2 June 2037.",
                  "In Testisle, five-star starting prices were a median forty percent lower in November than in July — measured in June 2037.",
                  "The same room at Four Seasons Testisle cost 33% less for 3 nights from Sunday 8 November than from Sunday 12 July, for 2 adults. Measured in June 2037.",
                  "Measured 3 days ago: Testisle's five-star rooms started a median 40% lower in November than in July.",
                  "En Testisle, los hoteles de cinco estrellas empezaban un 40 por ciento más bajos en noviembre que en julio, medido el 2 de junio de 2037.",
                  "En Testisle la mediana fue cuarenta por ciento menos en noviembre que en julio; medido en junio de 2037.",
                  "Hello! Where would you like to go?"]:
            self.assertEqual(ok(t), (True, "ok"), t)

    def test_an_unsupported_figure_is_replaced(self):
        cases = {"Testisle was a median 45% lower in November than in July, measured in June 2037.": "number",
                 "Nowhere was 61% lower in November, measured in June 2037.": "number",             # an item WITHOUT ids supports nothing
                 "Testisle was a median cincuenta y ocho por ciento lower, measured in June 2037.": "number",
                 "Testisle was 40% lower in November than in July.": "no_measured_date",            # a figure without its measured date
                 "Four Seasons Testisle was 40% lower in November, measured in June 2037.": "median_for_hotel",   # a hotel % from a median
                 "Testisle was a median 40% lower in November than in August, measured in June 2037.": "date",    # an unmeasured month
                 "Try Testisle on Friday 13 November, measured in June 2037.": "number",
                 "It cost €1,240 for 3 nights.": "amount", "About 1240 euros a night.": "amount", "Unos 300 dólares.": "amount",
                 "A night there was 412.50 in November.": "number"}
        for t, rule in cases.items():
            self.assertEqual(ok(t), (False, rule), t)

    def test_section_5_refusals(self):
        for t, rule in {"That's guaranteed to be the best price.": "superlative", "El mejor precio está garantizado.": "superlative",
                        "These come from Expedia's agent rates.": "supplier", "Our commission is small.": "commission",
                        "Prices will drop further in December.": "prediction", "Probablemente bajarán en diciembre.": "prediction",
                        "Rooms are available now at Four Seasons Testisle.": "availability"}.items():
            self.assertEqual(ok(t), (False, rule), t)

    def test_with_no_reader_output_no_figure_can_be_said(self):
        self.assertEqual(PC.check("Testisle was 40% lower in November, measured in June 2037.", []), (False, "number"))
        self.assertEqual(PC.check("I can't see the measurements right now.", []), (True, "ok"))

    def test_julias_own_fixed_lines_pass_it(self):
        for lang in J.LANGS:
            for s in (J.HELLO[lang], J.UNREAD[lang], J.NO_MEASUREMENT[lang]):
                self.assertEqual(PC.check(s, []), (True, "ok"), s)


def scripted(steps, seen):
    steps = list(steps)

    async def create(**kw):
        seen.append(copy.deepcopy(kw["messages"]))
        return types.SimpleNamespace(content=steps.pop(0))
    return types.SimpleNamespace(messages=types.SimpleNamespace(create=create))


def B(**kw):
    return types.SimpleNamespace(**kw)


class TheTurn(unittest.TestCase):
    def go(self, steps, reader, history=(), lang="en"):
        import app.services.llm as LLM
        seen, calls = [], []

        async def post(url, key, op, body, headers, timeout):
            calls.append((url, key, op, body, headers.get("Authorization")))
            return reader(body)
        with mock.patch.object(LLM, "client", scripted(steps, seen)), \
                mock.patch("agapi.agapi_route.post", post), \
                mock.patch.dict("os.environ", {"SASHA_AGAPI_URL": "https://agapi.example", "SASHA_AGAPI_KEY": "agp_live_" + "x" * 32,
                                               "SASHA_AGAPI_ROUTE": ""}):
            out = run(J.turn("How is Testisle in November?", lang, list(history)))
        return out, calls, seen

    ASK = [[B(type="tool_use", id="t1", name="offseason_deltas", input={"level": "destination"})]]

    def test_she_introduces_herself_before_anything_else(self):
        out, _, _ = self.go(self.ASK + [[B(type="text", text="Testisle was a median 40% lower in November than in July, measured in June 2037.")]],
                            lambda b: {"ok": True, "result": OUT[0]})
        self.assertTrue(out["say"].startswith("Hi, I'm Julia, an AI for Luxury Offseason."), out["say"])
        self.assertIn("40%", out["say"])
        again, _, _ = self.go(self.ASK + [[B(type="text", text="Testisle was a median 40% lower in November than in July, measured in June 2037.")]],
                              lambda b: {"ok": True, "result": OUT[0]},
                              history=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": J.HELLO["en"]}])
        self.assertFalse(again["say"].startswith("Hi, I'm Julia"), again["say"])
        es, _, _ = self.go([[B(type="text", text="¿Adónde quieres ir?")]], lambda b: {"ok": True, "result": OUT[0]}, lang="es")
        self.assertTrue(es["say"].startswith("Hola, soy Julia, una inteligencia artificial de Luxury Offseason."), es["say"])

    def test_until_cr_229_she_says_she_cant_see_them(self):
        unknown = lambda b: {"ok": False, "error": {"code": KC.ERR.UNKNOWN_OPERATION}}
        out, calls, _ = self.go(self.ASK + [[B(type="text", text="Nothing has been measured there yet.")]], unknown,
                                history=[{"role": "assistant", "content": J.HELLO["en"]}])
        self.assertEqual(out["say"], J.UNREAD["en"])                         # unread, never "nothing measured"
        self.assertEqual(out["rule"], "unread")
        es, _, _ = self.go(self.ASK + [[B(type="text", text="x")]], unknown, history=[{"role": "assistant", "content": J.HELLO["en"]}], lang="es")
        self.assertEqual(es["say"], J.UNREAD["es"])

    def test_the_one_source_sashas_key_the_one_route_the_published_op(self):
        _, calls, seen = self.go(self.ASK + [[B(type="text", text="Hi.")]], lambda b: {"ok": True, "result": OUT[0]})
        (url, key, op, body, auth), = calls
        self.assertEqual((url, op, body), ("https://agapi.example", KC.OP.OFFSEASON_DELTAS, {"level": "destination"}))
        self.assertEqual(auth, "Bearer " + "agp_live_" + "x" * 32)            # Sasha's own key (§3.1 b), via the one route
        self.assertIn('"rob_h1"', str(seen[-1]))                             # the model saw the items WITH their ids

    def test_a_made_up_figure_never_reaches_her_voice(self):
        out, _, _ = self.go(self.ASK + [[B(type="text", text="Testisle is 70% cheaper in November, measured in June 2037!")]],
                            lambda b: {"ok": True, "result": OUT[0]}, history=[{"role": "assistant", "content": J.HELLO["en"]}])
        self.assertEqual((out["say"], out["rule"]), (J.NO_MEASUREMENT["en"], "number"))
        out, _, _ = self.go([[B(type="text", text="Testisle is about 40% cheaper in November, I think, measured in June 2037.")]],
                            lambda b: {"ok": True, "result": OUT[0]}, history=[{"role": "assistant", "content": J.HELLO["en"]}])
        self.assertEqual(out["say"], J.NO_MEASUREMENT["en"])                 # no tool read this turn → nothing is supported


class NothingOfHerOwn(unittest.TestCase):
    def test_her_prompt_holds_no_figure_or_rule_of_the_readers(self):
        for lang in J.LANGS:
            p = J.prompt(lang)
            self.assertNotRegex(p, r"\d", "a figure in Julia's prompt")
            self.assertNotRegex(p, r"(?i)\bthreshold|\bdays?\s+old|\bminimum\b|\bat least\b", "a reader's rule in Julia's prompt")

    def test_no_threshold_literal_in_her_code(self):
        for mod in (J, PC, R):
            src = inspect.getsource(mod)
            for k in ("gap_max_age_days", "closure_max_age_days", "min_gap_pct", "lead_band_days", "median_min_hotels", "near_decay_days"):
                self.assertNotIn(k, src)

    def test_the_tool_is_the_published_request(self):
        hints = typing.get_type_hints(KC.OffseasonDeltasIn)
        s = J.TOOL["input_schema"]
        self.assertEqual(s["properties"]["level"]["enum"], [lv for lv in typing.get_args(hints["level"]) if lv != "stay"])   # Phase 1
        self.assertEqual(set(s["properties"]), set(hints) - {"check_in", "nights"})
        self.assertEqual(R.request_body({"level": "stay", "check_in": "2037-11-08", "nights": 3}), {"level": "destination"})

    def test_she_reads_through_the_one_route(self):
        from agapi import agapi_route as AR
        self.assertIn(R.FAMILY, AR.PINNED)
        self.assertEqual(AR.route(R.FAMILY), "live")
        self.assertNotRegex(inspect.getsource(R), r"getenv|agapi-live|https://")

    def test_her_voice_is_her_own(self):
        from app.api import voice_conductor as VC
        default = inspect.signature(VC.text_to_speech).parameters["voice"].default
        self.assertNotEqual(J.VOICE, default)                                # clearly not Sasha's
        self.assertRegex(J.VOICE, r"^aura-")                                 # the engine's own set


if __name__ == "__main__":
    unittest.main()
