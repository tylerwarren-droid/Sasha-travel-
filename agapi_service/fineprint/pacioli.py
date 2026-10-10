"""CR 77 · PACIOLI'S AUTO-CHECK — a fact is accepted automatically ("checked by Pacioli", with the check's results) only when ALL pass:

  a  verbatim        the quote is in the STORED copy word for word (only whitespace and line-break hyphenation normalised)
  b  official        the copy came from the issuer's / rental company's / government's own domain (the seed's sites, or the seed's
                     official_domains), or is a file a person supplied
  c  in_quote        every number, amount, currency, deadline and phone number in the fact's value appears in its quote
  d  sha256          the stored copy's bytes still hash to the sha256 recorded when it was read

Anything that fails goes to the EXCEPTIONS list on the review page — only those need a person. A person's earlier acceptance of a
card stays. The switch (fineprint_settings.auto_accept, review page / admin pacioli_switch) turns automatic acceptance off; checks still run."""
from __future__ import annotations

import hashlib
import io
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from .. import magellan as MG, objects as OB
from ..store import dumps, loads, ts
from . import copies as CP, schema as SC

CHECKER = "checked by Pacioli"
TABLES = ("create table if not exists card_checks (claim_id text primary key, product_id text not null, copy_id text, passed integer not null, "
          "results text not null, checked_at text not null, decided_by text, decision text, decided_at text)",
          "create table if not exists fineprint_settings (k text primary key, v text not null, at text not null, by text not null)")
CURRENCY = {"USD": ("$", "usd", "dollar", "dólar", "dolar"), "EUR": ("€", "eur", "euro"), "GBP": ("£", "gbp", "pound", "sterling", "libra"),
            "CHF": ("chf", "franc"), "JPY": ("¥", "jpy", "yen"), "CAD": ("cad", "c$", "$"), "AUD": ("aud", "a$", "$")}
_TEXT_CACHE: Dict[str, str] = {}


def ensure(store) -> None:
    for t in TABLES:
        store.x(t)


# ── the switch ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def auto_on(store) -> bool:
    ensure(store)
    r = store.one("select v from fineprint_settings where k = 'auto_accept'")
    return True if r is None else r["v"] == "on"


def set_auto(store, on: bool, by: str) -> None:
    ensure(store)
    if store.x("update fineprint_settings set v = ?, at = ?, by = ? where k = 'auto_accept'", "on" if on else "off", ts(), by) == 0:
        store.x("insert or ignore into fineprint_settings (k, v, at, by) values ('auto_accept', ?, ?, ?)", "on" if on else "off", ts(), by)


# ── the four checks ─────────────────────────────────────────────────────────────────────────────────────────────────────

def norm(t: str) -> str:
    t = (t or "").replace("­", "")
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)          # a word hyphenated across lines
    return MG._norm(t)


def copy_text(raw: bytes, content_type: str) -> str:
    if raw[:5] == b"%PDF-" or "pdf" in content_type:
        from .reader import pdf_text
        return pdf_text(raw)
    return MG.parse(raw.decode("utf-8", "replace"))[1]


def official_sites(seed: dict) -> List[str]:
    sites = {MG._site(urlsplit(u).hostname or "") for u in seed.get("seeds") or [] if u.startswith("http")}
    return sorted(s for s in sites | set(seed.get("official_domains") or []) if s)


UNITS = {"amount_minor": 100, "rate_x100": 100, "basis_points": 100}   # a stored value's own units → the number as a quote writes it


