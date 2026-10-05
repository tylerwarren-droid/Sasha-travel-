"""CR 23 · the live hand-over, offline: Browserbase and the cloud page faked; the test venue's OWN markup (form_rung) read
through the real checks. Every field filled or no link; the last step; "✅ Booked" from their answer page; refusals for a
CAPTCHA, a terms box, a payment step, a platform, a field that didn't take; read-only never sends; sessions always released.

    cd backend && python -m unittest tests.test_handover_cr23 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from unittest import mock

from booking_signer import form_rung as FR
from booking_signer import handover as HO

TV = "https://sasha-travel-production.up.railway.app/api/booking/test-venue/"


class FakeBB:
    def __init__(self):
        self.created, self.released = [], []

    async def create(self, purpose):
        self.created.append(purpose)
        return {"id": f"s{len(self.created)}", "connectUrl": "wss://connect.example/x"}

    async def live_urls(self, sid):
        return {"debuggerFullscreenUrl": "https://www.browserbase.com/devtools-fullscreen/inspector.html?wss=x",
                "pages": [{"debuggerFullscreenUrl": f"https://www.browserbase.com/devtools-fullscreen/inspector.html?wss={sid}"}]}

    async def release(self, sid):
        self.released.append(sid)


def page_html(variant):
    if variant == "wizard":
        return FR._WIZARD_ONE.format(token="t")
    head = '<script src="https://www.google.com/recaptcha/api.js"></script>' if variant == "captcha" else ""
    extra = {"consent": '<input id="acepto" name="acepto" type="checkbox" required><label for="acepto">Acepto la política de privacidad</label>\n',
             "captcha": '<div class="g-recaptcha" data-sitekey="k"></div>',
             "card": '<label for="card">Tarjeta</label><input id="card" name="card_number" autocomplete="cc-number">',
             "extra": '<label for="dni">DNI</label><input id="dni" name="dni" required>'}.get(variant, "")
    return FR._PAGE.format(variant=variant, head=head, extra=extra, token="t")


class FakePage:
    """The test venue, as a browser would hold it: its markup, the values typed, its own validity check."""
    frames: list = []
    stubborn: set = set()
    prefilled: dict = {}

    def __init__(self):
        self.url = self.html = None
        self.values, self.watching, self.advanced, self.closed = dict(self.prefilled), None, False, False
        self.guest_box = None

    async def connect(self, url):
        pass

    async def goto(self, url):
        self.url, self.html = url, page_html(url.rstrip("/").rsplit("/", 1)[-1])

    async def read(self):
        live = FR.read_form(self.html, self.url)
        fields = []
        for x in live.get("fields", []):
            vis = x["type"] != "hidden" and not x["hidden_by_style"]
            v = self.values.get(x["name"], x["value"] if x["type"] == "hidden" else "")
            fields.append({"name": x["name"], "type": x["type"], "autocomplete": "cc-number" if x["name"] == "card_number" else "",
                           "required": x["required"], "visible": vis, "empty": not v, "value": v})
        invalid = [f["name"] for f in fields if f["required"] and f["visible"] and f["empty"]]
        return {"url": self.url, "frames": list(self.frames), "fields": fields, "valid": not invalid, "invalid": invalid,
                "html": self.html, "text": ""}

    async def fill_all(self, values):
        for k, v in values.items():
            if k not in self.stubborn:
                self.values[k] = v
        return {k: ("" if k in self.stubborn else v) for k, v in values.items()}

    async def advance(self):
        self.advanced = True
        self.url = TV + "wizard/step2"
        self.html = FR._WIZARD_TWO.format(fecha=self.values["fecha"], hora=self.values["hora"], personas=self.values["personas"], token="t")
        self.values = {k: v for k, v in self.values.items() if k not in ("fecha", "hora", "personas")}
        for k in ("fecha", "hora", "personas"):   # now the page's own hidden fields
            pass

    async def point_at_book(self):
        return "Confirmar reserva" if self.advanced else "Reservar"

    async def watch(self, on_tap, on_press, read_only, on_navigated):
        self.watching = (on_tap, on_press, read_only, on_navigated)

    async def answer(self):
        return {"url": TV + "plain", "text": "Reserva confirmada Confirmado: mesa para 2 personas el martes 15 de diciembre a las 21:00, "
                                            "a nombre de Prueba Sasha. Localizador: TV-ABC123-4F"}

    async def snapshot(self):
        return b"\xff\xd8jpeg"

    async def fit(self, w, h):
        self.fitted = (w, h)
        return await self.point_at_book()

    async def screenshot(self):
        return b"png"

    async def close(self):
        self.closed = True


def values(names_roles):
    v = {"date": "2026-12-15", "time": "21:00", "party_size": "2", "person_name": "Prueba Sasha", "email": "prueba@example.com",
         "phone": "+34600000000", "free_text": "Prueba"}
    return [{"name": n, "value": v[r]} for n, (r, _) in names_roles.items()]


REQ = {"what": {"activity": "table", "activity_venue_lang": "mesa", "category": "restaurant"},
       "when": {"mode": "at", "at": "2026-12-15T21:00"}, "how_many": {"count": 2, "unit": "people"}, "who": {"name": "Prueba Sasha"}}


class Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bb, self.saved = FakeBB(), (HO.BB, HO.PAGE_FACTORY, dict(HO.HANDOVERS), list(HO.ON_BOOKED))
        self.pages = []

        def factory():
            p = FakePage()
            self.pages.append(p)
            return p
        HO.BB, HO.PAGE_FACTORY = self.bb, factory
        FakePage.frames, FakePage.stubborn = [], set()
        self.env = mock.patch.dict(os.environ, {"BROWSERBASE_API_KEY": "k", "SASHA_PUBLIC_BASE": "https://sasha-travel-production.up.railway.app"})
        self.env.start()

    def tearDown(self):
        for r in HO.HANDOVERS.values():
            if r.get("_watch"):
                r["_watch"].cancel()
        HO.BB, HO.PAGE_FACTORY = self.saved[0], self.saved[1]
        HO.HANDOVERS.clear(), HO.HANDOVERS.update(self.saved[2])
        HO.ON_BOOKED[:] = self.saved[3]
        self.env.stop()

    async def open(self, variant="plain", read_only=False, **kw):
        url = TV + variant
        m = FR.form_map(url)
        one = {"date", "time", "party_size"}
        if variant == "wizard":
            s1 = [v for v in values(FR.TEST_FIELDS) if FR.TEST_FIELDS[v["name"]][0] in one]
            s2 = [v for v in values(FR.TEST_FIELDS) if FR.TEST_FIELDS[v["name"]][0] not in one]
        else:
            s1, s2 = values(FR.TEST_FIELDS), []
        return await HO.open_handover(page_url=url, m=m, step1=s1, step2=s2, venue="Sasha Test Venue", account=None, form_id=None,
                                      read_only=read_only, request=REQ, fictional=True, **kw)


class Ready(Base):
    async def test_every_field_filled_one_press_left(self):
        rec = await self.open()
        self.assertEqual(rec["state"], "ready")
        self.assertEqual([f["name"] for f in rec["filled"]], list(FR.TEST_FIELDS))
        self.assertEqual(rec["book_label"], "Reservar")
        self.assertTrue(rec["live_url"].endswith("&navbar=false"))
        self.assertNotIn("website_url", self.pages[0].values)                      # the honeypot is never touched
        self.assertIn("/api/booking/handover/", HO.view_url(rec))

    async def test_the_session_is_eu_unrecorded_and_never_solves_a_captcha(self):
        body = {}

        class Spy(HO.Browserbase):
            async def _call(self, method, path, json=None):
                body.update(json or {})
                return {"id": "s1", "connectUrl": "wss://x"}
        await Spy().create("t")
        self.assertEqual(body["region"], "eu-central-1")
        bs = body["browserSettings"]
        self.assertEqual((bs["recordSession"], bs["logSession"], bs["solveCaptchas"]), (False, False, False))

    async def test_wizard_lands_on_the_last_step(self):
        rec = await self.open("wizard")
        self.assertTrue(self.pages[0].advanced)
        self.assertEqual(rec["book_label"], "Confirmar reserva")
        self.assertEqual({f["name"] for f in rec["filled"]}, set(FR.TEST_FIELDS))


class Refusals(Base):
    async def refused(self, rule, **kw):
        with self.assertRaises(HO.Refused) as c:
            await self.open(**kw)
        self.assertEqual(c.exception.rule, rule)
        self.assertEqual(self.bb.released, ["s1"])                                    # released, every time
        self.assertTrue(self.pages[0].closed)
        self.assertEqual(HO.HANDOVERS, self.saved[2])                                 # and no link exists

    async def test_a_real_venues_captcha_is_still_refused(self):
        seen = {"url": "https://www.hanakura.es/solicitar-reserva.html", "frames": [], "fields": [],
                "html": page_html("captcha").replace('action="/api/booking/test-venue/captcha"', 'action="/formularios/reservar.php"')}
        m = {**FR.FORM_MAPS["www.hanakura.es"], "test": False, "fields": dict(FR.TEST_FIELDS)}
        with self.assertRaises(HO.Refused) as c:
            HO.check_page(seen, m, "https://www.hanakura.es/solicitar-reserva.html")
        self.assertEqual(c.exception.rule, "captcha")

    async def test_our_test_venues_captcha_is_the_guests(self):   # Sasha 158 · item 7
        rec = await self.open("captcha")
        self.assertEqual((rec["taps_left"], rec["guest_box"], rec["box_label"]), (2, "captcha", "I'm not a robot"))
        self.assertIn("recaptcha", self.pages[0].guest_box)
        body = (await HO.view(rec["id"], rec["token"])).body.decode()
        self.assertIn("Tick <b>&#8220;I&#x27;m not a robot&#8221;</b>, then press", body)

    async def test_a_real_venues_terms_box_is_still_refused(self):
        page = page_html("consent")
        seen = {"url": "https://www.hanakura.es/solicitar-reserva.html", "frames": [], "fields": [],
                "html": page.replace('action="/api/booking/test-venue/consent"', 'action="/formularios/reservar.php"')}
        m = {**FR.FORM_MAPS["www.hanakura.es"], "test": False, "fields": dict(FR.TEST_FIELDS)}
        with self.assertRaises(HO.Refused) as c:
            HO.check_page(seen, m, "https://www.hanakura.es/solicitar-reserva.html")
        self.assertEqual(c.exception.rule, "consent_box")

    async def test_payment_field(self):
        await self.refused("payment_step", variant="card")

    async def test_payment_frame(self):
        FakePage.frames = ["https://js.stripe.com/v3/elements-inner-card.html"]
        await self.refused("payment_step")

    async def test_platform_frame(self):
        FakePage.frames = ["https://widget.thefork.com/abc"]
        await self.refused("platform")

    async def test_a_required_field_sasha_cannot_fill(self):
        await self.refused("unmapped_field", variant="extra")

    async def test_a_field_that_did_not_take_the_value(self):
        FakePage.stubborn = {"telefono"}
        await self.refused("not_all_prefilled")

    async def test_platform_page_never_opens_a_session(self):
        with self.assertRaises(HO.Refused) as c:
            await HO.open_handover(page_url="https://www.thefork.es/restaurante/x", m={"fields": {}}, step1=[], step2=[], venue="x",
                                   account=None, form_id=None, read_only=True, fictional=True)
        self.assertEqual(c.exception.rule, "platform")
        self.assertEqual(self.bb.created, [])

    async def test_real_guests_wait_for_the_dpa(self):
        with self.assertRaises(HO.Refused) as c:
            await HO.open_handover(page_url="https://www.hanakura.es/solicitar-reserva.html", m={**FR._HANAKURA, "test": False},
                                   step1=[], step2=[], venue="Hanakura", account="a", form_id="f", read_only=False)
        self.assertEqual(c.exception.rule, "no_dpa")
        self.assertEqual(self.bb.created, [])

    async def test_not_configured(self):
        with mock.patch.dict(os.environ, {"BROWSERBASE_API_KEY": ""}):
            with self.assertRaises(HO.Refused) as c:
                await self.open()
        self.assertEqual(c.exception.rule, "cloud_browser_not_configured")


class TestVenueConsent(Base):
    """Sasha 155 · on OUR test venue, the consent box is left for the guest: two taps (☐ + Reservar), everything else filled."""

    async def test_the_box_is_the_guests_two_taps(self):
        rec = await self.open("consent")
        self.assertEqual((rec["state"], rec["taps_left"], rec["guest_box"]), ("ready", 2, "acepto"))
        self.assertEqual(rec["box_label"], "Acepto la política de privacidad")
        self.assertNotIn("acepto", self.pages[0].values)              # never ticked by Sasha
        self.assertEqual(self.pages[0].guest_box, '[name="acepto"]')  # pointed at with the button
        self.assertEqual({f["name"] for f in rec["filled"]}, set(FR.TEST_FIELDS))
        body = (await HO.view(rec["id"], rec["token"])).body.decode()
        self.assertIn("Tick <b>&#8220;Acepto la política de privacidad&#8221;</b>, then press <b>&#8220;Reservar&#8221;</b>", body)

    async def test_a_box_ticked_by_anyone_but_the_guest_means_no_link(self):
        FakePage.prefilled = {"acepto": "on"}
        try:
            with self.assertRaises(HO.Refused) as c:
                await self.open("consent")
            self.assertEqual(c.exception.rule, "consent_box")
        finally:
            FakePage.prefilled = {}

    async def test_pressed_is_booked_as_today(self):
        rec = await self.open("consent")
        on_tap, on_press, _, on_nav = self.pages[0].watching
        on_tap("acepto"), on_tap("Reservar"), on_press("Reservar"), on_nav()
        await asyncio.wait_for(rec["_watch"], 2)
        self.assertEqual((rec["state"], rec["taps"]), ("booked", 2))


class TestNames(unittest.TestCase):
    def test_each_test_page_has_its_own_name(self):
        self.assertEqual(HO._test_name(TV + "hotel"), "Kanoe Test Hotel")
        self.assertEqual(HO._test_name(TV + "consent"), "Sasha Test Venue")


class Phone(Base):
    async def test_one_whatsapp_tap_when_the_sasha_tab_offers_it(self):
        from booking_signer import guest_whatsapp as GW
        sent = []

        async def tap(account, venue, url, what):
            sent.append((account, venue, url, what))
            return {"sent": True}
        rec = await self.open()
        with mock.patch.object(GW, "tap_to_finish", tap, create=True):
            out = await HO.tap_phone("acct-1", rec)
        self.assertEqual(out, {"sent": True})
        self.assertEqual(sent[0][:3], ("acct-1", "Sasha Test Venue", HO.view_url(rec)))
        self.assertIn("2 people", sent[0][3])

    async def test_its_words_say_whether_it_went(self):
        from booking_signer import guest_whatsapp as GW
        rec = await self.open()

        async def already(*a):
            return "not sent: already sent"

        async def went(*a):
            return "sent to +34600000000"
        with mock.patch.object(GW, "tap_to_finish", already, create=True):
            self.assertEqual(await HO.tap_phone("a", rec), {"sent": False, "detail": "not sent: already sent"})
        with mock.patch.object(GW, "tap_to_finish", went, create=True):
            self.assertTrue((await HO.tap_phone("a", rec))["sent"])

    async def test_no_tap_function_no_tap_and_no_failure(self):
        from booking_signer import guest_whatsapp as GW
        rec = await self.open()
        with mock.patch.object(GW, "tap_to_finish", None, create=True):
            self.assertFalse((await HO.tap_phone("acct-1", rec))["sent"])


class NoRequest(Base):
    async def test_without_a_reservation_it_is_sent_never_a_guess(self):
        url = TV + "plain"
        rec = await HO.open_handover(page_url=url, m=FR.form_map(url), step1=values(FR.TEST_FIELDS), step2=[], venue="Kanoe Test Hotel",
                                     account=None, form_id=None, read_only=False, request=None, fictional=True)
        _, on_press, _, on_nav = self.pages[0].watching
        on_press("Reservar"), on_nav()
        await asyncio.wait_for(rec["_watch"], 2)
        self.assertEqual(rec["state"], "answered")             # not stuck, and not a ✅ it can't stand behind
        self.assertIn("doesn't say it's confirmed", rec["say"])


class Pressed(Base):
    async def test_the_press_is_read_into_booked_with_taps_and_seconds(self):
        got = []

        async def told(rec):
            got.append(rec)
        HO.ON_BOOKED.append(told)
        rec = await self.open(return_to="https://wa.me/34600000000")
        r = await HO.view(rec["id"], rec["token"])                                     # the guest opens the link
        self.assertIn(rec["live_url"].replace("&", "&amp;"), r.body.decode())
        on_tap, on_press, ro, on_nav = self.pages[0].watching
        self.assertFalse(ro)
        on_tap("Reservar"), on_press("Reservar"), on_nav()
        await asyncio.wait_for(rec["_watch"], 2)
        self.assertEqual(rec["state"], "booked")
        self.assertTrue(rec["say"].startswith("✅ Booked — Sasha Test Venue, ref TV-ABC123-4F"))
        self.assertEqual(rec["taps"], 1)
        self.assertIsNotNone(rec["press_to_answer_ms"])
        self.assertIsNotNone(rec["open_to_booked_s"])
        self.assertEqual(self.bb.released, ["s1"])
        self.assertEqual(got[0]["state"], "booked")
        s = await HO.view_status(rec["id"], rec["token"])
        self.assertEqual((s["state"], s["return_to"]), ("booked", "https://wa.me/34600000000"))
        self.assertEqual(HO.measured([rec])[0]["taps"], 1)

    async def test_read_only_stops_at_the_press_and_sends_nothing(self):
        rec = await self.open(read_only=True)
        on_tap, on_press, ro, on_nav = self.pages[0].watching
        self.assertTrue(ro)
        on_press("Reservar")
        await asyncio.wait_for(rec["_watch"], 2)
        self.assertEqual(rec["state"], "read_only_stopped")
        self.assertNotIn("answer_text", rec)
        r = await HO.view(rec["id"], rec["token"])                                     # never a guest link
        self.assertEqual(r.status_code, 404)

    async def test_unpressed_session_expires_and_is_released(self):
        with mock.patch.object(HO, "SESSION_SECONDS", 30.05):
            rec = await self.open()
            await asyncio.wait_for(rec["_watch"], 2)
        self.assertEqual(rec["state"], "expired")
        self.assertEqual(self.bb.released, ["s1"])

    async def test_a_wrong_token_or_a_foreign_return_is_refused(self):
        rec = await self.open(return_to="https://evil.example/phish")
        self.assertIsNone(rec["return_to"])
        self.assertEqual((await HO.view(rec["id"], "nope")).status_code, 404)


class FromPreparedForm(Base):
    """The real path: a form the rung prepared → claimed at hand-over → finished from their answer (trip item confirmed)."""

    async def asyncSetUp(self):
        self.saved_store = FR.STORE
        FR.STORE = FR.MemoryFormStore()
        self.acct = str(uuid.uuid4())
        rec = {"form_id": str(uuid.uuid4()), "account_id": self.acct, "read_id": None, "host": "sasha-travel-production.up.railway.app",
               "page_url": TV + "plain", "action_url": TV + "plain", "fields": values(FR.TEST_FIELDS), "hidden_names": ["token"],
               "read_back_lines": ["I'll send the booking form on Sasha Test Venue's own website (…)"], "read_back_sha256": "x",
               "created_at": HO.NOW()}
        await FR.STORE.put(rec, {})
        self.fid = rec["form_id"]

    async def asyncTearDown(self):
        FR.STORE = self.saved_store

    async def call(self):
        req = mock.Mock()
        req.json = mock.AsyncMock(return_value={"return_to": "https://project.kanoe.ai/chat"})
        with mock.patch.object(HO, "account_for", return_value=self.acct), \
             mock.patch.object(HO.V, "_allowed", mock.AsyncMock(side_effect=self.robots)), \
             mock.patch("booking_signer.form_rung._request_of", mock.AsyncMock(return_value=REQ)), \
             mock.patch.object(HO, "_receipt", mock.AsyncMock()):
            return await HO.from_prepared_form(self.fid, req)

    async def robots(self, http, url, resolve):
        assert isinstance(url, str) and url.startswith("https://"), "robots check called as (http, url, resolve)"
        return True

    async def test_link_then_booked_in_the_form_store(self):
        out = await self.call()
        self.assertTrue(out["ok"])
        self.assertEqual(out["taps_left"], 1)
        self.assertIn("One tap left", out["say"])
        self.assertEqual(FR.STORE.forms[self.fid]["status"], "sending")                  # claimed: no second send can race
        rec = HO.HANDOVERS[out["handover_id"]]
        _, on_press, _, on_nav = self.pages[0].watching
        on_press("Reservar"), on_nav()
        with mock.patch.object(HO, "_receipt", mock.AsyncMock()):
            await asyncio.wait_for(rec["_watch"], 2)
        f = FR.STORE.forms[self.fid]
        self.assertEqual((f["status"], f["booking_reference"]), ("sent", "TV-ABC123-4F"))
        self.assertEqual(FR.STORE.attempts[-1]["status"], "confirmed")

    async def test_a_second_handover_is_refused(self):
        await self.call()
        out = await self.call()
        self.assertEqual(out.status_code, 409)

    async def test_a_refusal_marks_the_form_not_sent(self):
        FakePage.stubborn = {"email"}
        out = await self.call()
        self.assertEqual(out.status_code, 422)
        self.assertEqual(FR.STORE.forms[self.fid]["status"], "not_sent")


class GuestPage(Base):
    """CR 25 · the page the guest opens: what they're booking on top, the live view sized to their phone, the screens after."""

    async def test_live_page_says_what_is_filled_and_where_to_press(self):
        rec = await self.open(return_to="https://wa.me/34600000000")
        body = (await HO.view(rec["id"], rec["token"])).body.decode()
        self.assertIn('id="live"', body)
        self.assertIn('let state = "live"', body)
        self.assertIn("Everything&#8217;s filled in at <em>Sasha Test Venue</em>", body)
        self.assertIn("&#8220;Reservar&#8221;", body)
        for chip in ("Tue 15 Dec · 21:00", "2 people", "Prueba Sasha"):
            self.assertIn(f'<span class="chip">{chip}</span>', body)
        self.assertIn("Open it full screen", body)

    async def test_fit_takes_the_guest_frame_clamped(self):
        rec = await self.open()
        out = await HO.view_fit(rec["id"], rec["token"], w=5000, h=10)
        self.assertEqual((out["ok"], self.pages[0].fitted), (True, (1024, 320)))
        self.assertTrue(out["snapshot"].startswith("data:image/jpeg;base64,"))
        self.assertEqual((await HO.view_fit(rec["id"], "nope")).status_code, 404)

    async def test_booked_page_has_the_ref_and_the_way_back(self):
        rec = await self.open(return_to="https://wa.me/34600000000")
        _, on_press, _, on_nav = self.pages[0].watching
        on_press("Reservar"), on_nav()
        await asyncio.wait_for(rec["_watch"], 2)
        body = (await HO.view(rec["id"], rec["token"])).body.decode()
        self.assertIn('let state = "booked"', body)
        self.assertIn("Ref TV-ABC123-4F", body)
        self.assertIn('href="https://wa.me/34600000000"', body)

    async def test_expired_is_calm_and_says_nothing_was_sent(self):
        with mock.patch.object(HO, "SESSION_SECONDS", 30.05):
            rec = await self.open()
            await asyncio.wait_for(rec["_watch"], 2)
        body = (await HO.view(rec["id"], rec["token"])).body.decode()
        self.assertIn('let state = "expired"', body)
        self.assertIn("Nothing was sent to Sasha Test Venue.", body)

    async def test_an_unknown_link_is_calm_too(self):
        r = await HO.view("nope", "x")
        self.assertEqual(r.status_code, 404)
        self.assertIn('let state = "gone"', r.body.decode())
        self.assertIn("Nothing was sent.", r.body.decode())


if __name__ == "__main__":
    unittest.main()
