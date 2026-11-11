"""Sasha 369 · every passenger detail an airline needs comes from the traveller's OWN passport in the vault — including sex — never a default.

Found (CR 183, mailbox 1873): AgAPI sends every group passenger as "mr" / "m" because the Keep's passport has NO sex field; and Sasha's own
single-flight path invented "1 Jan 1980, Mr, M" whenever nothing was saved (travel.PLACEHOLDERS). Vueling refused Carmen Castro and Luis Pérez
twice; CR 183 now keeps the airline's own reason on error.details.

ONE source: the passport in the Keep — sex as printed (F | M | X), read from the passport's MRZ where the photo reader already reads it, asked on
the traveller's own vault page; missing → a missing fact (their link, said as done), never a guess.

    cd backend && python -m unittest tests.test_s369_passport_sex -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from unittest import mock

from agapi import keep as K, keep_scan as KS
from booking_signer import group_outcome as GO, groups as G, mandate as M
from tests import test_s365_mandate as T365, test_s367_mandate_at_agapi as T367

run = asyncio.run
ROOT = pathlib.Path(__file__).resolve().parents[2]
OWNER = T367.OWNER


def _mrz(sex: str) -> tuple:
    """A valid ICAO 9303 TD3 MRZ (fictional person, Spain) with the sex given: line 2 = number · cd · nationality · birth · cd · SEX · expiry ·
    cd · optional(14) · cd · composite cd."""
    cd = KS.check_digit
    num, dob, exp, opt = "L898902C3", "740812", "301015", "ZE184226B<<<<<"
    l2 = num + cd(num) + "ESP" + dob + cd(dob) + sex + exp + cd(exp) + opt + cd(opt)
    l2 = l2 + cd(l2[0:10] + l2[13:20] + l2[21:43])
    l1 = ("P<ESPERIKSSON<<ANNA<MARIA" + "<" * 44)[:44]
    return l1, l2


class ThePassportHoldsIt(unittest.TestCase):
    def test_sex_as_printed_on_the_passport(self):
        base = {"number": "X1234567", "country": "ES", "expires_on": "2031-01-01", "name": "Ana García", "born_on": "1985-03-12"}
        for given, kept in (("F", "F"), ("m", "M"), ("X", "X")):
            self.assertEqual(K.normalise("passport", {**base, "sex": given})["sex"], kept)
        with self.assertRaises(K.Refused):
            K.normalise("passport", {**base, "sex": "male"})                                   # as printed: F, M or X — nothing else

    def test_the_photo_reader_takes_sex_birth_date_and_name_from_the_mrz(self):
        for printed, kept in (("F", "F"), ("M", "M"), ("<", "X")):
            v = KS.parse_td3(*_mrz(printed))
            self.assertEqual(v["sex"], kept)
            self.assertEqual(v["born_on"], "1974-08-12")
            self.assertEqual(v["name"], "Anna Maria Eriksson")

    def test_the_travellers_own_page_asks_for_it(self):
        from booking_signer import traveller_vault as TV
        self.assertIn("sex", TV.REQUIRED_PASSPORT)
        page = (ROOT / "frontend" / "app" / "vault" / "[token]" / "page.tsx").read_text()
        self.assertIn("data-passport-sex", page)


class MissingIsAMissingFact(unittest.TestCase):
    def test_a_passport_without_sex_is_never_booked_and_its_link_goes_out(self):
        with T367.World() as w:
            T365._executives(T365.SIX)
            run(G.view(OWNER))
            amara = next(m for m in w.members() if m["name"] == "Amara Sample")
            from booking_signer import traveller_vault as TV
            with mock.patch.object(TV, "passport_missing", mock.AsyncMock(side_effect=lambda m: ["sex"] if m.get("name") == "Amara Sample" else [])):
                row = next(r for r in run(G.view(OWNER))["rows"] if r["name"] == "Amara Sample")
                self.assertEqual(GO.reason(row), "passport")                                   # the ONE "can be booked" rule says no
                self.assertEqual(row["vault"]["missing"], ["sex"])
                inv = run(G.invite_missing(OWNER))
        self.assertIn("Amara Sample", inv["invited"])                                          # her link, by email, unasked


class NoDefaultAnywhere(unittest.TestCase):
    def test_no_default_title_or_gender_in_sasha(self):
        hits = []
        for d in ("booking_signer", "agapi", "app", "products"):
            for f in sorted((ROOT / "backend" / d).rglob("*.py")):
                s = f.read_text(encoding="utf-8", errors="ignore")
                for rx in (r"PLACEHOLDERS", r"[\"']title[\"']\s*:\s*[\"']m(?:r|s|rs)?[\"']", r"[\"']gender[\"']\s*:\s*[\"'][mf][\"']",
                           r"[\"']born_on[\"']\s*:\s*[\"']\d{4}-\d{2}-\d{2}[\"']"):
                    if re.search(rx, s):
                        hits.append(f"{f.relative_to(ROOT)}: {rx}")
        self.assertEqual(hits, [])

    def test_a_flight_without_the_travellers_details_asks_never_invents(self):
        from booking_signer import travel as T
        c = {"id": "off_1", "amount": "41.47", "currency": "EUR", "owner": "easyJet", "flights": "U2 7640", "from": "MAD", "to": "LIS"}

        async def http(method, path, body=None, params=None):
            return 200, {"data": {"total_amount": "41.47", "total_currency": "EUR", "passengers": [{"id": "pas_1"}]}}
        with mock.patch.object(T, "token", lambda: "duffel_test_x"), mock.patch.object(T, "HTTP", http):
            r = run(T.order(c, "Sam Fictional", "sam@example.test", "+34612480135", people=[]))
        self.assertIn("why", r)
        self.assertIn("traveller's details", r["why"])
        self.assertEqual(r.get("needs"), ["travellers"])


if __name__ == "__main__":
    unittest.main()
