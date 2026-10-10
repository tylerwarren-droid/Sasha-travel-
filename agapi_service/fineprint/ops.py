"""CR 74 · FINE PRINT as AgAPI operations (Kanoe extensions for EU to formalize): a card's official terms as cited claims.

  cards.products   the card products in the claim store: read status, terms read date, freshness, whether a person accepted the first read
  cards.terms      one card product's benefits — every value with its source URL, the sentence quoted word for word, the date read;
                   a drifted or stale claim carries its warning; a field no source states isn't there (never a guess)
(Steps 2–3 add cards.intake / cards.mine / cards.ask / cards.which — further down.)"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import rules as R
from ..registry import AgapiError
from ..store import loads
from . import model as M

NOT_ACCEPTED = "Read on {d}; awaiting a Kanoe person's check of this first read — not used to answer anyone yet."


def _product_out(p: dict) -> dict:
    d = loads(p["data"])
    return {"product_id": p["id"], "issuer": p["issuer"], "product": p["product"], "network": p["network"], "country": p["country"],
            "accepted": bool(p["accepted_at"]), "terms_read_at": (p["last_read_at"] or "")[:10] or None, "reverify_after": (p["reverify_after"] or "")[:10] or None,
            "freshness": M.freshness(p), "test_fixture": bool(d.get("fixture")),
            **({"why_unread": (d.get("last_read") or {}).get("why") or "not read yet"} if not p["last_read_at"] else {})}


def warning(c: dict, p: dict) -> Optional[str]:
    if c["drift_state"] == "drifted":
        return f"The issuer's terms changed on {(c['drift_seen_at'] or '')[:10]}; this was read {c['read_at'][:10]} and is being re-read."
    if M.freshness(p) == "stale":
        return f"Last read {c['read_at'][:10]}, past its re-read date: check the source before relying on it."
    return None


def claim_out(c: dict, p: dict) -> dict:
    w = warning(c, p)
    return {"claim_id": c["id"], "value": loads(c["value"]), "source_url": c["source_url"], "read_at": c["read_at"][:10],
            "quote": R.wrap(c["quote"], "card_terms", c["read_at"][:19] + "Z", cap=500), "drift_state": c["drift_state"], **({"warning": w} if w else {})}


def get_product(store, pid: str) -> dict:
    M.ensure_loaded(store)
    p = store.one("select * from card_products where id = ?", pid)
    if not p:
        raise AgapiError("not_found", "No such card product in the claim store.", {"product_id": pid})
    return p


async def products(ctx, inp: dict):
    rows = M.products(ctx.store)
    q = (inp.get("query") or "").lower().strip()
    out = [_product_out(p) for p in rows if not q or q in f"{p['issuer']} {p['product']}".lower()]
    return {"products": out, "note": "Facts come only from the issuers' own terms, each quoted with its source and date. A first read is "
                                     "used only after a Kanoe person checks it."}, 200, None


async def terms(ctx, inp: dict):
    p = get_product(ctx.store, inp["product_id"])
    benefits: Dict[str, Dict[str, List[dict]]] = {}
    for c in M.claims(ctx.store, p["id"]):
        if inp.get("benefit") and c["benefit"] != inp["benefit"]:
            continue
        benefits.setdefault(c["benefit"], {}).setdefault(c["field"], []).append(claim_out(c, p))
    srcs = ctx.store.q("select url, kind, linked_from, read_at, changed_at from card_sources where product_id = ? order by url", p["id"])
    out = {"product": _product_out(p), "benefits": benefits,
           "sources": [{"url": s["url"], "kind": s["kind"], **({"linked_from": s["linked_from"]} if s["linked_from"] else {}),
                        "read_at": s["read_at"][:10], **({"changed_at": s["changed_at"][:10]} if s["changed_at"] else {})} for s in srcs],
           "unread": (loads(p["data"]).get("last_read") or {}).get("unread") or []}
    if not p["accepted_at"] and p["last_read_at"]:
        out["note"] = NOT_ACCEPTED.format(d=p["last_read_at"][:10])
    return out, 200, None


# ── step 2 · card products in the Keep: by photo / Wallet screenshot; "My cards" ─────────────────────────────────────────

def _terms_brief(p: Optional[dict]) -> Optional[dict]:
    if not p:
        return None
    return {"product_id": p["id"], "terms_read_at": (p["last_read_at"] or "")[:10] or None, "accepted": bool(p["accepted_at"]), "freshness": M.freshness(p)}


async def intake(ctx, inp: dict):
    """cards.intake — a photo of a card or a Wallet screenshot → the card PRODUCT (issuer, product, network, country), saved to the
    person's Keep as type card_product unless save is false. No digit is ever kept; the image is read once and dropped."""
    from .. import keep_ops as KO
    from ..engine import _end_user
    from . import intake as IN
    _end_user(ctx, inp["end_user"])
    card = await IN.read_card_image(inp["image"])
    if not card["issuer"] or not card["product"]:
        raise AgapiError("invalid_input", "The card's issuer and product couldn't be read from that image; nothing was kept. Try a clearer photo, "
                         "or add it by name.", {"path": "/image", "rule": "unreadable"})
    p = IN.match(ctx.store, card["issuer"], card["product"])
    out: Dict[str, Any] = {"card": card, "saved": False, "terms": _terms_brief(p),
                           "note": "Only the card's product was kept — no number, not even the last four digits. The image wasn't kept."}
    if inp.get("save", True):
        try:
            got, _, eid = await KO.keep_put(ctx, {"end_user": inp["end_user"], "type": "card_product",
                                                  "value": {k: v for k, v in card.items() if v}})
        except AgapiError as e:
            if (e.details or {}).get("rule") == "never_card":
                raise AgapiError("invalid_input", "What was read contained digits, so nothing was kept. Add the card by its name instead.",
                                 {"path": "/image", "rule": "never_card"})
            raise
        out.update(saved=True, item_id=got["item_id"], masked=got["masked"])
        return out, 201, eid
    return out, 200, None


