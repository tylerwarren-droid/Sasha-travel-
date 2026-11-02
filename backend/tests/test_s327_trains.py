"""Sasha 327 · TRAINS ARE TRAINS (docs/sasha/S-327-trains.md). A Renfe, Iryo or OUIGO ticket in his inbox → the ONE Gmail reader
(mailbox.sync) → AgAPI's ONE reader (venue.confirmation, faked here with AgAPI's own rail() answers for its rail_fixtures) → a TRAIN on
the ONE trip record (trip_items), linked to AgAPI's act, with every field on view and its manage page; never 'other'. Offline: no
network, no AgAPI import — AgAPI's answers are pasted below.

    cd backend && python3 -m unittest tests.test_s327_trains -v
"""
from __future__ import annotations

import asyncio
import base64
import json
import pathlib
import re
import unittest
from datetime import datetime, timezone
from unittest import mock

from booking_signer import mailbox as MB, trains as TR
from booking_signer.vault import crypto as VC

ROOT = pathlib.Path(__file__).resolve().parents[2]
ACCT = "11111111-2222-4333-8444-555555555327"

# ── AgAPI's rail_fixtures (SYNTHETIC — no real person, booking or card), copied from agapi_service/rail_fixtures.py ────────────────
RENFE = {"from": "Renfe <venta@renfe.com>", "subject": "Confirmación de compra - Localizador X7K2PQ", "date": "Sun, 01 Nov 2026 09:12:00 +0100",
         "text": "Hola Alex Test,\nGracias por tu compra. Estos son los datos de tu viaje:\n\nLocalizador: X7K2PQ\n"
                 "Trayecto: Madrid-Puerta de Atocha → Barcelona-Sants\nFecha: 13 de noviembre de 2026\nSalida: 08:00\nLlegada: 10:30\n"
                 "Tren: AVE 03063\nCoche: 6\nPlaza: 07A\nTarifa: Básico\nViajeros: 1\nImporte total: 45,60 €\nForma de pago: VISA **** 4242\n\n"
                 "Puedes gestionar tu billete en Mis viajes."}
IRYO = {"from": "iryo <noreply@iryo.eu>", "subject": "Tu viaje con iryo está confirmado", "date": "Sun, 01 Nov 2026 09:20:00 +0100",
        "text": "¡Tu reserva está confirmada!\nCódigo de reserva: IRY4M9Z\nOrigen: Madrid Puerta de Atocha\nDestino: Valencia Joaquín Sorolla\n"
                "Fecha del viaje: 20/11/2026\nHora de salida: 17:25\nHora de llegada: 19:05\nTren nº 6153\nCoche 3 · Asiento 12C\n"
                "Tarifa: Infinita\nPasajeros: 2\nTotal pagado: 79,80 €\nPagado con Mastercard terminada en 5555"}
OUIGO = {"from": "OUIGO España <confirmacion@ouigo.com>", "subject": "Confirmación de tu reserva OUIGO", "date": "Sun, 01 Nov 2026 09:31:00 +0100",
         "text": "Tu billete OUIGO\nReferencia: OUG8H3TQ\nViaje: Madrid Chamartín - Valencia Joaquín Sorolla\nFecha: 27 noviembre 2026\n"
                 "Salida 07:10 · Llegada 08:52\nTren 06501 — Coche 8, Plaza 41\nTarifa: OUIGO Esencial\nViajeros: 1\nImporte: 19,00 €\nVisa •••• 1111"}
EMAILS = {"m-renfe": RENFE, "m-iryo": IRYO, "m-ouigo": OUIGO}

