"""The card-terms claim store (CR 74 · EU 216 §1, on the registry's claim model): card products, their sources, and one claim per fact.

  card_products  issuer · product · network · country, the seeds, the read status; ACCEPTED by a person on the Kanoe side for its first
                 read (the accept surface, review.py) — until then no answer uses it. Later re-reads are automatic.
  card_claims    one benefit field each: value + source_url + verbatim quote + read_at (+ quote_sha256 / claim_sha256, rcl_ ids as the
                 registry). NEVER edited: a re-read writes new claims and supersedes the old ones; a quote that vanished from a changed
                 source is marked drifted (shown with its last read date and a warning) until the re-read replaces it.
  card_sources   each document read (url, kind, body_sha256, linked_from): a changed body_sha256 triggers a re-read.
  freshness      re-read every 60 days (reverify_after); "due" up to 30 days past it; then STALE — never used in an answer without
                 saying so."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..registers.model import make_claim, rid
from ..store import dumps, loads, ts

DATA = Path(__file__).parent / "data"
REREAD_DAYS, STALE_GRACE_DAYS = 60, 30

TABLES = (
    "create table if not exists card_products (id text primary key, key text not null, issuer text not null, product text not null, "
    "network text not null, country text not null, data text not null, accepted_at text, accepted_by text, rejected_at text, "
    "last_read_at text, reverify_after text, updated_at text not null)",
    "create table if not exists card_claims (id text primary key, product_id text not null, benefit text not null, field text not null, "
    "value text not null, source_url text not null, read_at text not null, quote text not null, quote_sha256 text not null, "
    "claim_sha256 text not null, method text not null, confidence text not null, drift_state text not null default 'fresh', "
    "drift_seen_at text, superseded_by text, superseded_at text, created_at text not null)",
    "create table if not exists card_sources (product_id text not null, url text not null, kind text not null, body_sha256 text not null, "
    "linked_from text not null, read_at text not null, last_checked_at text, changed_at text, primary key (product_id, url))",
    "create table if not exists card_loads (sha text primary key, at text not null)",
)


def ensure(store) -> None:
    for t in TABLES:
        store.x(t)


def product_id(key: str) -> str:
    return rid("cpr", key)


def _at(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def freshness(p: dict, now: Optional[datetime] = None) -> str:
    """fresh · due (past reverify_after, up to 30 days) · stale (beyond) · unread."""
    if not p.get("reverify_after"):
        return "unread"
    now = now or datetime.now(timezone.utc)
    ra = _at(p["reverify_after"])
    return "fresh" if now < ra else "due" if now < ra + timedelta(days=STALE_GRACE_DAYS) else "stale"


def apply_read(store, key: str, card: dict, read: dict, *, accepted_by: Optional[str] = None) -> Dict[str, Any]:
    """A read's facts → claims (new ones superseding the product's earlier live claims). A read with no facts changes nothing."""
    ensure(store)
    pid = product_id(key)
    now = ts()
    row = store.one("select * from card_products where id = ?", pid)
    data = {"seeds": card.get("seeds") or [], "seed_source": card.get("seed_source", ""), "fixture": bool(card.get("fixture")),
            "last_read": {k: read.get(k) for k in ("read_at", "unread", "dropped", "instruction_like", "why", "reader")}}
    if not row:
        store.x("insert or ignore into card_products (id, key, issuer, product, network, country, data, updated_at) values (?, ?, ?, ?, ?, ?, ?, ?)",
                pid, key, card["issuer"], card["product"], card.get("network") or "unknown", card.get("country") or "", dumps(data), now)
    else:
        store.x("update card_products set data = ?, updated_at = ? where id = ?", dumps({**loads(row["data"]), **data}), now, pid)
    if accepted_by and not (row or {}).get("accepted_at"):
        store.x("update card_products set accepted_at = ?, accepted_by = ? where id = ?", now, accepted_by, pid)
    facts = read.get("facts") or []
    if not facts:
        return {"product_id": pid, "claims": 0, "changed": False}
    at = read["read_at"]
    new_ids = []
    for f in facts:
        c = make_claim("card_product", pid, f"{f['benefit']}.{f['field']}", f["value"], f["source_url"], at, f["quote"], "magellan_fetch", "read_at_source")
        new_ids.append(c["id"])
        store.x("insert or ignore into card_claims (id, product_id, benefit, field, value, source_url, read_at, quote, quote_sha256, claim_sha256, "
                "method, confidence, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", c["id"], pid, f["benefit"], f["field"],
                dumps(f["value"]), f["source_url"], at, f["quote"], c["quote_sha256"], c["claim_sha256"], c["method"], c["confidence"], now)
    for r in store.q("select id from card_claims where product_id = ? and superseded_at is null", pid):
        if r["id"] not in new_ids:
            store.x("update card_claims set superseded_by = ?, superseded_at = ? where id = ?", f"read:{at}", now, r["id"])
    for s in read.get("sources") or []:
        if store.x("update card_sources set kind = ?, body_sha256 = ?, linked_from = ?, read_at = ?, changed_at = null where product_id = ? and url = ?",
                   s["kind"], s["body_sha256"], s.get("linked_from") or "", at, pid, s["url"]) == 0:
            store.x("insert or ignore into card_sources (product_id, url, kind, body_sha256, linked_from, read_at) values (?, ?, ?, ?, ?, ?)",
                    pid, s["url"], s["kind"], s["body_sha256"], s.get("linked_from") or "", at)
    ra = (_at(at) + timedelta(days=REREAD_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    store.x("update card_products set last_read_at = ?, reverify_after = ?, updated_at = ? where id = ?", at, ra, now, pid)
    return {"product_id": pid, "claims": len(new_ids), "changed": True}


def mark_drift(store, pid: str, url: str, new_text_norm: str, norm) -> int:
    """A source's body changed: each live claim quoting it whose sentence is gone is drifted (shown with a warning until re-read)."""
    n = 0
    for c in store.q("select id, quote from card_claims where product_id = ? and source_url = ? and superseded_at is null and drift_state = 'fresh'", pid, url):
        if norm(c["quote"]) not in new_text_norm:
            store.x("update card_claims set drift_state = 'drifted', drift_seen_at = ? where id = ?", ts(), c["id"])
            n += 1
    store.x("update card_sources set changed_at = ?, last_checked_at = ? where product_id = ? and url = ?", ts(), ts(), pid, url)
    return n


