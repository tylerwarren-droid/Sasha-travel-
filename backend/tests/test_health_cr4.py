"""CR 4 · health on WhatsApp, inside S-77: consent first; the reason never asked; a private clinic booked through Sasha's
call path (read-back, one yes, the call); SERMAS prepared for the person to press — values only from the vault (behind
the DPIA) or a FICTIONAL patient, dropped after 24 hours; new in Madrid as a sourced checklist with reminders; never a
public health centre called. Offline; the model is never called.

    cd backend && python -m unittest tests.test_health_cr4 -v
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import guest_whatsapp as GW
from booking_signer.vault import api as VA, crypto as VC, kms as VK
from booking_signer.vault.store import MemoryVaultStore
from products import routes as PR, store as ST
from products.health import sources as SRC, turn as HT
from tests import test_guest_whatsapp_s75 as TG

run = TG.run


class Fake(TG.FakeApi):
    """Sasha's routes at their in-process boundary: the contact, and the call's prepare and place."""

    def __init__(self):
        super().__init__()
        self.place = {"ok": True, "status": "placed", "say": "Calling Kanoe Test Clinic now."}

    async def __call__(self, account, method, path, body=None, timeout=90.0):
        if path == "/api/booking/calls" and method == "POST" and body.get("reservation"):
            self.calls.append((account, method, path, body))
            r = body["reservation"]
            lines = ["I'll phone Kanoe Test Clinic, +34 600 000 000.",
                     f"I'll say: “Hola, soy Sasha … para reservar {r['what']['activity_venue_lang']} para Tyler Warren el "
                     f"{r['when']['at']}. ¿Sería posible?”", "Shall I call them now?"]
            return 200, {"call_id": "call-health-1", "read_back": {"lines": lines, "sha256": "d" * 64}, "purpose": "book"}
        return await super().__call__(account, method, path, body, timeout)


class Base(TG.Base):
    def setUp(self):
        super().setUp()
        GW.api = Fake()
        self.saved = (ST.STORE, HT._clinic_read, GW._spawn)
        ST.STORE = ST.MemoryCaseStore()

        async def clinic(account):
            return "read-clinic-1" if HT.test_clinic_number() else None
        HT._clinic_read = clinic
        self.spawned = []
        GW._spawn = lambda coro: (self.spawned.append(coro.__name__), coro.close())
        self.env2 = mock.patch.dict(os.environ, {"SASHA_TEST_CALL_NUMBER": "+34600000000", "SASHA_VAULT_HEALTH_DPIA_REF": ""})
        self.env2.start()
        self.link()

    def tearDown(self):
        ST.STORE, HT._clinic_read, GW._spawn = self.saved
        self.env2.stop()
        super().tearDown()

    def said(self):
        return "\n".join(self.bodies() + [b for b, _ in GW.SENDER.contents])

    def buttons(self):
        return GW.SENDER.contents[-1][1]

    def start(self, choice):
        self.say("health I need a doctor this week")
        self.say("", payload="hx:consent:yes")
        self.say("", payload=choice)

    def case(self, kind):
        return next(r for r in ST.STORE.rows.values() if r["state"].get("kind") == kind)


class Consent(Base):
    def test_consent_comes_first_and_no_keeps_nothing(self):
        self.say("salud")
        self.assertIn("never why you need a doctor", self.said())
        self.assertIn("I keep it at most 30 days", self.said())
        self.say("", payload="hx:consent:no")
        self.assertIn("nothing kept", self.bodies()[-1])
        self.assertEqual(ST.STORE.rows, {})

    def test_the_reason_is_never_asked(self):
        self.start("hx:priv")
        self.assertNotRegex(self.said().lower(), r"what.s wrong|symptom|why do you|reason for")


class Private(Base):
    def test_read_back_then_one_yes_then_the_call(self):
        self.start("hx:priv")
        self.say("Tuesday 10:00")
        (acct, method, path, body), = [c for c in GW.api.calls if c[2] == "/api/booking/calls"]
        r = body["reservation"]
        self.assertEqual((r["what"]["category"], r["what"]["activity_venue_lang"], r["how_many"]), ("appointment",
                         "una cita con el médico general", {"count": 1, "unit": "people"}))
        self.assertEqual(r["when"], {"mode": "at", "at": "2026-10-06T10:00"})       # Tuesday after Fri 2 Oct, Madrid time
        self.assertNotIn("reason", json.dumps(r))
        self.assertIn("Exactly what I'll say:", self.said())
        self.assertIn("para reservar una cita con el médico general", self.said())
        self.assertNotIn("/place", " ".join(c[2] for c in GW.api.calls))               # nothing dialled before the yes
        self.say("", payload=self.buttons()[0][1])
        place = [c for c in GW.api.calls if c[2].endswith("/place")]
        self.assertEqual(place[0][3]["read_back_sha256"], "d" * 64)
        self.assertEqual(place[0][3]["approval"]["how"], "whatsapp_button")
        self.assertIn("📞 Calling Kanoe Test Clinic now.", self.said())
        self.assertEqual(self.spawned, ["watch_call"])

    def test_no_test_line_means_nothing_to_call(self):
        os.environ["SASHA_TEST_CALL_NUMBER"] = ""
        self.start("hx:priv")
        self.say("tomorrow at 9")
        self.assertIn("nothing to call. Nothing was dialled", self.bodies()[-1])

    def test_a_past_or_vague_time_is_asked_again(self):
        self.start("hx:priv")
        self.say("sometime soon")
        self.assertIn("A day and a time", self.bodies()[-1])

    def test_never_a_public_health_centre(self):
        self.assertTrue(HT.public_health("Centro de Salud Chamberí"))
        self.assertTrue(HT.public_health("", "https://www.citaprevia.sanidadmadrid.org/Forms/Acceso.aspx"))
        self.assertFalse(HT.public_health(HT.TEST_CLINIC))


class Public(Base):
    def setUp(self):
        super().setUp()
        # the hand-over's 24-hour expiry is checked by the page route on the REAL clock: the turn must run on it too, or the
        # frozen test clock (2 Oct 12:00) ages the values out as soon as real time passes 3 Oct 12:00 (it did, 3 Oct 2026)
        self.now = datetime.now(timezone.utc)

    def page(self, cid):
        app = FastAPI(); app.include_router(PR.router)
        return TestClient(app).get(f"/products/health/{cid}").json()

    def test_without_a_dpia_nothing_of_theirs_is_asked_or_kept(self):
        self.start("hx:pub")
        said = self.said()
        self.assertIn("I don't keep health card details yet", said)
        self.assertIn("you press", self.page(self.case("sermas")["id"])["sermas"]["name"] + " you press")
        j = self.page(self.case("sermas")["id"])
        self.assertIsNone(j["values"])
        self.assertEqual(j["sermas"]["primary_care_url"], "https://www.citaprevia.sanidadmadrid.org/Forms/Acceso.aspx")
        self.assertEqual(j["sermas"]["not_valid"], "No es válido el número de Pasaporte.")
        self.assertFalse(j["submits"])
        self.assertIn("I never sign in, book or press on a public health website", said)

    def test_demo_is_a_fictional_patient_and_its_values_go_after_24_hours(self):
        self.start("hx:pub")
        self.say("DEMO")
        c = [r for r in ST.STORE.rows.values() if r["state"].get("fictional")][0]
        j = self.page(c["id"])
        self.assertEqual((j["values"]["card"], j["fictional"]), ("EJEMPLO-0000-0000", True))
        c["state"]["values_expire_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.assertIsNone(self.page(c["id"])["values"])
        self.assertIsNone(ST.STORE.rows[c["id"]]["state"]["values"])                     # gone from the row, not just hidden

    def test_with_a_dpia_the_vault_is_opened_once_under_the_yes(self):
        fd, kek = tempfile.mkstemp(); os.write(fd, base64.b64encode(os.urandom(32))); os.close(fd)
        env = mock.patch.dict(os.environ, {"SASHA_VAULT_LOCAL_KEK_FILE": kek, "SASHA_VAULT_KMS_KEY": "", "SASHA_VAULT_GCP_SA_JSON": "",
                                           "ENV": "", "RAILWAY_ENVIRONMENT_NAME": "", "SASHA_VAULT_HEALTH_DPIA_REF": "DPIA-TEST"})
        env.start()
        VK.reset()
        saved_v = VC.STORE
        VC.STORE = MemoryVaultStore()
        try:
            self.now = datetime.now(timezone.utc)
            item = str(uuid.uuid4())
            sealed = run(VC.seal(TG.ACCOUNT, item, "identifier", json.dumps({"value": json.dumps(
                {"card": "TEST-CARD-1", "birth": "1990-01-02", "dni_nie": "X0000000T"})}).encode()))
            hc = VA.health_consent()
            run(VC.STORE.create({"id": item, "account_id": TG.ACCOUNT, "provider": HT.VAULT_PROVIDER, "label": HT.VAULT_LABEL,
                                 "kind": "identifier", **sealed, "special_category": True, "consent_at": self.now,
                                 "consent_wording_version": hc["version"], "consent_text_sha256": hc["sha256"],
                                 "created_at": self.now, "updated_at": self.now}))
            self.start("hx:pub")
            self.assertIn("• I'll use your saved Tarjeta sanitaria (Madrid) from your vault.", self.said())
            self.say("", payload=self.buttons()[0][1])
            j = self.page(self.case("sermas")["id"])
            self.assertEqual(j["values"], {"card": "TEST-CARD-1", "birth": "1990-01-02", "dni_nie": "X0000000T"})
            uses = run(VC.STORE.uses_of(TG.ACCOUNT))
            self.assertEqual([(u["action_kind"], u["status"]) for u in uses], [("health_handover", "done")])
        finally:
            VC.STORE = saved_v
            env.stop()


class NewInMadrid(Base):
    def test_the_four_steps_each_from_its_official_page_and_reminders(self):
        self.start("hx:new")
        c = self.case("new_in_madrid")["state"]
        self.assertEqual([s["step"][:2] for s in c["checklist"]], ["1.", "2.", "3.", "4."])
        self.assertEqual(c["checklist"][0]["link"], SRC.PADRON["appointment_url"])
        self.assertIn("issued in the last 90 days", json.dumps(c["checklist"]))
        self.assertTrue(all(s["source"] and s["how"] in ("● raw", "● tool") for s in c["checklist"]))
        self.assertIn("I never hunt for padrón appointments", self.said())
        self.say("20 October 2026")
        rs = self.case("new_in_madrid")["state"]["reminders"]
        self.assertEqual([r["on"] for r in rs], ["2026-10-21", "2026-12-19"])
        self.assertIn("ask before 18 January", rs[1]["text"])

    def test_mode_switch_and_sasha_untouched(self):
        self.say("hello")
        self.assertIn("Tell me what to book", self.bodies()[-1])
        self.say("salud")
        self.say("exit")
        self.assertEqual(self.bodies()[-1], "Back to Sasha — ask me anything: a booking, a flight, your plans.")
