"""CR 73 · the registry survey, wave 0 — registry.countries / get / documents / obtain_plan / verify on the certified core.
Offline: the committed snapshot (AD's read-only export + Magellan's reads, made on the sandbox server) and fakes for every fetch;
no test reads the internet, and none asks a never-fetch host for anything.

    python -m unittest agapi_service.tests.test_cr73 -v      (from the repo root)
"""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from agapi_service import magellan as MG, rules as R
from agapi_service.registers import gate, model as M, ops as O, plan as P, reader as RD, verify as V
from agapi_service.registry import operations
from agapi_service.store import Store
from agapi_service.tests.test_service import Base

VEC = Path(__file__).resolve().parents[1] / "spec" / "ext" / "vectors"
PAGE_URL = "https://www.justiz.gv.at/fees"
QUOTE = "Aktueller Firmenbuchauszug EUR 4,89"
READS = {"reads": {"AT": {
    "jurisdiction": "AT", "read_at": "2026-10-10T06:00:00Z", "pages": [{"url": PAGE_URL, "title": "Fees"}], "unread": [],
    "robots": {"https://justizonline.gv.at/jop/service/fba/search": {"verdict": "unreadable", "why": "robots.txt answered a web page, not a robots file",
                                                                    "robots_url": "https://justizonline.gv.at/robots.txt", "quote": ""},
               "https://justizonline.gv.at/jop/web/firmenbuchabfrage": {"verdict": "unreadable", "why": "robots.txt answered a web page, not a robots file",
                                                                         "robots_url": "https://justizonline.gv.at/robots.txt", "quote": ""}},
    "registers": ["firmenbuch"], "documents": {"current_extract": "firmenbuch", "certified_extract": "firmenbuch"},
    "routes": {"online": "current_extract", "court": "certified_extract", "verrechnung": "current_extract"},
    "facts": [
        {"entity": "register", "key": "firmenbuch", "field": "name_local", "value": "Firmenbuch", "source_url": PAGE_URL, "quote": "Das Firmenbuch ist ein öffentliches Verzeichnis."},
        {"entity": "register", "key": "firmenbuch", "field": "kind", "value": "company", "source_url": PAGE_URL, "quote": "Das Firmenbuch ist ein öffentliches Verzeichnis."},
        {"entity": "document", "key": "current_extract", "field": "name_local", "value": "Aktueller Firmenbuchauszug", "source_url": PAGE_URL, "quote": QUOTE},
        {"entity": "document", "key": "current_extract", "field": "kind", "value": "extract_current", "source_url": PAGE_URL, "quote": QUOTE},
        {"entity": "document", "key": "current_extract", "field": "who_may_obtain", "value": "anyone", "source_url": PAGE_URL, "quote": "jedermann ist zur Einzelabfrage befugt"},
        {"entity": "document", "key": "certified_extract", "field": "kind", "value": "certificate", "source_url": PAGE_URL, "quote": "Der Firmenbuchauszug bei Gericht kostet 19,00 Euro."},
        {"entity": "route", "key": "online", "field": "channel", "value": "paid_web", "source_url": PAGE_URL, "quote": "kostenpflichtig über JustizOnline"},
        {"entity": "route", "key": "online", "field": "cost", "value": {"amount_minor": 489, "currency": "EUR", "basis": "per_document"}, "source_url": PAGE_URL, "quote": QUOTE},
        {"entity": "route", "key": "online", "field": "entry_url", "value": "https://justizonline.gv.at/jop/web/firmenbuchabfrage", "source_url": PAGE_URL, "quote": "JustizOnline"},
        {"entity": "route", "key": "court", "field": "channel", "value": "in_person", "source_url": PAGE_URL, "quote": "Der Firmenbuchauszug bei Gericht kostet 19,00 Euro."},
        {"entity": "route", "key": "court", "field": "cost", "value": {"amount_minor": 1900, "currency": "EUR", "basis": "per_document"}, "source_url": PAGE_URL,
         "quote": "Der Firmenbuchauszug bei Gericht kostet 19,00 Euro."},
        {"entity": "route", "key": "verrechnung", "field": "actor", "value": "account_holder", "source_url": PAGE_URL, "quote": "über Verrechnungsstellen (Konto)"}],
    "dropped": {"not_verbatim": 0}, "instruction_like": []}}}


def run(c):
    return asyncio.run(c)


