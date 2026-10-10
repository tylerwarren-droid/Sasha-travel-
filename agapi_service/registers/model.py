"""The registry model (EU 214 model.md): Country → Register → Document type → Access route, and registry_claims — one row per fact.

  ids        rgr_ (register) · rdt_ (document type) · rrt_ (route) · rcl_ (claim); deterministic from what they name, so a reload is idempotent
  claims     NEVER edited: a re-read writes a new claim and the old one is superseded (superseded_by / superseded_at). An entity's field
             is its latest non-superseded claim; a field with no claim is "unknown".
  methods    magellan_fetch (an official page, quoted word for word) · magellan_robots (a robots.txt verdict) · ad_catalogue (AD's
             catalogue row, read-only export) · certification (AD's passed certification record) · magellan_verify (a re-read by verify)
  ladder     frontier → desk → read_at_source → proven
The snapshot (data/ad_export.json + seeds.json + reads.json) is loaded into the store once per change of its sha256."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .. import rules as R
from ..store import dumps, loads, ts

DATA = Path(__file__).parent / "data"
LADDER = ("frontier", "desk", "read_at_source", "proven")
KIND_BY_RECORD_TYPE = {"Company Registry/Filings": ("company", "company", "search_result"),
                       "Director & Officer Search": ("company", "person", "search_result"),
                       "Insolvency/Bankruptcy": ("insolvency", "company", "search_result"),
                       "Sanctions & Watchlist Screening": ("sanctions", "person", "search_result")}
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def rid(prefix: str, key: str) -> str:
    n = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:17], "big") >> 6
    return f"{prefix}_" + "".join(_CROCKFORD[(n >> (5 * i)) & 31] for i in reversed(range(26)))


def quote_sha256(quote: str) -> str:
    return "sha256:" + hashlib.sha256((quote or "").encode("utf-8")).hexdigest()


def claim_core(c: dict) -> dict:
    return {k: c[k] for k in ("entity", "entity_id", "field", "value", "source_url", "read_at", "quote", "method", "confidence")}


def make_claim(entity: str, entity_id: str, field: str, value: Any, source_url: str, read_at: str, quote: str, method: str, confidence: str,
               note: str = "") -> dict:
    c = {"entity": entity, "entity_id": entity_id, "field": field, "value": value, "source_url": source_url, "read_at": read_at,
         "quote": quote or "", "method": method, "confidence": confidence}
    c["quote_sha256"] = quote_sha256(c["quote"])
    c["claim_sha256"] = R.sha256(claim_core(c))
    c["id"] = rid("rcl", c["claim_sha256"])
    c["untrusted"] = method in ("magellan_fetch", "magellan_verify")       # fetched text: shown as data, never as instructions
    c["note"] = note
    return c


# ── the snapshot → entities + claims (pure) ───────────────────────────────────────────────────────────────────────────────

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]


def files() -> Tuple[dict, dict, dict]:
    ex = json.loads((DATA / "ad_export.json").read_text())
    se = json.loads((DATA / "seeds.json").read_text())
    rp = DATA / "reads.json"
    rd = json.loads(rp.read_text()) if rp.exists() else {"reads": {}}
    return ex, se, rd


def snapshot_sha() -> str:
    h = hashlib.sha256()
    for name in ("ad_export.json", "seeds.json", "reads.json"):
        p = DATA / name
        h.update(name.encode() + b"\0" + (p.read_bytes() if p.exists() else b"") + b"\0")
    return h.hexdigest()


def build(ex: dict, se: dict, rd: dict) -> Dict[str, Any]:
    """→ {jurisdictions, registers, documents, routes, claims}: every entity with its structural data; every value a claim."""
    exported = ex["export"]["exported_at"] + "T00:00:00Z"
    juris: Dict[str, dict] = {}
    regs: Dict[str, dict] = {}
    docs: Dict[str, dict] = {}
    routes: Dict[str, dict] = {}
    claims: List[dict] = []
    cells_by = {}
    for c in ex["cells"]:
        cells_by.setdefault(c["jurisdiction"], []).append(c)
    reads = rd.get("reads") or {}
    for code in sorted(set(cells_by) | set(se["jurisdictions"])):
        cells = cells_by.get(code, [])
        r = reads.get(code) or {}
        juris[code] = {"code": code, "name": cells[0]["jurisdiction_name"] if cells else code, "region": cells[0]["region"] if cells else "",
                       "wave": 0, "seed_source": (se["jurisdictions"].get(code) or {}).get("seed_source", ""),
                       "read": {"read_at": r.get("read_at"), "pages": r.get("pages") or [], "unread": r.get("unread") or [],
                                "dropped": r.get("dropped") or {}, "instruction_like": len(r.get("instruction_like") or []),
                                "why": r.get("why"), "reader": r.get("reader")} if r else None}
        at = r.get("read_at") or exported
        robots = r.get("robots") or {}
        reg_ids = {k: rid("rgr", f"{code}/{k}") for k in r.get("registers") or []}
        doc_ids = {k: rid("rdt", f"{code}/{rk}/{k}") for k, rk in (r.get("documents") or {}).items()}
        route_ids = {k: rid("rrt", f"{code}/{r['routes'][k]}/{k}") for k in r.get("routes") or {}}
        for k, i in reg_ids.items():
            regs[i] = {"id": i, "jurisdiction": code, "key": k, "origin": "magellan"}
        for k, rk in (r.get("documents") or {}).items():
            docs[doc_ids[k]] = {"id": doc_ids[k], "register_id": reg_ids[rk], "jurisdiction": code, "key": k, "origin": "magellan", "fulfils_cells": []}
        for k, dk in (r.get("routes") or {}).items():
            routes[route_ids[k]] = {"id": route_ids[k], "document_id": doc_ids[dk], "jurisdiction": code, "key": k, "origin": "magellan",
                                    "rail_config_key": None, "route_policy": None}
        ids = {"register": reg_ids, "document": doc_ids, "route": route_ids}
        for f in r.get("facts") or []:
            eid = ids[f["entity"]].get(f["key"])
            if eid:
                claims.append(make_claim(f["entity"], eid, f["field"], f["value"], f["source_url"], at, f["quote"], "magellan_fetch", "read_at_source"))
                if f["field"] == "entry_url" and f["value"] in robots:
                    v = robots[f["value"]]
                    claims.append(make_claim("route", eid, "robots_verdict", v["verdict"], v.get("robots_url") or "", at, v.get("quote") or "",
                                             "magellan_robots", "read_at_source", note=v.get("why") or ""))
        # the certified rails, from AD's catalogue (read-only export) and its certification records
        for c in cells:
            kind, subject, dkind = KIND_BY_RECORD_TYPE.get(c["record_type"], ("other", "company", "search_result"))
            cat_src, cat_at = f"ad://jurisdiction_record_types/{c['record_type_id']}", exported
            reg = next((i for i in reg_ids.values() if any(x["entity_id"] == i and x["field"] == "kind" and x["value"] == kind and x["method"] == "magellan_fetch"
                                                           for x in claims)), None)
            if not reg:
                reg = rid("rgr", f"{code}/ad-{kind}")
                if reg not in regs:
                    regs[reg] = {"id": reg, "jurisdiction": code, "key": f"ad-{kind}", "origin": "ad_catalogue"}
                    claims.append(make_claim("register", reg, "kind", kind, cat_src, cat_at, c["record_type"], "ad_catalogue", "desk"))
                    claims.append(make_claim("register", reg, "status", "exists", f"ad://jurisdiction_certifications/{c['certification']['id']}",
                                             c["certification"]["executed_at"], "", "certification", "proven",
                                             note="AD's certified rail read this register live: it exists"))
            d = rid("rdt", f"{code}/{reg}/ad-rail-{_slug(c['record_type'])}")
            docs[d] = {"id": d, "register_id": reg, "jurisdiction": code, "key": f"ad-rail-{_slug(c['record_type'])}", "origin": "ad_catalogue",
                       "fulfils_cells": [c["record_type_id"]]}
            claims.append(make_claim("document", d, "name_en", f"{c['record_type']} (AD's certified rail)", cat_src, cat_at, c["record_type"], "ad_catalogue", "desk"))
            claims.append(make_claim("document", d, "kind", dkind, cat_src, cat_at, c["record_type"], "ad_catalogue", "desk"))
            claims.append(make_claim("document", d, "subject", subject, cat_src, cat_at, c["record_type"], "ad_catalogue", "desk"))
            ro = rid("rrt", f"{code}/{d}/certified-rail")
            routes[ro] = {"id": ro, "document_id": d, "jurisdiction": code, "key": "certified-rail", "origin": "ad_catalogue",
                          "rail_config_key": code if c["record_type"] != "Director & Officer Search" else f"{code}-DO", "route_policy": None,
                          "acquisition_mode": c["acquisition_mode"]}
            channel = "bulk_download" if c["acquisition_mode"] == "operator_download" else "api"
            claims.append(make_claim("route", ro, "channel", channel, cat_src, cat_at, c["acquisition_mode"] or "api", "ad_catalogue", "desk"))
            claims.append(make_claim("route", ro, "actor", "anyone", cat_src, cat_at, c["consent_class"], "ad_catalogue", "desk",
                                     note="consent_class open: a public register, no subject consent"))
            claims.append(make_claim("route", ro, "cost", {"amount_minor": 0, "currency": None, "basis": "free"}, cat_src, cat_at, "base_cost_usd 0",
                                     "ad_catalogue", "desk", note="the register's own fee for this rail, as AD's catalogue records it"))
            claims.append(make_claim("route", ro, "turnaround", "instant", cat_src, cat_at, "access_method api", "ad_catalogue", "desk"))
            if c["api_endpoint"].startswith("http"):
                claims.append(make_claim("route", ro, "entry_url", c["api_endpoint"], cat_src, cat_at, c["api_endpoint"], "ad_catalogue", "desk"))
            cert = c["certification"]
            claims.append(make_claim("route", ro, "certified_rail", {"config_hash": c["certified_config_hash"], "suite": cert["suite_version"],
                                                                     "deployment_sha": cert["deployment_sha"], "executed_at": cert["executed_at"]},
                                     f"ad://jurisdiction_certifications/{cert['id']}", cert["executed_at"],
                                     f"suite {cert['suite_version']} passed · config {c['certified_config_hash'][:16]}", "certification", "proven"))
            claims.append(make_claim("route", ro, "catalogue_availability", c["availability"], cat_src, cat_at, c["availability"], "ad_catalogue", "desk"))
            if c["acquisition_mode"] == "operator_download":
                claims.append(make_claim("route", ro, "robots_verdict", "not_applicable", cat_src, cat_at, "operator_download", "ad_catalogue", "desk",
                                         note="a person downloads the register's file; queries then run on AD's own copy"))
            elif c["api_endpoint"] in robots:
                v = robots[c["api_endpoint"]]
                claims.append(make_claim("route", ro, "robots_verdict", v["verdict"], v.get("robots_url") or "", at, v.get("quote") or "",
                                         "magellan_robots", "read_at_source", note=v.get("why") or ""))
    return {"jurisdictions": juris, "registers": regs, "documents": docs, "routes": routes, "claims": {c["id"]: c for c in claims}}


# ── the store ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

TABLES = (
    "create table if not exists registry_jurisdictions (code text primary key, data text not null, updated_at text not null)",
    "create table if not exists registry_registers (id text primary key, jurisdiction text not null, data text not null, retired integer not null default 0, updated_at text not null)",
    "create table if not exists registry_documents (id text primary key, register_id text not null, jurisdiction text not null, data text not null, retired integer not null default 0, updated_at text not null)",
    "create table if not exists registry_routes (id text primary key, document_id text not null, jurisdiction text not null, data text not null, "
    "drift_state text not null default 'fresh', last_verified_at text, retired integer not null default 0, updated_at text not null)",
    "create table if not exists registry_claims (id text primary key, entity text not null, entity_id text not null, jurisdiction text not null, "
    "field text not null, value text not null, source_url text not null, read_at text not null, quote text not null, quote_sha256 text not null, "
    "claim_sha256 text not null, method text not null, confidence text not null, untrusted integer not null, note text not null, "
    "snapshot text, superseded_by text, superseded_at text, created_at text not null)",
    "create table if not exists registry_checks (id text primary key, claim_id text not null, host text not null, state text not null, "
    "failure_layer text, quote_still_present integer not null, at text not null)",
    "create table if not exists registry_loads (sha text primary key, at text not null, counts text not null)",
)


def ensure(store) -> None:
    for t in TABLES:
        store.x(t)


def ensure_loaded(store) -> str:
    """Load the snapshot once per sha (idempotent; safe if two workers race: every write is insert-or-ignore or a plain update)."""
    sha = snapshot_sha()
    if getattr(store, "_registry_sha", None) == sha:
        return sha
    ensure(store)
    if not store.one("select sha from registry_loads where sha = ?", sha):
        snap = build(*files())
        now = ts()
        for code, j in snap["jurisdictions"].items():
            if store.x("update registry_jurisdictions set data = ?, updated_at = ? where code = ?", dumps(j), now, code) == 0:
                store.x("insert or ignore into registry_jurisdictions (code, data, updated_at) values (?, ?, ?)", code, dumps(j), now)
        for table, parent, items in (("registry_registers", None, snap["registers"]), ("registry_documents", "register_id", snap["documents"]),
                                     ("registry_routes", "document_id", snap["routes"])):
            live = set(items)
            for i, e in items.items():
                if store.x(f"update {table} set data = ?, retired = 0, updated_at = ? where id = ?", dumps(e), now, i) == 0:
                    if parent:
                        store.x(f"insert or ignore into {table} (id, {parent}, jurisdiction, data, updated_at) values (?, ?, ?, ?, ?)",
                                i, e[parent], e["jurisdiction"], dumps(e), now)
                    else:
                        store.x(f"insert or ignore into {table} (id, jurisdiction, data, updated_at) values (?, ?, ?, ?)", i, e["jurisdiction"], dumps(e), now)
            for row in store.q(f"select id from {table} where retired = 0"):
                if row["id"] not in live:
                    store.x(f"update {table} set retired = 1, updated_at = ? where id = ?", now, row["id"])
        for c in snap["claims"].values():
            store.x("insert or ignore into registry_claims (id, entity, entity_id, jurisdiction, field, value, source_url, read_at, quote, quote_sha256, "
                    "claim_sha256, method, confidence, untrusted, note, snapshot, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    c["id"], c["entity"], c["entity_id"], _juris_of(snap, c), c["field"], dumps(c["value"]), c["source_url"], c["read_at"], c["quote"],
                    c["quote_sha256"], c["claim_sha256"], c["method"], c["confidence"], 1 if c["untrusted"] else 0, c["note"], sha[:16], now)
        for row in store.q("select id from registry_claims where snapshot is not null and snapshot != ? and superseded_at is null", sha[:16]):
            if row["id"] not in snap["claims"]:
                store.x("update registry_claims set superseded_by = ?, superseded_at = ? where id = ?", f"snapshot:{sha[:16]}", now, row["id"])
        counts = {k: len(snap[k]) for k in ("jurisdictions", "registers", "documents", "routes", "claims")}
        store.x("insert or ignore into registry_loads (sha, at, counts) values (?, ?, ?)", sha, now, dumps(counts))
    store._registry_sha = sha
    return sha


def _juris_of(snap: dict, c: dict) -> str:
    return snap[{"register": "registers", "document": "documents", "route": "routes"}[c["entity"]]][c["entity_id"]]["jurisdiction"]


def claim_out(row: dict) -> dict:
    return {"claim_id": row["id"], "value": loads(row["value"]), "source_url": row["source_url"], "read_at": row["read_at"],
            "quote": R.wrap(row["quote"], "registry_source", row["read_at"][:19] + ("Z" if not row["read_at"].endswith("Z") else ""), cap=500)
            if row["untrusted"] else {"text": row["quote"]},
            "quote_sha256": row["quote_sha256"], "method": row["method"], "confidence": row["confidence"],
            **({"note": row["note"]} if row["note"] else {})}


def fields_of(store, entity: str, entity_id: str, wanted: Tuple[str, ...]) -> Dict[str, dict]:
    """Each wanted field → {value, claim…} from its latest non-superseded claim, or {"value": "unknown"} with no claim behind it."""
    rows = store.q("select * from registry_claims where entity = ? and entity_id = ? and superseded_at is null", entity, entity_id)
    rank = {m: i for i, m in enumerate(LADDER)}
    best: Dict[str, dict] = {}
    for r in rows:
        k = (r["read_at"], rank.get(r["confidence"], 0), r["id"])
        if r["field"] not in best or k > best[r["field"]]["_k"]:
            best[r["field"]] = {**r, "_k": k}
    out = {}
    for f in wanted:
        out[f] = claim_out(best[f]) if f in best else {"value": "unknown", "why": "no claim behind it"}
    for f, r in best.items():
        if f not in out:
            out[f] = claim_out(r)
    return out


def value(fields: Dict[str, dict], f: str) -> Any:
    v = (fields.get(f) or {}).get("value", "unknown")
    return None if v == "unknown" else v
