"""CR 12 · the US Spanish consulates, each from its OWN page as read (consulates_read.json, pages kept with their sha256
in docs/products/reads/us/): which consulate covers a state, its numbered list in its own words, its appointment route —
or plainly none — and the document pack in its order. Offline; nothing is fetched, sent, booked or filed.

    cd backend && python -m unittest tests.test_consulates_cr12 -v
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from booking_signer import guest_whatsapp as GW
from products import store as ST
from products.relocation import consulates as CS
from tests import test_guest_whatsapp_s75 as TG

run = TG.run
READS = Path(__file__).resolve().parents[2] / "docs" / "products" / "reads" / "us"


class Read(TG.unittest.TestCase):
    def test_every_page_used_is_kept_and_its_hash_matches(self):
        for cid, r in CS.READ.items():
            for p in r.get("pages") or []:
                self.assertEqual(hashlib.sha256((READS / p["file"]).read_bytes()).hexdigest(), p["sha256"], (cid, p["file"]))
            if r.get("visa_page"):
                f = READS / r["visa_page"]["file"]
                self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(), r["visa_page"]["sha256"], cid)

    def test_each_item_is_the_pages_own_words(self):
        for cid in CS.READ:
            if not CS.usable(cid):
                continue
            html = (READS / CS.READ[cid]["visa_page"]["file"]).read_text(encoding="utf-8", errors="replace")
            for it in CS.READ[cid]["items"]:
                self.assertIn((it["title"] or it["text"][:40]).split(" (")[0][:30], html.replace("&#243;", "ó").replace("&#233;", "é")
                              .replace("&#237;", "í").replace("&#225;", "á").replace("&#250;", "ú").replace("&#241;", "ñ"), (cid, it["n"]))

    def test_what_was_read_and_what_wasnt(self):
        read = sorted(c for c in CS.READ if CS.usable(c))
        self.assertEqual(read, ["boston", "chicago", "losangeles", "miami", "newyork", "sanfrancisco", "washington"])
        self.assertIn("503", CS.READ["houston"]["error"])                       # the server's answer, said as it was
        self.assertEqual([c for c in CS.READ if CS.localised(c)], ["newyork"])  # only New York adds its own words
        self.assertEqual(CS.consulate("newyork")["appointment_email"], "cog.nuevayork.visnac@maec.es")
        for c in read:
            if c != "newyork":
                self.assertIsNone(CS.consulate(c)["appointment_email"])
                self.assertIsNone(CS.consulate(c)["appointment_url"])           # no route on the page: none from us

    def test_the_directory_code_fallback_was_checked(self):
        data = json.loads(Path(CS.__file__).with_name("consulates_read.json").read_text())
        self.assertGreaterEqual(data["codes_checked"], 5)
        self.assertTrue(all(r["code"]["agrees"] for r in data["consulates"].values() if (r.get("code") or {}).get("from") == "its own links"))


class Territory(TG.unittest.TestCase):
    def test_states_go_to_the_consulate_the_published_lists_name(self):
        for state, cid in (("New Jersey", "newyork"), ("Pennsylvania", "newyork"), ("Florida", "miami"), ("Georgia", "miami"),
                           ("Illinois", "chicago"), ("Massachusetts", "boston"), ("Texas", "houston"),
                           ("District of Columbia", "washington"), ("West Virginia", "washington"), ("Washington", "sanfrancisco"),
                           ("Arizona", "losangeles"), ("Hawaii", "sanfrancisco")):
            self.assertEqual(CS.for_state(state), cid, state)
        self.assertEqual(CS.territory("newyork")["from"], "its own page")
        self.assertEqual(CS.territory("newyork")["dated"], "23 de marzo de 2022")
        self.assertIn("network list", CS.territory("houston")["from"])

    def test_california_is_split_by_county_as_published(self):
        sp = CS.split("California")
        self.assertEqual((sp["named"], sp["rest"]), ("losangeles", "sanfrancisco"))
        self.assertEqual(CS.county_in("Los Angeles County", sp["counties"]), "Los Ángeles")
        self.assertIsNone(CS.county_in("San Mateo", sp["counties"]))

    def test_state_words(self):
        self.assertTrue(CS.is_us("USA") and CS.is_us("the United States") and CS.is_us("EEUU"))
        self.assertEqual((CS.state_from("NJ"), CS.state_from("nueva york"), CS.state_from("Florida")),
                         ("New Jersey", "New York", "Florida"))


class Pack(TG.unittest.TestCase):
    def test_numbered_named_and_in_the_consulates_order(self):
        items = CS.checklist("newyork")
        self.assertEqual(CS.numbers_in("1 3 4-6", 10), {1, 3, 4, 5, 6})
        self.assertIsNone(CS.numbers_in("not yet", 10))
        pk = CS.pack(items, {1, 3, 4})
        self.assertEqual([x["name"] for x in pk[:4]], ["01_National-visa-application-form", "02_EX-01-residence-authorisation-form",
                                                       "03_Passport-photo", "04_Passport"])
        self.assertEqual([x["status"] for x in pk[:5]], ["prepared", "prepared", "gathered", "gathered", "missing"])
        self.assertEqual(pk[3]["copies"], "the original and one copy")    # the page's own words: "el original y una fotocopia"
        self.assertEqual(pk[9]["copies"], "two signed copies")            # "dos ejemplares" of the 790-052

    def test_the_templates_unfilled_field_is_marked_not_a_rule(self):
        it = CS.checklist("miami")[9]
        self.assertIn("Campo para informar", it["placeholder"])


class NewYorkOnWhatsApp(TG.Base):
    def setUp(self):
        super().setUp()
        from products import itinerary as IT
        self.IT, self.saved = IT, (ST.STORE, IT.guest_booked)
        ST.STORE = ST.MemoryCaseStore()
        self.added = []

        async def fake(account, **kw):
            self.added.append(kw)
            return "item-1"
        IT.guest_booked = fake
        self.link()

    def tearDown(self):
        ST.STORE, self.IT.guest_booked = self.saved
        super().tearDown()

    def after(self):
        cid = run(GW.STORE.get_state(GW.wa_key(TG.GUEST)))["pending"]["case_id"]
        return run(ST.STORE.get(cid))["state"]["after"]

    def said(self):
        return "\n".join(self.bodies())

    def test_us_then_new_jersey_its_list_its_email_the_pack_the_tie_and_the_appointment(self):
        for t in ("relocation", "DEMO", "SIGNED", "USA"):
            self.say(t)
        self.assertIn("Which US state", self.bodies()[-1])
        self.say("New Jersey")
        from tests import calm as CALM                                     # CR 52 · one step at a time; details behind a tap
        self.assertIn("Your consulate is New York — you apply there in person.", CALM.everything(self))
        said = CALM.walk_consulate(self)
        self.assertIn("Consulado General de España en Nueva York covers Connecticut, Delaware, New Jersey", said)   # CR 37
        self.assertIn("mailto:cog.nuevayork.visnac@maec.es?", said)               # one tap: drafted in their own mail app
        self.assertIn("I never send it", said)
        self.assertIn("only by USPS money order", said)
        self.assertIn("C%29%20N%C3%BAmero%20de%20pasaporte%20y%20nacionalidad%3A%20%0A", said)   # never typed into the email by us
        self.assertEqual(len(self.after()["checklist"]), 10)
        self.assertIn("Your *document pack*", said)
        self.say("1 3 4 6-8")
        self.assertIn("3 still to gather", CALM.everything(self))
        pack = CALM.press(self, "rx:more:pack")
        self.assertIn("✓ 01_Formulario-de-solicitud-de-visado-nacional", pack)
        self.assertIn("✓ 02_EX-01 — sign one copy (prepared; you sign it)", pack)
        self.assertIn("☐ 09_Prueba-de-residencia-en-la-demarcacion — still to gather", pack)
        self.assertIn("☐ 05_Medios-economicos — still to gather", pack)
        self.assertIn("3 still to gather", pack)
        self.assertEqual([x["status"] for x in self.after()["pack"]][:5], ["prepared", "prepared", "gathered", "gathered", "missing"])
        self.say("1 March 2027")
        rs = self.after()["reminders"]
        self.assertEqual(len(rs), 1)                                 # the TIE, from ITS page; no 90-day window it doesn't state
        self.assertIn("Consulado General de España en Nueva York's own page gives you 1 month", rs[0]["text"])
        self.say("consulate booked 12 November 10:00")
        (x,) = self.added
        self.assertEqual((x["provider_name"], x["tz"]), ("Consulado General de España en Nueva York — visa appointment",
                                                         "America/New_York"))
        self.assertIn("Bring, in the consulate's order", self.said())
        self.say("pack 5")                                            # updated later, by the word PACK
        self.assertEqual(self.after()["pack"][4]["status"], "gathered")

    def test_a_template_only_page_says_so_and_gives_no_route(self):
        for t in ("relocation", "DEMO", "SIGNED", "Florida"):
            self.say(t)
        said = self.said()
        self.assertIn("*Consulado General de España en Miami*", said)
        self.assertIn("“Lugar de presentación” with nothing under it", said)
        self.assertIn("ministry's standard text", said)
        self.assertIsNone(self.after()["email_draft"])

    def test_texas_unreadable_page_no_checklist(self):
        for t in ("relocation", "DEMO", "SIGNED", "US", "TX"):
            self.say(t)
        said = self.said()
        self.assertIn("Consulado General de España en Houston", said)
        self.assertIn("answered HTTP 503", said)
        self.assertIn("I won't make one up", said)
        self.assertNotIn("checklist", self.after())
        self.assertIn("When do you plan to enter Spain?", self.bodies()[-1])

    def test_california_asks_the_county(self):
        for t in ("relocation", "DEMO", "SIGNED", "California"):
            self.say(t)
        self.assertIn("Which county", self.bodies()[-1])
        self.say("San Diego")
        self.assertIn("Consulado General de España en Los Ángeles", self.said())
