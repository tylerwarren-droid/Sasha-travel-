"""CR 15 · the WhatsApp mode words exactly as the founder types them — "relocate", "campus", "espana"/"españa", "sasha" —
and the Applied Diligence PREVIEW ("diligence"/"ad"): AD's answer with its source, both dates, its scope line first, its
standing said with a reason, the Netherlands never asked, people never looked up. Offline; the real WhatsApp turn.

    cd backend && python -m unittest tests.test_modes_cr15 -v
"""
from __future__ import annotations

import copy
import os
from unittest import mock

from booking_signer import guest_whatsapp as GW
from products import diligence as DG, store as ST
from tests import test_guest_whatsapp_s75 as TG

run = TG.run
LIVE = copy.deepcopy(DG.SAMPLE["response"])
LIVE.update(retrieved_at="2026-10-07T09:14:22Z", source_as_of=None)
# the US tab's v2 shape (4 Oct): status_raw + normalised status + standing_expressible on the entity, no standing object
V2 = {"status": "identified", "entity": {"legal_name": "TOTALENERGIES SE", "registration_number": "542051180", "register": "INSEE SIRENE",
      "status_raw": "Active", "status": "active", "standing_expressible": False,
      "address": "2 PLACE JEAN MILLIER, 92400 COURBEVOIE, FRANCE", "incorporated": "1924-03-28"},
      "candidates": [], "source": {"name": "INSEE SIRENE", "url": "https://api.insee.fr/entreprises/sirene"},
      "retrieved_at": "2026-10-07T09:14:22Z", "source_as_of": "2026-10-01", "scope": "SIRENE scope.", "preview": True}


class Base(TG.Base):
    def setUp(self):
        super().setUp()
        self.saved = (ST.STORE, DG.HTTP)
        ST.STORE = ST.MemoryCaseStore()
        self.calls, self.answer = [], (200, LIVE)

        async def http(url, key, body):
            self.calls.append((url, body))
            if isinstance(self.answer, Exception):
                raise self.answer
            return self.answer
        DG.HTTP = http
        self.env = mock.patch.dict(os.environ, {"AD_PREVIEW_URL": "https://ad.test", "AD_PREVIEW_KEY": "k", "AD_PREVIEW_SAMPLE": ""})
        self.env.start()
        self.link()

    def tearDown(self):
        ST.STORE, DG.HTTP = self.saved
        self.env.stop()
        super().tearDown()

    def said(self):
        return "\n".join(self.bodies() + [b for b, _ in GW.SENDER.contents])


class Words(Base):
    def test_relocate_campus_and_sasha(self):
        self.say("relocate")
        self.assertIn("I never file anything", self.said())
        self.say("sasha")
        self.assertEqual(self.bodies()[-1], "Back to Sasha — ask me anything: a booking, a flight, your plans.")
        self.say("campus")
        self.assertIn("CampusMe here", self.said())

    def test_espana_menu_six_areas_salud_live(self):
        for word in ("espana", "españa"):
            GW.SENDER.contents.clear()
            self.say(word)
            menu, buttons = GW.SENDER.contents[-1]
            self.assertIn("EspañaMe 🇪🇸 — Spain's public processes", menu)
            for area in ("1. *Salud*", "2. *Padrón*", "3. *Identity and access*", "4. *Social security and tax*", "5. *DGT*", "6. *Education*"):
                self.assertIn(area, menu)
            self.assertNotRegex(menu, r"(?i)movistar")
            self.assertEqual([b[1] for b in buttons], ["hx:es:salud", "hx:es:padron", "hx:es:identity"])
            self.say("sasha")
        self.say("españa")
        self.say("2")
        said = self.said()
        self.assertIn("○ *Padrón — registering at the town hall* — CONCEPT, not built yet", said)
        self.assertIn("*What you need* (from the official page)", said)
        self.assertIn("servpub.madrid.es", said)                               # the page actually read, nothing composed
        self.assertIn("*You press:* booking the appointment and going in person.", said)
        self.say("5")
        self.assertIn("DGT — exchanging a foreign driving licence* — CONCEPT", self.said())
        self.assertIn("the UK is on it; the US is not", self.said())             # dgt.es read at source (CR 19)
        self.say("4")
        self.assertIn("Modelo 030", self.said())                                  # read at source, 4 Oct
        self.say("6")
        self.assertIn("Secretaría Virtual", self.said())
        self.say("", payload="hx:es:movistar")                                   # an old button: it moved (CR 17)
        self.assertIn("part of RelocateMe now", self.said())
        self.say("1")
        said = self.said()
        self.assertIn("🟢 *Salud — health card, family doctor, SERMAS* — LIVE", said)
        self.assertIn("never why you need a doctor", said)                       # the working health demo, consent first

    def test_no_walls(self):
        self.say("españa")
        self.say("diligence")
        self.assertNotRegex(self.said(), r"(?i)say exit|go back to sasha")


