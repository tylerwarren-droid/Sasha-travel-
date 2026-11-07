"""Sasha 332 · GROUP MOVEMENT v1 (docs/sasha/S-332-group-movement.md). Offline: the store in memory, each worker's trip rows in an
in-memory basket (the same rows trip_basket_items holds), prices from a fixture.

    cd backend && python -m unittest tests.test_s332 -v
"""
from __future__ import annotations

import asyncio
import inspect
import io
import pathlib
import unittest
import zipfile
from unittest import mock

from booking_signer import groups as G

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "group_madrid_20.csv"
OWNER = "00000000-0000-4000-8000-000000000332"
run = asyncio.run

#: fixture prices (EUR): a worker's return flight, by home city; the hotel near the factory in Getafe per night
FARE = {"Lisbon": 180, "Porto": 160, "Paris": 240, "Milan": 210, "Rome": 230, "Berlin": 260, "Munich": 250, "Warsaw": 300,
        "Bucharest": 340, "Prague": 290, "Athens": 380, "Dublin": 270, "London": 220, "Amsterdam": 230, "Brussels": 210,
        "Vienna": 280, "Casablanca": 640, "Sofia": 360, "Krakow": 310, "Lyon": 190}   # Casablanca: over the worker's €600


class World:
    """The organiser's account: groups in memory, each worker's ONE trip's rows in memory, fixture prices."""

    def __init__(self, hotel_night=95.0):
        self.store, self.trips, self.hotel_night = G.MemStore(), {}, hotel_night

    def __enter__(self):
        async def suggest(account, trip_id, kind, found, slice_key=None, replace=True):
            rows = self.trips.setdefault(trip_id, [])
            if replace:
                rows[:] = [r for r in rows if not (r["kind"] == kind and r["state"] == "suggested" and r.get("slice_key") == slice_key)]
            for f in found:
                rows.append({**f, "kind": kind, "state": "suggested", "slice_key": slice_key})
            return [str(len(rows))]

        async def items(account, trip_id):
            return [dict(r) for r in self.trips.get(trip_id, [])]

        async def quote(m, mv):
            fare = FARE[m["home_city"]]
            card = lambda frm, to, day: {"id": f"off_{frm}_{to}", "owner": "Iberia", "from": frm[:3].upper(), "to": to[:3].upper(),
                                         "departs": f"{day}T09:00:00", "arrives": f"{day}T12:00:00", "amount": str(fare / 2), "currency": "EUR"}
            return {"flights": [card(m["home_city"], "Madrid", m["out_date"]), card("Madrid", m["home_city"], m["back_date"])],
                    "hotel": {"name": "Hotel Getafe Centro (example)", "eur_per_night": self.hotel_night, "address": "Getafe"}}
        self.p = [mock.patch.object(G, "STORE", self.store), mock.patch.object(G, "QUOTE", quote), mock.patch.object(G, "ITEMS", items),
                  mock.patch("booking_signer.basket.suggest", suggest)]
        for x in self.p:
            x.start()
        # an open trip already there (data, as a fixture: the product's own create_trip never makes one with nobody on it — Sasha 358)
        run(self.store.new_movement(OWNER, "Acme Components (fictional)", "Madrid", "2026-12-01", "2026-12-19", "near the factory in Getafe"))
        return self

    def __exit__(self, *a):
        for x in reversed(self.p):   # Sasha 339 · last in, first out: a nested patch of the same name restores the real one, never a fake
            x.stop()

    def limits(self):
        run(G.set_limits(OWNER, by_grade={"worker": {"flight_return_eur": 600, "hotel_night_eur": 110},
                                          "supervisor": {"flight_return_eur": 900, "hotel_night_eur": 140}}))


def _xlsx(csv_text: str) -> bytes:
    rows = [l.split(",") for l in csv_text.strip().splitlines()]
    shared = sorted({c for r in rows for c in r})
    idx = {s: i for i, s in enumerate(shared)}
    col = lambda i: chr(65 + i)
    sheet = "".join(f'<row r="{n}">' + "".join(f'<c r="{col(i)}{n}" t="s"><v>{idx[c]}</v></c>' for i, c in enumerate(r)) + "</row>"
                    for n, r in enumerate(rows, 1))
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>" + "".join(f"<si><t>{s}</t></si>" for s in shared) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{sheet}</sheetData></worksheet>")
    return b.getvalue()