def _plain(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: (x / UNITS[k] if k in UNITS and isinstance(x, (int, float)) else _plain(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v


def _numbers(v: Any) -> List[float]:
    v = _plain(v)
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    out = []
    for m in re.finditer(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])", s.replace(",", "")):
        n = float(m.group(0))
        if n not in out:
            out.append(n)
    return out


def _currencies(v: Any) -> List[str]:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return sorted({c for c in re.findall(r"\b[A-Z]{3}\b", s) if c in CURRENCY})


def in_quote(field: str, value: Any, quote: str) -> Dict[str, Any]:
    """(c) every number / amount / currency / deadline / phone of the value is in its quote."""
    missing: List[str] = []
    q = (quote or "").lower()
    if "phone" in field:
        vd = re.sub(r"\D", "", value if isinstance(value, str) else json.dumps(value))
        qd = re.sub(r"\D", "", quote or "")
        if vd and vd not in qd and vd.lstrip("0") not in qd:
            missing.append(f"phone {vd}")
    else:
        for n in _numbers(value):
            if not SC._in_quote(n, quote):
                missing.append(("%g" % n))
    for c in _currencies(value):
        if not any(w in q for w in CURRENCY[c]):
            missing.append(c)
    return {"pass": not missing, "missing": missing}


async def check_claim(store, claim: dict, product: dict, seed: Optional[dict], copy: Optional[dict]) -> Dict[str, Any]:
    r: Dict[str, Any] = {"copy_id": copy["id"] if copy else None, "checked_at": ts()[:19] + "Z", "checker": CHECKER}
    if not copy:
        return {**r, "passed": False, "a_verbatim": False, "b_official": False, "c_in_quote": False, "d_sha256": False,
                "why": ["no stored copy of the source this fact quotes"]}
    why: List[str] = []
    try:
        raw = await OB.get(copy["object_key"])
        d = "sha256:" + hashlib.sha256(raw).hexdigest() == copy["sha256"]
    except Exception as e:
        raw, d = b"", False
        why.append(f"the copy couldn't be read ({type(e).__name__})")
    if raw and not d:
        why.append("the stored copy's sha256 doesn't match the one recorded at the read")
    a = False
    if raw and d:
        t = _TEXT_CACHE.get(copy["sha256"])
        if t is None:
            t = _TEXT_CACHE[copy["sha256"]] = norm(copy_text(raw, copy["content_type"]))
        a = len(norm(claim["quote"])) >= 6 and norm(claim["quote"]) in t
        if not a:
            why.append("the quote isn't in the stored copy word for word")
    host_site = MG._site(urlsplit(copy["final_url"]).hostname or "")
    sites = official_sites(seed or {})
    b = bool(copy.get("supplied_by")) or (host_site in sites)
    if not b:
        why.append(f"{host_site or 'the source'} isn't the issuer's / company's / government's own domain ({', '.join(sites) or 'none listed'})")
    value = claim["value"]
    if isinstance(value, str):   # a stored claim's value is JSON; a fresh fact's text value is the text itself
        try:
            value = json.loads(value)
        except ValueError:
            pass
    c = in_quote(claim["field"], value, claim["quote"])
    if not c["pass"]:
        why.append("not in its quote: " + ", ".join(c["missing"]))
    return {**r, "passed": a and b and c["pass"] and d, "a_verbatim": a, "b_official": b, "c_in_quote": c["pass"], "d_sha256": d,
            "domain": host_site, "supplied_by": copy.get("supplied_by"), **({"missing": c["missing"]} if c["missing"] else {}), "why": why}


def record(store, claim_id: str, product_id: str, res: dict) -> None:
    ensure(store)
    if store.x("update card_checks set copy_id = ?, passed = ?, results = ?, checked_at = ? where claim_id = ?",
               res.get("copy_id"), int(bool(res["passed"])), dumps(res), ts(), claim_id) == 0:
        store.x("insert or ignore into card_checks (claim_id, product_id, copy_id, passed, results, checked_at) values (?, ?, ?, ?, ?, ?)",
                claim_id, product_id, res.get("copy_id"), int(bool(res["passed"])), dumps(res), ts())


def auto_accept(store, pid: str) -> bool:
    """A product no person has decided on, with at least one fact that passed, is accepted — by Pacioli (only while the switch is on)."""
    if not auto_on(store):
        return False
    p = store.one("select * from card_products where id = ?", pid)
    if not p or p["accepted_at"] or p["rejected_at"]:
        return False
    if not store.one("select claim_id from card_checks k join card_claims c on c.id = k.claim_id where k.product_id = ? and k.passed = 1 "
                     "and c.superseded_at is null limit 1", pid):
        return False
    store.x("update card_products set accepted_at = ?, accepted_by = ? where id = ?", ts(), CHECKER, pid)
    return True


async def run(store, *, keys: Optional[List[str]] = None) -> Dict[str, Any]:
    """Check every live fact of the beta set against its stored copy; record; auto-accept. → counts + the exceptions."""
    from . import model as M
    ensure(store)
    seeds = M.all_seeds()
    out = {"checked": 0, "passed": 0, "failed": 0, "fixtures_skipped": 0, "products_auto_accepted": [], "exceptions": []}
    for p in M.products(store):
        seed = seeds.get(p["key"])
        if keys and p["key"] not in keys:
            continue
        if not M.is_beta(p) or not p["last_read_at"]:
            continue
        if (seed or {}).get("fixture"):
            out["fixtures_skipped"] += 1
            continue
        for c in M.claims(store, p["id"], every=True):
            cp = CP.get(store, c["copy_id"]) if c.get("copy_id") else CP.for_source(store, p["key"], c["source_url"], c["read_at"])
            res = await check_claim(store, c, p, seed, cp)
            record(store, c["id"], p["id"], res)
            out["checked"] += 1
            out["passed" if res["passed"] else "failed"] += 1
            if not res["passed"]:
                out["exceptions"].append({"product": p["key"], "claim_id": c["id"], "fact": f"{c['benefit']}.{c['field']}", "why": res["why"]})
        if auto_accept(store, p["id"]):
            out["products_auto_accepted"].append(p["key"])
    return out


def exceptions(store) -> List[dict]:
    """The facts that failed a check and no person has decided on (live claims only)."""
    ensure(store)
    return store.q("select k.*, c.benefit, c.field, c.value, c.quote, c.source_url, p.product, p.issuer, p.key from card_checks k "
                   "join card_claims c on c.id = k.claim_id join card_products p on p.id = k.product_id "
                   "where k.passed = 0 and k.decision is null and c.superseded_at is null order by p.issuer, p.product, c.benefit, c.field")


def decide(store, claim_id: str, decision: str, by: str) -> bool:
    ensure(store)
    return store.x("update card_checks set decision = ?, decided_by = ?, decided_at = ? where claim_id = ?", decision, by, ts(), claim_id) > 0