class Snapshot(Base):
    """A small, known snapshot: the real export + seeds, and a fixed Austrian read."""

    def setUp(self):
        super().setUp()
        self.dir = Path(tempfile.mkdtemp())
        for f in ("ad_export.json", "seeds.json"):
            shutil.copy(M.DATA / f, self.dir / f)
        (self.dir / "reads.json").write_text(json.dumps(READS))
        p = mock.patch.object(M, "DATA", self.dir)
        p.start()
        self.addCleanup(p.stop)

    def doc(self, code, kind):
        for d in self.ok("registry.documents", {"jurisdiction": code})["documents"]:
            if d["fields"]["kind"].get("value") == kind:
                return d
        raise AssertionError(kind)


# ── the vectors (spec/ext/vectors/registry-*.json) ────────────────────────────────────────────────────────────────────────

class Vectors(Base):
    def test_registry_plan(self):
        cases = json.loads((VEC / "registry-plan.json").read_text())["cases"]
        self.assertGreaterEqual(len(cases), 20)
        for c in cases:
            with self.subTest(c["name"]):
                out = P.rank(c["routes"], c["actor"])
                e = c["expect"]
                self.assertEqual([r["route_id"] for r in out["routes"]], e["order"])
                if "tiers" in e:
                    self.assertEqual([r["tier"] for r in out["routes"]], e["tiers"])
                by = {r["route_id"]: r for r in out["routes"]}
                for rid, a in (e.get("automation") or {}).items():
                    self.assertEqual(by[rid]["automation"], a)
                for rid, o in (e.get("obtainable") or {}).items():
                    self.assertEqual(by[rid]["obtainable_by_agapi"], o)
                for rid, req in (e.get("requires") or {}).items():
                    self.assertEqual(by[rid]["requires"], req)
                if "excluded" in e:
                    self.assertEqual([x["route_id"] for x in out["excluded"]], e["excluded"])
                if "overall" in e:
                    self.assertEqual(out["obtainable_by_agapi"], e["overall"])

    def test_registry_drift(self):
        for c in json.loads((VEC / "registry-drift.json").read_text())["cases"]:
            with self.subTest(c["name"]):
                out = V.drift(c["quote"], c["page_text"], c["failure_layer"])
                self.assertEqual({k: out[k] for k in c["expect"]}, c["expect"])

    def test_registry_claim_fingerprints(self):
        v = json.loads((VEC / "registry-claim.json").read_text())
        for c in v["cases"]:
            got = M.make_claim(**c["claim"])
            self.assertEqual((got["quote_sha256"], got["claim_sha256"], got["id"]), (c["expect"]["quote_sha256"], c["expect"]["claim_sha256"], c["expect"]["claim_id"]))

    def test_untrusted_text_is_never_a_claim(self):
        u = json.loads((VEC / "registry-claim.json").read_text())["untrusted"]
        title, text, links, _ = MG.parse(u["page_html"])
        g = RD.ground(u["draft"], [{"url": u["url"], "title": title, "text": text, "links": [x for x, _ in links]}])
        self.assertEqual(sorted([f["entity"], f["field"]] for f in g["facts"]), sorted(u["expect"]["kept"]))
        self.assertEqual(g["dropped"], u["expect"]["dropped"])                              # the HTML-comment price, the AI instruction, "soon"
        self.assertEqual(next(f["quote"] for f in g["facts"] if f["field"] == "authority"), u["expect"]["authority_text"])   # RTL override stripped
        self.assertNotIn("clean", json.dumps(g["facts"]))


# ── the export and the snapshot ───────────────────────────────────────────────────────────────────────────────────────