# ── AgAPI's own answers: confirmations.rail(email, seller) for each fixture (run against AgAPI v1.52.0's reader, pasted) ─────────────
TRIPS = {
    "renfe.com": ("act_RENFE01", {"operator": "Renfe", "kind": "train", "origin": "Madrid-Puerta de Atocha", "destination": "Barcelona-Sants",
                                  "date": "2026-11-13", "departs": "08:00", "arrives": "10:30", "train": "AVE 03063", "coach": "6", "seat": "07A",
                                  "reference": "X7K2PQ", "passengers": 1, "fare": "Básico", "price_eur": 45.6, "card": {"brand": "Visa", "last4": "4242"}}),
    "iryo.eu": ("act_IRYO01", {"operator": "Iryo", "kind": "train", "origin": "Madrid Puerta de Atocha", "destination": "Valencia Joaquín Sorolla",
                               "date": "2026-11-20", "departs": "17:25", "arrives": "19:05", "train": "6153", "coach": "3", "seat": "12C",
                               "reference": "IRY4M9Z", "passengers": 2, "fare": "Infinita", "price_eur": 79.8, "card": {"brand": "Mastercard", "last4": "5555"}}),
    "ouigo.com": ("act_OUIGO01", {"operator": "OUIGO España", "kind": "train", "origin": "Madrid Chamartín", "destination": "Valencia Joaquín Sorolla",
                                  "date": "2026-11-27", "departs": "07:10", "arrives": "08:52", "train": "06501", "coach": "8", "seat": "41",
                                  "reference": "OUG8H3TQ", "passengers": 1, "fare": "OUIGO Esencial", "price_eur": 19.0, "card": {"brand": "Visa", "last4": "1111"}}),
}
#: venue.manage_options as AgAPI answers it for each act (its kinds.py manage pages and fare table)
PAGES = {"act_RENFE01": ("https://www.renfe.com/es/es/gestiona-tu-billete/tus-reservas/consulta-tus-viajes", None,
                         [{"action": "change", "allowed": True, "open_now": True, "say": "Change: €10 + the price difference; one change until 25 Jan 2027, until 24 hours before departure."},
                          {"action": "cancel", "allowed": False, "open_now": False, "say": "This fare can't be cancelled (except within 2 hours of buying it)."}]),
         "act_IRYO01": ("https://iryo.eu/es", "“Manage your booking” on iryo.eu or the app, with the booking reference and surname",
                        [{"action": "change", "allowed": True, "open_now": True, "say": "Change: a time change on the same day is free; a date change: the price difference only, until 30 minutes before departure."},
                         {"action": "cancel", "allowed": True, "open_now": True, "say": "Cancel: refund €67.83 (85%) until 30 minutes before departure."}]),
         "act_OUIGO01": ("https://www.ouigo.com/es/cuenta-cliente-OUIGO", "“Mis Reservas”, with the booking email and the localizador",
                         [{"action": "change", "allowed": True, "open_now": True, "say": "Change: a modification fee (its amount isn't on OUIGO's current conditions) + the price difference; free with the FLEX extra, until 30 minutes before departure."},
                          {"action": "cancel", "allowed": False, "open_now": False, "say": "Not refundable — unless you added Billete Reembolsable: 80% back, or a 100% voucher for 12 months"}])}


class FakeAgapi:
    """AgAPI's venue.confirmation (no act_id: its reader opens THE record; the same localizador twice → the same act, already) and
    venue.manage_options. What Sasha kept of each answer (the act pointers, _remember) is held here too."""
    def __init__(self):
        self.calls, self.opened, self.kept = [], set(), []

    async def call(self, account, op, body, approval=None):
        self.calls.append(op)
        if op == "venue.confirmation":
            e = body["emails"][0]
            dom = e["from"].rsplit("@", 1)[-1].rstrip(">").strip()
            if dom not in TRIPS:
                return {"ok": False, "error": {"code": "invalid_input", "message": "not a confirmation from a seller AgAPI knows"}}
            act, trip = TRIPS[dom]
            already = act in self.opened
            self.opened.add(act)
            return {"ok": True, "result": {"matched": True, "act_id": act, "kind": "train", "state": "confirmed", "trip": trip,
                                           "reference": trip["reference"], **({"already": True} if already else {}),
                                           "say_text": f"Got it: your {trip['operator']} train."}}
        if op == "venue.manage_options":
            act = body["act_id"]
            page, how, opts = PAGES[act]
            trip = next(t for a, t in TRIPS.values() if a == act)
            return {"ok": True, "result": {"act_id": act, "kind": "train", "operator": trip["operator"], "fare": trip["fare"],
                                           "departs_at": f"{trip['date']}T{trip['departs']}", "known": True, "options": opts,
                                           "where": {"page": page, "reference": trip["reference"], "filled": "never", **({"how": how} if how else {})}}}
        return {"ok": False, "error": {"code": "not_found", "message": op}}

    async def remember(self, account, act):
        self.kept = [a for a in self.kept if a["act_id"] != act["act_id"]] + [dict(act)]

    async def acts_of(self, account):
        return [dict(a) for a in self.kept]


