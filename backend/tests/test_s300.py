"""Sasha 300 · T78 — MANAGING THE BOOKING AFTER IT'S MADE (slice 1): ONE LIVE ITINERARY, CHANGE, CANCEL, REMINDERS.

The root test (written before code): the ONE record a venue booking lives on is AgAPI's — its act (act_id), read through
venue.booking_status; Sasha keeps a pointer (s2_memory "venue_acts"), never a second truth. The hand-overs AgAPI doesn't keep yet
(a platform's page, his own WhatsApp — CR 131 (a)) are their hand-over row until it does. THE ONE ITINERARY is agapi/itinerary.py:
my_plans (chat · voice · WhatsApp), the Trip tab and the reminders read it. A change, a cancellation or "running late" goes by the
route the booking was made on, on his yes in a later turn; where that route can't do it yet, she says so and nothing is sent.

    cd backend && python -m unittest tests.test_s300 -v
"""
from __future__ import annotations

import asyncio
import inspect
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from agapi import itinerary as IT, s2_manage as SM, s2_memory as M, s2_status as ST, venue_submit as VS, venues as VN
from app.agent import voice as V

ACCT = "00000000-0000-4000-8000-000000000300"
DAY = (date.today() + timedelta(days=3)).isoformat()


def run(c):
    return asyncio.run(c)


class AgAPI:
    """AgAPI as Sasha sees it: each act answers venue.booking_status; venue.change_booking is CR 131's (or unknown, as today)."""

    def __init__(self, change: bool = True):
        self.states, self.calls, self.change = {}, [], change

    async def __call__(self, op, body, approval=None, account=None):
        self.calls.append((op, dict(body), approval))
        if op == "users.register":
            return {"ok": True, "result": {"end_user_id": "usr_1"}}
        if op == "venue.booking_status":
            st = self.states.get(body["act_id"], "sent")
            return {"ok": True, "result": {"act_id": body["act_id"], "state": st,
                                           **({"venue_words": {"untrusted_text": "Sí, os esperamos a las 21:00."}} if st == "confirmed" else {})}}
        if op == "venue.change_booking":
            if not self.change:
                return {"ok": False, "error": {"code": "unknown_operation", "message": "There is no operation venue.change_booking in AgAPI v1."}}
            if not approval:
                what = f"arrive about {body['arrive']}" if body["kind"] == "late" else f"move it to {body.get('at', '')[11:16]}"
                return {"ok": False, "error": {"code": "approval_required", "details": {"read_back_id": "rb_ch", "read_back_sha256": "sha_ch",
                                                                                         "lines": [f"Ask DiverXO to {what}.", "OK?"]}}}
            return {"ok": True, "result": {"status": "sent", "change_act_id": "act_change", "say": "I've asked DiverXO. It stays as it was until they reply."}}
        if op == "sandbox.simulate_approval":
            return ({"ok": True, "result": {"approval_id": "apv_1"}} if "yes" in body["said"].lower() or body["said"].lower().startswith("ok")
                    else {"ok": False, "error": {"code": "no_explicit_yes"}})
        if op == "venue.cancel_booking":
            raise AssertionError("a hand-over's cancellation never reaches AgAPI")
        raise AssertionError(op)


class Ctx:
    def __init__(self, said="", ago=0):
        self.account, self.user_said, self.idem, self.claimed, self.surface = ACCT, said, None, None, "s2"
        self.started = datetime.now(timezone.utc) + timedelta(seconds=ago)


#: one booking per route: AgAPI's acts (email · Kanoe's WhatsApp · a call) and the hand-overs (a platform · his own WhatsApp · their page)
ACTS = [{"act_id": "act_mail", "venue": "DiverXO", "when": f"{DAY}T21:00", "party": 2, "state": "sent", "channel": "email", "at": 1,
         "place_id": "ChIJ-diverxo"},
        {"act_id": "act_wa", "venue": "Casa Lucio", "when": f"{DAY}T14:00", "party": 4, "state": "sent", "channel": "whatsapp", "at": 2},
        {"act_id": "act_call", "venue": "Botín", "when": f"{DAY}T20:30", "party": 3, "state": "calling", "route": "call", "at": 3}]
