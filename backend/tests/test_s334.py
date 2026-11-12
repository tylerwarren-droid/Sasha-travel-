"""Sasha 334 · GROUP MOVEMENT v1 complete (docs/sasha/S-334-group-v1.md). Offline: Sasha 332/333's world (the 20 fictional workers, their
trips, their Keeps) and a fake AgAPI that answers exactly CR 163's contract — and opens each keep:<id> through Sasha's REAL resolver, signed,
as AgAPI does over HTTPS.

    cd backend && python -m unittest tests.test_s334 -v
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import unittest
from unittest import mock

from booking_signer import group_book as GB, groups as G, keep_resolver as KR, traveller_vault as TV
from tests import test_s333 as W

run = asyncio.run
OWNER = W.OWNER
SECRET = "test-resolver-secret-334"


class FakeAgAPI:
    """CR 163 as Sasha sees it: approval_required with a read-back first; with the approval, each keep:<id> opened through Sasha's
    resolver (HMAC, fresh) INSIDE the supplier call — what the airline / hotel received is kept here to prove it reached them."""

    def __init__(self):
        self.records, self.rbs, self.apvs, self.answers, self.supplier, self.calls = [], {}, {}, [], [], []
        self.n = 0
        self.keys = {}   # Sasha 371b · CR 184: (Idempotency-Key) → (the request, its answer once it named a record)

    def _id(self, p):
        self.n += 1
        return f"{p}_{self.n:04d}"

    ACCOUNT = "acc_test_sasha"   # Sasha's own AgAPI account (keep_resolver asks usage.get; the World answers it)

    async def _open(self, ref, member, movement_id, booking_id, purpose="group.book"):
        """CR 189 · AgAPI's signed, BOUND call to Sasha's resolver: keep-resolve/1, canonical bytes, the binding in them."""
        body = KR.canonical({"account": self.ACCOUNT, "at": int(time.time()), "booking_id": booking_id, "member": member,
                             "movement_id": movement_id, "person": OWNER, "purpose": purpose, "ref": ref, "v": KR.VERSION})
        return (await KR.resolve(body, KR.sign(body)))["values"]

    def _price(self, kind):
        return {"amount_minor": 12000 if kind == "flight" else 30000, "currency": "EUR"}

    async def __call__(self, op, body, approval=None, idem=None):
        self.calls.append((op, json.loads(json.dumps(body))))   # Sasha 365 · what was asked (one group hotel search, never one per person)
        out = await self._keyed(op, body, approval, idem)
        self.answers.append(json.dumps(out))
        return out

    async def _keyed(self, op, body, approval, idem):
        """CR 184 (row 1885) as AgAPI keeps it: group acts need their key; the same key + the same request → the same answer (replayed);
        the same key + another request → idempotency_conflict; another key while the traveller's record on this movement is live →
        already_completed / outcome_unknown, never a second order."""
        if op not in ("group.book", "group.swap", "group.cancel"):
            return await self._do(op, body, approval)
        if not idem:
            return {"ok": False, "error": {"code": "idempotency_key_required", "message": "key"}}
        req = json.dumps({"op": op, **body}, sort_keys=True)
        seen = self.keys.get(idem)
        if seen and seen[0] != req:
            return {"ok": False, "error": {"code": "idempotency_conflict", "message": "another request"}}
        if seen and seen[1] is not None:
            return {**json.loads(seen[1]), "replayed": True}
        if op == "group.book":
            if not body.get("movement_id") or not (body.get("worker") or {}).get("key"):
                return {"ok": False, "error": {"code": "invalid_input", "message": "movement_id and worker.key", "details": {"path": "/movement_id"}}}
            live = next((b for b in self.records if b.get("movement_id") == body["movement_id"] and b["worker"]["key"] == body["worker"]["key"]
                         and b["state"] in ("booked", "unknown", "incomplete")), None)
            if live and approval or (live and body.get("mandate_id")):
                code = "outcome_unknown" if live["state"] == "unknown" else "already_completed"
                return {"ok": False, "error": {"code": code, "message": "on the record", "details": {"booking_id": live["booking_id"],
                                                                                                    "state": live["state"], "movement_id": live["movement_id"]}}}
        self.keys[idem] = (req, None)
        out = await self._do(op, body, approval)
        if out.get("ok") or ((out.get("error") or {}).get("details") or {}).get("booking_id"):
            self.keys[idem] = (req, json.dumps(out))
        return out

    async def _do(self, op, body, approval):
        if op == "users.register":
            return {"ok": True, "result": {"end_user_id": "usr_org"}}
        if op == "travel.find_flights":
            return {"ok": True, "result": {"offers": [{"offer_ref": f"off_{body['origin']['query']}_{body['destination']['query']}_{body['date']}"}]}}
        if op == "travel.find_stays":
            return {"ok": True, "result": {"stays": [{"stay_ref": "stay_getafe"}]}}
        if op == "sandbox.simulate_approval":
            a = self._id("apv")
            self.apvs[a] = body["read_back_id"]
            return {"ok": True, "result": {"approval_id": a}}
        if op == "group.bookings":   # CR 184 · by movement only
            assert body.get("movement_id"), "group.bookings is read by movement (CR 184)"
            return {"ok": True, "result": {"bookings": [dict(b) for b in self.records if b.get("movement_id") == body["movement_id"]]}}
        key = json.dumps({"op": op, **{k: v for k, v in body.items() if k != "end_user"}}, sort_keys=True)
        if not approval:
            rb = self.rbs.setdefault(key, self._id("rb"))
            w = body.get("worker") or {}
            lines = {"group.book": [f"For {w.get('given_name')} {w.get('family_name')}:", "Flight out EUR 120.00.", "Flight back EUR 120.00.",
                                    "Stay EUR 300.00.", "Passport: Passport ES ••••xxx — opened only to book these.", "Total EUR 540.00 — TEST."],
                     "group.swap": [f"{w.get('given_name')} {w.get('family_name')} replaces …:", "Difference EUR 0.00 — TEST."],
                     "group.cancel": ["Cancel …", "Refund in all EUR 540.00."]}[op]
            return {"ok": False, "error": {"code": "approval_required", "message": "needs the approval",
                                           "details": {"read_back_id": rb, "read_back_sha256": "sha_" + rb, "read_back": {"lines": lines}}}}
        assert self.apvs.get(approval) == self.rbs.get(key), "an approval for ANOTHER read-back"
        if op == "group.book":
            return {"ok": True, "result": await self._book(body["worker"], body["items"], movement_id=body["movement_id"])}
        if op == "group.cancel":
            b = next(x for x in self.records if x["booking_id"] == body["booking_id"])
            b["state"] = "cancelled"
            return {"ok": True, "result": {**b, "refund": {"amount_minor": 54000, "currency": "EUR"}}}
        if op == "group.swap":
            old = next(x for x in self.records if x["booking_id"] == body["booking_id"])
            new = await self._book(body["worker"], [{"kind": "flight", "ref": "re1"}, {"kind": "flight", "ref": "re2"}], stay=old["parts"][-1],
                                   movement_id=old.get("movement_id"))   # CR 184 · the newcomer belongs to the old booking's movement
            old.update(state="swapped_out", replaced_by=new["booking_id"])
            new["replaces"] = old["booking_id"]
            return {"ok": True, "result": {**new, "difference": {"amount_minor": 0, "currency": "EUR"}}}
        raise AssertionError(op)

    async def _book(self, w, items, stay=None, movement_id=None):
        bid = self._id("gbk")
        pp = await self._open(w["keep"]["passport"], w["key"], movement_id, bid)   # INSIDE the supplier call, bound to THIS booking
        self.supplier.append(pp["number"])
        pp = None
        parts = [{"kind": "flight", "reference": self._id("PNR"), "price": self._price("flight")} for i in items if i["kind"] == "flight"]
        parts.append(stay or {"kind": "stay", "reference": self._id("HTL"), "price": self._price("stay")})
        b = {"booking_id": bid, "worker": {"key": w["key"], "name": f"{w['given_name']} {w['family_name']}"}, "state": "booked", "parts": parts,
             "movement_id": movement_id}
        self.records.append(b)
        return dict(b)


async def _own_accounts():
    return {FakeAgAPI.ACCOUNT}


class World(W.World):
    def __enter__(self):
        super().__enter__()
        self.agapi = FakeAgAPI()
        settled = self.settled = []

        async def settle(account, item_id, state, ref):
            settled.append((item_id, state))
            for rows in self.trips.values():
                for r in rows:
                    if r.get("id") == item_id:
                        r["state"] = state
        for i, rows in enumerate(self.trips.values()):   # each planned row its id (the basket's own)
            for j, r in enumerate(rows):
                r.setdefault("id", f"item-{i}-{j}")
        import booking_signer.basket as BK
        inner = BK.suggest   # the 332 world's fake basket, each new row given an id as the real basket's insert returns one

        async def suggest(account, trip_id, kind, found, slice_key=None, replace=True):
            out = await inner(account, trip_id, kind, found, slice_key=slice_key, replace=replace)
            for j, r in enumerate(self.trips.get(trip_id, [])):
                r.setdefault("id", f"item-{trip_id}-{j}")
            return out
        for p in (mock.patch.object(BK, "suggest", suggest), mock.patch.object(BK, "_run", lambda: None)):   # offline: the claim is in memory
            p.start()
            self.p.append(p)
        for p in (mock.patch.object(GB, "CALL", self.agapi), mock.patch.object(GB, "SETTLE", settle),
                  mock.patch.dict(os.environ, {"SASHA_KEEP_RESOLVE_SECRET": SECRET}), mock.patch.dict(GB._CARDS, {}, clear=True),
                  mock.patch.object(KR, "ACCOUNTS", _own_accounts)):
            p.start()
            self.p.append(p)
        for i, m in enumerate(self.members()):
            self.fill(m, i)
        return self

    async def tap(self, card, choice="group_yes"):
        from agapi import v0 as API
        ctx = API.Ctx(account=OWNER, mode="test")
        ctx.idem = f"card_tap:{OWNER}:{card}:{choice}"
        try:
            await API.claim(ctx)
        except API.ToolError as e:
            return {"status": "nothing_waiting", "code": e.code}
        return await GB.confirm(OWNER, card, choice, "Yes, go ahead.")


class BookSwapCancelInvoice(unittest.TestCase):
    def test_the_whole_movement(self):
        with World() as w:
            card = run(GB.prepare(OWNER, "book"))
            self.assertEqual(card["status"], "awaiting_yes")
            from app.agent.sasha import yes_buttons
            yb = yes_buttons("group_book", card)
            self.assertEqual([c["route"] for c in yb["choices"]], ["group_yes", "group_no"])        # 330's one place
            self.assertEqual([s["name"] for s in card["skipped"]], ["Rania Mithal"])                 # over the limit: never without his yes
            self.assertEqual(w.agapi.supplier, [])                                                   # nothing before the yes
            out = run(w.tap(card["read_back_id"]))
            self.assertIn("done", out, out)
            self.assertEqual((len(out["done"]), out["failed"]), (19, []))
            self.assertEqual(run(w.tap(card["read_back_id"]))["status"], "nothing_waiting")         # a second tap: nothing
            v = {r["name"]: r["status"] for r in run(G.view(OWNER))["rows"]}
            self.assertEqual(sum(1 for s in v.values() if s == "booked"), 19)
            self.assertEqual(v["Rania Mithal"], "over limit")
            # Rania only on his explicit yes to HER, over the limit
            over = run(GB.prepare(OWNER, "book", ["Rania Mithal"], over_ok=True))
            self.assertTrue(any("OVER the group's limit" in l for l in over["read_back"]))
            run(w.tap(over["read_back_id"], "group_no"))
            self.assertEqual({r["name"]: r["status"] for r in run(G.view(OWNER))["rows"]}["Rania Mithal"], "over limit")
            # swap Bruno for a newcomer (who must have a vault)
            run(G.upload(OWNER, G.read_text("Zoe Newcomer, Seville, 2026-12-01, 2026-12-19, worker")))
            zoe = next(m for m in w.members() if m["name"] == "Zoe Newcomer")
            need = run(GB.prepare(OWNER, "swap", ["Bruno Example"], "Zoe Newcomer"))
            self.assertEqual(need["status"], "needs_vault")                                          # B's vault empty → invited
            w.fill(zoe, 19)
            sw = run(GB.prepare(OWNER, "swap", ["Bruno Example"], "Zoe Newcomer"))
            run(w.tap(sw["read_back_id"]))
            # cancel Hanna
            cx = run(GB.prepare(OWNER, "cancel", ["Hanna Dummy"]))
            self.assertIn("Refund in all EUR 540.00.", cx["read_back"])
            run(w.tap(cx["read_back_id"]))
            v = {r["name"]: r["status"] for r in run(G.view(OWNER))["rows"]}
            inv = run(GB.invoice(OWNER, run(G.store().movement(OWNER))["id"]))
            logs, answers = "\n".join(w.logs), "\n".join(w.agapi.answers)
        self.assertEqual((v["Bruno Example"], v["Zoe Newcomer"], v["Hanna Dummy"]), ("cancelled", "booked", "cancelled"))
        self.assertEqual(len(inv["lines"]), 18)                                                      # 19 − Bruno − Hanna + Zoe
        self.assertEqual([a["what"].split(" (")[0] for a in inv["adjustments"]], ["Swapped for Zoe Newcomer", "Cancelled"])
        self.assertEqual(inv["total"], "€9,720.00")                                                  # 18 × €540
        self.assertTrue(inv["test"] and inv["number"].endswith("-TEST") and "REAV" in inv["reav"])
        for n in W.PASSPORTS.values():                                                               # no passport number in Sasha's logs or AgAPI's answers
            self.assertNotIn(n, logs)
            self.assertNotIn(n, answers)
        self.assertEqual(len(w.agapi.supplier), 20)                                                  # …and each DID reach its supplier call
        print(f"\n[s334 proof] book all → 19 booked (Rania over the limit: held) · swap Bruno → Zoe · cancel Hanna · invoice "
              f"{inv['number']}: {len(inv['lines'])} lines + {len(inv['adjustments'])} adjustments, total {inv['total']}")


class TheResolver(unittest.TestCase):
    """Sasha 378 · CR 189: a reference opens ONLY for its own traveller, bound in AgAPI's signed call and checked against Sasha's records."""

    def _body(self, w, m, ref, **over):
        mv = run(G.store().movement(OWNER))
        b = {"account": FakeAgAPI.ACCOUNT, "at": int(time.time()), "booking_id": "gbk_378", "member": m["id"], "movement_id": str(mv["id"]),
             "person": OWNER, "purpose": "group.book", "ref": ref, "v": KR.VERSION, **over}
        return KR.canonical(b)

    def _refused(self, body, sig=None):
        with self.assertRaises(KR.Refused) as e:
            run(KR.resolve(body, KR.sign(body) if sig is None else sig))
        return e.exception.rule

    def test_only_its_own_traveller_on_its_own_movement_for_sashas_own_account(self):
        with World() as w:
            m, other = w.members()[0], w.members()[1]
            ref = run(TV.vault_view(m))["refs"]["passport"]
            body = self._body(w, m, ref)
            self.assertEqual(self._refused(body, "0" * 64), "bad_signature")
            self.assertEqual(self._refused(self._body(w, m, ref, at=int(time.time()) - 600)), "stale")
            self.assertEqual(self._refused(self._body(w, m, ref, account="acc_someone_else")), "not_this_account")
            self.assertEqual(self._refused(self._body(w, m, ref, person="00000000-0000-4000-8000-0000000000ff")), "not_this_movement")
            self.assertEqual(self._refused(self._body(w, m, ref, movement_id="00000000-0000-4000-8000-0000000000fe")), "not_this_movement")
            self.assertEqual(self._refused(self._body(w, m, ref, member="nobody")), "not_this_member")
            self.assertEqual(self._refused(self._body(w, other, ref)), "not_this_member")    # Ana's reference bound to Bruno: never opened
            self.assertEqual(self._refused(self._body(w, m, ref, purpose="group.cancel")), "bad_body")
            self.assertEqual(self._refused(self._body(w, m, ref, v="keep-resolve/0")), "bad_body")
            got = run(KR.resolve(body, KR.sign(body)))
        self.assertEqual(got["type"], "passport")
        self.assertEqual(got["values"]["number"], W.PASSPORTS["Worker0"])
        self.assertFalse(any(W.PASSPORTS["Worker0"] in l or ref in l for l in w.logs))          # never logged — not the value, not the reference

    def test_crs_vector_verifies(self):
        import pathlib as _pl
        v = json.loads((_pl.Path(KR.__file__).parent / "vectors" / "keep_resolve.json").read_text())["vectors"][0]
        self.assertEqual(KR.canonical({**v["bind"], "at": v["at"], "ref": v["ref"], "v": "keep-resolve/1"}).decode(), v["body"])
        self.assertEqual(KR.sign(v["body"].encode(), v["secret"]), v["signature"])

    def test_no_allow_list_left(self):
        import inspect
        src = inspect.getsource(KR) + inspect.getsource(GB)
        for gone in ("_GRANTS", "def grant", "def revoke", "KR.grant(", "KR.revoke("):
            self.assertNotIn(gone, src)

    def test_the_route_is_gate_exempt_only_for_its_signature(self):
        import inspect
        from booking_signer import gate
        src = inspect.getsource(gate.require_booking_key)
        self.assertIn('"/api/booking/keep/resolve"', src)
        self.assertIn("x-agapi-signature", inspect.getsource(__import__("booking_signer.group_routes", fromlist=["x"]).keep_resolve))


class TheOneRecords(unittest.TestCase):
    def test_no_second_copy(self):
        import inspect
        src = inspect.getsource(GB)
        self.assertNotIn("create table", src.lower())                                                # AgAPI's record, never a copy
        self.assertIn("OP.GROUP_BOOKINGS", src)   # Sasha 374 · the contract's name, never the string                                                       # read from it, each time
        self.assertNotIn("KR.grant(", src)                                                          # Sasha 378 · CR 189: bound in AgAPI's signed call
        from agapi import agapi_route as AR
        self.assertEqual(AR.route("group"), "sandbox")                                               # TEST only: the sandbox, by name
        with mock.patch.dict(os.environ, {"SASHA_AGAPI_ROUTE": "all=live"}):
            self.assertEqual(AR.route("group"), "sandbox")


if __name__ == "__main__":
    unittest.main()