def _msg(e):
    return {"payload": {"headers": [{"name": "Subject", "value": e["subject"]}, {"name": "From", "value": e["from"]}, {"name": "Date", "value": e["date"]}],
                        "mimeType": "text/plain", "body": {"data": base64.urlsafe_b64encode(e["text"].encode()).decode()}}}


class Base(unittest.TestCase):
    def setUp(self):
        from agapi import venue_submit as VS
        self.ag = FakeAgapi()
        self.msgs = dict(EMAILS)
        self.mb, self.tr = MB.MemoryMailboxStore(), TR.MemoryTrainStore()
        self.mb.links[ACCT] = {"account_id": ACCT, "vault_item_id": "v-327", "needs_reconnect_at": None}
        TR._OPTIONS.clear()

        async def gmail(method, url, token, params=None):
            if url.endswith("/messages"):
                return 200, {"messages": [{"id": k} for k in self.msgs]}
            return 200, _msg(self.msgs[url.rsplit("/", 1)[1]])
        self.patches = [mock.patch.object(MB, "STORE", self.mb), mock.patch.object(TR, "STORE", self.tr), mock.patch.object(MB, "GMAIL_HTTP", gmail),
                        mock.patch.object(MB, "NOW", lambda: datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)),
                        mock.patch.object(MB, "_told_train", mock.AsyncMock()), mock.patch.object(MB, "_offer_on_whatsapp", mock.AsyncMock()),
                        mock.patch.object(VC, "use_connection", mock.AsyncMock(return_value="ya29-fake")),
                        mock.patch.object(VS, "_call", self.ag.call), mock.patch.object(VS, "end_user", mock.AsyncMock(return_value="eu_327")),
                        mock.patch.object(VS, "_remember", self.ag.remember), mock.patch.object(VS, "acts_of", self.ag.acts_of)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def sync(self):
        return asyncio.run(MB.sync(ACCT))

    def rows(self):
        """The trip items as /api/booking/reservations shows them (its agapi_act from the item's act link), then THE view."""
        out = []
        for i in self.tr.items.values():
            at = i["date_time"]
            out.append({"id": i["id"], "type": i["type"], "venue": i["provider_name"], "date": at.date().isoformat() if at else None,
                        "time": at.strftime("%H:%M") if at else None, "timezone": i["local_timezone"], "party": i["party_size"],
                        "status": i["status"], "booking_reference": i["booking_reference"], "location": i["location_name"],
                        "duration_minutes": i["duration_minutes"], **({"agapi_act": TR.act_of(i["escalation_notes"])} if TR.act_of(i["escalation_notes"]) else {})})
        return asyncio.run(TR.view(ACCT, out))


