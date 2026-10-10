"""CR 77 · SOURCE COPIES + PACIOLI'S AUTO-CHECK. Offline: fakes for every fetch and for the AI reader; objects in memory (no bucket).

  · every source read is kept as read (a PDF as the file; a page as its HTML + a PDF rendered from it), sha256 · URL · date · reader kind;
    a re-read adds a copy and never overwrites; every fact points to its copy
  · Pacioli accepts a fact only when (a) its quote is in the stored copy, (b) the source is official (or supplied), (c) every number,
    currency and phone is in its quote, (d) the copy's sha256 matches — anything else is an exception, withheld until a person decides
  · a person's acceptance stays; the switch turns auto-accept off; sources.get → a signed link + sha256 + date read; the review page

    python -m unittest agapi_service.tests.test_cr77 -v      (from the repo root)
"""
from __future__ import annotations

import asyncio
import hashlib
from unittest import mock

from agapi_service import objects as OB
from agapi_service.fineprint import copies as CP, fixture as FX, model as M, pacioli as PC, reader as RD, review as RV
from agapi_service.tests.test_cr74 import GUIDE, ISSUER, VISA, Fetches, guide_facts, patched
from agapi_service.tests.test_service import Base

SEED = {"issuer": "Example Bank", "product": "Example Bank Travel Visa", "network": "Visa", "country": "ES", "seeds": [ISSUER],
        "official_domains": ["examplebank-cdn.test"]}   # the guide is on the bank's own CDN


def run(c):
    return asyncio.run(c)


def fake_pdf(html: bytes, base: str) -> bytes:
    return b"%PDF-1.4 rendered " + hashlib.sha256(html).hexdigest().encode()


class CopiesBase(Base):
    def setUp(self):
        super().setUp()
        OB.MEMORY.clear()
        PC._TEXT_CACHE.clear()
        self.ps = [mock.patch.object(CP, "RENDER", fake_pdf)]
        for p in self.ps:
            p.start()

    def tearDown(self):
        for p in self.ps:
            p.stop()
        super().tearDown()

    def read(self, key="cr77-visa", guide=None, seed=SEED, facts=None):
        f = Fetches(guide=guide)
        ps = patched(f.patch() + [mock.patch.object(RD, "EXTRACT", self._model(facts))])
        try:
            async def go():
                async with CP.keeping(self.store, key, "card_terms"):
                    return await RD.read_card({**seed, "key": key}, [ISSUER])
            out = run(go())
        finally:
            for p in ps:
                p.stop()
        M.apply_read(self.store, key, seed, out)
        return out

    @staticmethod
    def _model(facts):
        async def model(card, docs):
            d = guide_facts()
            for x in d["facts"]:
                x["applies_to"] = ""
            if facts is not None:
                d["facts"] = facts
            return d
        return model


class Copies(CopiesBase):
    def test_every_source_read_is_kept_with_its_sha_url_date_and_kind(self):
        out = self.read()
        kept = {c["final_url"]: c for c in out["copies"]}
        self.assertEqual(set(kept), {ISSUER, GUIDE})
        pdf, html = kept[GUIDE], kept[ISSUER]
        self.assertEqual(pdf["sha256"], "sha256:" + hashlib.sha256(FX.guide_pdf(VISA)).hexdigest())
        self.assertEqual((pdf["content_type"], pdf["reader_kind"], pdf["role"]), ("application/pdf", "card_terms", "read"))
        self.assertEqual(OB.MEMORY[pdf["object_key"]][0], FX.guide_pdf(VISA))                      # the original file
        self.assertTrue(OB.MEMORY[html["object_key"]][0].startswith(b"<html>"))                    # the HTML as read …
        self.assertTrue(OB.MEMORY[html["render_key"]][0].startswith(b"%PDF-"))                     # … plus a rendered PDF
        self.assertIsNone(pdf["render_key"])
        self.assertTrue(all(f["copy_id"] == pdf["id"] for f in out["facts"]))                      # every fact → its copy
        self.assertEqual({r["id"] for r in self.store.q("select id from source_copies where subject = 'cr77-visa'")}, {pdf["id"], html["id"]})
        self.assertTrue(all(r["copy_id"] for r in M.claims(self.store, M.product_id("cr77-visa"), every=True)))

    def test_a_re_read_adds_a_copy_and_never_overwrites(self):
        first = {c["final_url"]: c for c in self.read()["copies"]}
        changed = FX.guide_pdf(VISA).replace(b"%%EOF", b"% a changed edition\n%%EOF")
        with mock.patch.object(CP, "ts", lambda: "2026-12-01T00:00:00.000000Z"):
            second = {c["final_url"]: c for c in self.read(guide=changed)["copies"]}
        self.assertNotEqual(first[GUIDE]["id"], second[GUIDE]["id"])
        self.assertNotEqual(first[GUIDE]["object_key"], second[GUIDE]["object_key"])
        self.assertEqual(OB.MEMORY[first[GUIDE]["object_key"]][0], FX.guide_pdf(VISA))            # the first copy is untouched
        self.assertEqual(self.store.one("select count(*) n from source_copies where subject = 'cr77-visa' and final_url = ?", GUIDE)["n"], 2)

    def test_a_failed_store_never_fails_the_read(self):
        async def down(*a, **k):
            raise RuntimeError("bucket down")
        with mock.patch.object(OB, "put", down):
            out = self.read()
        self.assertTrue(out["facts"])
        self.assertTrue(all(f["copy_id"] is None and not f["pacioli"]["passed"] for f in out["facts"]))   # → exceptions (no copy)


