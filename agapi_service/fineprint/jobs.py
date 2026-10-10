"""The card-terms re-reads (EU 216 §1 freshness): every 60 days, and IMMEDIATELY when a source's body changes (body_sha256).
Runs on the sandbox only when AGAPI_FINEPRINT_SCHEDULE=1 (once a day); the signed admin action card_read runs one card now.
A changed source first marks the quotes that vanished as drifted (shown with a warning), then the card is re-read; a re-read that
gets nothing keeps the last good claims."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from typing import Any, Dict, List

from .. import config, magellan as MG
from ..registers import gate
from . import model as M, reader as RD

LOG = logging.getLogger("agapi.fineprint")
DAY_S = 24 * 3600


def seeds() -> Dict[str, dict]:
    d = json.loads((M.DATA / "seeds.json").read_text())
    return {**d["cards"], **(d.get("rentals") or {}), **(d.get("laws") or {})}           # CR 74b · rental companies' terms read the same way


def resolve(card: dict) -> List[str]:
    """Fixture seeds are the sandbox's own pages (its public URL)."""
    return [config.PUBLIC_URL + s if s.startswith("/") else s for s in card["seeds"]]


async def read_now(store, key: str) -> Dict[str, Any]:
    card = seeds()[key]
    res = await RD.read_card({**card, "key": key}, resolve(card))
    M.apply_read(store, key, card, res, accepted_by="fixture (test mode)" if card.get("fixture") else None)
    return res


async def check(store, key: str) -> Dict[str, Any]:
    """One card: due → re-read; else each source it quotes is fetched (robots first) and compared by body_sha256."""
    pid = M.product_id(key)
    p = store.one("select * from card_products where id = ?", pid)
    if not p or not p["accepted_at"]:
        return {"key": key, "action": "skipped (not accepted)"}
    if seeds().get(key, {}).get("supplied"):
        return {"key": key, "action": "supplied by a person: a re-read needs a new copy from the issuer (its site refuses our reader)"}
    if M.freshness(p) != "fresh":
        await read_now(store, key)
        return {"key": key, "action": "re-read (due)"}
    used = {r["source_url"] for r in store.q("select distinct source_url from card_claims where product_id = ? and superseded_at is null", pid)}
    changed = 0
    for s in store.q("select * from card_sources where product_id = ?", pid):
        if s["url"] not in used:
            continue
        v = await gate.robots_verdict(s["url"])
        if v["verdict"] != "allowed":
            continue
        try:
            st, ctype, body, _ = await RD.FETCH_BYTES(s["url"])
        except Exception:
            continue
        if not (200 <= st < 300):
            continue
        if "sha256:" + hashlib.sha256(body).hexdigest() != s["body_sha256"]:
            text = RD.pdf_text(body) if body[:5] == b"%PDF-" else MG.parse(body.decode("utf-8", "replace"))[1]
            M.mark_drift(store, pid, s["url"], MG._norm(text), MG._norm)
            changed += 1
        else:
            store.x("update card_sources set last_checked_at = ? where product_id = ? and url = ?", M.ts(), pid, s["url"])
    if changed:
        await read_now(store, key)
        return {"key": key, "action": f"re-read ({changed} source(s) changed)"}
    return {"key": key, "action": "unchanged"}


async def tick(store) -> List[dict]:
    M.ensure_loaded(store)
    out = []
    for key in seeds():
        try:
            out.append(await check(store, key))
        except Exception as e:
            out.append({"key": key, "action": f"failed ({type(e).__name__})"})
    return out


async def loop(get_store) -> None:
    if os.getenv("AGAPI_FINEPRINT_SCHEDULE", "") != "1" or config.LIVE_SERVICE:
        return
    while True:
        await asyncio.sleep(600)
        try:
            LOG.warning("card terms check: %s", await tick(get_store()))
        except Exception as e:
            LOG.warning("card terms check failed: %s", type(e).__name__)
        await asyncio.sleep(DAY_S)
