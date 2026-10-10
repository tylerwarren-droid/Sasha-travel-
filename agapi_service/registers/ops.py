"""registry.countries / get / documents / obtain_plan / verify — Kanoe extensions on EU 214's design (EU formalizes them in 1.3).
Every value carries its claim (source_url, read_at, quote, method, confidence) or is "unknown". registry.obtain is OFF: plans only.

EU 214's registry error codes ride on EU's existing codes until 1.3 adds them: details.registry_code says which
(jurisdiction_unknown / document_unknown → not_found · source_unreachable → upstream_unreachable)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from ..registry import AgapiError
from ..store import dumps, later, loads, ts
from . import gate, model as M, plan as P, verify as V

REGISTER_FIELDS = ("name_local", "name_en", "authority", "kind", "official_url", "governing_law", "status")
DOCUMENT_FIELDS = ("name_local", "name_en", "kind", "subject", "identifier_needed", "who_may_obtain", "certified_form_available")
ROUTE_FIELDS = ("channel", "actor", "cost", "turnaround", "entry_url", "robots_verdict")
OBTAIN = "off — registry.obtain isn't switched on: these are plans only. Nothing is bought, no account is used, no CAPTCHA is solved."
VERIFY_PER_HOST_HOUR = 20
REVERIFY_DAYS = 30


def _store(ctx):
    M.ensure_loaded(ctx.store)
    return ctx.store


def _jur(store, code: str) -> dict:
    row = store.one("select data from registry_jurisdictions where code = ?", (code or "").strip().upper())
    if not row:
        raise AgapiError("not_found", f"{code} isn't in the registry yet (wave 0 is the certified core).",
                         {"registry_code": "jurisdiction_unknown", "jurisdiction": code})
    return loads(row["data"])


def _name(f: Dict[str, dict]) -> str:
    return M.value(f, "name_en") or M.value(f, "name_local") or "unknown"


def route_input(store, route: dict, doc_fields: Dict[str, dict], fields: Dict[str, dict]) -> dict:
    """The planner's view of one route — every value from a claim, or None (unknown)."""
    data = loads(route["data"])
    cost = M.value(fields, "cost")
    rail = M.value(fields, "certified_rail")
    channel = M.value(fields, "channel")
    automation = ("api" if channel in ("api", "bulk_download") else "web_form" if channel in ("free_web", "paid_web") else
                  "human_only" if channel else "unknown")
    reads = [c.get("read_at") for c in fields.values() if c.get("read_at")]
    return {"route_id": route["id"], "channel": channel, "actor": M.value(fields, "actor") or "anyone", "automation": automation,
            "certified_rail": bool(rail), "rail_withdrawn": M.value(fields, "catalogue_availability") == "withdrawn",
            "policy_enabled": bool(data.get("route_policy")), "robots_verdict": M.value(fields, "robots_verdict") or "unknown",
            "cost_minor": cost["amount_minor"] if isinstance(cost, dict) else None, "turnaround": M.value(fields, "turnaround"),
            "freshest_read_at": max(reads) if reads else "", "who_may_obtain": M.value(doc_fields, "who_may_obtain"),
            "requires": ["api_key"] if data.get("acquisition_mode") == "allowlisted_machine" else []}


def _routes_of(store, doc_id: str) -> List[dict]:
    return store.q("select * from registry_routes where document_id = ? and retired = 0 order by id", doc_id)


def _docs_of(store, reg_id: str) -> List[dict]:
    return store.q("select * from registry_documents where register_id = ? and retired = 0 order by id", reg_id)


def _route_view(store, route: dict, doc_fields: Dict[str, dict], actor: str = "person") -> Dict[str, Any]:
    f = M.fields_of(store, "route", route["id"], ROUTE_FIELDS)
    inp = route_input(store, route, doc_fields, f)
    ranked = P.rank([inp], actor)["routes"]
    data = loads(route["data"])
    return {"route_id": route["id"], "fields": f, "automation": ranked[0]["automation"] if ranked else "human_only",
            "drift_state": route["drift_state"], "last_verified_at": route["last_verified_at"],
            **({"rail_config_key": data["rail_config_key"]} if data.get("rail_config_key") else {}), "_inp": inp}


