"""CR 74 · FINE PRINT as AgAPI operations (Kanoe extensions for EU to formalize): a card's official terms as cited claims.

  cards.products   the card products in the claim store: read status, terms read date, freshness, whether a person accepted the first read
  cards.terms      one card product's benefits — every value with its source URL, the sentence quoted word for word, the date read;
                   a drifted or stale claim carries its warning; a field no source states isn't there (never a guess)
(Steps 2–3 add cards.intake / cards.mine / cards.ask / cards.which — further down.)"""
from __future__ import annotations

import json
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
    rows = [p for p in M.products(ctx.store) if M.is_beta(p) and not M.is_rental(p) and not M.is_law(p)]   # CR 74b · the beta set's CARDS only
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
    if p and not M.is_beta(p):
        return {**base, "answer": "no_terms", "text": f"{name} isn't in the cards I answer for yet, so I can't say what it covers.", "quotes": []}, 200, None
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
        if not p or not p["accepted_at"] or not M.is_beta(p):
            skipped.append({"card": c["product"], "why": "its official terms haven't been read and checked yet" if not p or M.is_beta(p)
                            else "it isn't in the cards I answer for yet"})
            continue
        cards.append({"name": c["product"], "product_country": p["country"] or c.get("country") or "", "claims": _live(ctx.store, p)})
    if not cards:
        return {"framing": A.FRAMING, "ordered_by": "", "cards": [], "net_view": "", "skipped": skipped,
                "text": "None of your cards has checked official terms yet, so I can't compare them."}, 200, None
    out = A.rank_cards(inp["purchase"], cards)
    return {**out, "skipped": skipped}, 200, None


OPS.update({"cards.ask": ask, "cards.which": which})


# ── step 4 · rental cover: the counter card ────────────────────────────────────────────────────────────────────────────

def rental_terms_for(store, country: str, company: str):
    """The rental company's own terms for this country — (claims, note). Only an accepted read is used."""
    want = (company or "").strip().lower()
    for p in M.products(store):
        if M.is_rental(p) and p["country"] == country and want and (p["issuer"].lower().startswith(want) or want.startswith(p["issuer"].lower())):
            if not p["last_read_at"]:
                return None, f"I haven't read {p['issuer']}'s terms for {country} yet."
            if not p["accepted_at"]:
                return None, f"{p['issuer']}'s terms for {country} were read on {p['last_read_at'][:10]} and await a Kanoe check."
            return _live(store, p), None
    return None, f"I haven't read {company}'s terms for {country}."


async def rental_cover(ctx, inp: dict):
    """cards.rental_cover — the counter card for one rental: decline / keep / optional, each line quoted from the card's terms and the
    rental company's own terms for that country. Never "you don't need insurance"."""
    from ..engine import _end_user
    from . import rental as RT
    _end_user(ctx, inp["end_user"])
    country = inp["country"].upper()
    cards, skipped = [], []
    for c in await _my_cards(ctx, inp["end_user"]):
        p = c["_p"]
        if inp.get("card_item_id") and c["item_id"] != inp["card_item_id"]:
            continue
        if not p or not p["accepted_at"] or not M.is_beta(p):
            skipped.append({"card": c["product"], "why": "its official terms haven't been read and checked yet"})
            continue
        cards.append({"name": c["product"], "claims": _live(ctx.store, p)})
    rental, note = rental_terms_for(ctx.store, country, inp["rental_company"])
    out = RT.compose(country, inp["rental_company"], rental, note, cards, inp.get("days"), inp.get("vehicle"))
    return {**out, "skipped": skipped}, 200, None


OPS.update({"cards.rental_cover": rental_cover})

from . import claims as _CLAIMS   # noqa: E402   CR 74b · step 5: claims
OPS.update(_CLAIMS.OPS)


# ── CR 75 step 6 · when Sasha speaks up ───────────────────────────────────────────────────────────────────────────────

def _moment_tables(store) -> None:
    store.x("create table if not exists card_moments (account text not null, end_user text not null, event_id text not null, id text not null, "
            "moment text not null, data text not null, created_at text not null, primary key (account, end_user, event_id))")
    store.x("create table if not exists card_moment_settings (account text not null, end_user text not null, moment text not null, "
            "off integer not null, updated_at text not null, primary key (account, end_user, moment))")