PAGES = [{"venue": "La Mi Venta", "date": DAY, "time": "21:30", "party": 2, "url": "https://project.kanoe.ai/prepared/vpr_x",
          "platform": "CoverManager", "at": datetime.now(timezone.utc).isoformat()},
         {"venue": "Taberna Las Sobrinas", "date": DAY, "time": "22:00", "party": 2, "route": "your_whatsapp",
          "url": "https://wa.me/34611222333?text=Hola%2C%20%C2%BFten%C3%A9is%20mesa%3F", "at": datetime.now(timezone.utc).isoformat()},
         {"venue": "Bar Tomate", "date": DAY, "time": "13:00", "party": 2, "url": "https://bartomate.test/reservas",
          "at": datetime.now(timezone.utc).isoformat()}]


class Base(unittest.TestCase):
    change = True

    def setUp(self):
        self.api = AgAPI(self.change)
        self.sent = []   # anything that would reach a venue or a person from the old ladder's paths

        async def gw_api(account, method, path, body=None, timeout=None):
            if method != "GET":
                self.sent.append((method, path))
            if path == "/api/booking/reservations":
                return 200, {"reservations": []}
            return 404, {}
        from booking_signer import guest_whatsapp as GW, plan_store as PS, basket as BK, rental_moments as RM
        for p in (mock.patch.object(VS, "CALL", self.api), mock.patch.dict(VS._ACTS, {}, clear=True), mock.patch.dict(VS._USERS, {}, clear=True),
                  mock.patch.object(VS, "target", mock.AsyncMock(return_value="sandbox")),
                  mock.patch.object(M, "put_kind", mock.AsyncMock(return_value=True)),
                  mock.patch.object(M, "kind", mock.AsyncMock(side_effect=lambda a, k: [dict(x) for x in PAGES] if k == VN.PREPARED_KIND else None)),
                  mock.patch.object(GW, "api", gw_api), mock.patch.object(PS, "plans", mock.AsyncMock(return_value=[
                      {"trip_id": "trip-1", "title": "Madrid", "start": DAY, "end": DAY}])),
                  mock.patch.object(BK, "items", mock.AsyncMock(return_value=[])), mock.patch.object(RM, "rentals", mock.AsyncMock(return_value=[])),
                  mock.patch.dict(SM._HELD, {}, clear=True), mock.patch.dict(VN._CANCEL, {}, clear=True),
                  mock.patch("agapi.v0.claim", mock.AsyncMock()), mock.patch.object(SM, "_record", mock.AsyncMock())):
            p.start()
            self.addCleanup(p.stop)
        VS._ACTS[ACCT] = [dict(a) for a in ACTS]

    def rows(self):
        return {r["venue"]: r for r in run(IT.venue_rows(ACCT))}

    def agapi_sends(self):
        return [c for c in self.api.calls if c[0] in ("venue.change_booking", "venue.cancel_booking", "venue.submit_booking") and c[2]]


# ── (1) THE ONE ITINERARY: every route, its status, its route, the venue's words ────────────────────────────────────────────────