async def countries(ctx, inp: dict):
    store = _store(ctx)
    want = set(inp.get("has") or [])
    region = (inp.get("region") or "").lower()
    floor = M.LADDER.index(inp["min_confidence"]) if inp.get("min_confidence") else 0
    out = []
    for row in store.q("select data from registry_jurisdictions order by code"):
        j = loads(row["data"])
        if region and region not in (j.get("region") or "").lower():
            continue
        regs = store.q("select * from registry_registers where jurisdiction = ? and retired = 0", j["code"])
        kinds = {M.value(M.fields_of(store, "register", r["id"], ("kind",)), "kind") for r in regs}
        if want and not want <= kinds:
            continue
        mix = {"api": 0, "web_form": 0, "human_only": 0, "unknown": 0}
        n_docs = n_routes = 0
        reads = [c["read_at"] for c in store.q("select read_at, confidence from registry_claims where jurisdiction = ? and superseded_at is null", j["code"])
                 if M.LADDER.index(c["confidence"]) >= floor]
        if floor and not reads:
            continue
        for r in regs:
            for d in _docs_of(store, r["id"]):
                n_docs += 1
                df = M.fields_of(store, "document", d["id"], ("who_may_obtain",))
                for ro in _routes_of(store, d["id"]):
                    n_routes += 1
                    mix[_route_view(store, ro, df)["automation"]] += 1
        out.append({"code": j["code"], "name": j["name"], "region": j["region"], "wave": j["wave"], "registers": len(regs), "documents": n_docs,
                    "routes": n_routes, "automation_mix": mix, "kinds": sorted(k for k in kinds if k),
                    "as_of": max(reads)[:10] if reads else None, "oldest_read_at": min(reads)[:10] if reads else None})
    return {"jurisdictions": out, "note": "Every count rests on cited claims; a field with no claim is 'unknown'. Coverage is wave 0, the certified core."}, 200, None


async def get(ctx, inp: dict):
    store = _store(ctx)
    j = _jur(store, inp["jurisdiction"])
    regs = []
    for r in store.q("select * from registry_registers where jurisdiction = ? and retired = 0 order by id", j["code"]):
        f = M.fields_of(store, "register", r["id"], REGISTER_FIELDS)
        conf = max((M.LADDER.index(c["confidence"]) for c in f.values() if c.get("confidence")), default=0)
        regs.append({"register_id": r["id"], "name": _name(f), "fields": f, "confidence": M.LADDER[conf], "documents": len(_docs_of(store, r["id"]))})
    read = j.get("read") or {}
    return {"jurisdiction": {"code": j["code"], "name": j["name"], "region": j["region"], "wave": j["wave"], "seed_source": j.get("seed_source", "")},
            "registers": regs, "sources": {"read_at": read.get("read_at"), "pages": read.get("pages") or [], "unread": read.get("unread") or [],
                                           **({"why": read["why"]} if read.get("why") else {})}}, 200, None


async def documents(ctx, inp: dict):
    store = _store(ctx)
    j = _jur(store, inp["jurisdiction"])
    out = []
    for r in store.q("select * from registry_registers where jurisdiction = ? and retired = 0 order by id", j["code"]):
        rf = M.fields_of(store, "register", r["id"], ("name_local", "name_en", "kind"))
        for d in _docs_of(store, r["id"]):
            df = M.fields_of(store, "document", d["id"], DOCUMENT_FIELDS)
            if inp.get("kind") and M.value(df, "kind") != inp["kind"]:
                continue
            if inp.get("subject") and M.value(df, "subject") != inp["subject"]:
                continue
            routes = []
            for ro in _routes_of(store, d["id"]):
                v = _route_view(store, ro, df)
                routes.append({"route_id": ro["id"], "channel": M.value(v["fields"], "channel") or "unknown", "automation": v["automation"],
                               "cost": M.value(v["fields"], "cost") or "unknown", "turnaround": M.value(v["fields"], "turnaround") or "unknown"})
            out.append({"document_id": d["id"], "register_id": r["id"], "register": _name(rf), "name": _name(df), "fields": df,
                        "fulfils_cells": loads(d["data"]).get("fulfils_cells") or [], "routes": routes})
    return {"jurisdiction": j["code"], "documents": out}, 200, None


async def obtain_plan(ctx, inp: dict):
    store = _store(ctx)
    j = _jur(store, inp["jurisdiction"])
    actor = inp.get("actor") or "agapi"
    docs: List[dict] = []
    if inp.get("document_id"):
        d = store.one("select * from registry_documents where id = ? and jurisdiction = ? and retired = 0", inp["document_id"], j["code"])
        if not d:
            raise AgapiError("not_found", "No such document type in this jurisdiction.", {"registry_code": "document_unknown", "document_id": inp["document_id"]})
        docs = [d]
    else:
        need = inp.get("need") or {}
        for d in store.q("select * from registry_documents where jurisdiction = ? and retired = 0 order by id", j["code"]):
            df = M.fields_of(store, "document", d["id"], ("kind", "subject"))
            if (not need.get("kind") or M.value(df, "kind") == need["kind"]) and (not need.get("subject") or M.value(df, "subject") == need["subject"]):
                docs.append(d)
        if not docs:
            raise AgapiError("not_found", "No document type here matches that need (by its cited claims).",
                             {"registry_code": "document_unknown", "need": need})
    views, inputs = {}, []
    for d in docs:
        df = M.fields_of(store, "document", d["id"], DOCUMENT_FIELDS)
        for ro in _routes_of(store, d["id"]):
            v = _route_view(store, ro, df, actor)
            views[ro["id"]] = {**v, "document_id": d["id"], "document": _name(df)}
            inputs.append(v["_inp"])
    ranked = P.rank(inputs, actor)
    routes = []
    for x in ranked["routes"]:
        v = views[x["route_id"]]
        routes.append({**x, "document_id": v["document_id"], "document": v["document"], "fields": v["fields"],
                       **({"rail_config_key": v["rail_config_key"]} if v.get("rail_config_key") else {}), "drift_state": v["drift_state"]})
    return {"jurisdiction": j["code"], "actor": actor, "routes": routes, "excluded": ranked["excluded"],
            "obtainable_by_agapi": ranked["obtainable_by_agapi"], "obtain": OBTAIN}, 200, None


