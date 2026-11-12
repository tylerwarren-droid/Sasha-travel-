"""Sasha 371b · Sasha reads every booking fact from AgAPI's ONE record by movement id; Sasha keeps no copy. NO PATCHES.

CR 184 (mailbox row 1885, agapi cr/184 b2eed5f) is the contract: group.book / swap / cancel are idempotent (ONE key per traveller + movement
+ plan, re-sent unchanged on every retry); movement_id on every record and on the mandate; group.bookings read by {end_user, movement_id};
limits are EACH worker's own (limits.per_worker); every exit is on the record (booked | incomplete | unknown | cancelled | swapped_out).

    cd backend && python -m unittest tests.test_s371b_one_record_by_movement -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from unittest import mock

from booking_signer import group_book as GB, groups as G
from tests import test_s365_mandate as T365, test_s367_mandate_at_agapi as T367

run = asyncio.run
ROOT = pathlib.Path(__file__).resolve().parents[2]
BS = ROOT / "backend" / "booking_signer"
OWNER = T367.OWNER


class TheOneKey(unittest.TestCase):
    def test_the_key_is_crs_vectors(self):
        """agapi spec/ext/vectors/group.json "keys" (cr/184 b2eed5f)."""
        for mv, member, ver, key in (("mv_lisbon_2026_12", "ana-sample", "1", "7ca2168b87f579050ac953b7dfa5a65e9c02890da22adab54e1b74685acc177a"),
                                     ("mv_lisbon_2026_12", "ana-sample", "2", "a900abcf77d2ca32469ca6e98d618b26b15ec0faba6e93a7097c790c2a9edaa9"),
                                     ("mv_lisbon_2026_12", "luis-example", "1", "8334b1aa35f7e757d0669105611e3a6bddf3c3a60291ca1f108cb3fe02ff0755")):
            self.assertEqual(GB.idem_key("group.book", mv, member, ver), key)

    def test_a_group_act_without_its_key_is_refused_before_it_is_sent(self):
        for op in GB.GROUP_ACTS:
            with self.assertRaises(ValueError):
                run(GB._call(OWNER, op, {"end_user": "usr"}))

    def test_every_act_carries_its_key_and_the_read_back_and_the_act_share_it(self):
        with T367.World() as w:
            GB.KEYS.clear()
            T367._instruction(w)
        acts = [(op, k) for op, k in GB.KEYS if op in GB.GROUP_ACTS]
        self.assertTrue(acts)
        self.assertTrue(all(k and re.fullmatch(r"[0-9a-f]{64}", k) for _, k in acts), acts)
        books = [b for op, b in w.agapi.calls if op == "group.book"]
        self.assertTrue(all(b.get("movement_id") and (b.get("worker") or {}).get("key") for b in books))   # CR 184's required fields


class DropsTheFirstAnswer(T367.MandateAgAPI):
    """The connection drops AFTER AgAPI ordered (the order is on its record), once per traveller: Sasha never hears the first answer."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.dropped = set()

    async def __call__(self, op, body, approval=None, idem=None):
        out = await super().__call__(op, body, approval, idem=idem)
        who = (body.get("worker") or {}).get("key")
        if op == "group.book" and out.get("ok") and who not in self.dropped:
            self.dropped.add(who)
            return {"ok": False, "error": {"code": "timeout", "message": "ReadTimeout"}}
        return out


class TheRetryIsTheSameRequest(unittest.TestCase):
    def test_a_dropped_connection_is_resent_with_the_same_key_and_orders_once(self):
        with T367.World(DropsTheFirstAnswer()) as w:
            GB.KEYS.clear()
            r, evs = T367._instruction(w)
            mv = run(G.store().movement(OWNER))
        fin = T367._finish(evs)["text"]
        self.assertTrue(fin.startswith("All 6 booked (TEST)."), fin)
        self.assertEqual(len(w.agapi.supplier), 6 * 1)                                        # ONE order per traveller (the passport opened once each)
        self.assertEqual(len([b for b in w.agapi.records if b["movement_id"] == str(mv["id"])]), 6)   # ONE record each
        sent = [k for op, k in GB.KEYS if op == "group.book"]
        self.assertEqual(len(sent), 12)                                                       # each sent twice …
        self.assertEqual(len(set(sent)), 6)                                                   # … with the SAME key


