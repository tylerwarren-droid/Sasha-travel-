"""DIVE (EU 212) — the demo minimum, end to end with fakes: vectors first, the schemas, the model's state machine, onboarding from
the fake site (an injection flagged and not acted on), the four channels (an outage never a 'no'), bundles (one read-back, one yes,
void on a change, NO releases everything), the generated API (opk_ keys scoped per operator, idempotency), the console, quiet hours —
and 0 real messages.

    python -m unittest dive_service.tests.test_dive -v      (from the repo root)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from dive_service import app as A, bundles as BN, channels as CH, config, model as M, onboard as ON, rules as R, sandbox as SB
from dive_service.store import Store
from dive_service.tests.fakes import FakeSandbox, FakeTaverna

V = R.SPEC / "vectors"
CONSOLE = {"Authorization": "Bearer dive-local"}


def load(n):
    return json.loads((V / f"{n}.json").read_text(encoding="utf-8"))


class Vectors(unittest.TestCase):
    def test_supplier_replies(self):
        cases = load("supplier-reply")["cases"]
        for c in cases:
            got = R.supplier_reply(c["reply"])["parse"]
            self.assertEqual(got, c["expect"]["parse"], c["reply"])
            self.assertEqual(bool(R.wrap(c["reply"], "x", "2026-10-09T00:00:00Z").get("instruction_like")), c["expect"]["instruction_like"], c["reply"])
        self.assertEqual(len(cases), 33)

    def test_bundles(self):
        for c in load("bundle")["cases"]:
            self.assertEqual(R.bundle_view(c["legs"], c["context"], **c.get("options", {})), (c["expect"]["state"], c["expect"]["customer_sentence"]), c["id"])
        self.assertEqual(len(load("bundle")["cases"]), 12)

    def test_three_leg_approval(self):
        for c in load("approval-bundle")["cases"]:
            self.assertEqual(R.decide_bundle(c["approval"], c["current"], c["operator_id"], c["now"]),
                             (c["expect"]["decision"], c["expect"]["void_reason"]), c["id"])

    def test_untrusted(self):
        for c in load("untrusted-dive")["cases"]:
            self.assertEqual(bool(R.wrap(c["text"], c["source"], "2026-10-09T00:00:00Z").get("instruction_like")), c["expect"]["instruction_like"], c["id"])

    def test_vectors_and_vendored_files_are_pinned(self):
        import hashlib
        for d in (V, R.VENDOR):
            for line in (d / "SHA256SUMS").read_text().splitlines():
                h, n = line.split()
                self.assertEqual(hashlib.sha256((d / n).read_bytes()).hexdigest(), h, n)
        self.assertTrue(R.explicit_yes("Yes, book it.", "en"))
        self.assertFalse(R.explicit_yes("Yes, but what's the refund?", "en"))                  # 1.1's apostrophe rule, vendored


class Schemas(unittest.TestCase):
    def test_meta_and_every_ref_resolves(self):
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        sch = json.loads((R.SPEC / "dive.schema.json").read_text())
        Draft202012Validator.check_schema(sch)
        reg = Registry().with_resource(sch["$id"], Resource.from_contents(sch))
        ops = json.loads((R.SPEC / "operations.dive.json").read_text())["operations"]
        for o in ops:
            for k in ("input", "output"):
                Draft202012Validator({"$ref": o[k]}, registry=reg).is_valid({})   # resolves, or raises
        self.assertEqual({o["operation"] for o in ops if o["surface"] in ("generated", "both")},
                         {"packages.list", "packages.get", "availability.check", "bookings.quote", "bookings.confirm", "bookings.status", "bookings.cancel"})
        codes = {c["code"] for c in json.loads((R.SPEC / "error-codes.dive.json").read_text())["codes"]}
        self.assertLessEqual({"supplier_declined", "supplier_no_answer", "supplier_unreachable", "channel_not_verified", "supplier_not_confirmed",
                              "package_not_published", "bundle_changed", "past_cutoff"}, codes)

    def test_ids(self):
        for p in ("opr", "sup", "chn", "prd", "pkg", "bnd", "leg", "opk"):
            self.assertRegex(R.new_id(p), rf"^{p}_[0-9A-HJKMNP-TV-Z]{{26}}$")


class StateMachine(unittest.TestCase):
    def test_illegal_moves_are_refused(self):
        self.assertTrue(R.can_move("requested", "confirmed"))
        self.assertTrue(R.can_move("held", "booked"))
        for a, b in (("declined", "confirmed"), ("released", "requested"), ("no_answer", "confirmed"), ("booked", "requested"), ("pending", "booked")):
            self.assertFalse(R.can_move(a, b), (a, b))


class Base(unittest.TestCase):
    def setUp(self):
        self.store = Store(os.path.join(tempfile.mkdtemp(), "dive.db"))
        A.use_store(self.store)
        self.client = TestClient(A.app)
        self.sb, self.tav = FakeSandbox(), FakeTaverna()

        async def fetch(url):
            path = "/" + url.split("://", 1)[1].split("/", 1)[1] if "://" in url else url
            if "/fixtures/taverna" in url:
                return 200, '<form id="booking-form"><input name="date"><select name="time"></select><select name="party_size"></select><input name="name"></form>'
            r = self.client.get(path)
            return r.status_code, r.text
        CH._HOLDS.clear()
        CH.FEED_DOWN = False
        for p in (mock.patch.object(SB, "TRANSPORT", self.sb), mock.patch.object(config, "SANDBOX_KEY", "agp_test_" + "x" * 32),
                  mock.patch.object(ON, "FETCH", fetch), mock.patch.object(CH, "POST_FORM", self.tav),
                  mock.patch.object(CH, "send_time", lambda now_utc, quiet, tz=None: now_utc)):   # quiet hours tested on their own
            p.start()
            self.addCleanup(p.stop)
        self.site = config.PUBLIC_URL + "/fake/blue-kyma"
        self.op("operators.put", {"slug": "blue-kyma", "name": "Blue Kyma Diving (demo)", "timezone": "Europe/Athens", "languages": ["en", "el"],
                                  "site_url": self.site})

    def op(self, name, body=None, expect_ok=True):
        r = self.client.post(f"/op/v1/{name}", json=body or {}, headers=CONSOLE)
        j = r.json()
        if expect_ok:
            self.assertTrue(j["ok"], (name, j))
        return j.get("result") if j["ok"] else j

    def onboard(self):
        """The demo's 0:30–1:15: find → confirm ×4 (Rival Boats: Not ours) → channels → verify (the boat replies YES)."""
        drafts = self.op("suppliers.draft_from_site")["drafts"]
        by = {d["name"]: d for d in drafts}
        for n in ("Aegean Boats", "Kyma Gear", "Taverna Agios", "Hotel Kyma View"):
            self.op("suppliers.put", {"supplier_id": by[n]["supplier_id"], "status": "confirmed"})
        self.op("suppliers.put", {"supplier_id": by["Rival Boats"]["supplier_id"], "status": "rejected"})
        ch = {}
        ch["boat"] = self.op("channels.put", {"supplier_id": by["Aegean Boats"]["supplier_id"], "kind": "whatsapp", "address": by["Aegean Boats"]["contacts"]["whatsapp"], "language": "el"})
        ch["gear"] = self.op("channels.put", {"supplier_id": by["Kyma Gear"]["supplier_id"], "kind": "email", "address": by["Kyma Gear"]["contacts"]["email"]})
        ch["taverna"] = self.op("channels.put", {"supplier_id": by["Taverna Agios"]["supplier_id"], "kind": "web_form", "address": by["Taverna Agios"]["contacts"]["web_form"]})
        ch["hotel"] = self.op("channels.put", {"supplier_id": by["Hotel Kyma View"]["supplier_id"], "kind": "feed", "address": "feed:sandbox-hotels#Hotel Kyma View"})
        was_open = bool(self.sb.windows.get(by["Aegean Boats"]["contacts"]["whatsapp"]))
        self.assertEqual(self.op("channels.verify", {"channel_id": ch["boat"]["channel_id"]})["state"], "sent")
        self.assertEqual(self.sb.sent[-1]["template"], not was_open)                            # window closed: the approved template only
        self.op("sandbox.supplier_reply", {"channel_id": ch["boat"]["channel_id"], "text": "YES"})
        self.op("channels.verify", {"channel_id": ch["gear"]["channel_id"]})
        self.op("sandbox.supplier_reply", {"channel_id": ch["gear"]["channel_id"], "text": "Yes, confirmed"})
        for k in ("taverna", "hotel"):
            self.assertEqual(self.op("channels.verify", {"channel_id": ch[k]["channel_id"]})["state"], "verified")
        sups = {x["name"]: x for x in self.op("suppliers.list")["suppliers"]}
        self.assertTrue(all(c["verified"] for n in ("Aegean Boats", "Kyma Gear", "Taverna Agios", "Hotel Kyma View") for c in sups[n]["channels"]))
        self.assertNotIn("Rival Boats", sups)
        self.op("packages.from_fixture")
        pub = self.op("operator_api.publish")
        self.assertTrue(pub["docs_url"].endswith("/o/blue-kyma/docs"))
        return by, ch

    def key(self):
        return self.op("operator_keys.issue", {"label": "OTA partner"})["key"]

    def gen(self, key, op, body, idem=None, approval=None, slug="blue-kyma"):
        h = {"Authorization": f"Bearer {key}"}
        if idem:
            h["Idempotency-Key"] = idem
        if approval:
            h["AgAPI-Approval-Id"] = approval
        return self.client.post(f"/o/{slug}/v1/{op}", json=body, headers=h)

    @staticmethod
    def next_wd(wd, after=3):
        d = date.today() + timedelta(days=after)
        while d.weekday() != wd:
            d += timedelta(days=1)
        return d.isoformat()