def _moments_off(store, account: str, uid: str) -> set:
    return {r["moment"] for r in store.q("select moment from card_moment_settings where account = ? and end_user = ? and off = 1", account, uid)}


async def moment_settings(ctx, inp: dict):
    """cards.moment_settings — turn one of the four moments on or off; returns them all."""
    from ..engine import _end_user
    from ..store import ts
    from . import moments as MO
    _end_user(ctx, inp["end_user"])
    _moment_tables(ctx.store)
    if inp.get("moment"):
        off = 0 if inp.get("on", True) else 1
        if ctx.store.x("update card_moment_settings set off = ?, updated_at = ? where account = ? and end_user = ? and moment = ?",
                       off, ts(), ctx.account, inp["end_user"], inp["moment"]) == 0:
            ctx.store.x("insert or ignore into card_moment_settings (account, end_user, moment, off, updated_at) values (?, ?, ?, ?, ?)",
                        ctx.account, inp["end_user"], inp["moment"], off, ts())
    off = _moments_off(ctx.store, ctx.account, inp["end_user"])
    return {"moments": [{"moment": m, "on": m not in off} for m in MO.MOMENTS]}, 200, None


async def moment(ctx, inp: dict):
    """cards.moment — should Sasha speak up for this event? One line + a card, only when it saves money or prevents a mistake; once per event."""
    from ..engine import _end_user
    from ..rules import new_id
    from ..store import dumps, ts
    from . import moments as MO, rental as RT
    uid, ev = inp["end_user"], inp["event"]
    _end_user(ctx, uid)
    _moment_tables(ctx.store)
    kind = ev["kind"]
    if kind in _moments_off(ctx.store, ctx.account, uid):
        return {"speak": False, "why_silent": "turned off by the person"}, 200, None
    if ctx.store.one("select id from card_moments where account = ? and end_user = ? and event_id = ?", ctx.account, uid, ev["id"]):
        return {"speak": False, "why_silent": "already said once for this event"}, 200, None
    out: Optional[Dict[str, Any]] = None
    if kind in ("rental_booked", "pickup_tomorrow"):
        cover, _, _ = await rental_cover(ctx, {"end_user": uid, "country": ev["country"], "rental_company": ev["rental_company"],
                                               **({"days": ev["days"]} if ev.get("days") else {})})
        said = (MO.rental_line(cover, ev.get("place") or "", ev["rental_company"]) if kind == "rental_booked"
                else MO.pickup_line(cover, ev.get("pickup_time") or "", ev.get("place") or ""))
        if said:
            out = {**said, "card": {"type": "counter_card", **cover, **({"booking_ref": ev["booking_ref"]} if ev.get("booking_ref") else {})}}
    elif kind == "which_card":
        w, _, _ = await which(ctx, {"end_user": uid, "purchase": ev["purchase"]})
        if w["cards"]:
            out = {"line": w["framing"], "why": "on_demand", "card": {"type": "which_card", **w}}
    elif kind == "rental_returned":
        diff = MO.returned_diff(ev.get("quoted") or [], ev.get("final") or [], (ev.get("currency") or "EUR").upper())
        if diff:
            out = {"line": diff["line"], "why": diff["why"], "card": {"type": "charge_diff", **{k: diff[k] for k in diff if k not in ("line", "why")},
                                                                    "rental_company": ev.get("rental_company"), "country": ev.get("country")}}
    if not out:
        return {"speak": False, "why_silent": "nothing here saves money or prevents a mistake"}, 200, None
    mid = new_id("mom")
    ctx.store.x("insert or ignore into card_moments (account, end_user, event_id, id, moment, data, created_at) values (?, ?, ?, ?, ?, ?, ?)",
                ctx.account, uid, ev["id"], mid, kind, dumps({"event": ev, "said": out}), ts())
    return {"speak": True, "moment_id": mid, "moment": kind, **out}, 200, None


