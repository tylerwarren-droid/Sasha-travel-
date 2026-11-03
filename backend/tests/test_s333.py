"""Sasha 333 · THE TRAVELLER VAULT (docs/sasha/S-333-traveller-vault.md). Offline: the group in memory (Sasha 332's world), the Keep in
memory with a stand-in KMS, emails and WhatsApp captured, every log line captured.

    cd backend && python -m unittest tests.test_s333 -v
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import unittest
from unittest import mock

from agapi import keep as K, s2_keep as KEEP, s2_records as REC, v0 as API
from booking_signer import groups as G, traveller_vault as TV
from tests import test_s332 as W

run = asyncio.run
OWNER = W.OWNER
#: the fictional numbers saved through the page — the scan looks for each of them everywhere else
PASSPORTS = {f"Worker{i}": f"XK{i:02d}48{i:02d}21" for i in range(20)}


class World(W.World):
    def __enter__(self):
        super().__enter__()
        self.mails, self.logs = [], []
        self.keep = KEEP.MemoryKeepStore()
        kms = K.LocalKms(os.urandom(32))

        async def send(msg):
            self.mails.append(json.dumps(msg))
            return {"sent": True}
        for p in (mock.patch.object(KEEP, "STORE", self.keep), mock.patch("booking_signer.vault.kms.kek", lambda: kms),
                  mock.patch.object(REC, "RUN", None), mock.patch.object(TV, "SEND", send),
                  mock.patch.dict(os.environ, {"SASHA_BOOKING_KEY": "test-booking-key-333"})):
            p.start()
            self.p.append(p)
        REC.clear_memory()
        h = logging.Handler(level=logging.DEBUG)
        h.emit = lambda rec: self.logs.append(rec.getMessage())
        logging.getLogger().addHandler(h)
        self._h, self._lvl = h, logging.getLogger().level
        logging.getLogger().setLevel(logging.DEBUG)
        self.limits()
        rows = G.read_csv(W.FIX.read_bytes())
        for i, r in enumerate(rows[:20]):   # half the list has an email, a few a WhatsApp number (fictional: +1 500 555 01xx)
            if i % 2 == 0:
                r["email"] = f"worker{i}@example.test"
            if i < 4:
                r["phone"] = f"+15005550{110 + i}"
        self.mid = run(G.upload(OWNER, rows))["movement_id"]
        run(G.plan(OWNER))
        return self

    def __exit__(self, *a):
        logging.getLogger().removeHandler(self._h)
        logging.getLogger().setLevel(self._lvl)
        super().__exit__(*a)

    def members(self):
        return run(self.store.members(self.mid))

    def token(self, m):
        return TV.make_token(m["id"], OWNER, self.mid)

    def fill(self, m, i, loyalty=True):
        return run(TV.save(self.token(m), {"number": PASSPORTS[f"Worker{i}"], "country": "ES", "expires_on": "2031-05-01",
                                           "name": m["name"].upper(), "born_on": "1990-01-01"},
                           [{"program": "Iberia Plus", "number": f"IB7700{i:02d}99"}] if loyalty else []))


class InviteAndPage(unittest.TestCase):
    def test_invite_page_save_and_the_list_flips(self):
        with World() as w:
            before = run(G.view(OWNER))["counts"]
            inv = run(TV.invite(OWNER))
            self.assertEqual(len(inv["emailed"]), 10)                                 # the ones with an email
            self.assertEqual(len(inv["forward"]), 10)                                 # the rest: links for the organiser to forward
            self.assertTrue(all(l["link"] == TV.link(l["link"].rsplit("/vault/", 1)[1]) and TV.read_token(l["link"].rsplit("/", 1)[1])
                                for l in inv["forward"]))                           # each one: this site's /vault/<its own signed token>
            ms = {m["name"]: m for m in w.members()}
            filled = [n for n in ms if n not in ("Rania Mithal", "Liam Specimen")][:10]
            for n in filled:
                i = list(ms).index(n)
                page = run(TV.page(w.token(ms[n])))
                self.assertEqual((page["name"], page["saved"]), (n, []))
                w.fill(ms[n], i)
            after = run(G.view(OWNER))
            st = {r["name"]: r for r in after["rows"]}
        self.assertEqual(before, {"needs vault": 19, "over limit": 1})                # Rania's flight over the worker's €600
        self.assertEqual(after["counts"], {"planned": 10, "needs vault": 9, "over limit": 1})   # 10 filled → planned; over limit stays over
        self.assertTrue(all(st[n]["status"] == "planned" and st[n]["vault"] == {"passport": True, "loyalty": ["Iberia Plus"]} for n in filled))
        print(f"\n[s333 proof] invite: {len(inv['emailed'])} emailed, {len(inv['forward'])} to forward · master list before {before} → after "
              f"{after['counts']}")

    def test_a_link_is_one_person_and_expires(self):
        with World() as w:
            m = w.members()[0]
            t = w.token(m)
            self.assertEqual(TV.read_token(t)["member"], m["id"])
            b, s = t.split(".")
            forged = TV._b64(json.dumps({"m": w.members()[1]["id"], "o": OWNER, "v": w.mid, "n": "x", "e": int(time.time()) + 999}).encode())
            self.assertIsNone(TV.read_token(forged + "." + s))                      # another person's id under this signature: refused
            self.assertIsNone(TV.read_token(t, now=time.time() + TV.LIFE_S + 5))    # expired
            with self.assertRaises(TV.VaultRefused):
                run(TV.page(forged + "." + s))

    def test_the_airline_fields_are_required(self):
        with World() as w:
            m = w.members()[0]
            with self.assertRaises(TV.VaultRefused) as e:
                run(TV.save(w.token(m), {"number": "XK11223344", "country": "ES", "expires_on": "2031-05-01", "name": "A"}))
            self.assertIn("date of birth", e.exception.message)
            self.assertFalse(run(TV.has_passport(m)))                               # nothing saved


class NoFullNumberAnywhereElse(unittest.TestCase):
    def test_the_whole_class(self):
        """A full number appears ONLY in the vault (sealed) — never in a log, a trip, a message, the organiser's list or the model's
        inputs. The page and the organiser get masks / ✓."""
        with World() as w:
            ms = w.members()
            for i, m in enumerate(ms[:12]):
                w.fill(m, i)
            ctx = API.Ctx(account=OWNER, mode="test")
            model_inputs = [run(API.group_list(ctx, {})), run(API.group_invite_vault(ctx, {})), run(G.view(OWNER))]
            pages = [run(TV.page(w.token(m))) for m in ms[:12]]
            wa = run(TV.delete_by_phone("+15005550110", "please delete my passport"))
            stored = [json.dumps({k: (v.hex() if isinstance(v, bytes) else str(v)) for k, v in it.items()}) for it in w.keep.items.values()]
            places = {"logs": "\n".join(w.logs), "trips": json.dumps(w.trips, default=str), "emails": "\n".join(w.mails),
                      "whatsapp": wa or "", "model": json.dumps(model_inputs, default=str), "pages": json.dumps(pages),
                      "keep rows (sealed)": "\n".join(stored), "group tables": json.dumps(w.store.rows, default=str)}
        numbers = list(PASSPORTS.values())[:12] + [f"IB7700{i:02d}99" for i in range(12)]
        for where, text in places.items():
            leaked = [n for n in numbers if n in text]
            self.assertEqual(leaked, [], where)
        self.assertIn("Passport ES ••••", json.dumps(pages, ensure_ascii=False))   # the member's own page: masks
        self.assertNotIn("••••", places["model"])                                    # the organiser / the model: ✓ only, not even a mask
        print("\n[s333 proof] scanned for the 24 saved numbers: " + ", ".join(f"{k} 0" for k in places) + " — the full numbers live only "
              "inside the Keep's sealed rows")

    def test_the_model_never_gets_a_tool_that_reads_them(self):
        tools = {t["name"]: t for t in API.TOOLS}
        self.assertNotIn("group_vault_read", tools)
        for name in ("group_list", "group_invite_vault"):
            self.assertIn("never", tools[name]["description"].lower() if name == "group_invite_vault" else "never")
        self.assertIn("NEVER ask for a passport or any number in chat", tools["group_invite_vault"]["description"])


class Delete(unittest.TestCase):
    def test_from_the_page_and_on_whatsapp(self):
        with World() as w:
            ms = w.members()
            for i, m in enumerate(ms[:3]):
                w.fill(m, i)
            r = run(TV.erase(w.token(ms[0])))                                        # the page's "Delete everything"
            self.assertEqual((r["deleted"], r["key_destroyed"]), (2, True))
            self.assertFalse(run(TV.has_passport(ms[0])))
            self.assertIsNone(run(TV.delete_by_phone("+15005550111", "what time is my flight?")))   # not those words: nothing
            self.assertIsNone(run(TV.delete_by_phone("+15005550199", "delete my passport")))         # nobody's number: nothing
            said = run(TV.delete_by_phone("+15005550111", "Delete my passport please"))              # ms[1]'s own number
            self.assertTrue(said.startswith("Done"))
            self.assertFalse(run(TV.has_passport(ms[1])))
            self.assertTrue(run(TV.has_passport(ms[2])))                              # only theirs
            st = {r["name"]: r["status"] for r in run(G.view(OWNER))["rows"]}
        self.assertEqual((st[ms[0]["name"]], st[ms[2]["name"]]), ("needs vault", "planned"))

    def test_the_booking_call_gets_a_reference(self):
        with World() as w:
            m = w.members()[0]
            w.fill(m, 0)
            v = run(TV.vault_view(m))
        self.assertTrue(v["refs"]["passport"].startswith("keep:"))                   # CR 163 consumes the reference, never the value
        self.assertEqual(len(v["refs"]["loyalty"]), 1)


class TheOneRecord(unittest.TestCase):
    def test_the_keep_is_the_vault(self):
        import inspect
        src = inspect.getsource(TV)
        self.assertIn("KEEP.put(m[\"id\"], \"passport\"", src)                        # into the Keep, under the member's own id
        self.assertNotIn("create table", (W.FIX.parent.parent.parent / "booking_signer/sql/049_traveller_vault.sql").read_text().lower())
        self.assertNotIn("passport", G.__dict__.get("COLUMNS", {}))                   # the group list never carries a number column


if __name__ == "__main__":
    unittest.main()