class Diligence(Base):
    def test_check_totalenergies_in_france(self):
        self.say("diligence")
        self.assertIn("Applied Diligence — PREVIEW 🔎", self.bodies()[-1])
        self.say("check TotalEnergies in France")
        (url, body), = self.calls
        self.assertEqual((url, body), ("https://ad.test/api/preview/register",
                                       {"country": "FR", "name": "TotalEnergies", "registration_number": None}))
        r = self.bodies()[-1]
        lines = r.split("\n")
        self.assertEqual(lines[0], "🔎 *Applied Diligence — PREVIEW*")
        self.assertTrue(lines[1].startswith("Scope: This preview identifies the company"))   # never the casualty of a cut
        self.assertIn("*TOTALENERGIES SE*", r)
        self.assertIn("Registration no.: 542051180", r)
        self.assertIn("Standing: not shown — SIRENE publishes establishment and activity data", r)
        self.assertIn("Source: INSEE SIRENE — https://api.insee.fr/entreprises/sirene", r)
        self.assertIn("Read from the register: 7 Oct 2026, 09:14 UTC", r)
        self.say("check BNP Paribas in France")                               # same mode, another company
        self.assertEqual(len(self.calls), 2)

    def test_ad_one_shot_and_a_registration_number(self):
        self.say("ad SIREN 542051180 in France")
        self.assertEqual(self.calls[0][1], {"country": "FR", "name": None, "registration_number": "542051180"})

    def test_the_netherlands_is_never_asked(self):
        self.say("ad check Shell in the Netherlands")
        self.assertEqual(self.calls, [])
        self.assertIn("the Dutch company register's terms don't allow passing on its records", self.bodies()[-1])
        self.assertNotIn("Checking", self.said())                              # never "checking" before a refusal

    def test_people_are_never_looked_up(self):
        self.say("ad check Mr Patrick Pouyanné in France")
        self.assertEqual(self.calls, [])
        self.assertIn("companies only — not people", self.bodies()[-1])

    def test_ambiguous_unreachable_not_found_are_three_different_things(self):
        self.answer = (200, {**LIVE, "status": "ambiguous", "entity": None,
                             "candidates": [{"legal_name": "TOTAL SA", "registration_number": "1"}]})
        self.say("ad check Total in France")
        self.assertIn("possible matches, not confirmed", self.bodies()[-1])
        self.answer = (200, {**LIVE, "status": "not_found", "entity": None})
        self.say("check Nowhere Ltd in France")
        self.assertIn("The register's own answer: no company matching", self.bodies()[-1])
        self.answer = TimeoutError()
        self.say("check TotalEnergies in France")
        self.assertIn("couldn't be reached just now — nothing was checked", self.bodies()[-1])
        self.answer = (200, {**LIVE, "status": "uncovered_preview", "entity": None})
        self.say("check Foo in France")
        self.assertIn("isn't certified for sale — so no result is shown", self.bodies()[-1])

    def test_a_dinner_while_diligence_is_open_is_sashas(self):
        self.say("diligence")
        self.say("dinner in Spain for 2 tomorrow at 21:00")
        self.assertEqual(self.calls, [])

    def test_not_connected_says_so_and_the_sample_is_labelled(self):
        os.environ["AD_PREVIEW_URL"] = ""
        self.say("ad check TotalEnergies in France")
        self.assertIn("isn't connected here yet, so nothing was checked", self.bodies()[-1])
        os.environ["AD_PREVIEW_SAMPLE"] = "1"
        self.say("check TotalEnergies in France")
        r = self.bodies()[-1]
        self.assertIn("SAMPLE (a fixed example response, not a live register lookup)", r)
        self.assertIn("Read from the register: — (sample, not read live)", r)
        self.say("check BNP Paribas in France")                               # the sample is about ONE company only
        self.assertIn("isn't connected here yet", self.bodies()[-1])
        self.assertEqual(self.calls, [])