async def rental_dispute(ctx, inp: dict):
    """cards.rental_dispute — the [Draft a dispute] after a charge that differs from the quote: the draft is read back (the difference line by
    line, the rental terms quoted) → the person's yes in a later turn → one email to the rental company's own address from its terms. No
    address in the terms → the draft only, to send through their own form."""
    from .. import adapters as AD, config, engine as E, rules as R
    from ..store import dumps, loads, ts
    uid = inp["end_user"]
    _moment_tables(ctx.store)
    row = ctx.store.one("select * from card_moments where account = ? and end_user = ? and id = ?", ctx.account, uid, inp["moment_id"])
    if not row or row["moment"] != "rental_returned":
        raise AgapiError("not_found", "No such charge difference for this person.", {"moment_id": inp["moment_id"]})
    d = loads(row["data"])
    card = d["said"]["card"]
    if not card.get("can_dispute"):
        raise AgapiError("invalid_input", "The final charge isn't more than the quote; there's nothing to dispute.", {"path": "/moment_id", "rule": "no_overcharge"})
    if d.get("act_id"):
        raise AgapiError("already_completed", "This dispute was already sent.", {"act_id": d["act_id"]})
    company, country, cur = card.get("rental_company") or "the rental company", (card.get("country") or "").upper(), card["currency"]
    rental, note = rental_terms_for(ctx.store, country, company)
    to = next((c["value"] for c in (rental or []) if c["benefit"] == "rental_terms" and c["field"] == "contact_email"), None)
    rows = [r for r in card["rows"] if r["difference_minor"]]
    diff_lines = [f"{r['label']}: quoted {cur} {r['quoted_minor'] / 100:,.2f}, charged {cur} {r['charged_minor'] / 100:,.2f}" for r in rows]
    fuel = next((c for c in (rental or []) if c["benefit"] == "rental_terms" and c["field"] == "fuel_policy"), None)
    body = "\n".join(["Hello,", f"My final invoice from {company} is {cur} {(card['charged_total_minor'] - card['quoted_total_minor']) / 100:,.2f} more than the quote "
                      f"I was given ({cur} {card['quoted_total_minor'] / 100:,.2f}). The differences:", *[f"- {x}" for x in diff_lines],
                      "Please explain each of these charges with its evidence, or refund them.", "Thank you."])
    if not to:
        return {"state": "draft_only", "draft": body, "why": f"{company}'s terms I've read don't give an address for this; send it through their own "
                "contact form." + (f" ({note})" if note else "")}, 200, None
    lines = [f"Email {company} at {to} (the address in its terms) to dispute the final charge: {cur} {(card['charged_total_minor'] - card['quoted_total_minor']) / 100:,.2f} more than the quote.",
             *diff_lines, "It asks them to explain each charge with its evidence, or refund it."]
    if fuel:
        lines.append(f"Their own terms on fuel: \"{fuel['quote']}\"")
    if ctx.mode == "live":
        AD.precheck_live("messages.send_email", {"to": {"address": to}}, ctx.store, ctx.account)
    payload = {"moment_id": row["id"], "to": to, "body_sha256": R.sha256(body)}
    psha = R.sha256(payload)
    rb = ctx.store.one("select r.* from read_backs r join intents i on i.account = r.account and i.id = r.intent_id where r.account = ? "
                       "and i.operation = 'cards.rental_dispute' and i.state = 'open' and i.end_user = ? and r.payload_sha256 = ? "
                       "order by r.created_at desc", ctx.account, uid, psha)
    if not rb or E._rb_state(rb) in ("expired", "void"):
        iid = R.new_id("int")
        ctx.store.x("insert into intents (account, id, operation, end_user, state, created_at) values (?, ?, 'cards.rental_dispute', ?, 'open', ?)",
                    ctx.account, iid, uid, ts())
        rb = E._new_read_back(ctx, iid, "cards.rental_dispute", lines, payload, None, uid, True)
    it = ctx.store.one("select * from intents where account = ? and id = ?", ctx.account, rb["intent_id"])
    apv = E._check_and_consume(ctx, rb, {"intent_id": it["id"], "operation": "cards.rental_dispute", "lines": lines, "payload": payload}, 1)
    aid = R.new_id("act")
    sent = await AD.messenger("email", ctx.mode).adeliver(ctx.store, ctx.account, uid, to, "email",
                                                          f"From: {config.EMAIL_FROM}\nReply-To: {config.EMAIL_FROM}\nSubject: Final invoice — please explain or "
                                                          f"refund\n\n{body}", None)
    now = ts()[:19] + "Z"
    outcome = {"kind": "REQUESTED", "reference": sent or f"sbx_dispute_{aid[-8:].lower()}",
               "target_words": R.wrap(f"Dispute sent to {company}" + (" (sandbox: captured, never sent)" if not sent else "") + ".", "agapi", now)}
    E._new_act(ctx, aid, it, "rental_dispute", None, outcome, target=row["id"])
    eid = E._evidence(ctx, "cards.rental_dispute", aid, it["id"], {"moment_id": row["id"]}, outcome, apv,
                      [{"service": "message", "retrieved_at": now, "sha256": R.sha256(body), "snippet": R.wrap(f"to {to}", "agapi", now)}])
    ctx.store.x("update acts set evidence_id = ? where account = ? and id = ?", eid, ctx.account, aid)
    ctx.store.x("update intents set state = 'confirmed' where account = ? and id = ?", ctx.account, it["id"])
    d["act_id"] = aid
    ctx.store.x("update card_moments set data = ? where account = ? and end_user = ? and id = ?", dumps(d), ctx.account, uid, row["id"])
    return {"state": "sent", "act_id": aid, "outcome": outcome, "evidence_id": eid}, 201, eid