class Export(Base):
    def test_the_export_is_read_only_and_holds_the_certified_core(self):
        ex = json.loads((M.DATA / "ad_export.json").read_text())
        self.assertTrue(ex["export"]["read_only"])
        self.assertEqual(len(ex["cells"]), 20)                                               # the 20 live-hash record types
        self.assertEqual(sorted({c["jurisdiction"] for c in ex["cells"]}), sorted(
            "AT CY DE DK ES FI FR GLOBAL IE LT LV MT NL SE SI US-AL US-HI US-ID US-ND".split()))
        for c in ex["cells"]:
            self.assertRegex(c["certified_config_hash"], r"^[0-9a-f]{64}$")
            self.assertTrue(c["certification"]["passed"])
            self.assertFalse({"legal_basis_notes", "process_description", "notes"} & set(c))   # AD's internal prose is never copied

    def test_every_loaded_fact_is_a_cited_claim(self):
        snap = M.build(*M.files())
        self.assertEqual(len(snap["jurisdictions"]), 19)
        for c in snap["claims"].values():
            self.assertTrue(c["source_url"] and c["read_at"] and c["method"] in ("magellan_fetch", "magellan_robots", "ad_catalogue", "certification"))
            self.assertIn(c["confidence"], M.LADDER)
            if c["method"] == "magellan_fetch":
                self.assertTrue(c["source_url"].startswith("https://") or c["source_url"].startswith("http://"))
                self.assertGreaterEqual(len(c["quote"]), 6)
                self.assertTrue(c["untrusted"])
        has = {(c["entity"], c["entity_id"]) for c in snap["claims"].values()}
        for kind, table in (("register", "registers"), ("document", "documents"), ("route", "routes")):
            for i in snap[table]:
                self.assertIn((kind, i), has, f"{kind} {i} has no claim at all")
        reads = json.loads((M.DATA / "reads.json").read_text())["reads"] if (M.DATA / "reads.json").exists() else {}
        for code, r in reads.items():                                                        # every committed quote was found on its page
            for f in r["facts"]:
                self.assertIn(f["source_url"], [p["url"] for p in r["pages"]], code)


class Model(Snapshot):
    def test_no_claim_means_unknown_and_reloading_is_idempotent(self):
        g = self.ok("registry.get", {"jurisdiction": "AT"})
        fb = next(r for r in g["registers"] if r["name"] == "Firmenbuch")
        self.assertEqual(fb["fields"]["authority"], {"value": "unknown", "why": "no claim behind it"})
        self.assertEqual(fb["fields"]["name_local"]["quote"]["text"], "Das Firmenbuch ist ein öffentliches Verzeichnis.")
        self.assertEqual(fb["fields"]["name_local"]["method"], "magellan_fetch")
        n = self.store.one("select count(*) as n from registry_claims")["n"]
        M.ensure_loaded(Store(self.path))                                                    # another worker, the same snapshot
        self.assertEqual(self.store.one("select count(*) as n from registry_claims")["n"], n)

    def test_a_new_snapshot_supersedes_never_edits(self):
        self.ok("registry.countries", {})
        old = self.store.one("select * from registry_claims where field = 'cost' and value like '%489%'")
        r = json.loads(json.dumps(READS))
        r["reads"]["AT"]["read_at"] = "2026-11-10T06:00:00Z"
        (self.dir / "reads.json").write_text(json.dumps(r))
        self.ok("registry.countries", {})
        again = self.store.one("select * from registry_claims where id = ?", old["id"])
        self.assertEqual((again["value"], again["quote"], again["read_at"]), (old["value"], old["quote"], old["read_at"]))   # untouched…
        self.assertTrue(again["superseded_at"])                                                                         # …but superseded
        live = self.store.q("select * from registry_claims where field = 'cost' and value like '%489%' and superseded_at is null")
        self.assertEqual([x["read_at"] for x in live], ["2026-11-10T06:00:00Z"])