class V2Shape(Base):
    def test_active_is_the_registers_word_never_a_standing(self):
        self.answer = (200, V2)
        self.say("ad check TotalEnergies in France")
        r = self.bodies()[-1]
        self.assertIn("Register status (its own words): Active", r)
        self.assertIn("Standing: not shown — this register doesn't publish insolvency or winding-up", r)
        self.assertNotIn("Standing: active", r)
        self.assertIn("The source's own data last updated: 2026-10-01", r)         # both dates (Etalab: a licence condition)

    def test_a_sole_trader_is_a_person_never_shown(self):
        self.answer = (200, {**V2, "entity": {**V2["entity"], "legal_category": "1000", "legal_name": "JEAN DUPONT"}})
        self.say("ad check Dupont Plomberie in France")
        self.assertIn("a sole trader — a person, not a company", self.bodies()[-1])
        self.assertNotIn("JEAN DUPONT", self.bodies()[-1])

    def test_malta_and_austria_refused_locally_too(self):
        self.say("ad check Foo Ltd in Malta")
        self.say("check Bar GmbH in Austria")
        self.assertEqual(self.calls, [])

    def test_three_coverage_statuses_three_sentences(self):
        for st, words in (("not_covered", "doesn't cover that country's register"),
                          ("uncovered_preview", "isn't certified for sale"),
                          ("not_in_preview", "hasn't established that its licence allows passing its records on")):
            self.answer = (200, {**V2, "status": st, "entity": None})
            self.say("ad check Foo in France")
            self.assertIn(words, self.bodies()[-1], st)


class AdIsOnlyAWholeWord(Base):
    def test_add_address_adults_adhoc_are_never_the_mode(self):
        from products import whatsapp as PW
        for t in ("add it to my calendar", "address is Calle Mayor 1", "adults 2", "Ad-hoc dinner for 4", "Ad hoc meeting", "AD'S"):
            if t == "Ad hoc meeting":
                continue
            self.assertIsNone(PW._DILIGENCE.match(t), t)
        self.say("Ad hoc meeting tomorrow with the team")                  # "ad" as a word, but not a lookup: Sasha's
        self.assertNotIn("Applied Diligence", self.said())

    def test_sashas_open_question_wins_over_a_bare_ad(self):
        self.say("dinner for 2 in Chamberí on Saturday at 21:00")             # Sasha's own pending (cards)
        pend = run(GW.STORE.get_state(GW.wa_key(TG.GUEST)))["pending"]
        self.assertEqual(pend["kind"], "cards")
        self.say("ad check TotalEnergies in France")
        self.assertEqual(self.calls, [])                                     # not the AD mode while she asks
        self.say("diligence")                                                # the full word still switches, as every mode word does
        self.assertIn("Applied Diligence — PREVIEW 🔎", self.bodies()[-1])


class CapAndPerson(Base):
    def test_the_daily_cap_and_a_person_refused_by_ad(self):
        self.answer = (429, {"error": "rate_limited"})
        self.say("ad check TotalEnergies in France")
        self.assertIn("today's preview limit is reached", self.bodies()[-1])
        self.answer = (400, {"error": "person_not_supported", "message": "companies only"})
        self.say("check Jean Dupont Plomberie in France")
        self.assertIn("checks companies only — not people", self.bodies()[-1])
        self.assertNotIn("no company matching", self.bodies()[-1])


class SireneInconsistent(Base):
    def test_sirene_standing_claimed_expressible_is_said_inconsistent_not_corrected(self):
        self.answer = (200, {**LIVE, "standing": {"value": "active", "expressible": True, "because": "x"}})
        self.say("ad check TotalEnergies in France")
        r = self.bodies()[-1]
        self.assertIn("Standing: not shown — the register's capability could not be established for this answer.", r)
        self.assertNotIn("Standing: active", r)


class NotAttributable(Base):
    def test_a_record_without_its_attribution_date_is_not_shown(self):
        self.answer = (200, {**LIVE, "status": "not_attributable", "entity": None})
        self.say("ad check TotalEnergies in France")
        r = self.bodies()[-1]
        self.assertIn("didn't say when its information was last updated", r)
        self.assertNotIn("hasn't established that its licence", r)