OPS.update({"cards.moment": moment, "cards.moment_settings": moment_settings, "cards.rental_dispute": rental_dispute})


# ── CR 75 step 7 · the accident playbook ──────────────────────────────────────────────────────────────────────────────

def law_for(store, country: str):
    """The country's official accident rules — (claims, note). Only a read made at source AND checked by a Kanoe person is used."""
    for p in M.products(store):
        if M.is_law(p) and p["country"] == country:
            if not p["last_read_at"]:
                return None, "not read at source yet"
            if not p["accepted_at"]:
                return None, "read on " + p["last_read_at"][:10] + ", awaiting a Kanoe check"
            return _live(store, p), None
    return None, "no official source for this country yet"


def _emergency(store, country: str):
    own, _ = law_for(store, country)
    c = next((x for x in own or [] if x["field"] == "emergency_number"), None)
    if c:
        return c
    eu, _ = law_for(store, "ES")        # DGT's own words: "A nivel europeo está establecido como número teléfono de emergencias el 112"
    return next((x for x in eu or [] if x["field"] == "emergency_number" and "europeo" in x["quote"].lower()), None)


def _acc_tables(store) -> None:
    store.x("create table if not exists accident_cases (account text not null, id text not null, end_user text not null, data text not null, "
            "step text not null, created_at text not null, updated_at text not null)")


def _acc(ctx, uid: str, cid: str) -> dict:
    _acc_tables(ctx.store)
    row = ctx.store.one("select * from accident_cases where account = ? and end_user = ? and id = ?", ctx.account, uid, cid)
    if not row:
        raise AgapiError("not_found", "No such accident case for this person.", {"case_id": cid})
    return row


async def _acc_view(ctx, row: dict, said: Optional[dict] = None) -> Dict[str, Any]:
    """What the person sees at this step — and ONLY this step."""
    from datetime import datetime as _dt
    from . import accident as AC
    d = loads(row["data"])
    step, country = row["step"], d["country"]
    out: Dict[str, Any] = {"case_id": row["id"], "step": step, "steps": list(AC.STEPS), **({"handoff": AC.HANDOFF} if d.get("handoff") else {})}
    if step == "safety":
        return {**out, **(said or AC.safety(None, _emergency(ctx.store, country)))}
    law, note = law_for(ctx.store, country)
    if step == "duties":
        return {**out, **AC.duties(country, law, note), "next": "done"}
    if step == "photos":
        return {**out, **AC.photo_list([p["shot"] for p in d.get("photos") or []]), "next": "done"}
    keep = [r["masked"] for r in ctx.store.q("select masked from keep_items where account = ? and end_user = ? and type in "
                                             "('driving_licence', 'passport', 'national_id', 'home_address', 'insurance_policy')", ctx.account, row["end_user"])]
    if step == "statement":
        return {**out, **AC.statement(country, d.get("facts") or {}, keep, law), "next": "done"}
    rental, rnote = rental_terms_for(ctx.store, country, d.get("rental_company") or "")
    card = await _acc_card(ctx, row["end_user"], d.get("card_item_id"))
    at = _dt.fromisoformat(d["at"].replace("Z", ""))
    clocks = AC.clocks(at, rental, rnote, card[1] if card else None, card[0] if card else None, law, country, note)
    if step == "clocks":
        return {**out, "say": "Three clocks, each from its own source:", "clocks": clocks, "next": "done"}
    return {**out, "clocks": clocks, "say": d.get("notify_say") or "Ready to notify the rental company. I'll read it back first.",
            **({"claim_case_id": d["claim_case_id"]} if d.get("claim_case_id") else {})}


