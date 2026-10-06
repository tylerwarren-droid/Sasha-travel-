"""CR 46 · EspañaMe's case status for the platform's 🇪🇸 Health card tab (read-only): ID read → 1449F1 filled → centre → cita.

    cd backend && python -m unittest tests.test_health_status_cr46 -v
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from products import store as ST
from products.health import health_status
from tests import test_guest_whatsapp_s75 as TG

run = TG.run


class Status(TG.unittest.TestCase):
    def setUp(self):
        self.saved = ST.STORE
        ST.STORE = ST.MemoryCaseStore()

    def tearDown(self):
        ST.STORE = self.saved

    def case(self, **kv):
        exp = (datetime.now(timezone.utc) + timedelta(hours=kv.pop("hours", 20))).isoformat()
        return run(ST.STORE.put("health", "acct", "w", {"kind": "tarjeta", "rows": [{}] * 22, "values_expire_at": exp,
                                                         "status": "ready_for_you", **kv}))

    def states(self):
        return [s["state"] for s in run(health_status("acct"))["steps"]]

    def test_none_without_a_case(self):
        self.assertIsNone(run(health_status("acct")))

    def test_step_by_step(self):
        cid = self.case()
        got = run(health_status("acct"))
        self.assertEqual(self.states(), ["done", "done", "todo", "todo"])
        self.assertTrue(got["steps"][1]["pdf"].endswith(f"/api/products/health/{cid}/1449F1-prepared.pdf"))
        self.assertEqual(got["next"], "say “find my centre”")
        self.assertEqual(got["tab"], "Health card")
        st = run(ST.STORE.get(cid))["state"]
        run(ST.STORE.update(cid, {**st, "centre": {"name": "Centro de Salud Ejemplo", "address": "Calle Uno 1"},
                                  "cita": {"on": "2026-10-20", "at": "10:00", "place": "Centro de Salud Ejemplo"}}))
        self.assertEqual(self.states(), ["done", "done", "done", "done"])

    def test_values_gone_after_24_hours_is_said(self):
        self.case(hours=-1)
        got = run(health_status("acct"))
        self.assertEqual(got["steps"][1]["state"], "expired")
        self.assertIsNone(got["steps"][1]["pdf"])
        self.assertIn("fill it again", got["next"])

    def test_under_way_before_the_form(self):
        run(ST.STORE.put("health", "acct", "w", {"kind": "conversation", "pending": {"step": "ts_doc"}}))
        self.assertEqual(self.states(), ["doing", "todo", "todo", "todo"])


if __name__ == "__main__":
    TG.unittest.main()
