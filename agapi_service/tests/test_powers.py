"""CR 60 · S2's first powers — the shared module (backend/agapi/powers.py) against its frozen vectors (spec/ext/vectors/powers.json),
and both operations end to end through the sandbox: messages.send_email (read-back → the end user's Approval → captured, never
sent → Evidence) and calendar.add_event (an .ics + links, free, no Approval).

    python -m unittest agapi_service.tests.test_powers -v      (from the repo root)
"""
from __future__ import annotations

import json
import re
import unittest

from agapi_service import config, rules as R               # (config first: it puts backend/ on the path)
from agapi import powers as P  # noqa: E402
from agapi_service.tests.test_service import Base, TRAVELLER

VEC = json.loads((R.SPEC.parent / "ext" / "vectors" / "powers.json").read_text(encoding="utf-8"))


class Vectors(unittest.TestCase):
    def test_email(self):
        for c in VEC["email"]:
            with self.subTest(c["id"]):
                i = c["input"]
                m = P.email_message(i["from"], i["to"]["address"], i["to"].get("name"), i["subject"], i["body"])
                self.assertEqual(m, c["expect"]["message"])
                self.assertEqual(P.email_read_back(m), c["expect"]["read_back"])
                self.assertEqual(P.sha256(m), c["expect"]["payload_sha256"])
                self.assertEqual(R.sha256(m), c["expect"]["payload_sha256"])            # the same bytes as AgAPI's canonical JSON
                self.assertEqual(P.email_body_sha256(m), c["expect"]["body_sha256"])

    def test_email_refused(self):
        for c in VEC["email_refused"]:
            with self.subTest(c["id"]), self.assertRaises(P.Refused) as e:
                i = c["input"]
                P.email_message("Sasha <s@x.test>", i["to"]["address"], i["to"].get("name"), i["subject"], i["body"])
            self.assertEqual((e.exception.path, e.exception.rule), (c["expect"]["path"], c["expect"]["rule"]))

    def test_calendar(self):
        for c in VEC["calendar"]:
            with self.subTest(c["id"]):
                ev = c["event"]
                self.assertEqual(P.sha256(ev), c["expect"]["event_sha256"])
                text = P.ics(ev, c["dtstamp"])
                self.assertEqual(text, c["expect"]["ics"])
                self.assertEqual(P.text_sha256(text), c["expect"]["ics_sha256"])
                self.assertTrue(all(len(line.encode()) <= 75 for line in text.split("\r\n")))
                self.assertTrue(text.endswith("\r\n") and "\n" not in text.replace("\r\n", ""))
                self.assertEqual(P.calendar_links(ev, c["ics_url"]), c["expect"]["links"])

    def test_counts(self):
        self.assertEqual((len(VEC["email"]), len(VEC["email_refused"]), len(VEC["calendar"])), (3, 4, 3))


class SendEmail(Base):
    def email(self, uid, **over):
        inp = {"end_user": uid, "to": {"address": "marta@example.com", "name": "Marta"}, "subject": "Our trip to London",
               "body": "Hi Marta,\nWe land at 09:00 on Thu 12 Nov.\nAna"}
        inp.update(over)
        return inp

    def test_read_back_approval_captured_evidence(self):
        uid = self.user()
        r, b = self.call("messages.send_email", self.email(uid), expect="approval_required")
        rb, lines = b["error"]["details"]["read_back_id"], b["error"]["details"]["read_back"]["lines"]
        self.assertTrue(lines[0].startswith("Send this email from") and "not your mailbox" in lines[0])
        self.assertIn("To: Marta <marta@example.com>", lines)
        self.assertIn("Subject: Our trip to London", lines)
        self.assertIn("We land at 09:00 on Thu 12 Nov.", lines)
        # the same message again → the SAME read-back (no duplicates); a question is never a yes
        self.assertEqual(self.call("messages.send_email", self.email(uid))[1]["error"]["details"]["read_back_id"], rb)
        self.call("sandbox.simulate_approval", {"read_back_id": rb, "said": "Yes — what will it say exactly?"}, expect="no_explicit_yes")
        apv = self.tap_yes(rb)                                                           # the end user taps on their own phone
        r, b = self.call("messages.send_email", self.email(uid), approval=apv)
        self.assertEqual(r.status_code, 201, b)
        out = b["result"]
        self.assertEqual(out["outcome"]["kind"], "CONFIRMED")
        self.assertTrue(out["outcome"]["reference"].startswith("sbx_msg_"))
        self.assertEqual(out["message"]["to"]["address"]["source"], "user_named")           # the recipient is untrusted text
        self.assertEqual(out["message"]["body_sha256"], P.email_body_sha256(P.email_message("x", "marta@example.com", "Marta",
                                                                                               "Our trip to London", self.email(uid)["body"])))
        ev = self.ok("evidence.get", {"evidence_id": out["evidence_id"]})
        self.assertEqual((ev["approval"]["approval_id"], ev["sources"][0]["sha256"]), (apv, out["message"]["body_sha256"]))
        self.assertTrue(self.ok("evidence.verify", {"evidence": ev})["valid"])
        sent = [m for m in self.ok("sandbox.messages")["messages"] if m["channel"] == "email"]
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["to"], "marta@example.com")
        self.assertIn("Subject: Our trip to London", sent[0]["body"])
        self.call("messages.send_email", self.email(uid), approval=apv, expect="approval_consumed")    # one yes, one send

    def test_any_change_needs_a_new_yes(self):
        uid = self.user()
        rb = self.call("messages.send_email", self.email(uid))[1]["error"]["details"]["read_back_id"]
        apv = self.ok("sandbox.simulate_approval", {"read_back_id": rb, "said": "Yes, send it."})["approval_id"]
        r, b = self.call("messages.send_email", self.email(uid, subject="Our trip to London!!"), approval=apv)
        self.assertFalse(b["ok"])                                                        # a different subject is a different message
        self.assertIn(b["error"]["code"], ("approval_same_turn", "approval_void"))
        self.assertEqual([m for m in self.ok("sandbox.messages")["messages"] if m["channel"] == "email"], [])

    def test_refusals(self):
        uid = self.user()
        self.call("messages.send_email", self.email(uid, to={"address": "not-an-address"}), expect="invalid_input")
        r, b = self.call("messages.send_email", self.email(uid, subject="Hi\nBcc: evil@example.com"), expect="invalid_input")
        self.assertEqual(b["error"]["details"]["path"], "/subject")
        self.call("messages.send_email", self.email(uid, cc="x@example.com"), expect="invalid_input")       # one recipient, by schema