class Operations(Snapshot):
    def test_countries_is_the_wave_0_core(self):
        c = self.ok("registry.countries", {})
        self.assertEqual(len(c["jurisdictions"]), 19)
        at = next(j for j in c["jurisdictions"] if j["code"] == "AT")
        self.assertEqual((at["registers"], at["documents"], at["routes"]), (1, 3, 4))       # the Firmenbuch: 2 read + AD's rail
        self.assertEqual(self.ok("registry.countries", {"has": ["sanctions"]})["jurisdictions"][0]["code"], "GLOBAL")
        self.assertEqual(self.ok("registry.countries", {"min_confidence": "read_at_source"})["jurisdictions"][0]["code"], "AT")

    def test_unknown_jurisdiction_and_document_say_so(self):
        r, b = self.call("registry.get", {"jurisdiction": "AD"}, expect="not_found")
        self.assertEqual(b["error"]["details"]["registry_code"], "jurisdiction_unknown")
        r, b = self.call("registry.obtain_plan", {"jurisdiction": "AT", "document_id": "rdt_" + "0" * 26}, expect="not_found")
        self.assertEqual(b["error"]["details"]["registry_code"], "document_unknown")
        self.call("registry.get", {"jurisdiction": "at; drop table"}, expect="invalid_input")

    def test_documents_say_who_may_obtain_as_the_source_states_it(self):
        d = self.doc("AT", "extract_current")
        self.assertEqual(d["fields"]["who_may_obtain"]["value"], "anyone")
        self.assertEqual(d["fields"]["who_may_obtain"]["quote"]["text"], "jedermann ist zur Einzelabfrage befugt")
        self.assertEqual(d["fields"]["identifier_needed"]["value"], "unknown")

    def test_the_austrian_plan_is_honest_about_robots_and_accounts(self):
        p = self.ok("registry.obtain_plan", {"jurisdiction": "AT", "document_id": self.doc("AT", "extract_current")["document_id"]})
        self.assertEqual(p["obtain"].split(" ")[0], "off")                                   # plans only
        online = next(r for r in p["routes"] if r["fields"]["channel"].get("value") == "paid_web")
        self.assertEqual((online["automation"], online["obtainable_by_agapi"]), ("human_only", "with_human"))   # JustizOnline's robots: unreadable
        self.assertIn("payment", online["requires"])
        acct = next(r for r in p["routes"] if r["fields"].get("actor", {}).get("value") == "account_holder")
        self.assertIn("account", acct["requires"])
        rail = self.ok("registry.obtain_plan", {"jurisdiction": "AT", "need": {"kind": "search_result"}})["routes"][0]
        self.assertEqual(rail["fields"]["certified_rail"]["method"], "certification")
        self.assertEqual(rail["automation"], "human_only")          # the certified rail's own host has an unreadable robots.txt: said, not hidden
        self.assertTrue(any("robots.txt" in n for n in rail["notes"]))

    def test_a_certified_core_country_without_robots_trouble_is_instant(self):
        p = self.ok("registry.obtain_plan", {"jurisdiction": "LV", "need": {"kind": "search_result"}})
        self.assertEqual((p["routes"][0]["tier"], p["routes"][0]["obtainable_by_agapi"], p["obtainable_by_agapi"]), (1, "yes", "yes"))
        self.assertEqual(p["routes"][0]["fields"]["robots_verdict"]["value"], "not_applicable")   # an operator download

    def test_withdrawn_rails_and_never_fetch_hosts(self):
        dk = self.ok("registry.obtain_plan", {"jurisdiction": "DK", "need": {"kind": "search_result", "subject": "company"}})["routes"][0]
        self.assertEqual(dk["tier"], 3)
        self.assertIn("its certified rail is withdrawn in AD's catalogue", dk["notes"])

    def test_registry_obtain_stays_off(self):
        self.assertNotIn("registry.obtain", operations())
        self.call("registry.obtain", {}, expect="unknown_operation")