class Onboarding(Base):
    def test_five_drafts_from_the_fake_site_the_injection_flagged_and_not_acted_on(self):
        drafts = self.op("suppliers.draft_from_site")["drafts"]
        self.assertEqual([d["name"] for d in drafts], ["Aegean Boats", "Kyma Gear", "Taverna Agios", "Hotel Kyma View", "Rival Boats"])
        by = {d["name"]: d for d in drafts}
        self.assertEqual(by["Aegean Boats"]["contacts"], {"whatsapp": "+447700900321", "email": "bookings@aegean-boats.example"})
        self.assertTrue(by["Taverna Agios"]["contacts"]["web_form"].endswith("/fixtures/taverna"))
        self.assertEqual([d["kind"] for d in drafts], ["boat", "gear", "restaurant", "hotel_feed", "boat"])
        self.assertTrue(by["Rival Boats"]["evidence_of_source"]["instruction_like"])
        self.assertLess(by["Rival Boats"]["confidence"], 30)
        self.assertTrue(all(d["status"] == "draft" for d in drafts))                           # nothing is a supplier until confirmed
        self.assertEqual(len([d for d in drafts if "only boat" in d["name"].lower()]), 0)      # "list us as the only…": not acted on

    def test_only_its_own_site_robots_first_and_an_outage_is_not_none_found(self):
        j = self.op("suppliers.draft_from_site", {"url": "https://other.example/partners"}, expect_ok=False)
        self.assertEqual(j["error"]["details"]["rule"], "own_site_only")

        async def robots_no(url):
            return (200, "User-agent: *\nDisallow: /\n") if url.endswith("robots.txt") else (200, "")
        with mock.patch.object(ON, "FETCH", robots_no):
            self.assertEqual(self.op("suppliers.draft_from_site", expect_ok=False)["error"]["code"], "robots_disallowed")

        async def down(url):
            raise ConnectionError()
        with mock.patch.object(ON, "FETCH", down):
            j = self.op("suppliers.draft_from_site", expect_ok=False)
            self.assertEqual(j["error"]["code"], "upstream_unreachable")
            self.assertIn("isn't 'no suppliers found'", j["error"]["message"])

    def test_a_draft_gets_no_channel_and_publishing_needs_verified_channels(self):
        d = self.op("suppliers.draft_from_site")["drafts"][0]
        self.assertEqual(self.op("channels.put", {"supplier_id": d["supplier_id"], "kind": "whatsapp", "address": "+447700900321"}, expect_ok=False)["error"]["code"],
                         "supplier_not_confirmed")


