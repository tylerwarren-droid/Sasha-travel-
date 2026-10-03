"""CR 1 · relocation M3: the passport photo read by the model — CHECKED against the passport's own ICAO 9303 check
digits and confirmed by the person before it counts; then where THEY lodge it (from the consulate's own sheet), the
checklist with its source, and reminders. Nothing booked, pressed or filed. Offline: the media fetch and the model are
fakes at their one boundary each.

    cd backend && python -m unittest tests.test_relocation_m3_cr1 -v
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from booking_signer import guest_whatsapp as GW
from products import store as ST
from products.relocation import after as AF, checker as CK, docread as DR, ex01 as E, turn as RT
from tests import test_guest_whatsapp_s75 as TG

run = TG.run


def line2(number: str, birth: str, sex: str, expiry: str, nat: str = "CAN") -> str:
    n = (number + "<" * 9)[:9]
    return f"{n}{DR._cd(n)}{nat}{birth}{DR._cd(birth)}{sex}{expiry}{DR._cd(expiry)}" + "<" * 14 + "00"


GOOD = {"is_passport_photo_page": True, "legible": True, "issuing_country": "CAN", "passport_number": "AB1234567",
        "surnames": "EJEMPLO PRUEBA", "given_names": "ANA", "nationality": "CANADIAN", "sex": "F", "birth_date": "1985-03-14",
        "birth_place": "TORONTO", "expiry_date": "2031-06-30", "mrz_line_1": "P<CANEJEMPLO<PRUEBA<<ANA<<<<<<<<<<<<<<<<<<<<<",
        "mrz_line_2": line2("AB1234567", "850314", "F", "310630")}


class CheckDigits(TG.unittest.TestCase):
    def test_the_icao_specimen(self):
        m = DR.mrz_check("L898902C36UTO7408122F1204159ZE184226B<<<<<10")   # ICAO Doc 9303's own specimen
        self.assertTrue(m["number_ok"] and m["birth_ok"] and m["expiry_ok"])
        self.assertEqual(m["number"], "L898902C3")

    def test_a_misread_digit_is_caught(self):
        self.assertEqual(DR.verify(GOOD)["passport_number"], "ok")
        bad = {**GOOD, "passport_number": "AB1234561"}
        self.assertIn("differ", DR.verify(bad)["passport_number"])
        worse = {**GOOD, "mrz_line_2": GOOD["mrz_line_2"][:9] + "0" + GOOD["mrz_line_2"][10:]}
        self.assertIn("check digit fails", DR.verify(worse)["passport_number"])

    def test_surnames_are_kept_whole_as_printed(self):
        self.assertEqual(DR.to_facts(GOOD)["surname_1"], "EJEMPLO PRUEBA")
        self.assertEqual(DR.to_facts(GOOD)["sex"], "M")   # F on the passport = M (mujer) on the EX-01


class Flow(TG.Base):
    def setUp(self):
        super().setUp()
        self.saved = (ST.STORE, DR.FETCH, DR.READ)
        ST.STORE = ST.MemoryCaseStore()
        self.reads = []

        async def fetch(url):
            return b"\xff\xd8 fake jpeg", "image/jpeg"

        async def read(data, mt):
            self.reads.append(mt)
            return dict(self.next_read)
        DR.FETCH, DR.READ = fetch, read
        self.next_read = GOOD
        self.link()

    def tearDown(self):
        ST.STORE, DR.FETCH, DR.READ = self.saved
        super().tearDown()

    def photo(self):
        ch = run(GW.STORE.channel_for(GW.wa_key(TG.GUEST)))
        return run(GW.turn(ch, TG.SANDBOX, {"From": f"whatsapp:{TG.GUEST}", "To": f"whatsapp:{TG.SANDBOX}", "Body": "",
                                             "NumMedia": "1", "MediaUrl0": "https://api.twilio.com/media/ME1",
                                             "MediaContentType0": "image/jpeg"}))

    def start(self):
        for t in ("relocation", "first", "me", "myself"):
            self.say(t)

    def pend(self):
        return run(GW.STORE.get_state(GW.wa_key(TG.GUEST)))["pending"]

    def test_photo_read_checked_and_kept_only_on_their_yes(self):
        self.start()
        self.photo()
        said = "\n".join(self.bodies() + [b for b, _ in GW.SENDER.contents])
        self.assertIn("It goes to Anthropic's AI model to be read, once; I don't keep the photo.", said)
        self.assertIn("• Passport number: AB1234567 ✓ (the passport's own check digit agrees)", said)
        self.assertIn("• First surname: EJEMPLO PRUEBA", said)
        self.assertIn("• Sex: female — M (mujer) on the Spanish form ✓ (matches the machine-readable zone)", said)
        self.assertIn("• Date of birth: 14 March 1985 ✓", said)
        self.assertNotIn("EXPIRED", said)
        self.assertEqual(self.pend()["facts"]["applicant"], {})           # nothing kept before the yes
        self.say("", payload="rx:doc:yes")
        a = self.pend()["facts"]["applicant"]
        self.assertEqual(a["passport_number"]["value"], "AB1234567")
        self.assertEqual(a["passport_number"]["source"], "passport photo page, read by Kanoe's AI and confirmed by you")
        self.assertIn("Your second surname?", self.bodies()[-1])         # the next question nobody has answered yet

    def test_an_expired_passport_is_said_at_once(self):
        self.start()
        self.next_read = {**GOOD, "expiry_date": "2024-03-09", "mrz_line_2": line2("AB1234567", "850314", "F", "240309")}
        self.photo()
        self.assertIn("• Expires: 9 March 2024 ✓ (the passport's own check digit agrees) ⚠ this passport has EXPIRED",
                      "\n".join(self.bodies()))

    def test_no_keeps_nothing(self):
        self.start()
        self.photo()
        self.say("", payload="rx:doc:no")
        self.assertEqual(self.pend()["facts"]["applicant"], {})
        self.assertIn("nothing from the photo was kept", self.bodies()[-2])

    def test_a_value_its_own_check_digit_contradicts_is_never_kept(self):
        self.start()
        self.next_read = {**GOOD, "passport_number": "AB1234561"}
        self.photo()
        self.assertIn("⚠ the printed number (AB1234561) and the machine-readable one (AB1234567) differ",
                      "\n".join(self.bodies()))
        self.say("yes")
        self.assertNotIn("passport_number", self.pend()["facts"]["applicant"])
        self.assertEqual(self.bodies()[-1], "Your passport number?")

    def test_what_they_typed_stays_as_a_second_source_and_the_reviewer_shows_it(self):
        self.start()
        self.say("AB1234567")
        self.say("Ejemplo")
        self.photo()
        self.say("yes")
        f = self.pend()["facts"]
        self.assertEqual(f["documents"]["applicant.surname_1"][0]["value"], "Ejemplo")
        rows = {r["name"]: r for r in CK.review(E.rows(f, RT.applies(f)), f, date(2026, 10, 3))}
        self.assertIn("two sources disagree", json.dumps(rows["Texto5"]["checks"]))

    def test_not_a_passport(self):
        self.start()
        self.next_read = {**GOOD, "is_passport_photo_page": False}
        self.photo()
        self.assertIn("doesn't look like a legible passport photo page", self.bodies()[-1])

    def test_after_signing_the_consulates_own_route_the_checklist_and_reminders(self):
        self.say("relocation")
        self.say("DEMO")
        self.say("SIGNED")
        self.assertIn("Which country do you live in now?", self.bodies()[-1])
        self.say("London, UK")
        said = "\n".join(self.bodies())
        self.assertIn("*Consulado General de España en Londres*", said)
        self.assertIn("http://www.exteriores.gob.es/Consulados/LONDRES/en/Consulado/Pages/Visas.aspx", said)
        self.assertIn("I don't book or press anything", said)
        self.assertIn("dated 11 Feb 2022", said)
        cid = self.pend()["case_id"]
        items = {i["key"]: i for i in run(ST.STORE.get(cid))["state"]["after"]["checklist"]}
        self.assertEqual(items["passport"]["status"], "ok")               # the demo passport runs to 2031
        self.assertEqual(items["ex01"]["status"], "prepared")
        self.say("1 March 2027")
        rs = run(ST.STORE.get(cid))["state"]["after"]["reminders"]
        self.assertEqual([r["on"] for r in rs], ["2026-10-02", "2026-12-01", "2027-03-22"])   # in date order, from today
        self.assertIn("I'll remind you here", self.bodies()[-1])

    def test_a_consulate_whose_page_we_havent_read_gets_no_link(self):
        self.say("relocation")
        self.say("DEMO")
        self.say("SIGNED")
        self.say("Canada")
        self.assertIn("I won't give you a link I haven't checked", "\n".join(self.bodies()))
        self.assertNotIn("exteriores.gob.es/Consulados", self.bodies()[-2])

    def test_a_passport_under_a_year_is_flagged_from_the_sheets_own_rule(self):
        f = {"applicant": {"passport_expiry": {"value": "2027-02-01", "source": "x", "read_on": "y"}}}
        p = next(i for i in AF.checklist(f, date(2026, 10, 3), "united kingdom") if i["key"] == "passport")
        self.assertEqual(p["status"], "problem")
        self.assertIn("LESS than a year", p["why"])