def ensure_loaded(store) -> None:
    """The committed snapshot (data/reads.json — the first reads, made on the sandbox server) loaded once per sha."""
    import hashlib
    ensure(store)
    p = DATA / "reads.json"
    seeds = json.loads((DATA / "seeds.json").read_text())
    raw = (p.read_bytes() if p.exists() else b"") + (DATA / "seeds.json").read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if getattr(store, "_cards_sha", None) == sha:
        return
    if not store.one("select sha from card_loads where sha = ?", sha):
        reads = json.loads(p.read_text())["reads"] if p.exists() else {}
        for key, card in seeds["cards"].items():
            r = reads.get(key)
            if r and r.get("facts"):
                if not store.one("select id from card_claims where product_id = ? and read_at = ? limit 1", product_id(key), r["read_at"]):
                    apply_read(store, key, card, r, accepted_by="fixture (test mode)" if card.get("fixture") else None)
            elif not store.one("select id from card_products where id = ?", product_id(key)):
                apply_read(store, key, card, r or {"read_at": None, "facts": [], "why": "not read yet"})
        store.x("insert or ignore into card_loads (sha, at) values (?, ?)", sha, ts())
    store._cards_sha = sha


def products(store) -> List[dict]:
    ensure_loaded(store)
    return store.q("select * from card_products order by issuer, product")


def claims(store, pid: str) -> List[dict]:
    return store.q("select * from card_claims where product_id = ? and superseded_at is null order by benefit, field, read_at desc", pid)