class ThreeTicketsThreeTrains(Base):
    def test_1_renfe_iryo_ouigo_become_three_train_items_with_every_field(self):
        self.sync()
        items = sorted(self.tr.items.values(), key=lambda i: i["date_time"])
        self.assertEqual([i["type"] for i in items], ["train"] * 3)
        self.assertEqual([i["status"] for i in items], ["confirmed"] * 3)
        self.assertEqual([i["provider_name"] for i in items], ["Renfe", "Iryo", "OUIGO España"])
        self.assertEqual([i["booking_reference"] for i in items], ["X7K2PQ", "IRY4M9Z", "OUG8H3TQ"])
        self.assertEqual([i["date_time"].isoformat() for i in items], ["2026-11-13T08:00:00+01:00", "2026-11-20T17:25:00+01:00", "2026-11-27T07:10:00+01:00"])
        self.assertEqual([i["duration_minutes"] for i in items], [150, 100, 102])
        self.assertEqual(items[0]["location_name"], "Madrid-Puerta de Atocha → Barcelona-Sants")
        self.assertEqual([i["price_usd"] for i in items], [None] * 3)                      # never euros in a dollar column
        self.assertEqual([i["escalation_notes"] for i in items], ["agapi_act:act_RENFE01", "agapi_act:act_IRYO01", "agapi_act:act_OUIGO01"])
        for f in self.mb.finds.values():                                                   # the find: the item's id, AgAPI's answer, no card
            self.assertIn(f["trip_item_id"], self.tr.items)
            self.assertEqual(f["parsed_by"], "agapi")
            self.assertNotIn("card", f["facts"])
            self.assertNotIn("4242", json.dumps(f["facts"]))
        rows = sorted(self.rows(), key=lambda r: r["date"])
        print("\n── Sasha 327 · the three trains, as the trip shows them ──")
        for r in rows:
            print(json.dumps(r["train"], ensure_ascii=False))
        want = [("Renfe", "AVE 03063", "Madrid-Puerta de Atocha", "Barcelona-Sants", "08:00", "10:30", "6", "07A", "X7K2PQ", 1, "Básico", 45.6),
                ("Iryo", "6153", "Madrid Puerta de Atocha", "Valencia Joaquín Sorolla", "17:25", "19:05", "3", "12C", "IRY4M9Z", 2, "Infinita", 79.8),
                ("OUIGO España", "06501", "Madrid Chamartín", "Valencia Joaquín Sorolla", "07:10", "08:52", "8", "41", "OUG8H3TQ", 1, "OUIGO Esencial", 19.0)]
        for r, w in zip(rows, want):
            t = r["train"]
            self.assertEqual(tuple(t[k] for k in ("operator", "number", "origin", "destination", "departs", "arrives", "coach", "seat", "reference",
                                                  "passengers", "fare", "price_eur")), w)
            self.assertEqual(t["manage"]["page"], PAGES[r["agapi_act"]][0])                  # "Manage your ticket": the operator's own page
            self.assertEqual(t["manage"]["label"], "Manage your ticket")
            self.assertTrue(t["manage"]["options"])                                          # the fare's change / cancel rules, AgAPI's

    def test_2_idempotent_on_replay_the_same_email_and_the_same_act(self):
        self.sync()
        self.sync()                                                                        # the same messages: seen, nothing new
        self.assertEqual(len(self.tr.items), 3)
        self.mb.finds.clear()                                                              # the same tickets again (a re-sent email):
        self.msgs = {k + "-again": v for k, v in EMAILS.items()}                           # AgAPI answers the same act, already
        self.sync()
        self.assertEqual(len(self.tr.items), 3)
        self.assertEqual({f["trip_item_id"] for f in self.mb.finds.values()}, set(self.tr.items))

    def test_3_a_train_never_lands_as_other(self):
        self.sync()
        self.assertFalse([i for i in self.tr.items.values() if i["type"] != "train"])
        self.assertNotIn("'other'", (ROOT / "backend/booking_signer/trains.py").read_text().split("class PostgresTrainStore")[1].split("async def others")[0])
        self.assertEqual(TR.fields({"act_id": "act_x", "trip": TRAIN_ONLY})["type"], "train")

    def test_4_one_booking_one_row(self):
        rows = [{"id": "item-1", "type": "train", "agapi_act": "act_RENFE01"}, {"id": "act_RENFE01", "type": "venue", "venue": "Renfe"},
                {"id": "act_other", "type": "venue", "venue": "Casa Lucio"}]
        self.assertEqual([r["id"] for r in TR.one_row(rows)], ["item-1", "act_other"])


TRAIN_ONLY = {"operator": "Renfe", "date": "2026-11-13", "departs": "08:00", "reference": "X7K2PQ"}


class BeforeTheSQL(Base):
    def test_5_constraint_missing_keeps_the_act_logs_and_writes_it_after(self):
        self.tr.allow_train = False                                                        # the database before sql/046
        with self.assertLogs("booking_signer.trains", "WARNING") as logs:
            self.sync()
        self.assertTrue(any("046_train_items.sql" in m and "act_RENFE01" in m for m in logs.output))
        self.assertEqual(self.tr.items, {})                                                # nothing stored — and never as 'other'
        self.assertEqual({a["act_id"] for a in self.ag.kept}, {"act_RENFE01", "act_IRYO01", "act_OUIGO01"})   # AgAPI's act, as today
        self.assertEqual({f["facts"]["act_id"] for f in self.mb.finds.values()}, {"act_RENFE01", "act_IRYO01", "act_OUIGO01"})
        self.assertEqual({f["trip_item_id"] for f in self.mb.finds.values()}, {None})
        self.tr.allow_train = True                                                         # Tyler runs the SQL; the next sync's re-read
        got = asyncio.run(TR.reread(ACCT))
        self.assertEqual(len(got["added"]), 3)
        self.assertEqual(sorted(i["type"] for i in self.tr.items.values()), ["train"] * 3)
        self.assertEqual({f["trip_item_id"] for f in self.mb.finds.values()}, set(self.tr.items))
        self.assertEqual(asyncio.run(TR.reread(ACCT))["added"], [])                         # once
        self.assertEqual(len(self.tr.items), 3)


