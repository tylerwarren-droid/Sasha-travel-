"""CR 67 · the switch-on paths, with fakes for Twilio and Resend (no request leaves a test): OFF unless every variable is present
(exactly today's behaviour), the real WhatsApp sender to allow-listed numbers only, /hooks/twilio/whatsapp (signature, allow-list,
STOP, the 24-hour window) → the classifier → the bundle, the real gear email and /hooks/resend/inbound (svix signature, DIVE's domain,
allow-list, the quoted request ignored, STOP, a duplicate delivery) → the classifier, and the fake site's contacts from variables.

    python -m unittest dive_service.tests.test_switch_on -v      (from the repo root)
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from unittest import mock

from dive_service import channels as CH, config, model as M
from dive_service.tests.test_dive import CONSOLE, Base

JON = "+306900000001"            # a test number (never dialled: Twilio is a fake here)
OTHER = "+306900000099"
GEAR = "demo-gear@example.org"
TOKEN = "twilio-test-token"
SECRET = "whsec_" + base64.b64encode(b"k" * 24).decode()
HOOK = config.PUBLIC_URL + "/hooks/twilio/whatsapp"


class FakeHTTP:
    """Twilio's Messages API and Resend's received-email read, as fakes; every call recorded."""

    def __init__(self):
        self.calls, self.mail = [], {}

    async def __call__(self, method, url, *, headers=None, data=None, auth=None):
        self.calls.append({"method": method, "url": url, "data": data, "auth": auth})
        if "api.twilio.com" in url:
            return 201, {"sid": "SM" + hashlib.sha256(str(len(self.calls)).encode()).hexdigest()[:32], "status": "queued"}
        if "/emails/receiving/" in url:
            pid = url.rsplit("/", 1)[1]
            return (200, {"text": self.mail[pid]}) if pid in self.mail else (404, {})
        raise AssertionError("an unexpected request: " + url)

    def twilio(self):
        return [c for c in self.calls if "api.twilio.com" in c["url"]]


def sign_twilio(params, token=TOKEN, url=HOOK):
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


class Switch(Base):
    def setUp(self):
        super().setUp()
        self.http = FakeHTTP()
        p = mock.patch.object(CH, "HTTP", self.http)
        p.start()
        self.addCleanup(p.stop)
        self.n = 0

    def patch(self, **kw):
        for k, v in kw.items():
            p = mock.patch.object(config, k, v)
            p.start()
            self.addCleanup(p.stop)

    def whatsapp_on(self, allow=(JON,)):
        self.patch(REAL_WHATSAPP=True, TWILIO_SID="AC" + "0" * 32, TWILIO_TOKEN=TOKEN, WHATSAPP_ALLOW=set(allow))

    def email_on(self):
        self.patch(RESEND_KEY="re_test", EMAIL_FROM="Blue Kyma Diving (demo) <bookings@dive.kanoe.ai>", EMAIL_ALLOW={GEAR},
                   RESEND_WEBHOOK_SECRET=SECRET)

    def wa(self, text, frm=JON, token=TOKEN, sig=None):
        self.n += 1
        params = {"From": "whatsapp:" + frm, "To": "whatsapp:+14155238886", "Body": text, "MessageSid": f"SM{self.n:032d}", "NumMedia": "0"}
        h = {} if sig == "none" else {"X-Twilio-Signature": sig or sign_twilio(params, token)}
        return self.client.post("/hooks/twilio/whatsapp", data=params, headers=h)

    def mail(self, text, *, frm=GEAR, to="bookings@dive.kanoe.ai", subject="Re: booking requests", pid=None, secret=SECRET, stamp=None):
        self.n += 1
        pid = pid or f"em_{self.n}"
        self.http.mail[pid] = text
        raw = json.dumps({"type": "email.received", "data": {"email_id": pid, "from": f"Kyma Gear <{frm}>", "to": [to], "subject": subject}}).encode()
        sid, st = f"msg_{self.n}", str(stamp or int(time.time()))
        key = base64.b64decode(secret.removeprefix("whsec_"))
        sig = "v1," + base64.b64encode(hmac.new(key, f"{sid}.{st}.".encode() + raw, hashlib.sha256).digest()).decode()
        return self.client.post("/hooks/resend/inbound", content=raw, headers={"svix-id": sid, "svix-timestamp": st, "svix-signature": sig,
                                                                               "content-type": "application/json"})

    def suppliers(self):
        """Find → confirm ×4 (Rival Boats: Not ours) → each one's channel, from the fake site's contacts."""
        by = {d["name"]: d for d in self.op("suppliers.draft_from_site")["drafts"]}
        for n in ("Aegean Boats", "Kyma Gear", "Taverna Agios", "Hotel Kyma View"):
            self.op("suppliers.put", {"supplier_id": by[n]["supplier_id"], "status": "confirmed"})
        self.op("suppliers.put", {"supplier_id": by["Rival Boats"]["supplier_id"], "status": "rejected"})
        ch = {"boat": self.op("channels.put", {"supplier_id": by["Aegean Boats"]["supplier_id"], "kind": "whatsapp",
                                               "address": by["Aegean Boats"]["contacts"]["whatsapp"], "language": "el"}),
              "gear": self.op("channels.put", {"supplier_id": by["Kyma Gear"]["supplier_id"], "kind": "email", "address": by["Kyma Gear"]["contacts"]["email"]}),
              "taverna": self.op("channels.put", {"supplier_id": by["Taverna Agios"]["supplier_id"], "kind": "web_form",
                                                  "address": by["Taverna Agios"]["contacts"]["web_form"]}),
              "hotel": self.op("channels.put", {"supplier_id": by["Hotel Kyma View"]["supplier_id"], "kind": "feed", "address": "feed:sandbox-hotels#Hotel Kyma View"})}
        for k in ("taverna", "hotel"):
            self.op("channels.verify", {"channel_id": ch[k]["channel_id"]})
        return by, ch

    def channel(self, cid):
        return self.store.one("select * from channels where id = ?", cid)

    def publish(self):
        self.op("packages.from_fixture")
        self.op("operator_api.publish")

    def thursday(self):
        r = self.client.post("/console/api/bookings.test_quote", json={}, headers=CONSOLE).json()
        self.assertTrue(r["ok"], r)
        return r["result"], {l["supplier"]: l for l in r["result"]["legs"]}

    def real_count(self):
        return self.store.one("select count(*) n from captured where real = 1")["n"]


class Off(Switch):
    def test_with_no_variables_everything_is_exactly_todays(self):
        self.assertEqual(self.client.get("/health").json()["switches"], {"whatsapp_real": False, "whatsapp_hook": False, "email_real": False,
                                                                         "email_hook": False, "whatsapp_allow_count": 0, "email_allow_count": 0})
        self.assertEqual(self.wa("YES").status_code, 404)                                       # the hooks don't exist until switched on
        self.assertEqual(self.mail("YES").status_code, 404)
        site = self.client.get("/fake/blue-kyma/partners").text
        self.assertIn("+447700900321", site)                                                    # the fixtures, as before
        self.assertIn("gear@kyma-gear.example", site)
        self.onboard()                                                                           # the whole simulated onboarding, unchanged
        self.assertEqual(self.http.calls, [])                                                    # no request to Twilio or Resend
        self.assertEqual(self.real_count(), 0)
        self.assertIn("simulated", self.client.get("/start", headers=CONSOLE).text)
        self.assertIn("nothing on this demo sends a real message", self.client.get("/start", headers=CONSOLE).text)

    def test_half_switched_on_is_off(self):
        for kw in ({"TWILIO_SID": "AC" + "0" * 32, "TWILIO_TOKEN": TOKEN, "WHATSAPP_ALLOW": {JON}},              # no on switch
                   {"REAL_WHATSAPP": True, "TWILIO_TOKEN": TOKEN, "WHATSAPP_ALLOW": {JON}},                       # no account SID
                   {"REAL_WHATSAPP": True, "TWILIO_SID": "AC" + "0" * 32, "TWILIO_TOKEN": TOKEN, "WHATSAPP_ALLOW": set()}):   # nobody allowed
            with mock.patch.multiple(config, **kw):
                self.assertFalse(config.whatsapp_real_on(), kw)
        with mock.patch.multiple(config, RESEND_KEY="re_test", EMAIL_FROM="x <b@dive.kanoe.ai>", EMAIL_ALLOW=set()):
            self.assertFalse(config.email_real_on())


class WhatsAppReal(Switch):
    def test_the_boat_on_real_whatsapp_end_to_end(self):
        self.whatsapp_on()
        self.assertEqual(self.client.get("/health").json()["switches"]["whatsapp_real"], True)
        self.assertNotIn(TOKEN, self.client.get("/health").text)                                 # never a value
        self.assertIn(JON, self.client.get("/fake/blue-kyma/partners").text)                     # the site lists the one allow-listed number
        by, ch = self.suppliers()
        boat = ch["boat"]["channel_id"]
        self.assertEqual(self.channel(boat)["address"], JON)
        # before Jon says hi: outside the 24-hour window — refused here, never sent, and not a no
        r = self.op("channels.verify", {"channel_id": boat}, expect_ok=False)
        self.assertEqual(r["error"]["code"], "upstream_unreachable")
        self.assertEqual(self.http.twilio(), [])
        # the morning of the run: Jon says hi → the window opens
        self.assertEqual(self.wa("hi").text, '<?xml version="1.0" encoding="UTF-8"?><Response></Response>')
        sent_before = len(self.sb.sent)
        self.assertEqual(self.op("channels.verify", {"channel_id": boat})["state"], "sent")
        t = self.http.twilio()
        self.assertEqual(len(t), 1)
        self.assertEqual((t[0]["data"]["To"], t[0]["data"]["From"]), ("whatsapp:" + JON, "whatsapp:+14155238886"))
        self.assertIn("Reply YES to accept", t[0]["data"]["Body"])
        self.assertEqual(t[0]["auth"][0], "AC" + "0" * 32)
        self.assertEqual(len(self.sb.sent), sent_before)                                         # not through the sandbox
        self.wa("YES")
        self.assertEqual(self.channel(boat)["verified"], 1)                                      # their YES, from the hook
        self.assertIn("they replied YES on WhatsApp", self.channel(boat)["verified_how"])
        self.op("channels.verify", {"channel_id": ch["gear"]["channel_id"]})                     # the gear email: simulated (not switched on)
        self.op("sandbox.supplier_reply", {"channel_id": ch["gear"]["channel_id"], "text": "YES"})
        self.publish()
        b, legs = self.thursday()
        self.assertEqual(legs["Aegean Boats"]["state"], "requested")
        self.assertIn("Απαντήστε ΝΑΙ ή ΟΧΙ", self.http.twilio()[-1]["data"]["Body"])               # the request, in Greek, for real
        self.op("sandbox.supplier_reply", {"leg_id": legs["Kyma Gear"]["leg_id"], "text": "YES"})
        self.wa("ΝΑΙ")                                                                           # Jon's answer → the classifier → the bundle
        out = self.client.post("/console/api/bookings.list", json={}, headers=CONSOLE).json()["result"]["bookings"][0]
        self.assertEqual(out["state"], "confirmed")
        leg = self.store.one("select * from legs where id = ?", legs["Aegean Boats"]["leg_id"])
        self.assertEqual((leg["state"], leg["parse"]), ("confirmed", "yes"))
        ev = json.loads(self.store.one("select body from evidence where id = ?", leg["evidence_id"])["body"])
        self.assertTrue(M.verify_evidence(ev))
        self.assertEqual(ev["sources"][1]["snippet"]["text"], "ΝΑΙ")                            # their own words, on the record
        self.assertTrue(ev["sources"][0]["snippet"]["text"].startswith("message SM"))           # Twilio's message id
        self.assertEqual(self.real_count(), 2)                                                   # exactly 2: the verification + the request
        self.assertEqual({r["to_"] for r in self.store.q("select to_ from captured where real = 1")}, {JON})
        self.assertIn("REAL", self.client.get("/start", headers=CONSOLE).text)

    def test_a_bad_signature_is_refused_and_nothing_is_read(self):
        self.whatsapp_on()
        self.assertEqual(self.wa("hi", sig="none").status_code, 403)
        self.assertEqual(self.wa("hi", token="someone-elses-token").status_code, 403)
        self.assertEqual(self.wa("hi", sig="AAAA").status_code, 403)
        self.assertEqual(self.store.one("select count(*) n from inbound")["n"], 0)
        self.assertFalse(CH.window_open(self.store, JON))

    def test_a_number_not_on_the_allow_list(self):
        self.whatsapp_on()
        r = self.wa("YES", frm=OTHER)
        self.assertEqual(r.status_code, 200)                                                     # Twilio is answered; nothing is read
        self.assertEqual(self.store.one("select count(*) n from inbound")["n"], 0)
        o = self.store.one("select * from operators")
        got = asyncio.run(CH.whatsapp_send(self.store, o, OTHER, "Someone", "hello"))           # a send to it: simulated, as today
        self.assertTrue(got["ok"])
        self.assertNotEqual(got.get("real"), True)
        self.assertEqual(self.http.twilio(), [])
        self.assertEqual(self.sb.sent[-1]["to"], OTHER)
        self.assertEqual(self.real_count(), 0)

    def test_stop_means_no_more_messages_never_a_no(self):
        self.whatsapp_on()
        by, ch = self.suppliers()
        self.wa("hi")
        self.op("channels.verify", {"channel_id": ch["boat"]["channel_id"]})
        self.wa("YES")
        self.op("channels.verify", {"channel_id": ch["gear"]["channel_id"]})
        self.op("sandbox.supplier_reply", {"channel_id": ch["gear"]["channel_id"], "text": "YES"})
        self.publish()
        b, legs = self.thursday()
        n = len(self.http.twilio())
        self.wa("STOP")
        leg = self.store.one("select * from legs where id = ?", legs["Aegean Boats"]["leg_id"])
        self.assertEqual((leg["state"], leg["parse"]), ("requested", None))                    # not declined: STOP isn't about the booking
        self.assertTrue(CH.opted_out(self.store, "whatsapp", JON))
        acts = [i["line"] for i in self.client.post("/console/api/activity.list", json={}, headers=CONSOLE).json()["result"]["items"]]
        self.assertTrue(any("sent STOP" in a and "Not a no" in a for a in acts), acts)
        o = self.store.one("select * from operators")
        got = asyncio.run(CH.whatsapp_send(self.store, o, JON, "Aegean Boats", "again"))
        self.assertEqual((got["ok"], got["unreachable"]), (False, True))
        self.assertIn("STOP", got["why"])
        self.assertEqual(len(self.http.twilio()), n)                                             # nothing more went to Jon
        self.wa("START")
        self.assertFalse(CH.opted_out(self.store, "whatsapp", JON))
        self.assertTrue(asyncio.run(CH.whatsapp_send(self.store, o, JON, "Aegean Boats", "again"))["ok"])

    def test_the_24_hour_window(self):
        self.whatsapp_on()
        o = self.store.one("select * from operators")
        self.wa("hi")
        self.assertTrue(CH.window_open(self.store, JON))
        self.store.x("update inbound set received_at = '2026-01-01T08:00:00.000000Z'")         # their hi was long ago
        got = asyncio.run(CH.whatsapp_send(self.store, o, JON, "Aegean Boats", "hello"))
        self.assertFalse(got["ok"])
        self.assertIn("24-hour window", got["why"])
        self.assertEqual(self.http.twilio(), [])

    def test_a_duplicate_delivery_is_read_once(self):
        self.whatsapp_on()
        params = {"From": "whatsapp:" + JON, "To": "whatsapp:+14155238886", "Body": "hi", "MessageSid": "SM" + "7" * 32}
        for _ in range(2):
            self.assertEqual(self.client.post("/hooks/twilio/whatsapp", data=params, headers={"X-Twilio-Signature": sign_twilio(params)}).status_code, 200)
        self.assertEqual(self.store.one("select count(*) n from inbound")["n"], 1)


class EmailReal(Switch):
    def gear_verified(self):
        self.email_on()
        by, ch = self.suppliers()
        self.op("channels.verify", {"channel_id": ch["boat"]["channel_id"]})                     # the boat: simulated (not switched on)
        self.op("sandbox.supplier_reply", {"channel_id": ch["boat"]["channel_id"], "text": "YES"})
        return by, ch

    def resend_send(self):
        sent = []

        class R_:
            status_code = 200

            def json(self):
                return {"id": f"re_{len(sent)}"}

        class C:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def post(self, url, headers=None, json=None):
                sent.append(json); return R_()
        p = mock.patch("httpx.AsyncClient", C)
        p.start()
        self.addCleanup(p.stop)
        return sent

    def test_the_gear_email_real_end_to_end(self):
        sent = self.resend_send()
        self.email_on()
        self.assertIn(GEAR, self.client.get("/fake/blue-kyma/partners").text)                    # the site lists the one allow-listed inbox
        by, ch = self.gear_verified()
        gear = ch["gear"]["channel_id"]
        self.assertEqual(self.channel(gear)["address"], GEAR)
        self.op("channels.verify", {"channel_id": gear})
        self.assertEqual((len(sent), sent[0]["to"], sent[0]["from"]), (1, [GEAR], "Blue Kyma Diving (demo) <bookings@dive.kanoe.ai>"))
        # their reply quotes our request ("Reply YES to accept") — only what they typed above it counts
        r = self.mail("Yes, confirmed.\n\nOn Thu, 9 Oct 2026 at 10:02, Blue Kyma Diving (demo) wrote:\n> Blue Kyma Diving (demo) will send you booking "
                      "requests by email. Reply YES to accept.")
        self.assertEqual(r.json()["result"], "verification")
        self.assertEqual(self.channel(gear)["verified"], 1)
        self.publish()
        b, legs = self.thursday()
        self.assertEqual(legs["Kyma Gear"]["state"], "requested")
        self.assertEqual(len(sent), 2)
        ref = sent[1]["subject"].split("]")[0] + "]"
        # a reply quoting "Reply YES or NO" below their own no: their no, not "both" (unclear)
        r = self.mail("No sorry, fully booked that day.\n\n> Blue Kyma booking request: gear for 4. Reply YES or NO.", subject="Re: " + sent[1]["subject"])
        self.assertEqual(r.json()["result"], "leg")
        leg = self.store.one("select * from legs where id = ?", legs["Kyma Gear"]["leg_id"])
        self.assertEqual((leg["state"], leg["parse"]), ("declined", "no"))
        bk = self.client.post("/console/api/bookings.list", json={}, headers=CONSOLE).json()["result"]["bookings"][0]
        self.assertEqual(bk["state"], "failed")
        self.assertIn("Nothing has been charged.", bk["customer_sentence"])
        ev = json.loads(self.store.one("select body from evidence where id = ?", leg["evidence_id"])["body"])
        self.assertTrue(M.verify_evidence(ev))
        self.assertEqual(ev["sources"][1]["snippet"]["text"], "No sorry, fully booked that day.")
        self.assertTrue(ref.startswith("[BK-"))
        self.assertEqual(self.real_count(), 2)
        self.assertEqual(self.http.twilio(), [])

    def test_bad_or_stale_signatures_other_domains_and_strangers_are_not_read(self):
        self.email_on()
        self.assertEqual(self.mail("YES", secret="whsec_" + base64.b64encode(b"x" * 24).decode()).status_code, 401)
        self.assertEqual(self.mail("YES", stamp=int(time.time()) - 3600).status_code, 401)
        r = self.client.post("/hooks/resend/inbound", content=b'{"type":"email.received"}', headers={"content-type": "application/json"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.mail("YES", to="act-1@booking.kanoe.ai").json()["ignored"], "not addressed to DIVE's domain")   # e.g. Sasha's
        self.assertEqual(self.mail("YES", frm="someone@else.example").json()["ignored"], "not an allow-listed sender")
        self.assertEqual(self.store.one("select count(*) n from inbound")["n"], 0)
        self.assertEqual([c for c in self.http.calls if "/emails/receiving/" in c["url"]], [])   # their mail was never even read

    def test_stop_by_email_and_a_duplicate_delivery(self):
        sent = self.resend_send()
        by, ch = self.gear_verified()
        self.op("channels.verify", {"channel_id": ch["gear"]["channel_id"]})
        self.assertEqual(self.mail("YES", pid="em_dup").json()["result"], "verification")
        self.assertEqual(self.mail("YES", pid="em_dup").json(), {"ok": True, "duplicate": True})
        self.assertEqual(self.store.one("select count(*) n from inbound where provider_id = 'em_dup'")["n"], 1)
        self.assertEqual(self.mail("STOP\n\n> anything").json()["result"], "opt")
        got = asyncio.run(CH.email_send(self.store, GEAR, "s", "hello"))
        self.assertEqual((got["ok"], got["unreachable"]), (False, True))
        self.assertEqual(len(sent), 1)                                                           # nothing more to them
        self.mail("START")
        self.assertTrue(asyncio.run(CH.email_send(self.store, GEAR, "s", "hello"))["real"])

    def test_only_what_they_typed_counts(self):
        cases = {"YES\n\nOn Thu, 9 Oct 2026, Blue Kyma wrote:\n> Reply YES or NO": "YES",
                 "Ναι, εντάξει\n\nΣτις Πέμ 9 Οκτ 2026, ο/η Blue Kyma έγραψε:\n> Απαντήστε ΝΑΙ ή ΟΧΙ": "Ναι, εντάξει",
                 "no\r\n-----Original Message-----\r\nFrom: Blue Kyma\r\nReply YES or NO": "no",
                 "ok for 4\n\nSent from my iPhone": "ok for 4",
                 "> only a quote": ""}
        for text, want in cases.items():
            self.assertEqual(CH.top_reply(text), want, text)


class LiveCheck(Switch):
    def test_the_start_page_shows_hi_and_the_gear_email_arriving_and_nothing_is_sent(self):
        self.whatsapp_on()
        self.email_on()
        self.assertIn("nothing received yet. Ask Jon to send hi", self.client.get("/start", headers=CONSOLE).text.replace("<b>", "").replace("</b>", ""))
        self.client.post("/start/reset", headers=CONSOLE)
        self.wa("hi")
        self.mail("hi")
        page = self.client.get("/start", headers=CONSOLE).text
        self.assertIn("the 24-hour window is open until", page)
        self.assertIn("Gear inbox: last email received", page)
        self.assertNotIn(JON, page)
        self.assertNotIn(GEAR, page)                                                             # times only
        acts = [i["line"] for i in self.client.post("/console/api/activity.list", json={}, headers=CONSOLE).json()["result"]["items"]]
        self.assertTrue(any("the 24-hour window is open" in a for a in acts), acts)
        self.assertTrue(any("matched nothing waiting" in a for a in acts), acts)
        self.assertEqual((self.http.twilio(), self.real_count()), ([], 0))                       # the check sends nothing
        self.client.post("/start/reset", headers=CONSOLE)
        self.assertTrue(CH.window_open(self.store, JON))                                         # Reset demo keeps Jon's window open


class FakeSite(Switch):
    def test_contacts_from_variables(self):
        self.patch(BOAT_WHATSAPP="+30 690 000 0042", GEAR_EMAIL="Gear-Inbox@Example.org")
        site = self.client.get("/fake/blue-kyma/partners").text
        self.assertIn("+306900000042", site)
        self.assertIn("gear-inbox@example.org", site)
        drafts = {d["name"]: d for d in self.op("suppliers.draft_from_site")["drafts"]}
        self.assertEqual((drafts["Aegean Boats"]["contacts"]["whatsapp"], drafts["Kyma Gear"]["contacts"]["email"]), ("+306900000042", "gear-inbox@example.org"))

    def test_two_allow_listed_numbers_never_guess(self):
        self.patch(WHATSAPP_ALLOW={JON, OTHER})
        self.assertIn("+447700900321", self.client.get("/fake/blue-kyma/partners").text)         # ambiguous → the fixture, never a guess


if __name__ == "__main__":
    import unittest
    unittest.main()