class Verify(Snapshot):
    def claim(self):
        self.ok("registry.countries", {})
        return self.store.one("select * from registry_claims where method = 'magellan_fetch' and quote = ? and field = 'cost'", QUOTE)

    def fake(self, body="Gebühren\nAktueller   Firmenbuchauszug EUR 4,89", robots=(200, "text/plain", "User-agent: *\nAllow: /\n"), exc=None):
        calls = []

        async def fetch(url):
            calls.append(url)
            if url.endswith("/robots.txt"):
                return robots[0], robots[1], robots[2], url
            if exc:
                raise exc
            return 200, "text/html", f"<html><body><p>{body}</p></body></html>", url
        return calls, mock.patch.object(MG, "FETCH", fetch)

    def test_fresh_writes_a_new_claim_and_supersedes_the_old(self):
        c = self.claim()
        calls, p = self.fake()
        with p:
            v = self.ok("registry.verify", {"claim_id": c["id"]})
        self.assertEqual((v["state"], v["quote_still_present"]), ("fresh", True))            # whitespace changed: still fresh
        self.assertEqual(calls, ["https://www.justiz.gv.at/robots.txt", PAGE_URL])              # robots FIRST
        old = self.store.one("select * from registry_claims where id = ?", c["id"])
        self.assertEqual(old["superseded_by"], v["checked"][0]["new_claim_id"])
        self.assertEqual(old["quote"], QUOTE)                                                   # never edited
        self.call("registry.verify", {"claim_id": c["id"]}, expect="not_found")               # verify the newer one

    def test_drifted_and_broken(self):
        c = self.claim()
        _, p = self.fake(body="Aktueller Firmenbuchauszug EUR 4,99")
        with p:
            v = self.ok("registry.verify", {"claim_id": c["id"]})
        self.assertEqual(v["state"], "drifted")
        self.assertEqual(self.store.one("select drift_state from registry_routes where id = ?", c["entity_id"])["drift_state"], "drifted")
        _, p = self.fake(robots=(200, "text/html", "<html><body>Login</body></html>"))
        with p:
            v = self.ok("registry.verify", {"claim_id": c["id"]})
        self.assertEqual((v["state"], v["failure_layer"]), ("broken", "robots"))           # an HTML robots.txt = unreadable = not allowed
        import ssl
        _, p = self.fake(exc=ssl.SSLCertVerificationError("certificate verify failed"))
        with p:
            v = self.ok("registry.verify", {"claim_id": c["id"]})
        self.assertEqual((v["state"], v["failure_layer"]), ("broken", "tls"))

    def test_transport_is_source_unreachable_never_drifted(self):
        c = self.claim()
        _, p = self.fake(exc=ConnectionResetError())
        with p:
            r, b = self.call("registry.verify", {"claim_id": c["id"]}, expect="upstream_unreachable")
        self.assertEqual(b["error"]["details"]["registry_code"], "source_unreachable")
        self.assertTrue(b["error"]["retryable"])
        self.assertIsNone(self.store.one("select superseded_at from registry_claims where id = ?", c["id"])["superseded_at"])

    def test_a_catalogue_claim_is_not_a_page_and_the_host_budget_holds(self):
        self.ok("registry.countries", {})
        cert = self.store.one("select id from registry_claims where method = 'certification' limit 1")
        self.call("registry.verify", {"claim_id": cert["id"]}, expect="invalid_input")
        c = self.claim()
        for _ in range(O.VERIFY_PER_HOST_HOUR):
            self.store.x("insert into registry_checks (id, claim_id, host, state, failure_layer, quote_still_present, at) values (?, ?, ?, ?, ?, ?, ?)",
                         R.new_id("chk"), c["id"], "www.justiz.gv.at", "fresh", None, 1, M.ts())
        calls, p = self.fake()
        with p:
            self.call("registry.verify", {"claim_id": c["id"]}, expect="rate_limited")
        self.assertEqual(calls, [])                                                             # refused before any request


# ── the gate and the reader ───────────────────────────────────────────────────────────────────────────────────────────

