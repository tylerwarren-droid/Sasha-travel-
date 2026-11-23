"""Sasha 400 · A BROKEN CONNECTION IS NOTICED AND SAID (root test: the mailbox row of this ticket's measure).

Measured (Tyler's Gmail): Google refused the token on 8 Nov 20:03; mailbox.link_dead marked mailbox_links.needs_reconnect_at and tried
ONCE (WhatsApp outside its window; a one-slot /s2 "news" line); the 6-hourly loop then left the link out; nothing said it again. He
reconnected on 20 Nov. Google Calendar kept its OWN copy of that health (only invalid_grant counted); Gmail's receipts re-read Gmail's
columns and swallowed a refusal; Outlook had no health at all — a refused token was silently None.

THE CLASS: every person-held connection (Gmail, Google Calendar, Outlook) × every reader (its own sync, Gmail's receipts, the WhatsApp
watch, the calendar drainer and free/busy, the You page, get_status, the morning brief) → ONE truth (booking_signer/connections.py):
noticed (by any use, and the 6-hourly look), said ONCE with what it costs, said by get_status and the brief while it lasts, cleared
when it works again (a use, a reconnect) or is disconnected. RATCHET: no module but connections.py decides a connection's health.

    cd backend && python -m unittest tests.test_s400_connection_health -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from datetime import datetime, timezone
from unittest import mock

from booking_signer import connections as CN

BACKEND = pathlib.Path(__file__).resolve().parents[1]
ACCT = "00000000-0000-4000-8000-000000000400"
NOW = datetime(2037, 11, 8, 20, 3, tzinfo=timezone.utc)


def run(c):
    return asyncio.run(c)


class Record(unittest.TestCase):
    """The person's own record (s2_memory kinds; production: its database row), and the one outcome channel, stood in."""

    def setUp(self):
        from agapi import s2_memory as MEM
        from booking_signer import channel as CH
        self.kinds: dict = {}
        self.told: list = []
        CN._MEM.clear()

        async def put_kind(account, name, value):
            self.kinds[(account, name)] = value
            return True

        async def kind(account, name):
            return self.kinds.get((account, name))

        async def tell(account, text, **kw):
            self.told.append((account, text, kw.get("event")))
            return {"to": "s2"}
        for p in (mock.patch.object(MEM, "put_kind", put_kind), mock.patch.object(MEM, "kind", kind), mock.patch.object(CH, "tell", tell)):
            p.start()
            self.addCleanup(p.stop)


class OneTruth(Record):
    def test_said_once_with_its_cost_said_while_it_lasts_cleared_when_it_works(self):
        self.assertTrue(run(CN.broke(ACCT, "gmail", "connection_invalid_grant", NOW)))
        self.assertTrue(run(CN.broke(ACCT, "gmail", "connection_invalid_grant", NOW)))          # again: known, never said twice
        self.assertEqual(len(self.told), 1)
        self.assertIn("I can't read your booking confirmation emails until you reconnect it", self.told[0][1])
        self.assertEqual(self.told[0][2]["render"]["url"], "/you#gmail")                         # his one step
        self.assertIn("Gmail connection stopped working", run(CN.said(ACCT)))                    # get_status and the brief, meanwhile
        run(CN.working(ACCT, "gmail"))
        self.assertIsNone(run(CN.said(ACCT)))                                                    # cleared by itself
        self.assertTrue(run(CN.broke(ACCT, "gmail", "connection_invalid_grant", NOW)))           # a NEW break is said again
        self.assertEqual(len(self.told), 2)

    def test_busy_is_not_broken(self):
        for rule in ("connection_http_503", "connection_http_429", "network"):
            self.assertFalse(run(CN.broke(ACCT, "outlook", rule)))
        self.assertEqual((run(CN.broken(ACCT)), self.told), ({}, []))

    def test_every_person_held_connection_has_a_cost_and_a_step(self):
        for k in CN.PERSON:
            c = CN.CONNECTIONS[k]
            self.assertTrue(c["cost"] and c["where"].startswith("/you#") and c["label"] and c["purposes"], k)
        for k, c in CN.CONNECTIONS.items():
            if c["held"] == "platform":
                self.assertTrue(c["noticed"], k)                                                  # where its break is said