class OneItinerary(Base):
    def test_every_booking_on_every_route_is_on_it(self):
        r = self.rows()
        self.assertEqual(set(r), {"DiverXO", "Casa Lucio", "Botín", "La Mi Venta", "Taberna Las Sobrinas", "Bar Tomate"})
        self.assertEqual({k: v["route"] for k, v in r.items()},
                         {"DiverXO": "email", "Casa Lucio": "kanoe_whatsapp", "Botín": "call", "La Mi Venta": "platform",
                          "Taberna Las Sobrinas": "your_whatsapp", "Bar Tomate": "their_page"})
        self.assertEqual(r["La Mi Venta"]["route_words"], "on their booking platform")
        self.assertEqual(r["La Mi Venta"]["platform"], "CoverManager")   # its button's label only — never said (rule 249)
        self.assertEqual(r["Taberna Las Sobrinas"]["route_words"], "from your own phone")
        self.assertEqual([w for x in r.values() for w in V.channel_words(x["route_words"] + " " + x["status_words"])], [])

    def test_status_is_the_records_and_their_words_are_data(self):
        self.api.states["act_mail"] = "confirmed"
        self.api.states["act_wa"] = "proposed"
        r = self.rows()
        self.assertEqual(r["DiverXO"]["status"], "confirmed")
        self.assertEqual(r["DiverXO"]["status_words"], ST.WORDS["confirmed"])
        self.assertEqual(r["DiverXO"]["venue_said"], {"untrusted_text": "Sí, os esperamos a las 21:00."})
        self.assertEqual(r["Casa Lucio"]["status"], "offered")
        self.assertEqual(r["Casa Lucio"]["status_words"], ST.WORDS["proposed"])
        self.assertEqual(r["La Mi Venta"]["status"], "handed_over")
        self.assertEqual(r["Taberna Las Sobrinas"]["status_words"], ST.WORDS["your_whatsapp"])

    def test_a_cancelled_one_stays_on_it_said_cancelled(self):
        self.api.states["act_mail"] = "cancelled"
        self.assertEqual(self.rows()["DiverXO"]["status"], "cancelled")
        self.assertEqual(self.rows()["DiverXO"]["status_words"], "Cancelled")

    def test_the_map_link_is_its_place_id_never_googles_content(self):
        m = self.rows()["DiverXO"]["map_url"]
        self.assertEqual(m, "https://www.google.com/maps/search/?api=1&query=DiverXO&query_place_id=ChIJ-diverxo")

    def test_a_hand_over_on_a_record_is_that_record_once(self):
        PAGES.append({"venue": "DiverXO", "date": DAY, "time": "21:00", "party": 2, "url": "https://diverxo.test/"})
        try:
            self.assertEqual([r["source"] for r in run(IT.venue_rows(ACCT)) if r["venue"] == "DiverXO"], ["act"])
        finally:
            PAGES.pop()

    def test_my_plans_is_the_itinerary_each_in_its_trip(self):
        out = run(SM.my_plans(Ctx(), {}))
        titles = [i["title"] for i in out["items"]]
        self.assertEqual(sorted(titles), sorted(["DiverXO", "Casa Lucio", "Botín", "La Mi Venta", "Taberna Las Sobrinas", "Bar Tomate"]))
        self.assertTrue(all(i.get("trip") == "Madrid" and i.get("route_words") and i.get("status_words") for i in out["items"]))

    def test_the_trip_tab_gets_the_same_rows(self):
        extra = {r["venue"]: r for r in run(IT.extra_reservations(ACCT))}
        self.assertEqual(len(extra), 6)
        self.assertEqual(extra["DiverXO"]["trip_id"], "trip-1")
        self.assertEqual(extra["La Mi Venta"]["status"], "link_sent")   # the Trip tab's "not booked yet" words
        from booking_signer import ladder_routes as LR
        for fn in (LR.plan_view, LR.journeys_view):
            self.assertIn("IT.extra_reservations(account)", inspect.getsource(fn))

    def test_nothing_else_builds_the_list(self):
        self.assertIn("IT.of(account)", inspect.getsource(SM.plans_of))
        from booking_signer import proactive as PR
        self.assertIn("IT.upcoming(account", inspect.getsource(PR._rows))
        self.assertNotIn("GW._upcoming(account, names=False)", inspect.getsource(PR.tick))


# ── (2) CHANGE · RUNNING LATE · CANCEL: by the booking's own route, on his yes ─────────────────────────────────────────────────