class TheReRead(Base):
    def test_6_an_other_item_tied_to_a_train_act_becomes_a_train(self):
        asyncio.run(self.ag.remember(ACCT, {"act_id": "act_RENFE01", "kind": "train", "reference": "X7K2PQ", "venue": "Renfe · …"}))
        self.tr.items["old-1"] = {"id": "old-1", "account_id": ACCT, "type": "other", "status": "confirmed", "provider_name": "Madrid to Barcelona",
                                  "booking_reference": "x7k2pq", "escalation_notes": None}
        self.tr.items["old-2"] = {"id": "old-2", "account_id": ACCT, "type": "other", "status": "confirmed", "provider_name": "Renfe train to Sevilla",
                                  "booking_reference": None, "escalation_notes": None}           # a train by its NAME only: never guessed
        with self.assertLogs("booking_signer.trains", "INFO") as logs:
            got = asyncio.run(TR.reread(ACCT))
        self.assertEqual(got["retyped"], ["old-1"])
        self.assertEqual(self.tr.items["old-1"]["type"], "train")
        self.assertEqual(self.tr.items["old-1"]["escalation_notes"], "agapi_act:act_RENFE01")
        self.assertEqual(self.tr.items["old-2"]["type"], "other")
        self.assertTrue(any("old-2" in m and "no AgAPI train record ties to it" in m for m in logs.output))
        self.assertEqual(asyncio.run(TR.reread(ACCT))["retyped"], [])                       # idempotent
        self.sync()                                                                        # the Renfe email later: the SAME item, no second
        self.assertEqual(sum(1 for i in self.tr.items.values() if TR.act_of(i.get("escalation_notes")) == "act_RENFE01"), 1)

    def test_7_a_find_agapi_read_ties_its_other_item(self):
        self.mb.finds["f-1"] = {"id": "f-1", "account_id": ACCT, "gmail_message_id": "g", "kind": "train", "parsed_by": "agapi",
                                "trip_item_id": "old-3", "facts": {"act_id": "act_IRYO01", "kind": "train", "reference": "IRY4M9Z"},
                                "action_status": "done"}
        self.tr.items["old-3"] = {"id": "old-3", "account_id": ACCT, "type": "other", "provider_name": "Valencia trip", "booking_reference": None,
                                  "escalation_notes": "told on WhatsApp"}
        asyncio.run(TR.reread(ACCT))
        self.assertEqual((self.tr.items["old-3"]["type"], self.tr.items["old-3"]["escalation_notes"]), ("train", "told on WhatsApp · agapi_act:act_IRYO01"))


class TheReminder(Base):
    def test_8_the_day_before_says_the_train_and_its_manage_page(self):
        from booking_signer import proactive as PR
        self.sync()
        b = next(r for r in self.rows() if r["agapi_act"] == "act_RENFE01")
        text = PR.render("day_before", b, now=datetime(2026, 11, 12, 17, 0, tzinfo=timezone.utc))
        print("\n── the day-before reminder ──\n" + text)
        self.assertEqual(text, "Tomorrow: your Renfe train AVE 03063 Madrid-Puerta de Atocha → Barcelona-Sants at 08:00, coach 6, seat 07A, "
                               "ref X7K2PQ. Manage your ticket: https://www.renfe.com/es/es/gestiona-tu-billete/tus-reservas/consulta-tus-viajes")
        self.assertNotIn("Reply CANCEL", text)
        self.assertTrue(PR._due("day_before", b, datetime(2026, 11, 12, 17, 0, tzinfo=timezone.utc)))
        self.assertIn("train", PR.template_vars("day_before", b)[1])

    def test_9_the_reminders_read_the_view(self):
        from agapi import itinerary as IT
        from booking_signer import guest_whatsapp as GW, proactive as PR
        self.sync()
        rows = [{k: v for k, v in r.items() if k != "train"} for r in self.rows()]
        with mock.patch.object(GW, "_upcoming", mock.AsyncMock(return_value=rows)), \
                mock.patch.object(IT, "extra_reservations", mock.AsyncMock(return_value=[])):
            got = asyncio.run(PR._rows(ACCT))
        self.assertEqual(sorted(r["train"]["seat"] for r in got), ["07A", "12C", "41"])