class Pacioli(CopiesBase):
    def test_a_clean_read_passes_all_four_and_the_card_is_accepted_by_pacioli(self):
        out = self.read()
        self.assertTrue(all(f["pacioli"]["passed"] for f in out["facts"]), [f["pacioli"]["why"] for f in out["facts"] if not f["pacioli"]["passed"]])
        p = self.store.one("select * from card_products where key = 'cr77-visa'")
        self.assertEqual(p["accepted_by"], PC.CHECKER)
        self.assertTrue(M.accepted(p))
        self.assertEqual(len(M.claims(self.store, p["id"])), len(out["facts"]))

    def test_each_check_fails_on_its_own(self):
        out = self.read()
        cp = CP.get(self.store, out["facts"][0]["copy_id"])
        fx = next(f for f in out["facts"] if f["field"] == "baggage_delay_limit")
        ok = run(PC.check_claim(None, fx, {}, SEED, cp))
        self.assertTrue(ok["passed"])
        a = run(PC.check_claim(None, {**fx, "quote": fx["quote"] + " and more"}, {}, SEED, cp))
        self.assertEqual((a["a_verbatim"], a["passed"]), (False, False))
        b = run(PC.check_claim(None, fx, {}, {**SEED, "official_domains": []}, cp))                 # the CDN isn't the bank's own domain
        self.assertEqual((b["b_official"], b["passed"]), (False, False))
        c = run(PC.check_claim(None, {**fx, "value": {"amount_minor": 30000, "currency": "USD"}}, {}, SEED, cp))
        self.assertEqual((c["c_in_quote"], c["missing"]), (False, ["USD"]))
        c2 = run(PC.check_claim(None, {**fx, "field": "phone", "value": "+34 900 111 222"}, {}, SEED, cp))
        self.assertFalse(c2["c_in_quote"])
        OB.MEMORY[cp["object_key"]] = (b"%PDF- tampered", "application/pdf")
        PC._TEXT_CACHE.clear()
        d = run(PC.check_claim(None, fx, {}, SEED, cp))
        self.assertEqual((d["d_sha256"], d["passed"]), (False, False))

    def test_number_words_and_thousand_separators_count_as_in_the_quote(self):
        self.assertTrue(PC.in_quote("notice_deadline_days", 7, "dentro del plazo de SIETE días")["pass"])
        self.assertTrue(PC.in_quote("baggage_loss_limit", {"amount_minor": 1500000, "currency": "EUR"}, "hasta 15.000 euros")["pass"])   # cents → 15,000
        self.assertFalse(PC.in_quote("baggage_loss_limit", {"amount_minor": 150000, "currency": "EUR"}, "hasta 15.000 euros")["pass"])
        self.assertTrue(PC.in_quote("x", "15000 EUR", "hasta 15.000 euros")["pass"])
        self.assertTrue(PC.in_quote("phone", "900 816 955", "Tel. 900 816 955")["pass"])

    def test_a_supplied_file_is_official(self):
        k = CP.Keeper(self.store, "cr77-supplied", "card_terms", supplied_by="Tyler")
        raw = FX.guide_pdf(VISA)
        cp = run(k.keep("https://www.bank.example/cert.pdf", "https://www.bank.example/cert.pdf", "application/pdf", raw, role="supplied"))
        g = FX.CARDS[VISA]["guide"]
        r = run(PC.check_claim(None, {"quote": g[2], "field": "percent", "value": {"basis_points": 0}}, {}, {"seeds": []}, cp))
        self.assertTrue(r["b_official"])

    def test_an_exception_is_withheld_until_a_person_decides(self):
        g = FX.CARDS[VISA]["guide"]
        facts = [{"benefit": "fx_fee", "field": "percent", "value": "0", "source_url": GUIDE, "quote": g[2], "applies_to": ""},
                 {"benefit": "claims", "field": "phone", "value": "+34 900 000 000", "source_url": GUIDE, "quote": g[19], "applies_to": ""},
                 {"benefit": "claims", "field": "notice_deadline_days", "value": "60", "source_url": GUIDE, "quote": g[17], "applies_to": "all"}]
        self.read(facts=facts)
        pid = M.product_id("cr77-visa")
        bad = self.store.q("select id from card_claims where product_id = ? and field = 'phone'", pid)[0]["id"]
        PC.record(self.store, bad, pid, {"passed": False, "why": ["planted"], "copy_id": None})
        self.assertNotIn(bad, {c["id"] for c in M.claims(self.store, pid)})
        self.assertEqual([e["claim_id"] for e in PC.exceptions(self.store)], [bad])
        PC.decide(self.store, bad, "accept", "kanoe review · test")
        self.assertIn(bad, {c["id"] for c in M.claims(self.store, pid)})
        self.assertEqual(PC.exceptions(self.store), [])

    def test_the_switch_turns_auto_accept_off_and_a_persons_acceptance_stays(self):
        self.read()
        p = self.store.one("select * from card_products where key = 'cr77-visa'")
        PC.set_auto(self.store, False, "test")
        M._AUTO["on"] = False
        try:
            self.assertFalse(M.accepted(self.store.one("select * from card_products where id = ?", p["id"])))
            self.store.x("update card_products set accepted_by = 'kanoe review · session x' where id = ?", p["id"])   # a person accepts
            self.assertTrue(M.accepted(self.store.one("select * from card_products where id = ?", p["id"])))
        finally:
            PC.set_auto(self.store, True, "test")
            M._AUTO["on"] = True

    def test_run_rechecks_the_store_and_counts(self):
        self.read()
        with mock.patch.object(M, "is_beta", lambda p: True), mock.patch.object(M, "all_seeds", lambda: {"cr77-visa": SEED}):
            out = run(PC.run(self.store, keys=["cr77-visa"]))
        self.assertEqual((out["checked"], out["failed"]), (15, 0))