class ChangeByItsRoute(Base):
    def test_an_email_booking_is_changed_through_agapi_by_its_act_read_back_first(self):
        out = run(SM.change_booking(Ctx("move DiverXO to 21:30", ago=-1), {"what": "venue", "venue": "DiverXO", "new_time": "21:30"}))
        self.assertEqual(out["status"], "awaiting_yes")
        self.assertEqual(out["route"], "email")
        self.assertEqual(out["read_back"][0], "Ask DiverXO to move it to 21:30.")
        op = next(c for c in self.api.calls if c[0] == "venue.change_booking")
        self.assertEqual(op[1], {"end_user": "usr_1", "act_id": "act_mail", "kind": "change", "at": f"{DAY}T21:30"})
        self.assertEqual(self.agapi_sends(), [])   # nothing sent before the yes

    def test_his_yes_in_a_later_turn_sends_it_and_the_change_is_on_the_booking(self):
        run(SM.change_booking(Ctx("move DiverXO to 21:30", ago=-1), {"what": "venue", "venue": "DiverXO", "new_time": "21:30"}))
        out = run(SM.change_booking(Ctx("Yes, do it", ago=5), {"what": "venue", "venue": "DiverXO", "approval": {"said": "Yes, do it"}}))
        self.assertEqual(out["status"], "requested")
        self.assertEqual([(c[0], c[1]["act_id"]) for c in self.agapi_sends()], [("venue.change_booking", "act_mail")])
        self.assertEqual(self.rows()["DiverXO"]["change"]["state"], "requested")   # the itinerary shows it, awaiting their answer

    def test_running_late_goes_the_same_way(self):
        out = run(SM.running_late(Ctx("running 20 minutes late for DiverXO", ago=-1), {"venue": "DiverXO", "minutes": 20}))
        self.assertEqual(out["status"], "awaiting_yes")
        op = next(c for c in self.api.calls if c[0] == "venue.change_booking")
        self.assertEqual(op[1]["kind"], "late")
        self.assertEqual(op[1]["arrive"], "21:20")

    def test_a_platform_booking_is_his_on_their_page_nothing_sent(self):
        out = run(SM.change_booking(Ctx("move La Mi Venta to 22:00", ago=-1), {"what": "venue", "venue": "La Mi Venta", "new_time": "22:00"}))
        self.assertEqual(out["status"], "yours_there")
        self.assertEqual(out["open"], "https://project.kanoe.ai/prepared/vpr_x")
        self.assertEqual(out["say"], V.manage_line("change", "platform", "La Mi Venta", "CoverManager"))
        self.assertEqual(out["say"], "La Mi Venta is on their booking platform, so you change it there — here's their page. Nothing is sent from here.")
        self.assertEqual(V.channel_words(out["say"]), [])
        self.assertNotIn("booked", out["say"])   # a hand-over isn't booked until they confirm: never said as booked
        self.assertEqual((self.agapi_sends(), self.sent), ([], []))

    def test_his_own_whatsapp_booking_opens_his_chat_never_a_message_written_here(self):
        out = run(VN.cancel_venue(Ctx("cancel Las Sobrinas", ago=-1), {"venue": "Taberna Las Sobrinas"}))
        self.assertEqual(out["status"], "yours_there")
        self.assertEqual(out["open"], "https://wa.me/34611222333")   # the chat only: no ?text= written by Sasha (CR 131 (d))
        self.assertEqual(out["button"]["label"], "Open your WhatsApp chat")
        self.assertEqual((self.agapi_sends(), self.sent), ([], []))

    def test_their_own_page_booking_is_cancelled_there(self):
        out = run(VN.cancel_venue(Ctx("cancel Bar Tomate", ago=-1), {"venue": "Bar Tomate"}))
        self.assertEqual((out["status"], out["open"]), ("yours_there", "https://bartomate.test/reservas"))
        self.assertEqual(self.sent, [])


class HerVoice(Base):
    def test_no_line_of_hers_here_names_a_channel(self):
        lines = [V.manage_line(k, r, "Casa", "CoverManager", link=l) for k in ("change", "cancel", "late")
                 for r in ("platform", "your_whatsapp", "their_page") for l in (True, False)]
        lines += [V.change_not_yet("Casa", IT.route_words(r), k) for r in IT.ROUTE_WORDS for k in ("change", "late")]
        self.assertEqual(V.check(lines), [])


class WhatHeSees(Base):
    def test_the_page_she_says_is_on_the_screen_as_its_button(self):
        from app.agent import sasha as S
        out = run(SM.change_booking(Ctx("move La Mi Venta to 22:00", ago=-1), {"what": "venue", "venue": "La Mi Venta", "new_time": "22:00"}))
        ev = S.render("change_booking", out, {})
        self.assertEqual((ev["kind"], ev["url"], ev["label"]), ("handover", "https://project.kanoe.ai/prepared/vpr_x", "Open CoverManager"))
        wa = S.render("cancel_venue", run(VN.cancel_venue(Ctx("cancel Las Sobrinas", ago=-1), {"venue": "Taberna Las Sobrinas"})), {})
        self.assertEqual((wa["url"], wa["label"]), ("https://wa.me/34611222333", "Open your WhatsApp chat"))

    def test_a_platform_is_named_from_the_decisions_words(self):
        self.assertEqual(IT.platform_name(None, "CoverManager booking widget"), "CoverManager")
        self.assertEqual(IT.platform_name("their booking page", "Book on TheFork"), "TheFork")
        self.assertIsNone(IT.platform_name("their booking form", "WhatsApp"))