class TheUpload(unittest.TestCase):
    def check(self, rows):
        with World() as w:
            w.limits()
            r = run(G.upload(OWNER, rows))
            members = run(w.store.members(r["movement_id"]))
        self.assertEqual((r["added"], len(members)), (20, 20))
        self.assertEqual([u["row"]["name"] for u in r["unclear"]], ["Victor Unclear", "Wanda Unknowngrade"])
        self.assertEqual(r["ask"].count("\n•"), 2)                                     # ONE question, both rows in it — never one each
        self.assertIn("the out date (“31/02/2026”)", r["ask"])
        self.assertIn("the grade (“intern”", r["ask"])
        self.assertEqual(len({m["home_city"] for m in members}), 20)
        return r

    def test_csv(self):
        r = self.check(G.read_csv(FIX.read_bytes()))
        print(f"\n[s332 proof] csv → 20 members · the one question:\n{r['ask']}")

    def test_pasted_text(self):
        pasted = FIX.read_text().replace(",", "\t")                                       # as pasted from a spreadsheet: tab-separated
        self.check(G.read_text(pasted))
        self.check(G.read_text("\n".join(FIX.read_text().splitlines()[1:])))              # typed, no header: name, city, out, back, grade

    def test_xlsx_and_photo(self):
        self.check(G.read_xlsx(_xlsx(FIX.read_text())))

        async def photo(image, mt):
            return FIX.read_text().replace(",", " | ")
        with mock.patch.object(G, "READ_PHOTO", photo):
            self.check(run(G.read_photo(b"\x89PNG...", "image/png")))

    def test_dates_and_names_never_guessed(self):
        mv = {"starts_on": "2026-12-01", "ends_on": "2026-12-19"}
        good, unclear = G.members_from([{"name": "Ana Sample", "home_city": "Lisbon", "out_date": "3 Dec", "back_date": "19/12/2026", "_line": "1"},
                                        {"name": "Ana Sample", "home_city": "Lisbon", "_line": "2"},
                                        {"name": "B", "home_city": "Porto", "out_date": "2026-12-05", "back_date": "2026-12-02", "_line": "3"}], mv)
        self.assertEqual(good, [{"name": "Ana Sample", "home_city": "Lisbon", "out_date": "2026-12-03", "back_date": "2026-12-19", "grade": None}])
        self.assertEqual([u["line"] for u in unclear], ["2", "3"])
        self.assertIn("listed twice", unclear[0]["why"][0])