class ReadByMovement(unittest.TestCase):
    def test_another_movements_record_never_reaches_this_one(self):
        with T367.World() as w:
            T367._instruction(w)
            mv = run(G.store().movement(OWNER))
            for b in w.agapi.records:
                b["movement_id"] = "mv_another"                                                # the same people, booked on ANOTHER trip
            rows = run(G.view(OWNER, mv["id"]))["rows"]
            inv = run(GB.invoice(OWNER, mv["id"]))
        self.assertFalse([x for x in rows if x["status"] == "booked"])                       # not booked HERE (Sasha's rows never say it)
        self.assertEqual(inv.get("lines") or [], [])
        self.assertTrue(all(b.get("movement_id") for op, b in w.agapi.calls if op == "group.bookings"))

    def test_unknown_and_incomplete_are_states_never_not_booked(self):
        recs = [{"worker": {"key": "a"}, "state": "unknown", "why": "internal", "parts": []},
                {"worker": {"key": "b"}, "state": "incomplete", "why": "upstream_refused", "parts": [{"kind": "flight"}]},
                {"worker": {"key": "c"}, "state": "booked", "parts": []}]
        members = [{"id": k} for k in "abc"]
        self.assertEqual(GB.record_states(recs, members), {"a": "confirming", "b": "incomplete", "c": "booked"})
        self.assertEqual(GB.record_whys(recs, members), {"a": "internal", "b": "upstream_refused"})
        for code in ("already_completed", "outcome_unknown", "timeout"):
            self.assertNotIn("not booked", GB.recorded({"code": code, "details": {}})["why"].lower())

    def test_the_invoice_link_opens_its_own_movement(self):
        src = (BS / "group_routes.py").read_text()
        self.assertIn('return await GB.invoice(t["owner"], t["movement"])', src)


class EachWorkersOwnLimit(unittest.TestCase):
    def test_a_worker_with_no_limit_is_asked_never_given_anothers(self):
        real = G.limit_for
        with T367.World() as w:
            with mock.patch.object(G, "limit_for", lambda rules, m: {} if m.get("name") == "Amara Sample" else real(rules, m)):
                r, evs = T367._instruction(w)
        mand = [b for op, b in w.agapi.calls if op == "approvals.mandate"][0]
        self.assertEqual(len(mand["limits"]["per_worker"]), 5)                                # Amara left out: AgAPI asks (limits_missing)
        fin = T367._finish(evs)["text"]
        self.assertIn("Amara Sample: no limit is set for them yet", fin)
        self.assertTrue(fin.startswith("5 of 6 booked (TEST)."), fin)


class Ratchet(unittest.TestCase):
    """Whole class: no path reads a booking fact except from group.bookings by movement, no retry mints a new key, no shared limit."""

    def test_the_source_holds_it(self):
        gb = (BS / "group_book.py").read_text()
        hits = []
        for f in sorted(BS.glob("*.py")) + sorted((ROOT / "backend" / "agapi").glob("*.py")):
            s = f.read_text(encoding="utf-8", errors="ignore")
            for rx, why in ((r"_records\(account\)", "records read without the movement"),
                            (r"\"group\.bookings\", \{\"end_user\": org\}\)", "group.bookings without movement_id"),
                            (r"\b_latest\(records", "latest-by-member"),
                            (r"GB\.invoice\(account\)|GB\.invoice\(t\[\"owner\"\]\)", "an invoice of the open trip"),
                            (r"max\(fl\)|max\(st\)", "a limit shared across workers")):
                if re.search(rx, s):
                    hits.append(f"{f.name}: {why}")
        self.assertEqual(hits, [])
        self.assertNotIn('return "booked"', (BS / "groups.py").read_text().split("def status_of")[1].split("def _transport")[0])
        self.assertIn('"Idempotency-Key": idem or "s334_"', gb)                               # a random key only where no act is sent
        self.assertIn("raise ValueError(f\"{op} needs its idempotency key (act_key)\")", gb)
        acts = re.findall(r"_call\(account, it\[\"op\"\], it\[\"body\"\][^)]*\)", gb)
        self.assertEqual(acts, [])                                                            # every act goes through _send (one key, re-sent)


if __name__ == "__main__":
    unittest.main()