class Download(CopiesBase):
    def test_sources_get_by_copy_and_by_claim(self):
        out = self.read()
        pdf = next(c for c in out["copies"] if c["final_url"] == GUIDE)
        html = next(c for c in out["copies"] if c["final_url"] == ISSUER)
        r = self.ok("sources.get", {"copy_id": pdf["id"]})
        self.assertEqual((r["sha256"], r["source_url"], r["reader_kind"], r["format"]), (pdf["sha256"], GUIDE, "card_terms", "pdf"))
        self.assertTrue(r["url"].startswith("memory://sources/"))
        cid = self.store.q("select id from card_claims where product_id = ?", M.product_id("cr77-visa"))[0]["id"]
        self.assertEqual(self.ok("sources.get", {"claim_id": cid})["copy_id"], pdf["id"])
        h = self.ok("sources.get", {"copy_id": html["id"], "format": "pdf"})
        self.assertEqual((h["format"], h["rendering"]["of_sha256"]), ("pdf", html["sha256"]))
        self.assertTrue(self.ok("sources.get", {"copy_id": html["id"]})["pdf_available"])
        self.call("sources.get", {"copy_id": "scp_" + "0" * 24}, expect=404)

    def test_the_review_page_offers_the_download_and_the_exceptions(self):
        self.read()
        with mock.patch.object(M, "is_beta", lambda p: True):
            code = RV.new_code(self.store)
            tok = self.client.get(f"/fineprint/review/start/{code}", follow_redirects=False).cookies.get(RV.COOKIE)
            page = self.client.get("/fineprint/review", cookies={RV.COOKIE: tok}).text
            self.assertIn("Download source", page)
            self.assertIn("✓ checked by Pacioli", page)
            self.assertIn("Exceptions", page)
            self.assertIn("Automatic acceptance: <b>on</b>", page)
            cid = self.store.q("select id from card_claims where product_id = ?", M.product_id("cr77-visa"))[0]["id"]
            r = self.client.get(f"/fineprint/review/source?claim={cid}", cookies={RV.COOKIE: tok}, follow_redirects=False)
            self.assertEqual((r.status_code, r.headers["location"][:17]), (303, "memory://sources/"))
            self.assertEqual(self.client.get(f"/fineprint/review/source?claim={cid}", follow_redirects=False).status_code, 401)
            self.assertTrue(self.client.post("/fineprint/review/switch", json={"on": False}, cookies={RV.COOKIE: tok}).json()["ok"])
            self.assertFalse(PC.auto_on(self.store))
            PC.set_auto(self.store, True, "test")
            M._AUTO["on"] = True


class ObjectStore(CopiesBase):
    def test_content_addressed_write_once(self):
        run(OB.put("sources/aa/x.pdf", b"one", "application/pdf"))
        run(OB.put("sources/aa/x.pdf", b"two", "application/pdf"))   # the same key is never overwritten
        self.assertEqual(run(OB.get("sources/aa/x.pdf")), b"one")

    def test_presign_shape(self):
        env = {"AGAPI_S3_ENDPOINT": "https://t3.storage.test", "AGAPI_S3_BUCKET": "b-1", "AGAPI_S3_KEY_ID": "AKID", "AGAPI_S3_SECRET": "s",
               "AGAPI_S3_REGION": "auto"}
        with mock.patch.dict("os.environ", env):
            u = OB.presign("sources/ab/c.pdf", 600, filename="scp_x.pdf")
        self.assertTrue(u.startswith("https://b-1.t3.storage.test/sources/ab/c.pdf?"))
        self.assertIn("X-Amz-Expires=600", u)
        self.assertIn("X-Amz-Signature=", u)
        self.assertNotIn("&s&", u)