class ChangeNotYetInAgAPI(Base):
    change = False   # today: AgAPI has no venue.change_booking (CR 131 (c))

    def test_said_plainly_and_nothing_is_sent(self):
        out = run(SM.change_booking(Ctx("move DiverXO to 21:30", ago=-1), {"what": "venue", "venue": "DiverXO", "new_time": "21:30"}))
        self.assertEqual(out["status"], "not_possible")
        self.assertFalse(out["sent"])
        self.assertEqual(out["say"], V.change_not_yet("DiverXO", "by email"))
        self.assertIn("Nothing was sent", out["say"])
        self.assertEqual((self.agapi_sends(), self.sent), ([], []))
        self.assertEqual(SM._HELD, {})   # no read-back held: a later "yes" binds to nothing

    def test_never_another_route_instead(self):
        run(SM.running_late(Ctx("running late for DiverXO", ago=-1), {"venue": "DiverXO", "minutes": 15}))
        self.assertFalse([p for m, p in self.sent if "/notice" in p or "/calls/" in p])   # no email or call chosen by "what's available"


# ── (3) REMINDERS: from the itinerary — where, the map, running late ───────────────────────────────────────────────────────────

class Reminders(Base):
    def test_the_two_hours_line_has_the_map_and_running_late(self):
        from booking_signer import proactive as PR
        b = {"venue": "DiverXO", "time": "21:00", "party": 2, "map_url": IT.map_url("DiverXO", "ChIJ-diverxo"), "status": "confirmed"}
        self.assertEqual(PR.render("two_hours", b), "In 2 hours: DiverXO, 21:00, 2 people. Map: "
                         "https://www.google.com/maps/search/?api=1&query=DiverXO&query_place_id=ChIJ-diverxo Running late? Tell me.")
        self.assertIn(" Calle de Padre Damián 23.", PR.render("day_before", {**b, "address": "Calle de Padre Damián 23", "date": DAY}))

    def test_due_two_hours_before_and_never_in_the_last_hour(self):
        from booking_signer import proactive as PR
        b = {"date": DAY, "time": "21:00", "timezone": "Europe/Madrid"}
        start = PR.starts_at(b)
        self.assertFalse(PR._due("two_hours", b, start - timedelta(hours=2, minutes=1)))
        self.assertTrue(PR._due("two_hours", b, start - timedelta(hours=1, minutes=59)))
        self.assertFalse(PR._due("two_hours", b, start - timedelta(minutes=59)))

    def test_an_agapi_booking_is_reminded_of(self):
        from booking_signer import proactive as PR, guest_whatsapp as GW
        self.api.states["act_mail"] = "confirmed"
        with mock.patch.object(GW, "_upcoming", mock.AsyncMock(return_value=[])):
            rows = {r["venue"]: r for r in run(PR._rows(ACCT))}
        self.assertEqual(rows["DiverXO"]["status"], "confirmed")
        self.assertEqual(rows["DiverXO"]["id"], "act_mail")
        self.assertTrue(rows["DiverXO"]["map_url"])

    def test_before_043_a_booking_with_no_trip_item_is_never_sent(self):
        from booking_signer import proactive as PR

        class Base_:
            async def _run(self, fn):
                raise RuntimeError("column booking_key does not exist")
        pg = PR.PostgresProactiveStore(Base_())
        self.assertEqual(run(pg.claim({"account_id": ACCT, "trip_item_id": "act_mail", "kind": "day_before",
                                       "local_day": date.today(), "status_at_send": "confirmed"})), -1)

    def test_the_043_migration_is_drafted_not_applied(self):
        import pathlib
        sql = (pathlib.Path(__file__).resolve().parents[1] / "booking_signer" / "sql" / "043_itinerary_reminders.sql").read_text()
        self.assertIn("APPLY AFTER DEPLOY", sql)
        self.assertIn("'two_hours'", sql)
        self.assertIn("booking_key", sql)


if __name__ == "__main__":
    unittest.main()
