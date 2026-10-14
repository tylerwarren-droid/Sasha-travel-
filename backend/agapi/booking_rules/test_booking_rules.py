"""CR 91 · the booking rules' gate: every vector in vectors.json holds (EU 250 §A3 — one or more per rule, R1–R14 + access).
Runs in AgAPI CI and against Sasha's vendored copy (the same three files, byte for byte)."""
from __future__ import annotations

import json
import os
import unittest

try:
    from . import booking_rules as BR
except ImportError:   # run from the vendored directory itself
    import booking_rules as BR   # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
FNS = {"decide": lambda i: BR.decide(i), "call_opening": lambda i: {"text": BR.call_opening(i["rest"])},
       "call_answer": lambda i: BR.call_answer(i["said"]), "call_payload": lambda i: BR.CALL_PAYLOAD, "stopped": lambda i: BR.stopped(i["what"], i["why"]),
       "no_answer": lambda i: BR.no_answer(i.get("page_link"), i.get("phone"), i.get("email")),            # booking-rules/2
       "call_allowed": lambda i: BR.call_allowed(i["access"], i["state"], i["now"]), "on_it": lambda i: {"text": BR.on_it(i["next"])}}


def get(d, path):
    for k in path.split("."):
        d = d[int(k)] if isinstance(d, list) else d.get(k) if isinstance(d, dict) else None
    return d


class Vectors(unittest.TestCase):
    def test_every_vector(self):
        data = json.load(open(os.path.join(HERE, "vectors.json"), encoding="utf-8"))
        self.assertEqual(data["version"], BR.VERSION)
        rules = set()
        for v in data["vectors"]:
            out = FNS[v["fn"]](v["input"])
            rules.add(v["rule"])
            with self.subTest(rule=v["rule"], name=v["name"]):
                if v["fn"] in ("decide", "no_answer"):
                    self.assertTrue(out["takeover"]["say"], "R11: every decision carries the takeover")
                for k, want in v["expect"].items():
                    if k == "startswith":
                        self.assertTrue(out["text"].startswith(want), out["text"])
                    elif k.startswith("!"):
                        self.assertNotEqual(get(out, k[1:]), want)
                    else:
                        self.assertEqual(get(out, k), want, f"{v['name']}: {k}")
        self.assertEqual(rules, {f"R{i}" for i in range(1, 15)} | {"access"})   # one gate per rule, none missing