class AddEvent(Base):
    def test_a_confirmed_booking_becomes_an_event(self):
        uid = self.user()
        h = self.venue_hold(uid)
        apv = self.ok("sandbox.simulate_approval", {"read_back_id": h["read_back"]["read_back_id"], "said": "Yes, book it."})["approval_id"]
        act = self.ok("trip.complete", {"hold_id": h["hold_id"]}, approval=apv)
        r, b = self.call("calendar.add_event", {"act_id": act["act_id"]}, headers={})
        self.assertEqual(r.status_code, 200, b)
        out = b["result"]
        self.assertTrue(out["event"]["title"].startswith("Table for 2 at"))
        self.assertEqual(out["event_sha256"], P.sha256(out["event"]))
        self.assertIn("BEGIN:VEVENT", out["ics"])
        self.assertTrue(out["links"]["google"].startswith("https://calendar.google.com/calendar/render?action=TEMPLATE"))
        self.assertTrue(out["links"]["outlook"].startswith("https://outlook.live.com/calendar/0/deeplink/compose?"))
        path = "/" + out["links"]["ics"].split("://", 1)[1].split("/", 1)[1]
        f = self.client.get(path)
        self.assertEqual((f.status_code, f.headers["content-type"].split(";")[0]), (200, "text/calendar"))
        self.assertEqual(f.text.replace("\r\n", "\n"), out["ics"].replace("\r\n", "\n"))
        ev = self.ok("evidence.get", {"evidence_id": out["evidence_id"]})
        self.assertEqual(ev["sources"][0]["sha256"], out["event_sha256"])
        self.assertNotIn("approval", ev)                                                   # free, no Approval, nothing left the account
        u = self.store.q("select cost_units from usage_records where operation = 'calendar.add_event'")
        self.assertEqual([x["cost_units"] for x in u], [0])

    def test_a_flight_event_and_refusals(self):
        uid = self.user()
        h = self.flight_hold(uid)
        apv = self.ok("sandbox.simulate_approval", {"read_back_id": h["read_back"]["read_back_id"], "said": "Yes, book it."})["approval_id"]
        act = self.ok("trip.complete", {"hold_id": h["hold_id"]}, approval=apv)
        self.call("calendar.add_event", {"act_id": act["act_id"]}, expect="invalid_input")                  # awaiting payment: not yet
        self.client.post("/" + act["outcome"]["payment_url"].split("://", 1)[1].split("/", 1)[1])
        ev = self.ok("calendar.add_event", {"act_id": act["act_id"]})["event"]
        self.assertRegex(ev["title"], r"^Flight UX1013 MAD → LGW$")
        self.assertTrue(ev["starts_at"].endswith("06:30:00Z"))                                              # 07:30 Madrid = 06:30 UTC
        self.call("calendar.add_event", {"act_id": R.new_id("act")}, expect="not_found")


if __name__ == "__main__":
    unittest.main()