async def verify(ctx, inp: dict):
    store = _store(ctx)
    if inp.get("claim_id"):
        rows = [store.one("select * from registry_claims where id = ?", inp["claim_id"])]
        if not rows[0]:
            raise AgapiError("not_found", "No such claim.", {"claim_id": inp["claim_id"]})
        if rows[0]["superseded_at"]:
            nxt = rows[0]["superseded_by"] or ""
            raise AgapiError("not_found", "That claim was superseded by a newer read; verify the newer one.", {"claim_id": inp["claim_id"],
                             **({"superseded_by": nxt} if nxt.startswith("rcl_") else {})})
    else:
        if not store.one("select id from registry_routes where id = ?", inp.get("route_id") or ""):
            raise AgapiError("not_found", "No such route.", {"route_id": inp.get("route_id")})
        rows = store.q("select * from registry_claims where entity = 'route' and entity_id = ? and superseded_at is null and method in "
                       "('magellan_fetch', 'magellan_verify') order by read_at desc", inp["route_id"])[:3]
        if not rows:
            raise AgapiError("invalid_input", "This route's facts come from AD's catalogue and certification records, not a page — nothing to re-read.",
                             {"path": "/route_id", "rule": "no_page_claims"})
    checked = []
    for c in rows:
        if c["method"] not in ("magellan_fetch", "magellan_verify") or not c["source_url"].startswith(("http://", "https://")):
            raise AgapiError("invalid_input", "This claim cites AD's catalogue or certification record, not a page — nothing to re-read.",
                             {"path": "/claim_id", "rule": "not_a_page"})
        host = (urlsplit(c["source_url"]).hostname or "").lower()
        hour_ago = later(minutes=-60)
        if len(store.q("select id from registry_checks where host = ? and at > ?", host, hour_ago)) >= VERIFY_PER_HOST_HOUR:
            raise AgapiError("rate_limited", f"{host} was re-read {VERIFY_PER_HOST_HOUR} times this hour — the per-host budget; never a bulk crawl.",
                             retry_after_s=600)
        now = ts()[:19] + "Z"
        try:
            text, _ = await gate.read_page(c["source_url"])
            res = V.drift(c["quote"], text)
        except gate.Broken as b:
            res = {**V.drift(c["quote"], None, b.layer), "why": b.why}
        except gate.Unreachable as u:
            raise AgapiError("upstream_unreachable", f"Couldn't reach {host} now ({u}). Not 'drifted': try again.",
                             {"registry_code": "source_unreachable", "host": host}, retry_after_s=60)
        from ..rules import new_id
        store.x("insert into registry_checks (id, claim_id, host, state, failure_layer, quote_still_present, at) values (?, ?, ?, ?, ?, ?, ?)",
                new_id("chk"), c["id"], host, res["state"], res.get("failure_layer"), 1 if res["quote_still_present"] else 0, ts())
        out = {"claim_id": c["id"], **res, "read_at": now, "source_url": c["source_url"]}
        if res["state"] == "fresh":       # claims are never edited: the re-read is a NEW claim; the old one is superseded by it
            n = M.make_claim(c["entity"], c["entity_id"], c["field"], loads(c["value"]), c["source_url"], now, c["quote"], "magellan_verify",
                             "read_at_source")
            store.x("insert or ignore into registry_claims (id, entity, entity_id, jurisdiction, field, value, source_url, read_at, quote, quote_sha256, "
                    "claim_sha256, method, confidence, untrusted, note, snapshot, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    n["id"], n["entity"], n["entity_id"], c["jurisdiction"], n["field"], dumps(n["value"]), n["source_url"], n["read_at"], n["quote"],
                    n["quote_sha256"], n["claim_sha256"], n["method"], n["confidence"], 1, "re-read by registry.verify", None, ts())
            if n["id"] != c["id"]:
                store.x("update registry_claims set superseded_by = ?, superseded_at = ? where id = ?", n["id"], ts(), c["id"])
            out["new_claim_id"] = n["id"]
        if c["entity"] == "route":
            store.x("update registry_routes set drift_state = ?, last_verified_at = ? where id = ?", res["state"], ts(), c["entity_id"])
        checked.append(out)
    order = {"broken": 2, "drifted": 1, "fresh": 0}
    worst = max(checked, key=lambda x: order[x["state"]])
    return {**{k: worst[k] for k in ("state", "read_at", "quote_still_present") if k in worst},
            **({"failure_layer": worst["failure_layer"]} if worst.get("failure_layer") else {}), "checked": checked,
            "reverify_after": later(minutes=REVERIFY_DAYS * 24 * 60)[:10]}, 200, None


OPS = {"registry.countries": countries, "registry.get": get, "registry.documents": documents, "registry.obtain_plan": obtain_plan,
       "registry.verify": verify}