class LimitsAndTheMasterList(unittest.TestCase):
    def test_planned_within_limits_flagged_over_and_the_list(self):
        with World() as w:
            w.limits()
            mid = run(G.upload(OWNER, G.read_csv(FIX.read_bytes())))["movement_id"]
            pid = next(m["id"] for m in run(w.store.members(mid)) if m["name"] == "Liam Specimen")
            run(G.set_limits(OWNER, by_member={pid: {"hotel_night_eur": 90}}))            # one person's own limit, on the same rules
            out = run(G.plan(OWNER))
            v = run(G.view(OWNER))
            rules_after = run(w.store.movement(OWNER))["rules"]
        self.assertEqual((out["planned"], out["failed"]), (20, []))
        self.assertEqual(len(v["rows"]), 20)
        st = {r["name"]: r["status"] for r in v["rows"]}
        self.assertEqual(st["Rania Mithal"], "over limit")                               # €640 return > the worker's €600 — flagged
        self.assertEqual(st["Liam Specimen"], "over limit")                              # €95/night > his own €90
        self.assertEqual(st["Greta Sampleton"], "needs vault")                           # within; no passport yet (the vault is 333)
        self.assertEqual(v["counts"], {"needs vault": 18, "over limit": 2})
        r = next(r for r in v["rows"] if r["name"] == "Chloé Placeholder")
        self.assertEqual((r["limit"], r["flight_eur"], r["hotel_eur_per_night"]), ({"flight_return_eur": 900.0, "hotel_night_eur": 140.0}, 240.0, 95.0))
        self.assertIn("Iberia", r["transport"])
        self.assertEqual(rules_after["limits"]["by_member"], {pid: {"hotel_night_eur": 90.0}})
        print("\n[s332 proof] master list: " + " · ".join(f"{k} {n}" for k, n in v["counts"].items()) + "\n" + G.summary(v, top=5))

    def test_live_as_each_trip_changes(self):
        with World() as w:
            w.limits()
            run(G.upload(OWNER, G.read_csv(FIX.read_bytes())))
            run(G.plan(OWNER))
            m = next(r for r in run(G.view(OWNER))["rows"] if r["name"] == "Amara Sample")
            for row in w.trips[m["trip_id"]]:
                row["state"] = "booked"                                                     # its trip changes (CR 163 books it)
            self.assertEqual(next(r for r in run(G.view(OWNER))["rows"] if r["name"] == "Amara Sample")["status"], "booked")
            for row in w.trips[m["trip_id"]]:
                row["state"] = "cancelled"
            self.assertEqual(next(r for r in run(G.view(OWNER))["rows"] if r["name"] == "Amara Sample")["status"], "cancelled")
            with mock.patch.object(G, "VAULT", mock.AsyncMock(return_value=True)):     # the vault has their documents (333)
                self.assertEqual(next(r for r in run(G.view(OWNER))["rows"] if r["name"] == "Bruno Example")["status"], "planned")


class TheWholeClass(unittest.TestCase):
    def test_the_master_list_is_a_view_never_a_copy(self):
        sql = (pathlib.Path(__file__).resolve().parents[1] / "booking_signer/sql/048_group_movement.sql").read_text()
        for word in ("price", "status", "transport", "hotel_name", "flight"):
            self.assertNotIn(f"  {word} ", sql)                                            # no copy of a trip's rows on the group's tables
        self.assertIn("trip_id      uuid references public.trips(id)", sql)                # each worker → their ONE trip
        src = inspect.getsource(G.view)
        self.assertIn("_items(account, m[\"trip_id\"])", src)                             # read from the trip, now
        self.assertNotIn("set_", src)                                                       # writes nothing

    def test_one_place_for_the_rules(self):
        self.assertIn("rules        jsonb", (pathlib.Path(__file__).resolve().parents[1] / "booking_signer/sql/048_group_movement.sql").read_text())
        self.assertEqual(G.limit_for({"limits": {"by_grade": {"worker": {"flight_return_eur": 600}},
                                                 "by_member": {"m1": {"flight_return_eur": 650}}}}, {"id": "m1", "grade": "worker"}),
                         {"flight_return_eur": 650.0})
        for name in ("plan", "view"):
            self.assertIn("limit_for(mv.get(\"rules\") or {}, m)", inspect.getsource(getattr(G, name)))

    def test_planning_never_books(self):
        src = inspect.getsource(G)
        for word in ("BK.choose(", "BK.hold(", "BK.booked(", "venue.submit_booking", "T.order("):
            self.assertNotIn(word, src)


class TheTools(unittest.TestCase):
    def test_agent_tools(self):
        from agapi import v0 as API
        self.assertTrue({"group_start", "group_upload", "group_limits", "group_plan", "group_list"} <= set(API.BY_NAME))
        with World() as w:
            ctx = API.Ctx(account=OWNER, mode="test")
            w.limits()
            r = run(API.group_upload(ctx, {"text": FIX.read_text()}))
            self.assertTrue(r["say"].startswith("Added 20 people to the list. 2 rows I couldn't read for sure"), r["say"])   # Sasha 346 · the ONE outcome's words
            run(G.plan(OWNER))
            s = run(API.group_list(ctx, {}))
        self.assertIn("19 needs vault, 1 over limit", s["say"])   # Rania's flight (no personal limit set here)
        self.assertEqual(len(s["card"]["rows"]), 20)   # Sasha 345 · the list goes out WITH the list


if __name__ == "__main__":
    unittest.main()