class NoSecondReader(unittest.TestCase):
    def test_10_sasha_has_no_rail_parser_of_its_own(self):
        """AgAPI's confirmations.rail is THE rail reader: no regex in Sasha's backend reads a coach, a seat or a train's labels, and no
        file pairs a localizador regex with a seat/coach/train one. The detector is proved on AgAPI's own reader's lines first."""
        raw = re.compile(r"""\b[rR][fF]?(?P<q>"|')(?P<s>(?:\\.|(?!(?P=q)).)*)(?P=q)|\b[fF][rR](?P<q2>"|')(?P<s2>(?:\\.|(?!(?P=q2)).)*)(?P=q2)""")

        def rail_regexes(text):
            pats = [m.group("s") or m.group("s2") or "" for m in raw.finditer(text)]
            out = [x for x in pats if re.search(r"coche|asiento|vag\[?o|vag[oó]n", x, re.I)]
            if any(re.search("localizador", x, re.I) for x in pats):
                out += [x for x in pats if re.search(r"plaza|\btren\b|\btrain\b|\bseat\b|\bcoach\b", x, re.I)]
            return out
        agapis = ('"reference": re.compile(_L(r"localizador|c[oó]digo de reserva") + r"([A-Z0-9]{5,10})\\b", re.I),\n'
                  '"coach": re.compile(_L(r"coche|coach|vag[oó]n|car") + r"(\\d{1,2})\\b", re.I),\n'
                  '"seat": re.compile(_L(r"plaza|asiento|seat") + r"(\\d{1,3}[A-F]?)\\b", re.I),')   # AgAPI confirmations._RAIL
        self.assertTrue(rail_regexes(agapis))                                     # the detector sees a rail reader
        for p in (ROOT / "backend").rglob("*.py"):
            if "/tests/" in str(p) or "venv/" in str(p) or "site-packages" in str(p):
                continue
            self.assertEqual(rail_regexes(p.read_text(encoding="utf-8", errors="replace")), [], str(p))
        src = (ROOT / "backend/booking_signer/trains.py").read_text() + (ROOT / "backend/booking_signer/mailbox.py").read_text()
        self.assertNotRegex(src.lower(), r"renfe|iryo|ouigo")                                # no operator list: AgAPI's kind table decides
        self.assertNotIn("re.compile", (ROOT / "backend/booking_signer/trains.py").read_text().replace('_ACT = re.compile(r"agapi_act:(act_[0-9A-Za-z]+)")', ""))

    def test_11_the_hooks(self):
        mb = (ROOT / "backend/booking_signer/mailbox.py").read_text()
        self.assertIn("tid = await TR.keep(account, got)", mb)
        self.assertIn("await TR.reread(account)", mb)
        self.assertNotIn('"trip_item_id": got["act_id"]', mb)                               # the act's id is never a trip item's id
        self.assertIn('_trains.act_of(r.get("escalation_notes"))', (ROOT / "backend/booking_signer/routes.py").read_text())
        self.assertIn("rows = await TR.view(account, rows)", (ROOT / "backend/booking_signer/ladder_routes.py").read_text())
        self.assertIn("TR.one_row(", (ROOT / "backend/booking_signer/journeys.py").read_text())
        self.assertIn("<TrainLine t={r.train}", (ROOT / "frontend/app/components/workspace/TripPanel.tsx").read_text())
        sql = (ROOT / "backend/booking_signer/sql/046_train_items.sql").read_text()
        self.assertIn("'appointment','other','train']", sql)
        self.assertEqual(sql.lower().count("alter table"), 2)                               # only the type check is replaced
        self.assertNotIn("add column", sql.lower())


if __name__ == "__main__":
    unittest.main()
