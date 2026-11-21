"""Sasha 389 · A TAPPED ALTERNATIVE BOOKS THE VENUE AgAPI ALREADY RESOLVED — never a re-resolve, never a map.

Measured (Tyler's WhatsApp, 19 Nov 06:34–06:37; agapi-live and Twilio, read-only): AgAPI's four options for La Taberna de Peñalver (21:45 ·
22:00 · 22:15 · 20:00) went as a LIST PICKER (more than three), its rows' ids card:alt_…:alt:<n>. Sasha 344's tap reader kept a list row's
id only when it started with "kanoe:" — Sasha's own card ids were dropped as "another tool's row", the tap reached the MODEL as "21:45",
which re-resolved the venue by NAME (agapi-live: venue.profile only — no prepare_booking, mandate or submit) and handed over a Google Maps
SEARCH as "Tap to finish".

THE CLASS, made impossible:
  (a) ONE id namespace — products.tools.OWN_IDS: a button and a list row with Sasha's own id are the same tap, on the real webhook;
  (b) every alternative kind (same evening, other day, other service, nearby) × the tap → venue.prepare_booking with AgAPI's OWN identity
      of the venue (its book terms; the held place only for a same-venue kind — never a name comparison) → platform_book;
  (c) ONE fallback: the venue's own page; a map or a search link is never handed over, anywhere a hand-over link is made.

    cd backend && python -m unittest tests.test_s389_tap_books_agapis_venue -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import re
import unittest
from unittest import mock

from agapi import venue_submit as VS, venues as VN
from app.agent import voice as V
from booking_signer import guest_whatsapp as GW, inbound_phone as IP, wa_agent as WA
from products import tools as TL
from tests.test_cr165_tools import ListSender
from tests.test_guest_whatsapp_s75 import Base as WABase, GUEST, SANDBOX
from tests.test_s329 import CARD, Ctx, VENUE, run
from tests.test_s384_alternatives_as_taps import ALTS, Base384

BACKEND = pathlib.Path(__file__).resolve().parents[1]
MAPS = ("https://www.google.com/maps/search/?api=1&query=La%20Taberna%20de%20Pe%C3%B1alver", "https://maps.google.com/?cid=1",
        "https://www.google.es/maps/place/x", "https://maps.app.goo.gl/abc", "https://www.google.com/search?q=penalver")


class TheTapReachesItsCard(WABase):
    """(a) on the real webhook: the SAME card id as a quick-reply button and as a list row (Twilio's ListId) → card_tap, never the model."""

    def tap(self, fields):
        GW.SENDER = ListSender()
        ran = []
        GW._spawn = lambda coro: ran.append(coro)
        self.link()
        seen = {}

        async def card_tap(ch, payload, st, out, now, button_text=""):
            seen["card_tap"] = payload
            return "x"

        async def agent_turn(ch, body, payload, st, out, now, button_text="", voice_in=False):
            seen["payload"] = payload
            return await (card_tap(ch, payload, st, out, now) if payload.startswith("card:") else asyncio.sleep(0, "model"))
        p = {"From": f"whatsapp:{GUEST}", "To": f"whatsapp:{SANDBOX}", "MessageSid": "SM389" + str(len(fields)), "NumMedia": "0",
             "WaId": GUEST.lstrip("+"), **fields}
        loop = asyncio.get_event_loop()
        with mock.patch.object(IP, "_verified", mock.AsyncMock(return_value=p)), \
                mock.patch.object(VS, "whatsapp_inbound", mock.AsyncMock(return_value={"matched": False})), \
                mock.patch.object(WA, "agent_turn", agent_turn), mock.patch.object(WA, "card_tap", card_tap), \
                mock.patch.object(GW, "first_time", mock.AsyncMock(return_value=True)), \
                mock.patch.object(GW, "linked", mock.AsyncMock(return_value=True)):
            loop.run_until_complete(IP.sms(None))
            while ran:
                loop.run_until_complete(ran.pop(0))
        return seen

    def test_a_list_row_and_a_button_are_the_same_tap(self):
        cid = "card:alt_a0586c2f5b7b2269e0b647a9:alt:1"   # the id Tyler's 21:45 row carried (Twilio content 919be439)
        as_list = self.tap({"Body": "21:45 · Fri 20 Nov", "ListId": cid, "ListTitle": "21:45 · Fri 20 Nov", "MessageType": "interactive"})
        as_button = self.tap({"Body": "21:45", "ButtonText": "21:45", "ButtonPayload": cid, "MessageType": "button"})
        self.assertEqual(as_list.get("card_tap"), cid)
        self.assertEqual(as_button.get("card_tap"), cid)

    def test_one_namespace(self):
        for i in ("kanoe:tool:diligence", "card:x:alt:1", "pick:ChIJ", "say:Yes", "yn:yes", "photo:passport:SM1", "keep:yes"):
            self.assertEqual(TL.own_id({"ListId": i, "ListTitle": "t"}), i, i)          # a list row of hers: kept
        self.assertEqual(TL.own_id({"ListId": "ad_case_42", "ListTitle": "Show my cases"}), "")   # another tool's row: its title
        self.assertIn("TL.is_own(payload)", inspect.getsource(WA.ours))                   # the brain reads the SAME list
        src = (BACKEND / "products/tools.py").read_text()
        self.assertEqual(len(re.findall(r'"card:", "pick:"', src)), 1)                    # defined once


class EveryKindBooksAgAPIsVenue(Base384):
    """(b) every alternative kind × the tap → prepare with AgAPI's own identity → platform_book. AgAPI's venue name differs from the Places
    listing on purpose (Peñalver: "… Cava Baja | Restaurante La Latina" vs "La Taberna de Peñalver") — never compared."""
    ALTS = [{**x, "venue": (x["venue"] + " | Restaurante (AgAPI's name)") if x["kind"] != "nearby_venue" else x["venue"]} for x in ALTS] + [
        {"rank": 5, "kind": "other_service_time", "venue": VENUE + " (AgAPI's name)", "date": "2037-11-20", "time": "14:00",
         "reason": "lunch that day", "book": {"place_id": "ChIJ329", "date": "2037-11-20", "time": "14:00", "party": 2}}]

    def kind(self, rank, pid, same, booked=True):
        q = self.options()
        done = run(VN.answer_card(Ctx(f"tap {rank}"), q["read_back_id"], f"alt:{rank}"))
        if booked:   # (the fake AgAPI calls every 22:00 on the 20th full, whatever the venue: the nearby one is checked at its prepare)
            self.assertEqual(done["status"], "confirmed", (rank, done))
            self.assertTrue(done["line"].startswith("Booking now:"), done["line"])
        prep = self.ag.bodies("venue.prepare_booking")[-1]["place"]
        self.assertEqual(prep["place_id"], pid)                                            # AgAPI's identity, carried unchanged
        # the venue the options came from: its held place (its own website too), whatever AgAPI calls it; nearby: only its own
        self.assertEqual(prep.get("website"), CARD.get("website") if same else "https://casavecina.example")
        self.assertEqual(self.holds, [])                                                   # never the whole path / a re-resolve by name

    def test_same_evening(self):
        self.kind(1, "ChIJ329", True)

    def test_other_day(self):
        self.kind(3, "ChIJ329", True)

    def test_nearby(self):
        self.kind(4, "ChIJvecina", False, booked=False)

    def test_other_service(self):
        self.kind(5, "ChIJ329", True)

    def test_no_name_comparison_decides_the_venue(self):
        src = inspect.getsource(VN.alternative_answer) + inspect.getsource(VN.option_place)
        self.assertNotIn("_base(", src)
        self.assertNotIn("hold_venue(", inspect.getsource(VN.alternative_answer))
        self.assertIn("SAME_VENUE_KINDS", inspect.getsource(VN.option_place))

    def test_agapi_deciding_the_option_another_way_is_its_answer(self):
        q = self.options()
        real = self.ag.call

        async def other_way(op, body, approval=None, account=None):
            got = await real(op, body, approval, account)
            if op == "venue.prepare_booking" and body.get("time") == "21:45":
                got["result"]["decision"] = {"route": "none", "say_text": "They don't take that one online.",
                                             "button": {"link": MAPS[0], "label": "See it"}}
                got["result"]["link"] = MAPS[1]
            return got
        with mock.patch("agapi.venue_submit.CALL", other_way):
            done = run(VN.answer_card(Ctx("21:45"), q["read_back_id"], "alt:2"))
        self.assertEqual((done["status"], done["booked"], done["say"]), ("not_booked", False, "They don't take that one online."))
        self.assertFalse(any(VN._NOT_OWN.match(u) for u in (MAPS[0], MAPS[1]) if u == (done.get("button") or {}).get("link")))
        self.assertTrue(VN.own_page((done.get("button") or {}).get("link")))               # AgAPI's own hand-over page, never the map
        self.assertEqual(self.holds, [])


class TheOneFallback(unittest.TestCase):
    """(c) a map or a search is never a booking fallback — the one rule (own_page) at the one hand-over constructor and the floor."""

    def test_own_page(self):
        for u in MAPS:
            self.assertFalse(VN.own_page(u), u)
            self.assertNotIn("open", VN._link_out(u))
        for u in ("https://www.tabernadepenalver.com/reservas", "http://cafe.example/", "https://www.covermanager.com/reservation/x"):
            self.assertTrue(VN.own_page(u), u)
            self.assertEqual(VN._link_out(u)["page_url"], u)

    def test_the_floor_never_builds_a_map(self):
        f = VN.floor({"name": "La Taberna de Peñalver Cava Baja | Restaurante La Latina", "place_id": "ChIJvVx"}, {"venue": "x"})
        self.assertNotIn("button", f)
        self.assertEqual(f["say"], V.NO_OWN_PAGE.format(venue="La Taberna de Peñalver Cava Baja | Restaurante La Latina"))

    def test_ratchet_no_booking_path_builds_a_map_or_search_link(self):
        """Every module on the venue booking path: no google.com/maps / maps search / web search URL is BUILT (a hand-over could carry it)."""
        path = ("agapi/venues.py", "agapi/venue_submit.py", "agapi/venue_truth.py", "booking_signer/wa_agent.py", "app/agent/sasha.py",
                "app/agent/voice.py", "booking_signer/guest_whatsapp.py")
        built = re.compile(r"""f?["']https?://(?:www\.)?(?:google\.[a-z.]+/(?:maps|search)|maps\.google\.)""")
        hits = [f"{rel}:{i}" for rel in path for i, line in enumerate((BACKEND / rel).read_text().splitlines(), 1)
                if built.search(line) and not line.lstrip().startswith("#")]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