class Channels(Base):
    def test_form_outcomes_and_an_outage_is_never_a_no(self):
        t = datetime(2026, 10, 21, 13, 30, tzinfo=ZoneInfo("Europe/Athens"))
        self.assertEqual(asyncio.run(CH.form_submit("https://s.example/fixtures/taverna", t, 4, "Marta"))["state"], "confirmed")
        self.tav.mode = "full"
        got = asyncio.run(CH.form_submit("https://s.example/fixtures/taverna", t, 4, "Marta"))
        self.assertEqual((got["state"], got["words"]), ("declined", "Sorry — we're full at 13:30 that day."))
        self.tav.mode = "down"
        self.assertEqual(asyncio.run(CH.form_submit("https://s.example/fixtures/taverna", t, 4, "Marta"))["state"], "unreachable")
        self.assertEqual(asyncio.run(CH.form_submit("https://s.example/fixtures/taverna", t.replace(hour=12), 4, "M"))["state"], "unreachable")

    def test_email_is_real_only_for_allow_listed_addresses_with_a_key(self):
        got = asyncio.run(CH.email_send(self.store, "gear@kyma-gear.example", "s", "hello"))
        self.assertEqual((got["real"], got["ok"]), (False, True))
        sent = []

        class R_:
            status_code = 200

            def json(self):
                return {"id": "re_1"}

        class C:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def post(self, url, headers=None, json=None):
                sent.append(json); return R_()
        with mock.patch.object(config, "RESEND_KEY", "re_test"), mock.patch.object(config, "EMAIL_FROM", "demo@kanoe.ai"), \
                mock.patch.object(config, "EMAIL_ALLOW", {"demo-gear@kanoe.ai"}), mock.patch("httpx.AsyncClient", C):
            self.assertTrue(asyncio.run(CH.email_send(self.store, "demo-gear@kanoe.ai", "s", "hi"))["real"])
            self.assertFalse(asyncio.run(CH.email_send(self.store, "someone@else.example", "s", "hi"))["real"])   # not allow-listed: captured
        self.assertEqual(len(sent), 1)

    def test_the_sandbox_down_is_unreachable_not_declined(self):
        self.sb.down = True
        o = self.store.one("select * from operators")
        got = asyncio.run(CH.whatsapp_send(self.store, o, "+447700900321", "Aegean Boats", "hi"))
        self.assertEqual((got["ok"], got["unreachable"]), (False, True))


class QuietHours(unittest.TestCase):
    def test_send_time(self):
        from dive_service.channels import send_time
        q = "22:00-08:00"
        late = datetime(2026, 10, 20, 20, 30, tzinfo=timezone.utc)                              # 23:30 Mykonos
        self.assertEqual(send_time(late, q).astimezone(ZoneInfo("Europe/Athens")).strftime("%d %H:%M"), "21 08:00")
        noon = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)                                # 12:00 Mykonos
        self.assertEqual(send_time(noon, q), noon)
        early = datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc)                               # 06:00 Mykonos
        self.assertEqual(send_time(early, q).astimezone(ZoneInfo("Europe/Athens")).strftime("%d %H:%M"), "21 08:00")
        self.assertEqual(send_time(late, None), late)