async def _my_cards(ctx, uid: str) -> List[dict]:
    """The person's card products, opened server-side (tier free: nothing secret is in them) and matched to the claim store."""
    from agapi import keep as K
    from .. import keep_ops as KO
    from . import intake as IN
    rows = ctx.store.q("select * from keep_items where account = ? and end_user = ? and type = 'card_product' order by created_at", ctx.account, uid)
    if not rows:
        return []
    dek = await KO._dek(ctx, uid, create=False)
    out = []
    for it in rows:
        v = K.open_(dek, K.item_aad(ctx.account, uid, it["id"], it["type"]), bytes(it["nonce"]), bytes(it["ciphertext"]))
        p = IN.match(ctx.store, v.get("issuer", ""), v.get("product", ""))
        out.append({"item_id": it["id"], "masked": it["masked"], "issuer": v.get("issuer"), "product": v.get("product"), "network": v.get("network"),
                    **({"country": v["country"]} if v.get("country") else {}), "terms": _terms_brief(p), "_p": p})
    return out


async def mine(ctx, inp: dict):
    """cards.mine — "My cards": each card product with its terms status ("terms read 02 OCT 2026" · not read yet · awaiting a check)."""
    from ..engine import _end_user
    _end_user(ctx, inp["end_user"])
    cards = await _my_cards(ctx, inp["end_user"])
    for c in cards:
        p = c.pop("_p")
        c["status"] = ("no official terms read for this card yet" if not p or not p["last_read_at"] else
                       f"terms read {p['last_read_at'][:10]}" + ("" if p["accepted_at"] else ", awaiting a Kanoe check"))
    return {"cards": cards}, 200, None


OPS = {"cards.products": products, "cards.terms": terms, "cards.intake": intake, "cards.mine": mine}


# ── step 3 · answers only from quotes; which of my cards ────────────────────────────────────────────────────────────

def _live(store, p: dict) -> List[dict]:
    return [{**c, "value": loads(c["value"]), **({"warning": warning(c, p)} if warning(c, p) else {})} for c in M.claims(store, p["id"])]


async def ask(ctx, inp: dict):
    """cards.ask — "What does my X cover for Y?" answered ONLY from the card's quoted terms; otherwise "the terms don't say" + the claims line."""
    from ..engine import _end_user
    from . import answer as A
    _end_user(ctx, inp["end_user"])
    if inp.get("card_item_id"):
        mine = {c["item_id"]: c for c in await _my_cards(ctx, inp["end_user"])}
        c = mine.get(inp["card_item_id"])
        if not c:
            raise AgapiError("not_found", "That card isn't in this person's cards.", {"card_item_id": inp["card_item_id"]})
        p, name = c["_p"], c["product"]
    else:
        p = get_product(ctx.store, inp.get("product_id") or "")
        name = p["product"]
    base = {"card": name, "framing": A.FRAMING}
    if not p or not p["last_read_at"]:
        return {**base, "answer": "no_terms", "text": f"I haven't read {name}'s official terms yet, so I can't say what it covers.", "quotes": []}, 200, None
    if not p["accepted_at"]:
        return {**base, "answer": "awaiting_check", "text": f"I read {name}'s terms on {p['last_read_at'][:10]}; a Kanoe person still has to check that "
                                                            "first read before I answer from it.", "quotes": []}, 200, None
    out = await A.ask(p, _live(ctx.store, p), inp["question"])
    return {**base, **out, "product_id": p["id"]}, 200, None


async def which(ctx, inp: dict):
    """cards.which — "which of my cards for this?": the person's cards ranked from their own quoted terms (FX fee, cover, points)."""
    from ..engine import _end_user
    from . import answer as A
    _end_user(ctx, inp["end_user"])
    cards, skipped = [], []
    for c in await _my_cards(ctx, inp["end_user"]):
        p = c["_p"]
        if not p or not p["accepted_at"]:
            skipped.append({"card": c["product"], "why": "its official terms haven't been read and checked yet"})
            continue
        cards.append({"name": c["product"], "product_country": p["country"] or c.get("country") or "", "claims": _live(ctx.store, p)})
    if not cards:
        return {"framing": A.FRAMING, "ordered_by": "", "cards": [], "net_view": "", "skipped": skipped,
                "text": "None of your cards has checked official terms yet, so I can't compare them."}, 200, None
    out = A.rank_cards(inp["purchase"], cards)
    return {**out, "skipped": skipped}, 200, None


OPS.update({"cards.ask": ask, "cards.which": which})