async def _acc_card(ctx, uid: str, item_id: Optional[str]):
    if not item_id:
        return None
    c = next((c for c in await _my_cards(ctx, uid) if c["item_id"] == item_id), None)
    if not c or not c["_p"] or not c["_p"]["accepted_at"] or not M.is_beta(c["_p"]):
        return None
    return c["product"], _live(ctx.store, c["_p"])


async def accident_start(ctx, inp: dict):
    """cards.accident_start — "I've had an accident": the playbook starts at safety, and nothing else comes until it's answered."""
    from ..engine import _end_user
    from ..rules import new_id
    from ..store import dumps, ts
    _end_user(ctx, inp["end_user"])
    _acc_tables(ctx.store)
    cid = new_id("acc")
    d = {"country": inp["country"].upper(), "place": inp.get("place") or "", "at": inp.get("at") or ts()[:19],
         "rental_company": inp.get("rental_company") or "", "card_item_id": inp.get("card_item_id"), "photos": [], "facts": {}}
    ctx.store.x("insert into accident_cases (account, id, end_user, data, step, created_at, updated_at) values (?, ?, ?, ?, 'safety', ?, ?)",
                ctx.account, cid, inp["end_user"], dumps(d), ts(), ts())
    return await _acc_view(ctx, _acc(ctx, inp["end_user"], cid)), 201, None


async def accident_step(ctx, inp: dict):
    """cards.accident_step — the person's answer to THIS step (or none: where am I?). One step at a time; never on until answered."""
    from ..store import dumps, ts
    from . import accident as AC
    uid = inp["end_user"]
    row = _acc(ctx, uid, inp["case_id"])
    d = loads(row["data"])
    flags = [f for f in inp.get("flags") or [] if f in AC.HANDOFF_FLAGS]
    if flags:
        d["handoff"] = sorted(set((d.get("handoff") or []) + flags))
    step, ans, said = row["step"], (inp.get("answer") or "").strip().lower(), None
    if step == "safety":
        said = AC.safety(ans or None, _emergency(ctx.store, d["country"]))
        if said.get("handoff"):
            d["handoff"] = sorted(set((d.get("handoff") or []) + ["injuries"]))
        if said["done"]:
            d["safety"] = ans
            step, said = "duties", None
    elif ans in ("done", "skip", "next"):
        step = AC.STEPS[min(AC.STEPS.index(step) + 1, AC.STEPS.index("notify"))]
    if inp.get("facts") and row["step"] in ("statement", "photos", "duties"):
        clean = {k: v for k, v in inp["facts"].items() if k in ("date", "time", "place", "your_vehicle", "your_insurer", "witnesses", "injuries")}
        d["facts"] = {**(d.get("facts") or {}), **clean}
    ctx.store.x("update accident_cases set data = ?, step = ?, updated_at = ? where account = ? and id = ?", dumps(d), step, ts(), ctx.account, row["id"])
    return await _acc_view(ctx, _acc(ctx, uid, row["id"]), said), 200, None


