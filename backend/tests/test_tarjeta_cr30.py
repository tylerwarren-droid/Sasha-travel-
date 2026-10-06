"""CR 30 (3) · EspañaMe — your health card: the DNI (front, back) or a passport read from a photo, checked (the DNI letter,
the machine-readable lines' check digits), read back for one yes; only what's missing asked; the Comunidad de Madrid's own
form 1449F1 filled field by field, each value naming its source; the objection boxes, the notification, the date and the
signature left for the citizen; never the Social Security number; the details dropped after 24 hours. SPECIMENS only (a
fictional DNI through a fake reader); the model is never called.

    cd backend && python -m unittest tests.test_tarjeta_cr30 -v
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import guest_whatsapp as GW
from products import routes as PR, store as ST, web as PWEB
from products.health import tarjeta as TS, turn as HT
from products.relocation import docread as DR
from tests import test_guest_whatsapp_s75 as TG
from tests import test_health_cr4 as TH

run = TG.run
SP = TS.SPECIMEN
FRONT = {"doc_type": "dni_front", "legible": True, "dni_number": SP["dni"], "passport_number": "", "support_number": "BAA000000",
         "surname_1": SP["surname_1"], "surname_2": SP["surname_2"], "given_names": SP["given_names"], "sex": "F",
         "nationality": "ESP", "birth_date": SP["birth_date"], "expiry_date": SP["expiry"], "birth_place": "",
         "birth_province": "", "address_line": "", "address_municipality": "", "address_province": "", "mrz_lines": []}
BACK = {**{k: "" for k in FRONT}, "doc_type": "dni_back", "legible": True, "birth_place": "MADRID", "birth_province": "MADRID",
        "address_line": SP["address_line"], "address_municipality": "MADRID", "address_province": "MADRID",
        "mrz_lines": TS.SPECIMEN_MRZ}


class Base(TH.Base):
    def setUp(self):
        super().setUp()
        self.now = datetime.now(timezone.utc)          # the PDF route checks the 24 hours on the real clock
        self.saved_ts = (DR.FETCH, TS.READ)
        self.reads, self.fetched, self.queue = [], [], []

        async def fetch(url):
            self.fetched.append(url)
            return b"\xff\xd8 specimen", "image/jpeg"

        async def read(data, mt):
            self.reads.append(mt)
            return dict(self.queue.pop(0))
        DR.FETCH, TS.READ = fetch, read

    def tearDown(self):
        DR.FETCH, TS.READ = self.saved_ts
        super().tearDown()

    def photo(self, read):
        self.queue.append(read)
        ch = run(GW.STORE.channel_for(GW.wa_key(TG.GUEST)))
        return run(GW.turn(ch, TG.SANDBOX, {"From": f"whatsapp:{TG.GUEST}", "To": f"whatsapp:{TG.SANDBOX}", "Body": "",
                                             "NumMedia": "1", "MediaUrl0": "https://api.twilio.com/media/ME1",
                                             "MediaContentType0": "image/jpeg"}))

    def to_photo(self):
        self.say("españa")
        self.say("", payload="hx:es:salud")
        self.say("", payload="hx:consent:yes")
        self.say("", payload="hx:tsi")

    def mark(self):
        self._m = (len(GW.SENDER.sent), len(GW.SENDER.contents))

    def last(self):
        """What was said since mark() (plain messages and button questions)."""
        a, b = self._m
        return "\n".join([s["body"] for s in GW.SENDER.sent[a:]] + [c for c, _ in GW.SENDER.contents[b:]])

    def through(self, read_back_yes=True):
        self.to_photo()
        self.photo(FRONT)
        self.photo(BACK)
        if read_back_yes:
            self.say("", payload=f"hx:ts:ok:{self.pend()['ts_sha']}")

    def pend(self):
        return run(GW.STORE.get_state(GW.wa_key(TG.GUEST)))["pending"]

    def answers(self):
        self.say("", payload="hx:ts:m:NUEVA")
        self.say("", payload="hx:ts:addr:yes")
        self.say("28013")
        self.say("600 000 000")
        self.say("SKIP")
        self.say("", payload="hx:ts:s:TARDE")
        self.say("skip")

    def pdf(self, cid):
        app = FastAPI(); app.include_router(PR.router)
        return TestClient(app).get(f"/products/health/{cid}/1449F1-prepared.pdf")


class Checks(Base):
    def test_the_dni_letter_and_the_machine_readable_lines(self):
        self.assertTrue(TS.dni_ok("99999999R"))
        self.assertFalse(TS.dni_ok("99999999A"))
        m = TS.mrz_td1(TS.SPECIMEN_MRZ)
        self.assertTrue(m["ok"])
        self.assertEqual((m["dni"], m["birth"], m["expiry"]), ("99999999R", "800101", "310630"))
        bad = list(TS.SPECIMEN_MRZ); bad[1] = bad[1][:6] + ("0" if bad[1][6] != "0" else "1") + bad[1][7:]
        self.assertFalse(TS.mrz_td1(bad)["ok"])

    def test_the_address_is_split_into_the_forms_boxes(self):
        self.assertEqual(TS.split_address("AVDA. DE AMERICA 12, 3º B"),
                         {"type": "AVENIDA", "name": "DE AMERICA", "number": "12", "floor": "3", "letter": "B"})
        self.assertEqual(TS.split_address("C. EJEMPLO 1 P02 A")["type"], "CALLE")

    def test_the_citizens_boxes_are_refused_by_the_filler(self):
        for field in ("ITICDA_DNI", "ITTIPONOTIFICA_NOTIF", "DDFECHA_PIE", "TLNUMAFILSS_INTER"):
            with self.assertRaises(ValueError):
                TS.fill([{"field": field, "value": "X", "source": "x"}])
        with self.assertRaises(ValueError):
            TS.fill([{"field": "TLNOMBRE_INTER", "value": "X", "source": ""}])

    def test_the_official_form_is_the_one_read(self):
        self.assertEqual(hashlib.sha256(TS.PDF.read_bytes()).hexdigest(), TS.PDF_SHA256)


class Flow(Base):
    def test_whatsapp_dni_front_and_back_to_the_filled_official_form(self):
        self.to_photo()
        self.assertIn("I don't ask for your Social Security number", self.said())
        self.mark()
        self.photo(FRONT)
        self.assertIn("Now the BACK of your DNI", self.last())
        self.photo(BACK)
        said = self.said()
        self.assertIn("• DNI: 99999999R", said)
        self.assertIn("✓ The DNI letter matches its number.", said)
        self.assertIn("check digits are right, and they agree with the front", said)
        self.assertEqual(self.reads, ["image/jpeg", "image/jpeg"])
        self.say("", payload=f"hx:ts:ok:{self.pend()['ts_sha']}")
        self.assertIn("What is the card for?", self.said())
        self.answers()
        said = self.said()
        self.assertIn("✅ Your health-card form is ready", said)
        self.assertNotRegex(said.lower(), r"(your|what is your|send).{0,20}social security number\?")
        c = self.case("tarjeta")
        rs = {r["field"]: r for r in c["state"]["rows"]}
        self.assertEqual(rs["CDDOCIDENT_INTER"]["source"], "your DNI (front), read from your photo")
        self.assertEqual(rs["CDPOSTAL_INTER"]["source"], "you, in this chat")
        self.assertEqual((rs["ITMOTIVO_SOLIC"]["value"], rs["ITTURNO_SOLI"]["value"], rs["DSSEXO_INTER"]["value"]),
                         ("NUEVA", "TARDE", "M"))
        self.assertFalse(any(TS.NEVER.match(f) for f in rs))
        r = self.pdf(c["id"])
        self.assertEqual((r.status_code, r.headers["content-type"]), (200, "application/pdf"))
        back = TS.read_pdf(r.content)
        self.assertEqual((back["TLNOMBRE_INTER"], back["NMNUMVIAL_INTER"], back["ITMOTIVO_SOLIC"]), ("CARMEN", "1", "/NUEVA"))
        self.assertFalse([k for k in back if k.startswith(("ITICDA_", "ITTIPONOTIFICA", "TLNUMAFILSS"))])
        self.assertIn("/api/products/health/", "\n".join(str(m) for m in GW.SENDER.sent))

    def test_a_wrong_letter_is_said_and_no_rereads_it(self):
        self.to_photo()
        self.photo({**FRONT, "dni_number": "99999999A"})
        self.photo(BACK)
        self.assertIn("⚠ The DNI letter does NOT match its number.", self.said())
        self.mark()
        self.say("no")
        self.assertIn("nothing kept", self.last())
        self.assertEqual(self.pend()["ts"]["facts"], {})

    def test_a_wrong_answer_is_asked_again_with_why(self):
        self.through()
        self.say("", payload="hx:ts:m:DOMICILIO")
        self.mark()
        self.say("", payload="hx:ts:addr:no")
        self.assertIn("Your current address", self.last())
        self.say("Avenida de América 12, 3º B")
        self.say("123")
        self.assertIn("starting 28", self.said())
        self.say("28028")
        f = self.pend()["ts"]["facts"]
        self.assertEqual((f["street"]["value"], f["postcode"]["value"]), ("Avenida de América 12, 3º B", "28028"))

    def test_demo_is_a_fictional_specimen(self):
        self.to_photo()
        self.say("DEMO")
        self.assertIn("fictional", self.pend()["ts"]["facts"]["dni"]["source"])
        self.assertEqual(self.reads, [])

    def test_a_voice_note_that_could_not_be_heard_is_not_read_as_a_photo(self):
        self.to_photo()
        self.mark()
        ch = run(GW.STORE.channel_for(GW.wa_key(TG.GUEST)))
        run(GW.turn(ch, TG.SANDBOX, {"From": f"whatsapp:{TG.GUEST}", "To": f"whatsapp:{TG.SANDBOX}", "Body": "",
                                      "NumMedia": "1", "MediaUrl0": "https://api.twilio.com/media/ME2",
                                      "MediaContentType0": "audio/ogg"}))
        self.assertIn("couldn't make out that voice note", self.last())
        self.assertEqual((self.reads, self.pend()["step"]), ([], "ts_doc"))

    def test_after_24_hours_the_details_are_gone(self):
        self.through()
        self.answers()
        c = self.case("tarjeta")
        c["state"]["values_expire_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.assertEqual(self.pdf(c["id"]).status_code, 410)
        self.assertIsNone(ST.STORE.rows[c["id"]]["state"]["rows"])

    def test_the_daily_job_drops_them_too(self):
        self.through()
        self.answers()
        c = self.case("tarjeta")
        run(HT.due(datetime.now(timezone.utc) + timedelta(hours=25)))
        self.assertIsNone(ST.STORE.rows[c["id"]]["state"]["rows"])


class Menu(Base):
    def test_three_is_the_health_card_and_new_in_madrid_is_off_the_menu(self):
        self.say("españa")
        self.say("", payload="hx:es:salud")
        self.say("", payload="hx:consent:yes")
        self.assertEqual([b for _, b in self.buttons()][2], "hx:tsi")
        self.assertNotIn("new in Madrid", HT.CHOOSE)
        self.say("3")
        self.assertEqual(self.pend()["step"], "ts_doc")


class Web(Base):
    def test_the_laptop_upload_is_read_from_its_bytes(self):
        web = lambda m="", payload=None, media=None: run(PWEB.web_turn(TG.ACCOUNT, m, payload=payload, now=self.now,
                                                                         signed_in=True, media=media))
        web("españa")
        web(payload="hx:es:salud")
        web(payload="hx:consent:yes")
        web(payload="hx:tsi")
        self.queue += [FRONT, BACK]
        r = web(media=[{"bytes": b"\xff\xd8 front", "content_type": "image/jpeg"},
                       {"bytes": b"\xff\xd8 back", "content_type": "image/jpeg"}])
        self.assertEqual(self.fetched, [])
        self.assertIn("• DNI: 99999999R", r["response"])
        self.assertTrue(r["quick_replies"][0]["payload"].startswith("hx:ts:ok:"))


if __name__ == "__main__":
    TG.unittest.main()
