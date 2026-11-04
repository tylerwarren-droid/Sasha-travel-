"""Sasha 334 · GROUP MOVEMENT v1 COMPLETE — book / swap / cancel from the master list through AgAPI (CR 163, TEST), and ONE invoice.
docs/sasha/S-334-group-v1.md.

THE ONE RECORDS: each worker's ONE trip (Sasha: trips + trip_basket_items — 332), each worker trip's ONE booking record (AgAPI's
group_bookings — CR 163), each person's ONE vault (the Keep — 333). Sasha passes AgAPI only keep:<id> REFERENCES; AgAPI opens them through
Sasha's resolver (keep_resolver.py) inside its one supplier call, under a grant Sasha makes for THAT worker at THAT moment.

  prepare(account, action, who)   AgAPI's read-back for each worker in the action (group.book / group.swap / group.cancel, nothing done),
                                  held as ONE card → its lines + Yes / No (sasha.yes_buttons — 330's one place)
  confirm(account, card, choice)  once (claimed): No → nothing; Yes → each worker: the organiser's approval of THAT read-back (the app tap,
                                  the WhatsApp reply, or in TEST the sandbox's simulated yes on their words) → the act → the worker's trip
                                  rows settled (booked / cancelled), live on the master list
  invoice(account)                ONE invoice per movement, from AgAPI's records: one line per worker, swaps and cancellations with their
                                  refunds, the total, the REAV note — TEST in test mode
"""
from __future__ import annotations

import logging
import secrets
import time
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("booking_signer.group_book")
FAMILY = "group"
CARD_S = 900
_CARDS: Dict[str, Dict[str, Any]] = {}   # card id → {account, action, items, lines, at} — what the organiser is shown, held for their yes
HOTEL_WORDS = ("marriott", "bonvoy", "hilton", "hyatt", "ihg", "accor", "all ", "meliá", "melia", "nh ", "iberostar", "radisson",
               "wyndham", "barceló", "barcelo", "best western", "choice", "leading hotels")


# ── the ONE transport (agapi_route.post), on the group family (the sandbox: CR 163 is TEST) ─────────────────────────────────

async def _call(account: str, op: str, body: dict, approval: Optional[str] = None) -> Dict[str, Any]:
    if CALL is not None:
        return await CALL(op, body, approval)
    from agapi import agapi_route as AR
    url, key = await AR.client_for(FAMILY, account)
    if not key:
        return {"ok": False, "error": {"code": "not_configured", "message": "AgAPI's sandbox key isn't set here"}}
    h = {"Authorization": f"Bearer {key}", "content-type": "application/json", "Idempotency-Key": "s334_" + secrets.token_hex(12),
         **({"AgAPI-Approval-Id": approval} if approval else {})}
    return await AR.post(url, key, op, body, h, 60.0)


CALL = None   # tests replace it: (op, body, approval) → envelope


async def _organiser(account: str) -> Optional[str]:
    r = await _call(account, "users.register", {"external_ref": f"sasha:{account}"})
    return ((r.get("result") or {}).get("end_user_id")) if r.get("ok") else None


# ── a worker as AgAPI takes them: names + Keep REFERENCES only ───────────────────────────────────────────────────────────────