async def accident_photo(ctx, inp: dict):
    """cards.accident_photo — one guided shot: sealed under the person's own Keep key, recorded as hashed, timestamped evidence."""
    import base64 as _b64
    import hashlib as _h
    from agapi import keep as K
    from .. import engine as E, keep_ops as KO, rules as R
    from ..store import dumps, ts
    from . import accident as AC, claims as CL
    uid = inp["end_user"]
    row = _acc(ctx, uid, inp["case_id"])
    if row["step"] == "safety":
        raise AgapiError("invalid_input", "Safety first: answer whether anyone is hurt before anything else.", {"path": "/case_id", "rule": "safety_first"})
    if inp["shot"] not in AC.SHOTS:
        raise AgapiError("invalid_input", "That isn't one of the guided shots.", {"path": "/shot", "rule": "enum"})
    try:
        raw = _b64.b64decode(inp["content_base64"], validate=True)
    except Exception:
        raise AgapiError("invalid_input", "The photo isn't valid base64.", {"path": "/content_base64", "rule": "base64"})
    CL._tables(ctx.store)
    dek = await KO._dek(ctx, uid, create=True)
    fid = R.new_id("cfl")
    sha = "sha256:" + _h.sha256(raw).hexdigest()
    nonce, ct = K.seal(dek, K.item_aad(ctx.account, uid, fid, "claim_file"), {"b64": _b64.b64encode(raw).decode()})
    ctx.store.x("insert into claim_files (account, id, case_id, end_user, kind, name, media_type, sha256, size, nonce, ciphertext, created_at) "
                "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ctx.account, fid, row["id"], uid, "photos", f"{inp['shot']}.jpg",
                inp.get("media_type") or "image/jpeg", sha, len(raw), nonce, ct, ts())
    now = ts()[:19] + "Z"
    eid = E._evidence(ctx, "cards.accident_photo", None, None, {"case_id": row["id"], "shot": inp["shot"]}, None, None,
                      [{"service": "photo", "retrieved_at": now, "sha256": sha, "snippet": R.wrap(AC.SHOT_SAY[inp["shot"]], "agapi", now)}])
    raw = None
    d = loads(row["data"])
    d["photos"] = [p for p in d.get("photos") or [] if p["shot"] != inp["shot"]] + [{"shot": inp["shot"], "file_id": fid, "sha256": sha, "evidence_id": eid, "at": now}]
    ctx.store.x("update accident_cases set data = ?, updated_at = ? where account = ? and id = ?", dumps(d), ts(), ctx.account, row["id"])
    return {**(await _acc_view(ctx, _acc(ctx, uid, row["id"]))), "saved": {"shot": inp["shot"], "sha256": sha, "evidence_id": eid, "at": now}}, 201, eid


