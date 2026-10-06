"""CR 33 · a filled official form as a card in the chat: page 1 of the SAME filled PDF as an image, the filled boxes
highlighted (and only those), a strip saying it is not signed and not submitted, the full PDF one tap away; on WhatsApp an
image message whose caption carries the PDF link, on the web a picture that opens the PDF. Specimens only.

    cd backend && python -m unittest tests.test_formcard_cr33 -v
"""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from booking_signer import guest_whatsapp as GW
from products import formcard as FC, routes as PR, store as ST
from products.health import tarjeta as TS
from tests import test_guest_whatsapp_s75 as TG
from tests import test_tarjeta_cr30 as TT
from tests.test_relocation_cr1 import NA, E, ana

run = TG.run


def client():
    app = FastAPI(); app.include_router(PR.router)
    return TestClient(app)


def yellowish(px):
    r, g, b = px[:3]
    return r > 200 and g > 170 and b < 190


class Card(TG.unittest.TestCase):
    def test_only_the_filled_boxes_are_highlighted(self):
        rows = E.rows(ana(), NA)
        filled = [r["name"] for r in rows if r["state"] == E.FILLED]
        img = Image.open(io.BytesIO(FC.card(E.fill(rows), filled, "Filled by Sasha")))
        self.assertEqual(img.format, "JPEG")
        self.assertGreater(img.width, 800)
        from pypdf import PdfReader
        pdf = E.fill(rows)
        page = PdfReader(io.BytesIO(pdf)).pages[0]
        h = float(page.mediabox.height)
        bar = max(54, img.width // 16)
        centre = lambda a: (int((float(a["/Rect"][0]) + float(a["/Rect"][2])) / 2 * FC.SCALE),
                            bar + int((h - (float(a["/Rect"][1]) + float(a["/Rect"][3])) / 2) * FC.SCALE))
        annots = {str(a.get_object().get("/T")): a.get_object() for a in page["/Annots"] if a.get_object().get("/T")}
        x, y = centre(annots["Texto1"])                            # the passport number: filled
        self.assertTrue(any(yellowish(img.getpixel((x + dx, y))) for dx in range(-40, 40, 4)))
        x, y = centre(annots["Texto2"])                            # the NIE: empty for this applicant → no highlight
        self.assertFalse(any(yellowish(img.getpixel((x + dx, y))) for dx in range(-10, 10, 2)))

    def test_the_link_line_is_split_for_the_web(self):
        cap, link = FC.split(f"Page 1.\n{FC.PDF_LINE}https://x.test/a.pdf")
        self.assertEqual((cap, link), ("Page 1.", "https://x.test/a.pdf"))
        self.assertEqual(FC.split("no link"), ("no link", None))


class HealthCard(TT.Base):
    def test_whatsapp_gets_the_card_with_the_pdf_link_and_the_route_draws_it(self):
        TT.Base.through(self)
        self.answers()
        sent = next(s for s in GW.SENDER.sent if s["media"])
        cid = self.case("tarjeta")["id"]
        self.assertTrue(sent["media"].endswith(f"/api/products/health/{cid}/1449F1-card.jpg"))
        self.assertIn(f"Open the full PDF: ", sent["body"])
        self.assertIn(f"/api/products/health/{cid}/1449F1-prepared.pdf", sent["body"])
        r = client().get(f"/products/health/{cid}/1449F1-card.jpg")
        self.assertEqual((r.status_code, r.headers["content-type"]), (200, "image/jpeg"))
        self.assertEqual(Image.open(io.BytesIO(r.content)).format, "JPEG")
        self.case("tarjeta")["state"]["values_expire_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.assertEqual(client().get(f"/products/health/{cid}/1449F1-card.jpg").status_code, 410)

    def test_the_web_gets_a_picture_that_opens_the_pdf(self):
        from products import web as PWEB
        web = lambda m="", payload=None: run(PWEB.web_turn(TG.ACCOUNT, m, payload=payload, now=self.now, signed_in=True))
        web("españa")
        for pl in ("hx:es:salud", "hx:consent:yes", "hx:tsi"):
            web(payload=pl)
        r = web("DEMO")
        web(payload=r["quick_replies"][0]["payload"])                  # the read-back's one yes
        for pl, m in (("hx:ts:m:NUEVA", ""), ("hx:ts:addr:yes", ""), (None, "28013"), (None, "600000000"), (None, "SKIP"),
                      ("hx:ts:s:INDISTINTO", "")):
            r = web(m, payload=pl)
        r = web("skip")
        card = r["media"][0]
        self.assertTrue(card["url"].endswith("1449F1-card.jpg"))
        self.assertTrue(card["link"].endswith("1449F1-prepared.pdf"))
        self.assertNotIn("Open the full PDF", card["caption"])


class RelocationCard(TG.unittest.TestCase):
    def test_the_ex01_card_route(self):
        saved = ST.STORE
        ST.STORE = ST.MemoryCaseStore()
        try:
            cid = run(ST.STORE.put("relocation", TG.ACCOUNT, "wa", {"rows": E.rows(ana(), NA), "status": "prepared"}))
            r = client().get(f"/products/relocation/{cid}/EX-01-card.jpg")
            self.assertEqual((r.status_code, r.headers["content-type"]), (200, "image/jpeg"))
            self.assertEqual(client().get("/products/relocation/nope/EX-01-card.jpg").status_code, 404)
        finally:
            ST.STORE = saved


if __name__ == "__main__":
    TG.unittest.main()