class UtilitiesInRelocateMe(Base):
    def test_phone_line_and_utilities_are_a_relocateme_concept(self):
        for t in ("relocation", "first", "me", "myself"):
            self.say(t)
        self.say("what about my phone line and utilities?")
        said = "\n".join(self.bodies()[-2:])
        self.assertIn("🏠 *Setting up your home* — your phone and internet (e.g. Movistar), electricity, and a Spanish bank account", said)
        self.assertIn("no provider's or bank's pages have been read", said)
        self.assertIn("Your passport number?", self.bodies()[-1])                  # the file exactly where it was


class EspanaAreasRoute(TG.unittest.TestCase):
    def test_the_tab_reads_the_same_six_areas(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from products import routes as PR
        app = FastAPI(); app.include_router(PR.router)
        j = TestClient(app).get("/products/espana/areas").json()
        self.assertEqual([(a["key"], a["live"]) for a in j["areas"]],
                         [("salud", True), ("padron", False), ("identity", False), ("social", False), ("dgt", False), ("education", False)])
        dgt = next(a for a in j["areas"] if a["key"] == "dgt")
        self.assertTrue(dgt["read"])                                               # CR 19: dgt.es, not the sede
        self.assertEqual(dgt["route_url"], "https://www.dgt.es/.galleries/enlaces/sede/permisos/canjes-extranjeros.html")

    def test_the_dgt_pages_kept_match_their_hashes(self):
        import hashlib, json
        from pathlib import Path
        from products.health import espana as ES
        reads = Path(ES.__file__).resolve().parents[3] / "docs" / "products" / "reads" / "espana"
        f = ES._READ["topics"]["F"]["sha256"]
        for name, sha in (("2026-10-04-dgt-canje-paises-extracomunitarios.html", f["canje-paises-extracomunitarios"]),
                          ("2026-10-04-dgt-paises-con-convenio.html", f["paises-con-convenio"])):
            self.assertEqual(hashlib.sha256((reads / name).read_bytes()).hexdigest(), sha, name)


class Truncated(Base):
    def test_a_short_list_is_never_the_whole_register(self):
        self.answer = (200, {**LIVE, "status": "ambiguous", "entity": None, "candidate_count": 221, "candidates_shown": 5,
                             "candidates": [{"legal_name": f"TOTALENERGIES {i}", "registration_number": str(i)} for i in range(5)]})
        self.say("ad check TotalEnergies in France")
        self.assertIn("Showing 5 of 221 names the register matched. This list is not complete, and a name that does not "
                      "appear here has not been ruled out", self.bodies()[-1])
        self.answer = (200, {**LIVE, "status": "ambiguous", "entity": None, "candidate_count": None, "candidates_shown": 2,
                             "candidates": [{"legal_name": "A", "registration_number": "1"}, {"legal_name": "B", "registration_number": "2"}]})
        self.say("check Foo in France")
        self.assertIn("Showing 2 names; the register did not say how many it matched. This list may not be complete, and a name "
                      "that does not appear here has not been ruled out — narrow the search or give a registration number.",
                      self.bodies()[-1])                                          # byte-identical to AD's own sentence
        self.answer = (200, {**LIVE, "status": "ambiguous", "entity": None, "candidate_count": 2, "candidates_shown": 2,
                             "candidates": [{"legal_name": "A", "registration_number": "1"}, {"legal_name": "B", "registration_number": "2"}]})
        self.say("check Bar in France")
        self.assertNotIn("Showing", self.bodies()[-1])

    def test_one_name_and_none(self):
        from products import diligence as DG
        self.assertIn("Showing 1 name; the register did not say", DG.truncated_line({"candidate_count": None, "candidates_shown": 1}))
        self.assertEqual(DG.truncated_line({"candidate_count": None, "candidates_shown": 0}), "")
        self.assertEqual(DG.truncated_line({"candidate_count": 5, "candidates_shown": 5}), "")


class MachineryFailure(Base):
    def test_unrecorded_is_never_a_finding(self):
        self.answer = (503, {"error": "unrecorded", "message": "the dispatch decision was not recorded"})
        self.say("ad check TotalEnergies in France")
        r = self.bodies()[-1]
        self.assertIn("the check could not be run right now — nothing was checked", r)
        self.assertNotRegex(r, r"(?i)no company|not found|matches|identified|unrecorded")