async def accident_notify(ctx, inp: dict):
    """cards.accident_notify — tell the rental company (its own address, from its terms) with the evidence pack, on the person's yes; then
    the claim for the card insurer is prepared (its own read-back and yes: cards.claim_file)."""
    import base64 as _b64
    from .. import adapters as AD, config, engine as E, rules as R
    from ..store import dumps, ts
    from . import claims as CL
    uid = inp["end_user"]
    row = _acc(ctx, uid, inp["case_id"])
    if row["step"] != "notify":
        raise AgapiError("invalid_input", "One step at a time: finish the steps before notifying.", {"path": "/case_id", "rule": "step_order", "step": row["step"]})
    d = loads(row["data"])
    if d.get("notify_act"):
        raise AgapiError("already_completed", "The rental company was already notified.", {"act_id": d["notify_act"]})
    rental, rnote = rental_terms_for(ctx.store, d["country"], d.get("rental_company") or "")
    to = next((c["value"] for c in rental or [] if c["field"] == "contact_email"), None)
    rep = next((c for c in rental or [] if c["field"] == "accident_report_deadline_hours"), None)
    f = d.get("facts") or {}
    facts_txt = "\n".join([f"Date: {f.get('date') or d['at'][:10]}", f"Time: {f.get('time') or d['at'][11:16]}", f"Place: {f.get('place') or d['place']}",
                           f"Vehicle: {json.dumps(f.get('your_vehicle') or {}, ensure_ascii=False)}", f"Injuries: {f.get('injuries', 'none reported')}",
                           "Circumstances boxes, sketch, signature: left to the drivers (not filled by Sasha)."])
    photos = d.get("photos") or []

    async def into_claim() -> Optional[str]:
        if not d.get("card_item_id") or d.get("claim_case_id"):
            return d.get("claim_case_id")
        try:
            got, _, _ = await CL.start(ctx, {"end_user": uid, "card_item_id": d["card_item_id"], "kind": "rental_damage",
                                             "incident_date": (f.get("date") or d["at"][:10]), "description": f"Accident at {f.get('place') or d['place']}."})
        except AgapiError:
            return None
        if got.get("case_id"):
            for p in photos:
                ctx.store.x("update claim_files set case_id = ? where account = ? and id = ? and case_id = ?", got["case_id"], ctx.account, p["file_id"], row["id"])
            return got["case_id"]
        return None
    if not to:
        d["claim_case_id"] = await into_claim()
        d["notify_say"] = (f"{d.get('rental_company') or 'The rental company'}'s terms I've read don't give an address for accident reports"
                           + (f" ({rnote})" if rnote else "") + ": call them or use their app. The statement and photos are ready to send.")
        ctx.store.x("update accident_cases set data = ?, updated_at = ? where account = ? and id = ?", dumps(d), ts(), ctx.account, row["id"])
        return {**(await _acc_view(ctx, _acc(ctx, uid, row["id"]))), "state": "draft_only", "draft": facts_txt}, 200, None
    lines = [f"Report the accident to {d['rental_company']} at {to} (the address in its terms).", *facts_txt.splitlines(),
             f"With: {len(photos)} photo(s), each recorded with its fingerprint and time.",
             (f"Their deadline: within {rep['value']} hours (their terms: \"{rep['quote']}\")." if rep else "Their terms I've read give no deadline: this goes now.")]
    body = "\n".join(["Hello,", f"I'm reporting an accident with my rental car from {d['rental_company']}.", facts_txt,
                      "Photos: " + (", ".join(f"{p['shot']} (sha256 {p['sha256'][7:19]}…)" for p in photos) or "none yet") + ".",
                      "Please confirm receipt and tell me what else you need.", "Thank you."])
    if ctx.mode == "live":
        AD.precheck_live("messages.send_email", {"to": {"address": to}}, ctx.store, ctx.account)
    payload = {"case_id": row["id"], "to": to, "body_sha256": R.sha256(body), "photos": [p["sha256"] for p in photos]}
    psha = R.sha256(payload)
    rb = ctx.store.one("select r.* from read_backs r join intents i on i.account = r.account and i.id = r.intent_id where r.account = ? "
                       "and i.operation = 'cards.accident_notify' and i.state = 'open' and i.end_user = ? and r.payload_sha256 = ? "
                       "order by r.created_at desc", ctx.account, uid, psha)
    if not rb or E._rb_state(rb) in ("expired", "void"):
        iid = R.new_id("int")
        ctx.store.x("insert into intents (account, id, operation, end_user, state, created_at) values (?, ?, 'cards.accident_notify', ?, 'open', ?)",
                    ctx.account, iid, uid, ts())
        rb = E._new_read_back(ctx, iid, "cards.accident_notify", lines, payload, None, uid, True)
    it = ctx.store.one("select * from intents where account = ? and id = ?", ctx.account, rb["intent_id"])
    apv = E._check_and_consume(ctx, rb, {"intent_id": it["id"], "operation": "cards.accident_notify", "lines": lines, "payload": payload}, 1)
    aid = R.new_id("act")
    sent = await AD.messenger("email", ctx.mode).adeliver(ctx.store, ctx.account, uid, to, "email",
                                                          f"From: {config.EMAIL_FROM}\nReply-To: {config.EMAIL_FROM}\nSubject: Accident report — rental car\n\n{body}", None)
    now = ts()[:19] + "Z"
    outcome = {"kind": "REQUESTED", "reference": sent or f"sbx_accident_{aid[-8:].lower()}",
               "target_words": R.wrap(f"Accident reported to {d['rental_company']} by email" + (" (sandbox: captured, never sent)" if not sent else "") + ".", "agapi", now)}
    E._new_act(ctx, aid, it, "accident_notify", None, outcome, target=row["id"])
    eid = E._evidence(ctx, "cards.accident_notify", aid, it["id"], {"case_id": row["id"]}, outcome, apv,
                      [{"service": "message", "retrieved_at": now, "sha256": R.sha256(body), "snippet": R.wrap(f"to {to}", "agapi", now)}])
    ctx.store.x("update acts set evidence_id = ? where account = ? and id = ?", eid, ctx.account, aid)
    ctx.store.x("update intents set state = 'confirmed' where account = ? and id = ?", ctx.account, it["id"])
    d["notify_act"] = aid
    d["claim_case_id"] = await into_claim()
    d["notify_say"] = (f"Sent to {d['rental_company']}." + (" Next: your card's insurer — I'll read that claim back too, and it goes on your yes."
                                                              if d.get("claim_case_id") else ""))
    ctx.store.x("update accident_cases set data = ?, step = 'claim', updated_at = ? where account = ? and id = ?", dumps(d), ts(), ctx.account, row["id"])
    return {**(await _acc_view(ctx, _acc(ctx, uid, row["id"]))), "state": "sent", "outcome": outcome, "evidence_id": eid}, 201, eid


OPS.update({"cards.accident_start": accident_start, "cards.accident_step": accident_step, "cards.accident_photo": accident_photo,
            "cards.accident_notify": accident_notify})