class TheDemo(Base):
    def test_the_whole_script_with_simulated_replies(self):
        by, ch = self.onboard()
        key = self.key()
        pkgs = self.gen(key, "packages.list", {}).json()["result"]["packages"]
        self.assertEqual([p["title"] for p in pkgs], ["Discover Mykonos"])
        pid, tue = pkgs[0]["package_id"], self.next_wd(1)
        av = self.gen(key, "availability.check", {"package_id": pid, "date": tue, "start_time": "09:00", "party": 4}).json()["result"]
        self.assertEqual([l["availability"] for l in av["legs"]], ["likely", "likely", "likely", "available"])
        q = self.gen(key, "bookings.quote", {"package_id": pid, "date": tue, "start_time": "09:00", "party": 4,
                                             "customer": {"name": "Marta Ruiz", "phone": "+15005550101"}}, idem="quote-marta-000000001").json()
        b = q["result"]
        lines = b["read_back"]["lines"]
        self.assertEqual(lines[0], "Blue Kyma Diving (demo) · Discover Mykonos")
        self.assertTrue(any("Aegean Boats · confirmed by the boat within 2 h" in l for l in lines), lines)
        self.assertTrue(any("Kyma Gear · confirmed by email within 2 h" in l for l in lines), lines)
        self.assertTrue(any("Taverna Agios · booked on their form" in l for l in lines), lines)
        self.assertTrue(any("Hotel Kyma View · instant (feed)" in l for l in lines), lines)
        self.assertIn("Total €660 for 4", lines[-2])
        again = self.gen(key, "bookings.quote", {"package_id": pid, "date": tue, "start_time": "09:00", "party": 4,
                                                 "customer": {"name": "Marta Ruiz", "phone": "+15005550101"}}, idem="quote-marta-000000001").json()
        self.assertEqual((again["replayed"], again["result"]["bundle_id"]), (True, b["bundle_id"]))
        # no yes → refused; the customer's tap on THEIR phone → the approval
        self.assertEqual(self.gen(key, "bookings.confirm", {"bundle_id": b["bundle_id"]}, idem="confirm-marta-0000001").json()["error"]["code"], "approval_required")
        self.gen(key, "approvals.request", {"bundle_id": b["bundle_id"]})
        link = self.store.one("select body from captured where channel = 'sms' order by id desc")["body"].rsplit(" ", 1)[-1]
        path = "/" + link.split("://", 1)[1].split("/", 1)[1]
        page = self.client.get(path).text
        self.assertIn("Yes, book it", page)
        self.assertIn("Aegean Boats", page)
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        self.client.post(path, data={"csrf": csrf}, follow_redirects=False)
        st = self.gen(key, "bookings.status", {"bundle_id": b["bundle_id"]}).json()["result"]
        apv = st["approval"]["approval_id"]
        c = self.gen(key, "bookings.confirm", {"bundle_id": b["bundle_id"]}, idem="confirm-marta-0000002", approval=apv).json()["result"]
        legs = {l["supplier"]: l for l in c["legs"]}
        self.assertEqual(legs["Taverna Agios"]["state"], "confirmed")                           # the form confirmed on the page
        self.assertEqual(legs["Taverna Agios"]["reference"], "TAV-1A2B3C")
        self.assertEqual((legs["Aegean Boats"]["state"], legs["Kyma Gear"]["state"], legs["Hotel Kyma View"]["state"]), ("requested", "requested", "held"))
        self.assertIn("ΝΑΙ", self.sb.sent[-1]["text"])                                          # the boat's request, in Greek
        self.assertIn("Αίτημα κράτησης Blue Kyma Diving", self.sb.sent[-1]["text"])
        self.assertIn("Waiting for Aegean Boats and Kyma Gear to confirm", c["customer_sentence"])
        # the suppliers answer (simulated): the gear email "YES", the boat "ΝΑΙ" through the sandbox's simulate_reply
        self.op("sandbox.supplier_reply", {"leg_id": legs["Kyma Gear"]["leg_id"], "text": "YES"})
        r = self.op("sandbox.supplier_reply", {"leg_id": legs["Aegean Boats"]["leg_id"], "text": "ΝΑΙ"})
        self.assertEqual((r["parse"], r["leg_state"], r["bundle_state"]), ("yes", "confirmed", "confirmed"))
        st = self.gen(key, "bookings.status", {"bundle_id": b["bundle_id"]}).json()["result"]
        self.assertEqual(st["customer_sentence"], "All confirmed. Here's your plan.")
        self.assertEqual({l["supplier"]: l["state"] for l in st["legs"]}["Hotel Kyma View"], "booked")
        # proof: every settled leg and the bundle; each verifies; the boat's holds the sent message + their words
        for l in st["legs"]:
            ev = json.loads(self.store.one("select body from evidence where id = ?", l["evidence_id"])["body"])
            self.assertTrue(M.verify_evidence(ev), l["supplier"])
        boat = json.loads(self.store.one("select body from evidence where id = ?", {l["supplier"]: l for l in st["legs"]}["Aegean Boats"]["evidence_id"])["body"])
        self.assertEqual(boat["sources"][1]["snippet"]["text"], "ΝΑΙ")
        self.assertIn("TEST BRIDGE", boat["sources"][0]["snippet"]["text"])                    # the 1.2 gap, on the record
        bev = json.loads(self.store.one("select body from evidence where id = ?", st["evidence_id"])["body"])
        self.assertEqual((bev["approval"]["method"], bev["outcome"]["kind"]), ("tap", "CONFIRMED"))
        # the yes was used once
        self.assertEqual(self.gen(key, "bookings.confirm", {"bundle_id": b["bundle_id"]}, idem="confirm-marta-0000003", approval=apv).json()["result"]["state"], "confirmed")
        self.assertEqual(self.store.one("select count(*) n from captured where real = 1")["n"], 0)          # 0 real messages

    def test_the_failure_beat_a_required_no_releases_everything(self):
        self.onboard()
        r = self.client.post("/console/api/bookings.test_quote", json={}, headers=CONSOLE).json()["result"]
        legs = {l["supplier"]: l for l in r["legs"]}
        self.assertEqual(legs["Taverna Agios"]["state"], "confirmed")
        self.op("sandbox.supplier_reply", {"leg_id": legs["Kyma Gear"]["leg_id"], "text": "Yes"})
        out = self.op("sandbox.supplier_reply", {"leg_id": legs["Aegean Boats"]["leg_id"], "text": "NO, full"})
        self.assertEqual((out["parse"], out["leg_state"], out["bundle_state"]), ("no", "declined", "failed"))
        b = self.client.post("/console/api/bookings.list", json={}, headers=CONSOLE).json()["result"]["bookings"][0]
        self.assertRegex(b["customer_sentence"], r"^Aegean Boats can't take your group on Thu \d\d [A-Z]{3} 20\d\d\. Nothing has been charged\. Blue Kyma Diving will offer you another time\.$")
        st = {l["supplier"]: l["state"] for l in b["legs"]}
        self.assertEqual(st, {"Aegean Boats": "declined", "Kyma Gear": "released", "Taverna Agios": "released", "Hotel Kyma View": "released"})
        rel = [m for m in self.store.q("select * from captured where body like '%cancelled%' or body like '%ακυρώνεται%'")]
        self.assertEqual(len(rel), 1)                                                            # a "sorry" to the gear shop, who said yes
        self.assertEqual([h for h in CH._HOLDS.values() if h["booked"]], [])                     # the hotel was never booked

    def test_an_unclear_reply_goes_to_the_operator_and_a_changed_leg_voids_the_yes(self):
        self.onboard()
        key = self.key()
        pid = self.gen(key, "packages.list", {}).json()["result"]["packages"][0]["package_id"]
        b = self.gen(key, "bookings.quote", {"package_id": pid, "date": self.next_wd(1), "start_time": "09:00", "party": 4, "customer": {"name": "Ana"}},
                     idem="quote-ana-0000000001").json()["result"]
        bundle = self.store.one("select * from bundles where id = ?", b["bundle_id"])
        apv = BN.approve(self.store, bundle)
        self.store.x("update products set price = ? where title like 'Gear%'", json.dumps({"amount_minor": 3500, "currency": "EUR"}))   # terms changed
        r = self.gen(key, "bookings.confirm", {"bundle_id": b["bundle_id"]}, idem="confirm-ana-00000001", approval=apv).json()
        self.assertEqual((r["error"]["code"], r["error"]["details"]["void_reason"]), ("bundle_changed", "payload_changed"))
        self.store.x("update products set price = ? where title like 'Gear%'", json.dumps({"amount_minor": 3000, "currency": "EUR"}))
        b = self.gen(key, "bookings.quote", {"package_id": pid, "date": self.next_wd(1), "start_time": "09:00", "party": 4, "customer": {"name": "Ana"}},
                     idem="quote-ana-0000000002").json()["result"]
        apv = BN.approve(self.store, self.store.one("select * from bundles where id = ?", b["bundle_id"]))
        c = self.gen(key, "bookings.confirm", {"bundle_id": b["bundle_id"]}, idem="confirm-ana-00000002", approval=apv).json()["result"]
        boat = [l for l in c["legs"] if l["supplier"] == "Aegean Boats"][0]
        out = self.op("sandbox.supplier_reply", {"leg_id": boat["leg_id"], "text": "yes but only 3 seats"})
        self.assertEqual((out["parse"], out["leg_state"]), ("unclear", "requested"))            # never guessed
        act = self.client.post("/console/api/activity.list", json={}, headers=CONSOLE).json()["result"]["items"]
        self.assertIn("Aegean Boats replied — unclear: for you to decide", [i["line"] for i in act])

    def test_a_second_rehearsal_reuses_an_open_window_and_reset_empties_the_console(self):
        self.onboard()
        self.assertEqual(self.op("sandbox.reset")["reset"], True)
        self.assertEqual(self.op("suppliers.list")["suppliers"], [])
        by, ch = self.onboard()                                                                  # again: the boat's window is open now
        self.assertTrue(self.sb.sent[0]["template"])                                             # the first time: the template
        verify = [m for m in self.sb.sent if m["text"] and "Reply YES to accept" in m["text"]]
        self.assertEqual(len(verify), 1)                                                         # the operator's own words, inside the window

    def test_keys_are_scoped_and_revocable(self):
        self.onboard()
        k = self.op("operator_keys.issue", {"label": "A"})
        self.assertEqual(self.gen(k["key"], "packages.list", {}, slug="someone-else").status_code, 401)
        self.assertEqual(self.gen("opk_test_" + "x" * 32, "packages.list", {}).status_code, 401)
        self.op("operator_keys.revoke", {"key_id": k["key_id"]})
        self.assertEqual(self.gen(k["key"], "packages.list", {}).status_code, 401)
        self.assertEqual(self.client.post("/op/v1/suppliers.list", json={}).status_code, 401)     # the console's door

    def test_docs_and_pages_carry_the_operators_name_and_footer(self):
        self.onboard()
        d = self.client.get("/o/blue-kyma/docs").text
        self.assertIn("<h1>Blue Kyma Diving API</h1>", d)
        self.assertIn("Blue Kyma API · powered by AgAPI", d)
        self.assertIn("Discover Mykonos", d)
        self.assertIn("This isn't a no", d)
        self.assertIn("Blue Kyma API · powered by AgAPI", self.client.get("/o/blue-kyma/book").text)
        self.assertEqual(self.client.get("/console", follow_redirects=False).status_code, 303)   # the console needs its token

    def test_the_booking_page_end_to_end(self):
        self.onboard()
        pid = self.store.one("select id from packages")["id"]
        r = self.client.post("/o/blue-kyma/book", data={"package_id": pid, "date": self.next_wd(1), "start_time": "09:00", "party": "2",
                                                         "name": "Jo Test", "phone": "+15005550102"})
        self.assertIn("We sent the link to your phone", r.text)
        link = re.search(r'href="(http[^"]+/a/[^"]+)"', r.text).group(1)
        path = "/" + link.split("://", 1)[1].split("/", 1)[1]
        page = self.client.get(path).text
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        self.assertEqual(self.client.post(path, data={"csrf": "wrong"}, follow_redirects=False).status_code, 404)
        r = self.client.post(path, data={"csrf": csrf}, follow_redirects=False)
        self.assertEqual(r.status_code, 303)                                                     # the operator's own page: the tap goes straight on
        self.assertEqual(self.client.post(path, data={"csrf": csrf}, follow_redirects=False).status_code, 404)   # once
        st = self.client.get(r.headers["location"].replace("/b/", "/s/")).json()
        self.assertIn("Waiting for", st["customer_sentence"])