async def worker_of(m: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from . import traveller_vault as TV
    v = await TV.vault_view(m)
    if not v["refs"].get("passport"):
        return None
    airline, hotel = [], []
    for name, ref in zip(v["loyalty"], v["refs"]["loyalty"]):
        (hotel if any(w in f"{name.lower()} " for w in HOTEL_WORDS) else airline).append(ref)
    given, _, family = m["name"].partition(" ")
    return {"key": m["id"], "given_name": given, "family_name": family or given,
            "keep": {"passport": v["refs"]["passport"], "loyalty": airline[:4], "hotel_loyalty": hotel[:4]}}


def _refs(w: Dict[str, Any]) -> List[str]:
    k = w.get("keep") or {}
    return [k.get("passport")] + list(k.get("loyalty") or []) + list(k.get("hotel_loyalty") or [])


async def _items(account: str, m: Dict[str, Any], mv: Dict[str, Any]) -> Tuple[Optional[List[dict]], Optional[str]]:
    """The worker's flights out and back and the stay, as AgAPI's own offers (AgAPI books only what it found) — the planned flight when
    AgAPI has it, else its cheapest on that route and day. PATCH (said): Sasha planned with its own Duffel search (332); AgAPI finds again."""
    items = []
    for frm, to, day in ((m["home_city"], mv["destination"], m["out_date"]), (mv["destination"], m["home_city"], m["back_date"])):
        r = await _call(account, "travel.find_flights", {"origin": {"query": frm}, "destination": {"query": to}, "date": str(day)[:10], "passengers": 1})
        offers = (r.get("result") or {}).get("offers") or [] if r.get("ok") else []
        if not offers:
            return None, f"no flight {frm} → {to} on {str(day)[:10]} on AgAPI's sandbox" + (f" ({(r.get('error') or {}).get('code')})" if not r.get("ok") else "")
        items.append({"kind": "flight", "ref": offers[0]["offer_ref"]})
    nights = max(1, (date.fromisoformat(str(m["back_date"])[:10]) - date.fromisoformat(str(m["out_date"])[:10])).days)
    r = await _call(account, "travel.find_stays", {"city": {"query": mv.get("hotel_area") or mv["destination"], "country": "ES"},
                                                   "check_in": str(m["out_date"])[:10], "nights": nights, "party": 1})
    res = (r.get("result") or {}) if r.get("ok") else {}
    stays = res.get("stays") or res.get("offers") or []
    if not stays and mv.get("hotel_area"):   # the area as a place AgAPI doesn't know: the destination itself
        r = await _call(account, "travel.find_stays", {"city": {"query": mv["destination"], "country": "ES"}, "check_in": str(m["out_date"])[:10],
                                                       "nights": nights, "party": 1})
        res = (r.get("result") or {}) if r.get("ok") else {}
        stays = res.get("stays") or res.get("offers") or []
    if not stays:
        return None, "no stay found on AgAPI's sandbox"
    s = stays[0]
    items.append({"kind": "stay", "ref": s.get("stay_ref") or s.get("offer_ref") or s.get("ref"), "at": f"{str(m['out_date'])[:10]}T15:00:00", "nights": nights})
    return items, None


async def _records(account: str) -> List[dict]:
    org = await _organiser(account)
    r = await _call(account, "group.bookings", {"end_user": org}) if org else {}
    return ((r.get("result") or {}).get("bookings") or []) if r.get("ok") else []


def _live_record(records: List[dict], member_id: str) -> Optional[dict]:
    return next((b for b in reversed(records) if (b.get("worker") or {}).get("key") == member_id and b.get("state") == "booked"), None)


# ── prepare: AgAPI's read-backs, ONE card ───────────────────────────────────────────────────────────────────────────────────

def summary_taps(skipped: List[dict]) -> List[Dict[str, Any]]:
    """Sasha 336 · "Book all" with nothing bookable: a SHORT list with taps — never a paragraph per worker.
    "18 over limit — book anyway?" (the same card and Yes, over_ok for exactly those) · "2 need their vault — invite" (their links)."""
    by: Dict[str, List[dict]] = {}
    for x in skipped:
        by.setdefault(x.get("kind") or "other", []).append(x)
    out: List[Dict[str, Any]] = []
    if by.get("over_limit"):
        n = len(by["over_limit"])
        out.append({"label": f"{n} over limit — book anyway?", "act": {"action": "book", "who": [x["name"] for x in by["over_limit"]], "over_ok": True}})
    if by.get("needs_vault"):
        n = len(by["needs_vault"])
        out.append({"label": f"{n} need{'s' if n == 1 else ''} their vault — invite", "invite": [x["member_id"] for x in by["needs_vault"]]})
    rest = [x for k, v in by.items() if k not in ("over_limit", "needs_vault") for x in v]
    if rest:
        out.append({"label": f"{len(rest)} not bookable now — " + "; ".join(f"{x['name']}: {x['why']}" for x in rest[:3]) + ("…" if len(rest) > 3 else "")})
    return out


async def prepare(account: str, action: str, who: Optional[List[str]] = None, swap_to: Optional[str] = None,
                  over_ok: bool = False, newcomer: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """→ {status: awaiting_yes, read_back, read_back_id (the card), ask, skipped} or {status: nothing, say}."""
    from . import groups as G
    st = G.store()
    mv = await st.movement(account)
    if not mv:
        return {"status": "nothing", "say": "There's no group movement yet."}
    members = await st.members(mv["id"])
    by_name = {m["name"].lower(): m for m in members}
    org = await _organiser(account)
    if not org:
        return {"status": "nothing", "say": "AgAPI's sandbox didn't answer — nothing was prepared."}
    view = {r["member_id"]: r for r in (await G.view(account))["rows"]}
    items, skipped, lines = [], [], []
    records = await _records(account) if action in ("swap", "cancel") else []
    if action == "book":
        pick = [by_name[w.lower()] for w in who or [] if w.lower() in by_name] if who else members
        for m in pick:
            st_ = view.get(m["id"], {}).get("status")
            if st_ == "booked":
                continue
            w = await worker_of(m)   # Sasha 336 · the vault first: without a passport nobody can be booked, over the limit or not
            if not w:
                skipped.append({"name": m["name"], "member_id": m["id"], "kind": "needs_vault", "why": "no passport in their vault yet (invite them)"})
                continue
            if st_ == "over limit" and not (who and over_ok):   # never without the organiser's explicit yes to THAT worker over the limit
                skipped.append({"name": m["name"], "member_id": m["id"], "kind": "over_limit",
                                "why": "over the limit — say \"book " + m["name"].split()[0] + " anyway\" to include them"})
                continue
            its, why = await _items(account, m, mv)
            if not its:
                skipped.append({"name": m["name"], "member_id": m["id"], "kind": "not_found", "why": why})
                continue
            items.append({"op": "group.book", "member": m["id"], "name": m["name"], "worker": w,
                          "body": {"end_user": org, "worker": w, "items": its}, "over": st_ == "over limit"})
    elif action == "swap":
        a, b = (by_name.get((who or [""])[0].lower()), by_name.get((swap_to or "").lower()))
        if not a:
            return {"status": "nothing", "say": f"{(who or [''])[0] or 'The one who leaves'} isn't on the list."}
        rec = _live_record(records, a["id"])
        if not rec:
            return {"status": "nothing", "say": f"{a['name']} has no booking to swap."}
        if not b:   # Sasha 336 · the newcomer isn't on the list: the swap adds them (the list's own upload) and invites them, in this flow
            nc = newcomer or {}
            if not (swap_to or "").strip() or not str(nc.get("city") or "").strip():
                return {"status": "needs_details", "need": ["city", "grade"],
                        "say": f"{swap_to or 'The newcomer'} isn't on the list yet — give their home city and grade, and I'll add them "
                               "and invite them to their vault."}
            line = ", ".join([swap_to.strip(), str(nc["city"]).strip(), str(mv.get("starts_on") or ""), str(mv.get("ends_on") or ""),
                              str(nc.get("grade") or "worker").strip()])
            await G.upload(account, G.read_text(line), mv["id"])
            b = next((m for m in await st.members(mv["id"]) if m["name"].lower() == swap_to.strip().lower()), None)
            if not b:
                return {"status": "nothing", "say": f"{swap_to} couldn't be added to the list — check the name and city."}
        w = await worker_of(b)
        if not w:
            from . import traveller_vault as TV
            inv = await TV.invite(account, [b["id"]])
            return {"status": "needs_vault", "added": b["name"] if newcomer else None, "say": (f"{b['name']} is on the list now. " if newcomer else "")
                    + f"{b['name']}'s passport isn't in their vault yet — I've "
                    + ("emailed them their secure link." if inv.get("emailed") else "made their secure link (on the master list to forward).")
                    + " I'll swap as soon as it's there.", "links": inv.get("forward") or []}
        items.append({"op": "group.swap", "member": b["id"], "from_member": a["id"], "name": f"{a['name']} → {b['name']}", "worker": w,
                      "body": {"end_user": org, "booking_id": rec["booking_id"], "worker": w}})
    elif action == "cancel":
        for nm in who or []:
            m = by_name.get(nm.lower())
            rec = _live_record(records, m["id"]) if m else None
            if not rec:
                skipped.append({"name": nm, "why": "no booking to cancel"})
                continue
            items.append({"op": "group.cancel", "member": m["id"], "name": m["name"], "body": {"end_user": org, "booking_id": rec["booking_id"]}})
    for it in items:   # AgAPI's read-back for each (nothing is done without the approval)
        r = await _call(account, it["op"], it["body"])
        e = r.get("error") or {}
        if e.get("code") != "approval_required":
            skipped.append({"name": it["name"], "why": e.get("message") or "AgAPI didn't give a read-back"})
            it["skip"] = True
            continue
        d = e.get("details") or {}
        it.update(read_back_id=d["read_back_id"], sha=d.get("read_back_sha256") or "", lines=list((d.get("read_back") or {}).get("lines") or []))
        lines += it["lines"] + ([f"⚠ {it['name']} is OVER the group's limit — included only because you asked."] if it.get("over") else []) + [""]
    items = [i for i in items if not i.get("skip")]
    if not items:
        taps = summary_taps(skipped)
        return {"status": "nothing", "say": (" · ".join(t["label"] for t in taps) if taps else "Nothing to do."), "taps": taps, "skipped": skipped}
    cid = "grp_" + secrets.token_hex(10)
    _CARDS[cid] = {"account": account, "action": action, "items": items, "at": time.time()}
    n = len(items)
    verb = {"book": "Book", "swap": "Swap", "cancel": "Cancel"}[action]
    ask = {"book": f"Book {'these ' + str(n) if n > 1 else items[0]['name']}? Everything is on the card (TEST — nothing is charged now).",
           "swap": f"Swap {items[0]['name']}? The difference is on the card (TEST).",
           "cancel": f"Cancel {', '.join(i['name'] for i in items)}? The refund is on the card (TEST)."}[action]
    return {"status": "awaiting_yes", "action": action, "read_back": [l for l in lines if l is not None][:400], "read_back_id": cid, "ask": ask,
            "verb": verb, "skipped": skipped, "how": "Say `ask` word for word — nothing happens until they say yes."}


# ── confirm: once, the organiser's yes → each act ───────────────────────────────────────────────────────────────────────────

async def _approval(account: str, it: dict, said: str) -> Optional[str]:
    from agapi import agapi_route as AR, venue_submit as VS
    with AR.using(await AR.target_for(FAMILY, account)):   # the read-back is the group family's target (pinned: the sandbox) — its approval goes there too
        if VS.TAP.get() is not None:
            r = await VS.in_app_tap(account, it["read_back_id"], it["sha"])
            return r.get("approval_id") if r.get("ok") else None
        if VS.WA.get() is not None:
            r = await VS.whatsapp_tap(account, it["read_back_id"], it["sha"])
            return r.get("approval_id") if r.get("ok") else None
    r = await _call(account, "sandbox.simulate_approval", {"read_back_id": it["read_back_id"], "said": (said or "Yes, go ahead.")[:200]})
    return ((r.get("result") or {}).get("approval_id")) if r.get("ok") else None


SETTLE = None   # tests replace it: (account, item_id, state, reference) → None


async def _settle(account: str, trip_id: Optional[str], state: str, parts: List[dict]) -> None:
    """The worker's ONE trip follows AgAPI's record: its rows booked (with their references) or cancelled — the master list reads them."""
    if not trip_id:
        return
    from . import groups as G
    rows = [r for r in await G._items(account, trip_id) if r.get("state") in ("suggested", "chosen", "booked")]
    refs = {"flight": [p.get("reference") for p in parts if p.get("kind") == "flight"], "stay": [p.get("reference") for p in parts if p.get("kind") == "stay"]}
    for r in rows:
        kind = "flight" if r.get("kind") == "flight" else "stay"
        ref = refs[kind].pop(0) if refs[kind] else None
        if SETTLE is not None:
            await SETTLE(account, r["id"], state, ref)
            continue
        from . import basket as BK
        await BK._settle(account, r["id"], state, booking_reference=ref)


async def confirm(account: str, card_id: str, choice: str, said: str = "") -> Dict[str, Any]:
    from . import groups as G
    from . import keep_resolver as KR
    c = _CARDS.get(card_id)
    if not c or c["account"] != account or time.time() - c["at"] > CARD_S:
        return {"status": "nothing_waiting", "say": "That card's already answered."}
    _CARDS.pop(card_id, None)   # once: a second tap finds nothing (and card_tap's durable claim holds it across restarts)
    if choice not in ("group_yes", "yes"):
        return {"status": "kept", "say": "Kept — nothing changed."}
    st = G.store()
    mv = await st.movement(account)
    members = {m["id"]: m for m in await st.members(mv["id"])}
    done, failed = [], []
    for it in c["items"]:
        apv = await _approval(account, it, said or "Yes, go ahead.")
        if not apv:
            failed.append({"name": it["name"], "why": "the yes wasn't accepted for this one"})
            continue
        refs = [r for r in _refs(it.get("worker") or {}) if r]
        KR.grant(it.get("member"), refs)   # THIS worker's references, for THIS act only
        try:
            r = await _call(account, it["op"], it["body"], approval=apv)
        finally:
            KR.revoke(refs)
        if not r.get("ok"):
            failed.append({"name": it["name"], "why": (r.get("error") or {}).get("message") or "AgAPI refused"})
            continue
        res = r.get("result") or {}
        parts = res.get("parts") or []
        if it["op"] == "group.book":
            await _settle(account, members[it["member"]].get("trip_id"), "booked", parts)
        elif it["op"] == "group.cancel":
            await _settle(account, members[it["member"]].get("trip_id"), "cancelled", [])
        else:   # a swap: the one who leaves — cancelled; the one who comes — their trip, booked with the new references
            await _settle(account, members[it["from_member"]].get("trip_id"), "cancelled", [])
            await _swap_in(account, mv, members[it["member"]], parts)
        done.append({"name": it["name"], "state": res.get("state"), "parts": [p.get("reference") for p in parts],
                     **({"refund": res["refund"]} if res.get("refund") else {}), **({"difference": res["difference"]} if res.get("difference") else {})})
    verb = {"book": "booked", "swap": "swapped", "cancel": "cancelled"}[c["action"]]
    say = (f"Done — {len(done)} {verb} (TEST)." if done else "Nothing was done.") + \
        (" Not done: " + "; ".join(f"{f['name']} ({f['why']})" for f in failed) + "." if failed else "") + " The master list shows it now."
    return {"status": "done", "done": done, "failed": failed, "say": say}


async def _swap_in(account: str, mv: dict, m: dict, parts: List[dict]) -> None:
    """The worker who comes in: their ONE trip gets the booked parts (references; prices from AgAPI's record), so the list shows them."""
    from . import groups as G, basket as BK
    tid = await G.store().trip_of(account, m, f"{mv['company']} — {m['name']} to {mv['destination']}")
    for p in parts:
        price = (p.get("price") or {})
        row = {"provider": "agapi_group", "provider_ref": p.get("reference"), "day": str(m.get("out_date") or "")[:10] or None, "party": 1,
               "price_amount": (price.get("amount_minor") or 0) / 100 if price else None, "price_currency": price.get("currency") or "EUR",
               "price_source": "quoted", "snapshot": {"from_swap": True, "reference": p.get("reference")}}
        await BK.suggest(account, tid, "flight" if p.get("kind") == "flight" else "stay", [row], slice_key=f"swap {p.get('reference')}", replace=False)
    await _settle(account, tid, "booked", parts)


# ── ONE invoice per movement, from AgAPI's records ──────────────────────────────────────────────────────────────────────────

REAV = ("Travel services arranged by Kanoe. Spanish travel-agency register (REAV) number: to be added before invoices go live. "
        "Package-travel rights under Spain's Real Decreto Legislativo 1/2007 apply where the booking is a package.")


def _eur(minor: int) -> str:
    return f"€{minor / 100:,.2f}"


async def invoice(account: str) -> Dict[str, Any]:
    from . import groups as G
    st = G.store()
    mv = await st.movement(account)
    if not mv:
        return {"why": "there's no group movement yet"}
    members = {m["id"]: m for m in await st.members(mv["id"])}
    recs = await _records(account)
    lines, adj, total = [], [], 0
    for b in recs:
        m = members.get((b.get("worker") or {}).get("key")) or {}
        price = sum(((p.get("price") or {}).get("amount_minor") or 0) for p in b.get("parts") or [])
        nights = max(1, (date.fromisoformat(str(m["back_date"])[:10]) - date.fromisoformat(str(m["out_date"])[:10])).days) if m.get("out_date") and m.get("back_date") else None
        row = {"who": b["worker"]["name"], "route": f"{m.get('home_city') or '?'} ⇄ {mv['destination']}", "dates": f"{m.get('out_date')} – {m.get('back_date')}",
               "hotel_nights": nights, "price": _eur(price), "references": [p.get("reference") for p in b.get("parts") or []], "state": b["state"]}
        if b["state"] == "booked":
            total += price
            lines.append(row)
        elif b["state"] == "cancelled":
            adj.append({**row, "what": "Cancelled", "refund": _eur(price)})
        elif b["state"] == "swapped_out":
            fl = sum(((p.get("price") or {}).get("amount_minor") or 0) for p in b.get("parts") or [] if p.get("kind") == "flight")
            nxt = next((x for x in recs if x["booking_id"] == b.get("replaced_by")), None)
            adj.append({**row, "what": f"Swapped for {nxt['worker']['name'] if nxt else 'another worker'} (flights cancelled and rebooked; the stay renamed)",
                        "refund": _eur(fl)})
    test = True
    return {"to": mv.get("company"), "movement": {k: mv.get(k) for k in ("destination", "starts_on", "ends_on", "hotel_area")},
            "number": f"KAN-{str(mv['id'])[:8].upper()}{'-TEST' if test else ''}", "date": date.today().isoformat(), "test": test,
            "lines": lines, "adjustments": adj, "total": _eur(total), "total_minor": total, "currency": "EUR", "reav": REAV}


__all__ = ["prepare", "confirm", "invoice", "worker_of", "REAV"]


# the invoice's own link (WhatsApp): signed, the organiser's movement only, 30 days — its own key (never a vault link's)
def _ikey() -> bytes:
    import hashlib
    import os
    k = os.getenv("SASHA_BOOKING_KEY", "").strip()
    if not k:
        raise RuntimeError("no signing secret (SASHA_BOOKING_KEY)")
    return hashlib.sha256(("sasha-group-invoice:" + k).encode()).digest()


def invoice_token(owner: str, movement_id: str, now: Optional[float] = None) -> str:
    import base64
    import hmac
    import hashlib
    import json
    body = json.dumps({"o": owner, "v": movement_id, "e": int((now or time.time()) + 30 * 86400)}, separators=(",", ":")).encode()
    b = lambda x: base64.urlsafe_b64encode(x).decode().rstrip("=")   # noqa: E731
    return b(body) + "." + b(hmac.new(_ikey(), body, hashlib.sha256).digest())


def read_invoice_token(token: str, now: Optional[float] = None) -> Optional[Dict[str, str]]:
    import base64
    import hmac
    import hashlib
    import json
    try:
        a, s = token.split(".")
        un = lambda x: base64.urlsafe_b64decode(x + "=" * (-len(x) % 4))   # noqa: E731
        body, sig = un(a), un(s)
    except Exception:
        return None
    if not hmac.compare_digest(sig, hmac.new(_ikey(), body, hashlib.sha256).digest()):
        return None
    d = json.loads(body)
    return {"owner": d["o"], "movement": d["v"]} if d.get("e", 0) >= (now or time.time()) else None


def invoice_link(owner: str, movement_id: str) -> str:
    import os
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/") + "/invoice/" + invoice_token(owner, movement_id)