class Gate(Base):
    def test_never_fetch_hosts_are_refused_before_any_request(self):
        async def fetch(url):
            raise AssertionError(f"requested {url}")
        with mock.patch.object(MG, "FETCH", fetch):
            for u in ("https://arc-sos.state.al.us/cgi/corpname.mbr/input", "https://data.gov.gr/x", "https://opencorporates.com/companies"):
                self.assertEqual(run(gate.robots_verdict(u))["verdict"], "never_fetch")
                with self.assertRaises(gate.Broken):
                    run(gate.read_page(u))
            got = run(RD.read_pages(["https://arc-sos.state.al.us/cgi/corpname.mbr/input"]))
        self.assertEqual(got["pages"], [])
        self.assertIn("never fetched", got["unread"][0]["why"])

    def test_robots_is_strict_and_names_claude_too(self):
        self.assertEqual(gate.classify_robots(200, "text/html", "<!doctype html><html>login</html>")[0], "unreadable")
        self.assertEqual(gate.classify_robots(503, "", "")[0], "unreadable")
        self.assertEqual(gate.classify_robots(404, "", "")[0], "allowed")
        _, rp, _ = gate.classify_robots(200, "text/plain", "User-agent: ClaudeBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
        self.assertFalse(gate.may_fetch(rp, "https://x.example/fees"))

    def test_the_reader_reads_seeds_robots_first_and_skips_challenge_pages(self):
        pages = {"https://reg.example/fees": "<html><head><title>Fees</title></head><body><p>" + ("An extract costs EUR 4.89. " * 30) +
                 "</p><a href='/extract-prices'>Extract prices</a><a href='/search?q=x'>search</a></body></html>",
                 "https://reg.example/extract-prices": "<html><body><p>Checking your browser</p></body></html>"}
        seen = []

        async def fetch(url):
            seen.append(url)
            if url.endswith("/robots.txt"):
                return 200, "text/plain", "User-agent: *\nDisallow: /private\n", url
            return 200, "text/html", pages.get(url, "<html></html>"), url
        with mock.patch.object(MG, "FETCH", fetch), mock.patch.object(MG, "GAP_S", 0):
            got = run(RD.read_pages(["https://reg.example/fees", "https://reg.example/private/x"]))
        self.assertEqual([p["url"] for p in got["pages"]], ["https://reg.example/fees"])
        self.assertEqual(seen[0], "https://reg.example/robots.txt")
        self.assertNotIn("https://reg.example/private/x", seen)                                 # disallowed: never requested
        self.assertNotIn("https://reg.example/search?q=x", seen)                                # a site search is not a source
        self.assertEqual(got["unread"][0]["robots"], "disallowed")

    def test_values_are_the_models_vocabulary_or_dropped(self):
        links = {"https://reg.example/order"}
        self.assertEqual(RD.normal_value("route", "cost", "4,89 EUR per_document", links), {"amount_minor": 489, "currency": "EUR", "basis": "per_document"})
        self.assertEqual(RD.normal_value("route", "cost", "free", links)["basis"], "free")
        self.assertIsNone(RD.normal_value("route", "cost", "about five euros", links))
        self.assertIsNone(RD.normal_value("route", "entry_url", "https://evil.example/", links))   # a URL the pages never showed
        self.assertEqual(RD.normal_value("route", "entry_url", "https://reg.example/order", links), "https://reg.example/order")
        self.assertIsNone(RD.normal_value("route", "automation", "api", links))                    # the reader never decides automation
        self.assertIsNone(RD.normal_value("document", "who_may_obtain", "everyone basically", links))

    def test_a_jurisdiction_read_with_a_fake_model(self):
        async def fetch(url):
            if url.endswith("/robots.txt"):
                return 404, "text/plain", "", url
            return 200, "text/html", "<html><body><p>The Register of Companies is kept by the Registrar.</p><p>A certificate costs 20 EUR.</p></body></html>", url

        async def model(code, pages):
            u = pages[0]["url"]
            return {"registers": [{"key": "roc"}], "documents": [{"key": "cert", "register_key": "roc"}], "routes": [{"key": "post", "document_key": "cert"}],
                    "facts": [{"entity": "register", "key": "roc", "field": "name_en", "value": "Register of Companies", "source_url": u,
                               "quote": "The Register of Companies is kept by the Registrar."},
                              {"entity": "document", "key": "cert", "field": "kind", "value": "certificate", "source_url": u, "quote": "A certificate costs 20 EUR."},
                              {"entity": "route", "key": "post", "field": "cost", "value": "20 EUR per_document", "source_url": u, "quote": "A certificate costs 20 EUR."},
                              {"entity": "route", "key": "post", "field": "turnaround", "value": "days:3", "source_url": u, "quote": "It arrives in three days."}],
                    "instruction_like": [], "_usage": {"input_tokens": 1000, "output_tokens": 200}}
        with mock.patch.object(MG, "FETCH", fetch), mock.patch.object(MG, "GAP_S", 0), mock.patch.object(RD, "EXTRACT", model):
            out = run(RD.read_jurisdiction("XX", ["https://roc.example/"], ["https://arc-sos.state.al.us/x"]))
        self.assertEqual(len(out["facts"]), 3)
        self.assertEqual(out["dropped"]["not_verbatim"], 1)                                     # "three days" isn't on the page: never a claim
        self.assertEqual(out["robots"]["https://arc-sos.state.al.us/x"]["verdict"], "never_fetch")
        self.assertGreater(out["reader"]["usd"], 0)


class Page(Snapshot):
    def test_the_demo_page_and_its_reads(self):
        r = self.client.get("/registry")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Registry survey", r.text)
        c = self.client.get("/registry/api/countries").json()
        self.assertEqual(len(c["result"]["jurisdictions"]), 19)
        at = self.client.get("/registry/api/country/AT").json()["result"]
        self.assertTrue(at["registers"] and at["documents"])
        d = next(x for x in at["documents"] if x["fields"]["kind"].get("value") == "extract_current")
        p = self.client.get(f"/registry/api/plan/AT/{d['document_id']}").json()["result"]
        self.assertTrue(p["routes"] and p["obtain"].startswith("off"))
        self.assertEqual(self.client.get("/registry/api/country/ZZ").status_code, 404)