class Actions(Base):
    """CR 65 · the operator's actions on a booking and the cancellation (EU 212 surfaces.md A3, bundles.md §3)."""

    def booking(self, party=4, wd=1, onboard=True):
        if onboard:
            self.onboard()
        key = self.key()
        pid = self.gen(key, "packages.list", {}).json()["result"]["packages"][0]["package_id"]
        b = self.gen(key, "bookings.quote", {"package_id": pid, "date": self.next_wd(wd), "start_time": "09:00", "party": party,
                                             "customer": {"name": "Marta Ruiz", "phone": "+15005550101"}}, idem=f"q-{os.urandom(8).hex()}").json()["result"]
        apv = BN.approve(self.store, self.store.one("select * from bundles where id = ?", b["bundle_id"]))
        c = self.gen(key, "bookings.confirm", {"bundle_id": b["bundle_id"]}, idem=f"c-{os.urandom(8).hex()}", approval=apv).json()["result"]
        return key, c, {l["supplier"]: l for l in c["legs"]}

    def tap(self, phone_link_text="cancellation"):
        body = [m["body"] for m in self.store.q("select body from captured where channel = 'sms' order by id desc") if phone_link_text in m["body"]][0]
        path = "/" + body.rsplit(" ", 1)[-1].split("://", 1)[1].split("/", 1)[1]
        page = self.client.get(path).text
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        r = self.client.post(path, data={"csrf": csrf}, follow_redirects=False)
        return page, r

    def test_accept_3_requotes_for_3_and_asks_the_customer_again(self):
        key, c, legs = self.booking()
        out = self.op("sandbox.supplier_reply", {"leg_id": legs["Aegean Boats"]["leg_id"], "text": "yes but only 3 seats"})
        self.assertEqual(out["parse"], "unclear")
        from dive_service import actions as AC
        self.assertEqual(AC.suggested_party("yes but only 3 seats", 4), 3)
        self.assertEqual(self.op("legs.accept_partial", {"leg_id": legs["Aegean Boats"]["leg_id"], "party": 4}, expect_ok=False)["error"]["code"], "invalid_input")
        r = self.op("legs.accept_partial", {"leg_id": legs["Aegean Boats"]["leg_id"], "party": 3})
        self.assertEqual(r["state"], "replaced")
        self.assertTrue(any("3 divers" in l for l in r["new_read_back"]))                          # a NEW read-back for 3
        self.assertTrue(any("Call Taverna Agios" in t for t in r["todo"]))                         # the form booking: said plainly
        old = self.gen(key, "bookings.status", {"bundle_id": c["bundle_id"]}).json()["result"]
        self.assertEqual(old["state"], "replaced")
        self.assertIn("can take 3 of 4. We've sent you a new read-back", old["customer_sentence"])
        self.assertTrue(all(l["state"] in ("released",) for l in old["legs"]))
        new = self.store.one("select * from bundles where id = ?", r["new_bundle_id"])
        self.assertEqual((new["party"], new["state"]), (3, "quoted"))                              # nothing goes until the new yes
        self.assertTrue(any("approve your booking" in m["body"] for m in self.store.q("select body from captured where channel = 'sms'")))

    def test_treat_as_no_and_ask_again(self):
        key, c, legs = self.booking()
        self.op("sandbox.supplier_reply", {"leg_id": legs["Kyma Gear"]["leg_id"], "text": "maybe?"})
        n_before = len(self.sb.sent)
        r = self.op("legs.ask_again", {"leg_id": legs["Kyma Gear"]["leg_id"]})
        self.assertEqual({l["supplier"]: l["state"] for l in r["legs"]}["Kyma Gear"], "requested")
        self.assertNotIn("parse", {l["supplier"]: l for l in r["legs"]}["Kyma Gear"])           # a fresh answer window
        self.op("sandbox.supplier_reply", {"leg_id": legs["Aegean Boats"]["leg_id"], "text": "ok?"})
        r = self.op("legs.treat_as_no", {"leg_id": legs["Aegean Boats"]["leg_id"], "by": "Nikos (operator)"})
        self.assertEqual(r["state"], "failed")
        self.assertIn("Aegean Boats can't take your group", r["customer_sentence"])
        ev = json.loads(self.store.one("select body from evidence where id = ?", {l["supplier"]: l for l in r["legs"]}["Aegean Boats"]["evidence_id"])["body"])
        self.assertEqual([x["service"] for x in ev["sources"]], ["whatsapp_reply", "operator_decision"])
        self.assertEqual(ev["sources"][0]["snippet"]["text"], "ok?")                             # their words, and the operator's decision
        self.assertEqual(self.op("legs.treat_as_no", {"leg_id": legs["Kyma Gear"]["leg_id"]}, expect_ok=False)["error"]["details"]["rule"], "not_unclear")

    def test_ask_by_phone_record_answer_and_offer_another_time(self):
        key, c, legs = self.booking()
        self.op("legs.ask_by_phone", {"leg_id": legs["Aegean Boats"]["leg_id"], "by": "Nikos"})
        self.op("sandbox.supplier_reply", {"leg_id": legs["Kyma Gear"]["leg_id"], "text": "YES"})
        r = self.op("legs.record_answer", {"leg_id": legs["Aegean Boats"]["leg_id"], "answer": "yes", "note": "Spoke to Kostas at 10:12", "by": "Nikos"})
        self.assertEqual(r["state"], "confirmed")
        boat = {l["supplier"]: l for l in r["legs"]}["Aegean Boats"]
        ev = json.loads(self.store.one("select body from evidence where id = ?", boat["evidence_id"])["body"])
        self.assertEqual((ev["sources"][0]["service"], ev["sources"][0]["snippet"]["source"]), ("manual", "operator:Nikos"))
        self.assertIn("Spoke to Kostas", ev["sources"][0]["snippet"]["text"])
        self.assertEqual(self.op("legs.record_answer", {"leg_id": legs["Aegean Boats"]["leg_id"], "answer": "maybe", "by": "N"}, expect_ok=False)["error"]["code"], "invalid_input")
        # a booking that failed (no answer): the late phone yes is recorded, never revives it; Offer another time goes on
        key2, c2, legs2 = self.booking(wd=3, onboard=False)
        self.store.x("update legs set answer_by = ? where id = ?", "2000-01-01T00:00:00.000000Z", legs2["Aegean Boats"]["leg_id"])
        st = self.gen(key2, "bookings.status", {"bundle_id": c2["bundle_id"]}).json()["result"]
        self.assertEqual(st["state"], "failed")
        self.assertIn("didn't confirm in time", st["customer_sentence"])
        late = self.op("legs.record_answer", {"leg_id": legs2["Aegean Boats"]["leg_id"], "answer": "yes", "note": "called back", "by": "Nikos"})
        self.assertEqual((late["state"], late["late_answer"]["next"]), ("failed", "offer_another_time"))
        self.assertEqual(self.op("bookings.offer_another_time", {"bundle_id": c["bundle_id"], "date": self.next_wd(5), "start_time": "09:00"}, expect_ok=False)["error"]["code"], "invalid_input")
        off = self.op("bookings.offer_another_time", {"bundle_id": c2["bundle_id"], "date": self.next_wd(5), "start_time": "09:00"})
        self.assertEqual(self.store.one("select state from bundles where id = ?", off["new_bundle_id"])["state"], "quoted")

    def test_cancel_has_its_own_read_back_and_the_customers_yes_then_each_supplier_is_told(self):
        key, c, legs = self.booking()
        self.op("sandbox.supplier_reply", {"leg_id": legs["Kyma Gear"]["leg_id"], "text": "YES"})
        self.op("sandbox.supplier_reply", {"leg_id": legs["Aegean Boats"]["leg_id"], "text": "ΝΑΙ"})
        r = self.gen(key, "bookings.cancel", {"bundle_id": c["bundle_id"]}, idem="cancel-1-0000000001").json()
        self.assertEqual(r["error"]["code"], "approval_required")
        lines = r["error"]["details"]["read_back"]["lines"]
        self.assertTrue(lines[0].startswith("Cancel: Blue Kyma Diving · Discover Mykonos"))
        self.assertIn("• Aegean Boats is told on WhatsApp", lines)
        self.assertIn("• Taverna Agios is told by phone (their form can't cancel)", lines)
        # the booking's yes can't cancel: a yes is for one read-back
        old = self.store.one("select id from approvals where bundle_id = ?", c["bundle_id"])["id"]
        self.assertEqual(self.gen(key, "bookings.cancel", {"bundle_id": c["bundle_id"]}, idem="cancel-1-0000000002", approval=old).json()["error"]["code"], "approval_void")
        page, _ = self.tap("cancellation")
        self.assertIn("Yes, cancel it", page)
        st = self.gen(key, "bookings.status", {"bundle_id": c["bundle_id"]}).json()["result"]
        apv = st["cancellation"]["approval"]["approval_id"]
        n = len(self.sb.sent)
        done = self.gen(key, "bookings.cancel", {"bundle_id": c["bundle_id"]}, idem="cancel-1-0000000003", approval=apv).json()["result"]
        self.assertEqual(done["state"], "cancelled")
        self.assertEqual(done["customer_sentence"], "Your booking is cancelled. Nothing more will be charged.")
        self.assertEqual({l["supplier"]: l["state"] for l in done["legs"]}, {"Aegean Boats": "cancelled", "Kyma Gear": "cancelled", "Taverna Agios": "cancelled", "Hotel Kyma View": "cancelled"})
        self.assertIn("ακυρώθηκε", self.sb.sent[-1]["text"])                                     # the boat, told in Greek on WhatsApp
        self.assertTrue(any("cancelled by the customer" in m["body"] for m in self.store.q("select body from captured where channel = 'email'")))
        bev = json.loads(self.store.one("select body from evidence where id = ?", done["evidence_id"])["body"])
        self.assertEqual((bev["operation"], bev["approval"]["method"]), ("bookings.cancel", "tap"))
        todo = [e["line"] for e in self.store.q("select line from events where kind = 'todo'")]
        self.assertTrue(any("Call Taverna Agios to cancel" in t for t in todo))
        self.assertEqual(self.gen(key, "bookings.cancel", {"bundle_id": c["bundle_id"]}, idem="cancel-1-0000000003", approval=apv).json()["replayed"], True)
        from dive_service import actions as AC
        self.assertTrue(R.explicit_yes_any("Yes, cancel it", "cancel")[0])                       # 1.1 act_kind: a typed yes to a cancellation
        self.assertEqual(self.store.one("select count(*) n from captured where real = 1")["n"], 0)

    def test_a_cancellation_read_back_that_changed_is_void(self):
        key, c, legs = self.booking()
        r = self.gen(key, "bookings.cancel", {"bundle_id": c["bundle_id"]}, idem="cancel-2-0000000001").json()
        self.tap("cancellation")
        self.op("sandbox.supplier_reply", {"leg_id": legs["Kyma Gear"]["leg_id"], "text": "YES"})     # a leg changed after the yes
        st = self.gen(key, "bookings.status", {"bundle_id": c["bundle_id"]}).json()["result"]
        apv = st["cancellation"]["approval"]["approval_id"]
        self.assertEqual(self.gen(key, "bookings.cancel", {"bundle_id": c["bundle_id"]}, idem="cancel-2-0000000002", approval=apv).json()["error"]["code"], "bundle_changed")