class EveryReaderAsksIt(Record):
    def test_gmails_sync_and_its_receipts(self):
        from booking_signer import mailbox as MB
        from booking_signer.vault import crypto as VC
        from agapi import s2_gmail_receipts as GR
        st = MB.MemoryMailboxStore()
        run(st.put_link({"account_id": ACCT, "vault_item_id": "v1", "consent_at": NOW, "consent_wording_version": "v1",
                         "consent_text_sha256": "0" * 64}))
        refused = mock.AsyncMock(side_effect=VC.UseRefused("connection_invalid_grant", "Google refused the connection's token"))
        with mock.patch.object(MB, "STORE", st), mock.patch.object(VC, "use_connection", refused):
            self.assertEqual(run(MB.sync(ACCT)), [])
            self.assertTrue(run(CN.is_broken(ACCT, "gmail")))
            self.assertFalse(run(GR.connected(ACCT)))                                            # the receipts read the ONE truth
            self.assertEqual(run(MB.sync(ACCT)), [])
        self.assertEqual(len(self.told), 1)
        run(CN.working(ACCT, "gmail"))
        with mock.patch.object(MB, "STORE", st), mock.patch.object(VC, "use_connection", refused):
            self.assertIsNone(run(GR.receipts(ACCT)))                                            # a refusal there is kept too
        self.assertTrue(run(CN.is_broken(ACCT, "gmail")))

    def test_outlook_a_refusal_is_no_longer_silent(self):
        from agapi import s2_outlook_receipts as OR
        from booking_signer import outlook as OL
        from booking_signer.vault import crypto as VC
        with mock.patch.object(OL, "link", mock.AsyncMock(return_value={"id": "o1"})), \
                mock.patch.object(VC, "use_connection", mock.AsyncMock(side_effect=VC.UseRefused("connection_invalid_grant", "x"))):
            self.assertIsNone(run(OR.receipts(ACCT)))
        self.assertTrue(run(CN.is_broken(ACCT, "outlook")))
        self.assertIn("Outlook", self.told[0][1])

    def test_calendar_the_one_rule_not_only_invalid_grant(self):
        from booking_signer import calendar_sync as CS
        self.assertTrue(run(CS._broke(ACCT, "vault_item_unavailable")))                          # revoked elsewhere: broken too
        self.assertTrue(run(CS._broken(ACCT)))
        self.assertIn("calendar", self.told[0][1].lower())

    def test_the_6_hourly_look_notices_and_clears(self):
        from booking_signer.vault import crypto as VC
        live = [{"id": "c1", "account_id": ACCT, "provider": "google.com", "label": "Google Calendar", "kind": "oauth"},
                {"id": "g1", "account_id": ACCT, "provider": "google.com", "label": "Gmail (read-only)", "kind": "oauth"}]
        store = mock.Mock(live_connections=mock.AsyncMock(return_value=live))
        with mock.patch.object(VC, "STORE", store), \
                mock.patch.object(VC, "use_connection", mock.AsyncMock(side_effect=VC.UseRefused("connection_invalid_grant", "x"))):
            self.assertEqual(run(CN.check_all()), ["google_calendar: broken"])                  # Gmail: its own sync looks
        with mock.patch.object(VC, "STORE", store), mock.patch.object(VC, "use_connection", mock.AsyncMock(return_value="tok")):
            self.assertEqual(run(CN.check_all()), ["google_calendar: ok"])
        self.assertEqual(run(CN.broken(ACCT)), {})

    def test_status_and_brief_say_it_while_it_lasts(self):
        from booking_signer import proactive as PR
        line = CN.line("gmail")
        self.assertIn(line, PR.render("morning_brief", {"time": "21:00", "venue": "Lhardy", "status": "confirmed"},
                                      {"items": [{"time": "21:00", "venue": "Lhardy", "status": "confirmed"}], "connections": line}))
        self.assertNotIn("\n", PR.render("morning_brief", {}, {"items": [], "connections": line}))   # one line: a template variable
        self.assertIn('"connections_line"', (BACKEND / "agapi/s2_status.py").read_text())
        self.assertIn("connections_line", (BACKEND / "agapi/v0.py").read_text())


#: the only modules that may hold a connection's health: the ONE truth. Nobody reads or writes the old columns, and every refused use
#: is handed to it.
OWN = {"booking_signer/connections.py"}


class Ratchet(unittest.TestCase):
    def files(self):
        for d in ("agapi", "app", "booking_signer", "products"):
            for p in (BACKEND / d).rglob("*.py"):
                yield p.relative_to(BACKEND).as_posix(), p.read_text()

    def test_no_reader_decides_health_for_itself(self):
        for rel, src in self.files():
            if rel in OWN:
                continue
            code = "\n".join(l.split("#", 1)[0] for l in src.splitlines())
            self.assertNotRegex(code, r"needs_reconnect_at|told_reconnect_at", rel)             # the old per-connection copies
            for m in re.finditer(r"except[^\n]*UseRefused[^\n]*:\n((?:[ \t]+[^\n]*\n){1,4})", code):
                body = m.group(1)
                if "revoke" in code[max(0, m.start() - 400):m.start()]:
                    continue   # a disconnect's revoke at Google: the connection is going, not broken
                self.assertRegex(body, r"CN\.broke\(|_broke\(|raise\b", f"{rel}: a refused connection decided here, not by connections.py")

    def test_every_connection_has_a_health_truth(self):
        from booking_signer.vault import crypto as VC
        claimed = {p for k in CN.PERSON for p in CN.CONNECTIONS[k]["purposes"]}
        for provider, purposes in VC.CONNECTION_PURPOSES.items():
            for purpose in purposes:
                if purpose.endswith("_revoke"):
                    continue
                self.assertIn(purpose, claimed, f"{provider}/{purpose}: a connection no health truth claims")
        for rel, src in self.files():   # every oauth item a module creates is one the truth knows (its provider and label)
            for m in re.finditer(r'"provider":\s*([A-Z_]+|"[^"]+"),\s*"label":\s*([A-Z_]+|"[^"]+"),\s*"kind":\s*"oauth"', src):
                prov, lab = (eval(x, {"PROVIDER": "microsoft.com", "LABEL": "Outlook (read-only)"}) for x in m.groups())
                self.assertIsNotNone(CN.kind_of({"provider": prov, "label": lab}), f"{rel}: {prov} / {lab}")


if __name__ == "__main__":
    unittest.main()
