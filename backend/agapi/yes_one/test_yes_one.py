"""yes_one · THE conformance set (generated alongside yes_one.py; DO NOT EDIT — tools/yes_one/generate.py). The same cases run against
yes_one.ts (yes_one.test.ts). Runs next to the vendored module:  python -m unittest <package>.test_yes_one"""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("yes_one_vendored", HERE / "yes_one.py")
Y = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(Y)
C = json.loads((HERE / "conformance.json").read_text(encoding="utf-8"))

ACCOUNT, PERSON, AT = "acct_flow", "usr_flow", "2026-10-10T10:00:00Z"
PAYLOAD = {"total_minor": 89000, "currency": "EUR", "offer": "off_1"}
LINES = ["Iberia IB6061 Madrid → Hanoi, 2 Nov", "Total EUR 890.00"]


def flow(case: dict):
    op = case.get("operation", "trip.complete")
    rb = Y.read_back(ACCOUNT, "int_flow", op, LINES, PAYLOAD, PERSON, "t1", AT)
    apv = Y.approval(rb, case.get("approved_by", PERSON), case["approved_turn"], case["approved_at"], said=case.get("said"),
                     channel=case.get("channel", "sasha_chat"))
    if case.get("consumed"):
        apv["state"] = "consumed"
    cur = {"intent_id": "int_flow", "operation": op, "lines": case.get("act_lines", LINES), "payload": case.get("act_payload", PAYLOAD)}
    return Y.check(rb, apv, cur, case["act_at"], lang=case.get("lang", "en"))


def idempotency(case: dict) -> list:
    """The I-vectors as a runtime walks them: authenticate → rate limit → ledger.begin → act → ledger.finish."""
    L, out, acts, pending = Y.Ledger(), [], {}, None
    for i, s in enumerate(case["steps"]):
        caller = s["caller"]
        if caller == "anonymous":
            out.append({"status": 401, "code": "unauthenticated", "replayed": False, "key_store_touched": False})
            continue
        acct, op = caller.split("·")[0], s.get("operation", "trip.complete")
        if op == "acts.status":
            p = pending
            L.resolve(p["acct"], p["op"], p["key"], 201, {"ok": True, "result": {"outcome": "CONFIRMED", "n": p["n"]}}, intent_id=p["intent"], act_id=p["act"])
            out.append({"status": 200, "outcome": "CONFIRMED"})
            continue
        if s["upstream"] == "rate_limited_by_us":
            out.append({"status": 429, "code": "rate_limited", "stored": False})
            continue
        intent = (s.get("input") or {}).get("hold_id") if op == "trip.complete" else None
        b = L.begin(acct, op, s.get("idempotency_key"), s.get("input"), intent_id=intent)
        if b["do"] == "refuse":
            out.append({"status": b["status"], "code": b["code"], "upstream_calls": 0, **({"details": b["details"]} if b.get("details") else {})})
            continue
        if b["do"] == "replay":
            body = b["body"]
            out.append({"status": b["status"], "ok": body.get("ok"), "replayed": True, "upstream_calls": 0, "charged": False, "body": body,
                        **({"code": body["error"]["code"]} if not body.get("ok") else {})})
            continue
        act = f"act_{i}_{acct}"
        up = s["upstream"]
        key = s.get("idempotency_key")
        if up in ("confirmed", "cancelled"):
            body, st = {"ok": True, "result": {"act_id": act, "n": f"{acct}:{i}"}}, 201
        elif up == "slow_confirmed":                    # the next step arrives while this one runs; it finishes after
            out.append({"status": 201, "ok": True, "upstream_calls": 1, "_finish": (acct, op, key, 201, {"ok": True, "result": {"act_id": act}}, intent, act)})
            continue
        elif up == "refused":
            body, st = {"ok": False, "error": {"code": "upstream_refused"}}, 422
        elif up == "unreachable":
            body, st = {"ok": False, "error": {"code": "upstream_unreachable"}}, 503
        elif up == "timeout_after_send":
            body, st = {"ok": False, "error": {"code": "outcome_unknown", "details": {"act_id": act}}}, 502
            pending = {"acct": acct, "op": op, "key": key, "intent": intent, "act": act, "n": f"{acct}:{i}"}
        else:
            raise AssertionError(up)
        L.finish(acct, op, key, st, body, intent_id=intent, act_id=act)
        out.append({"status": st, "ok": body.get("ok"), "replayed": False, "upstream_calls": 1, "charged": bool(body.get("ok")), "body": body,
                    "stored": L.store.get((acct, op, key)) is not None and L.store.get((acct, op, key))["state"] == "done",
                    **({"code": body["error"]["code"]} if not body.get("ok") else {}),
                    **({"details": body["error"]["details"]} if not body.get("ok") and body["error"].get("details") else {})})
    for o in out:                                      # finish the slow acts at the end (they were running during the next step)
        if "_finish" in o:
            a, op, k, st, body, intent, act = o.pop("_finish")
            L.finish(a, op, k, st, body, intent_id=intent, act_id=act)
    return out


class Conformance(unittest.TestCase):
    def test_contract_version(self):
        self.assertEqual(Y.CONTRACT_VERSION, C["contract_version"])

    def test_approval_vectors(self):
        for c in C["approval"]:
            with self.subTest(c["id"]):
                self.assertEqual(list(Y.decide(c)), [c["expect"]["decision"], c["expect"]["void_reason"]], c["description"])

    def test_explicit_yes_vectors(self):
        for c in C["explicit_yes"]:
            with self.subTest(c["said"]):
                self.assertEqual(Y.explicit_yes(c["said"], c["lang"], c.get("act_kind")), c["explicit_yes"])

    def test_canonical_vectors(self):
        for c in C["canonical"]:
            with self.subTest(c["id"]):
                if c.get("expect") == "refused":
                    with self.assertRaises(Y.Refused):
                        Y.canonical(json.loads(c["input_json"]))
                else:
                    self.assertEqual((Y.canonical(c["input"]), Y.sha256(c["input"])), (c["canonical"], c["sha256"]))

    def test_idempotency_vectors(self):
        for c in C["idempotency"]:
            with self.subTest(c["id"]):
                got = idempotency(c)
                for i, (s, g) in enumerate(zip(c["steps"], got)):
                    e = s["expect"]
                    for k in ("status", "code", "ok", "replayed", "upstream_calls", "stored", "outcome"):
                        if k in e:
                            self.assertEqual(g.get(k), e[k], f"{c['id']} step {i + 1} {k}")
                    if e.get("same_result_as_step"):
                        self.assertEqual(g["body"], got[e["same_result_as_step"] - 1]["body"])
                    if e.get("result_differs_from_step"):
                        self.assertNotEqual(g["body"], got[e["result_differs_from_step"] - 1]["body"])
                    if (e.get("details") or {}).get("act_id"):
                        self.assertTrue(g.get("details", {}).get("act_id"))

    def test_flow(self):
        for c in C["flow"]:
            with self.subTest(c["id"]):
                self.assertEqual(list(flow(c)), c["expect"], c["says"])


if __name__ == "__main__":
    unittest.main()