class StartPage(Base):
    """CR 66 · Tyler's start page: behind the console token; 10 steps, each one link that resolves; Reset demo → the starting state;
    the phone and Proof links land on the newest; nothing is sent."""

    def test_behind_the_console_token(self):
        for path in ("/start", "/start/phone", "/start/proof"):
            r = self.client.get(path, follow_redirects=False)
            self.assertEqual((r.status_code, r.headers["location"]), (303, "/console/login?next=/start"), path)
        self.onboard()
        r = self.client.post("/start/reset", follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(len(self.op("suppliers.list")["suppliers"]), 4)                       # no token: nothing was reset
        self.assertIn('name="next" value="/start"', self.client.get("/console/login?next=/start").text)
        self.assertNotIn('name="next"', self.client.get("/console/login?next=https://evil.example").text)
        r = self.client.post("/console/login", data={"token": "dive-local", "next": "/start"}, follow_redirects=False)
        self.assertEqual(r.headers["location"], "/start")
        self.assertEqual(self.client.get("/start", follow_redirects=False).status_code, 200)   # the cookie opens it
        r = self.client.post("/console/login", data={"token": "dive-local", "next": "https://evil.example"}, follow_redirects=False)
        self.assertEqual(r.headers["location"], "/console")

    def test_ten_steps_each_a_link_that_resolves(self):
        self.onboard()
        page = self.client.get("/start", headers=CONSOLE).text
        self.assertEqual(page.count('data-testid="beat"'), 10)
        links = re.findall(r'data-testid="beat-\d+"', page)
        self.assertEqual(len(links), 9)                                                          # the opening is just talk
        hrefs = re.findall(r'<a class="btn go" href="([^"]+)"', page)
        self.assertEqual(sorted({h.split("#")[0] for h in hrefs}), ["/console", "/o/blue-kyma/book", "/o/blue-kyma/docs", "/start/phone", "/start/proof"])
        self.assertEqual({h.split("#")[1] for h in hrefs if "#" in h}, {"find", "drawer", "activity"})
        for h in sorted(set(hrefs)):
            self.assertEqual(self.client.get(h.split("#")[0], headers=CONSOLE).status_code, 200, h)
        for say in ("AgAPI gives them one.", "In test mode we can play the supplier.", "nothing is charged, nothing half-booked"):
            self.assertIn(say, page)
        self.assertIn(config.SANDBOX_URL + "/docs", page)                                        # AgAPI's public docs, linked
        self.assertIn("4 suppliers confirmed · 4 channels verified · package published · 0 booking(s)", page)
        c = self.client.get("/console", headers=CONSOLE).text
        self.assertIn('id="findbtn"', c)
        self.assertIn('h0.startsWith("proof=")', c)

    def test_reset_demo_restores_the_starting_state(self):
        self.op("operators.put", {"slug": "blue-kyma", "name": "Renamed in a rehearsal", "timezone": "Europe/London", "languages": ["en"],
                                  "site_url": self.site, "footer": "Some other footer"})
        self.onboard()
        self.client.post("/console/api/bookings.test_quote", json={}, headers=CONSOLE)
        self.assertTrue(self.store.one("select count(*) n from captured")["n"] > 0)
        r = self.client.post("/start/reset", headers=CONSOLE, follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/start?done=reset"))
        row = self.store.one("select * from operators where slug = 'blue-kyma'")
        self.assertEqual((row["name"], row["timezone"], json.loads(row["languages"]), row["site_url"], row["footer"]),
                         ("Blue Kyma Diving (demo)", "Europe/Athens", ["en", "el"], self.site, "Blue Kyma API · powered by AgAPI"))
        self.assertEqual(self.op("suppliers.list")["suppliers"], [])
        self.assertEqual(self.op("packages.list")["packages"], [])
        for t in ("bundles", "events", "evidence", "op_keys"):
            self.assertEqual(self.store.one(f"select count(*) n from {t}")["n"], 0, t)
        self.assertEqual(self.store.one("select count(*) n from captured")["n"], 0)
        page = self.client.get("/start?done=reset", headers=CONSOLE).text
        self.assertIn("✓ Reset. The console is empty and ready for step 1.", page)
        self.assertIn("0 suppliers confirmed · 0 channels verified · package not published · 0 booking(s)", page)
        self.onboard()                                                                           # and the demo runs again from there

    def test_reset_on_a_fresh_service_creates_the_operator(self):
        self.store.x("delete from operators")
        self.assertEqual(self.client.post("/start/reset", headers=CONSOLE, follow_redirects=False).status_code, 303)
        self.assertEqual(self.store.one("select name from operators where slug = 'blue-kyma'")["name"], "Blue Kyma Diving (demo)")

    def test_the_phone_and_proof_links_land_on_the_newest(self):
        self.assertIn("Nothing on the customer", self.client.get("/start/phone", headers=CONSOLE).text)
        self.assertIn("No booking has proof yet", self.client.get("/start/proof", headers=CONSOLE).text)
        self.onboard()
        key = self.key()
        pid = self.gen(key, "packages.list", {}).json()["result"]["packages"][0]["package_id"]
        b = self.gen(key, "bookings.quote", {"package_id": pid, "date": self.next_wd(1), "start_time": "09:00", "party": 4,
                                             "customer": {"name": "Marta Ruiz", "phone": "+15005550101"}}, idem="quote-start-00000001").json()["result"]
        self.gen(key, "approvals.request", {"bundle_id": b["bundle_id"]})
        link = self.store.one("select body from captured where channel = 'sms' order by id desc")["body"].rsplit(" ", 1)[-1]
        r = self.client.get("/start/phone", headers=CONSOLE, follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (303, link[len(config.PUBLIC_URL):]))
        self.assertIn("Yes, book it", self.client.get(r.headers["location"]).text)
        self.assertIn("No booking has proof yet", self.client.get("/start/proof", headers=CONSOLE).text)   # not confirmed yet
        r = self.client.post("/console/api/bookings.test_quote", json={}, headers=CONSOLE).json()["result"]
        legs = {l["supplier"]: l for l in r["legs"]}
        self.op("sandbox.supplier_reply", {"leg_id": legs["Kyma Gear"]["leg_id"], "text": "YES"})
        self.op("sandbox.supplier_reply", {"leg_id": legs["Aegean Boats"]["leg_id"], "text": "ΝΑΙ"})
        ev = self.store.one("select evidence_id from bundles where id = ?", r["bundle_id"])["evidence_id"]
        self.assertTrue(ev)
        r = self.client.get("/start/proof", headers=CONSOLE, follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/console#proof=" + ev))
        self.assertEqual(self.store.one("select count(*) n from captured where real = 1")["n"], 0)          # 0 real messages


if __name__ == "__main__":
    unittest.main()
