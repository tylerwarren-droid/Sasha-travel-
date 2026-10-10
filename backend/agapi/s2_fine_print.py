"""CR 74 · S2'S FINE PRINT — "what does my card cover?" answered only from the card's own terms. /s2 ONLY: these four tools are added in
/s2's own tool selection (app/agent/sasha.py) and run there; S1 (/next) never sees them (its tool list and fingerprint are unchanged).
The work is AgAPI's (cards.mine / intake / ask / which, on the sandbox by default); Sasha only asks and says.

  my_cards     the person's cards (products only: issuer · product · network), each with whether its official terms were read
  add_card     a photo of the card or a Wallet screenshot (uploaded on /s2: POST /api/agent/s2/card-image → a card_image_ref, kept in
               this server's memory for 10 minutes, read once, never on disk) — or the card's name → its PRODUCT, never a digit
  card_cover   "what does my X cover for Y?" → AgAPI's answer, built from the card's quoted terms: say its `say` text as given
  which_card   "which of my cards for this?" → the cards ranked by quoted FX fee, cover and points — information, never advice
Where: SASHA_FINE_PRINT_VIA = sandbox (default) | live.  Keys: SASHA_AGAPI_TEST_KEY (sandbox) / SASHA_AGAPI_KEY (live). Never printed."""
from __future__ import annotations

import base64
import json
import os
import re
import secrets
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

TOOL_NAMES = ("my_cards", "add_card", "card_cover", "which_card")
SAY_AS_GIVEN = ("Say `say` as given: it's built from the card's own terms, quoted. Never add cover the quotes don't state, never say "
                "'you're covered' without the quote, and never present it as advice.")
TOOLS = [
    {"name": "my_cards", "description": "The person's cards — products only (issuer, product, network), never a number — and whether each "
                                        "card's official terms have been read.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "add_card", "description": (
        "Add one of the person's cards: from the photo or Wallet screenshot they uploaded on this page (card_image_ref), or by its name "
        "(issuer + product). Only the card's PRODUCT is kept — never its number, not even the last four digits. If they type digits, "
        "don't repeat them; ask for the card's name instead."),
     "input_schema": {"type": "object", "properties": {"card_image_ref": {"type": "string"}, "issuer": {"type": "string"},
                                                       "product": {"type": "string"},
                                                       "network": {"type": "string", "enum": ["visa", "mastercard", "amex", "discover", "jcb", "unionpay", "diners", "other"]}}}},
    {"name": "card_cover", "description": (
        "What one of their cards covers — rental cars, trip delay, baggage, purchases, the FX fee, points, how to claim — answered ONLY "
        "from that card's official terms. " + SAY_AS_GIVEN + " If it says the terms don't say, say that and give the claims line."),
     "input_schema": {"type": "object", "properties": {"question": {"type": "string"}, "card": {"type": "string", "description": "which card, in their words"}},
                      "required": ["question"]}},
    {"name": "which_card", "description": (
        "Which of their cards for one purchase or trip: ranked by the FX fee, the cover that applies and the points, each reason quoted "
        "from the card's terms. Start with the framing line, as given. Never call a card 'recommended' or 'best'; say what each costs and covers."),
     "input_schema": {"type": "object", "properties": {"amount": {"type": "number"}, "currency": {"type": "string"},
                                                       "kind": {"type": "string", "enum": ["flight", "hotel", "car_rental", "dining", "groceries", "gas", "transit", "other"]}},
                      "required": ["amount", "currency"]}},
]

# ── CR 75 · the counter card, the accident playbook, claims (step 11: /s2's screens) ────────────────────────────────────
TOOL_NAMES = TOOL_NAMES + ("rental_cover", "accident", "accident_notify", "file_claim", "claim_status")
TOOLS += [
    {"name": "rental_cover", "description": (
        "The counter card for a car rental: which of their cards to pay with, and what to decline, keep and consider at the counter — each line "
        "quoted from the card's terms and the rental company's own terms for that country. Say the card's first line briefly; the card on screen "
        "has every line with its source. Never say they don't need insurance."),
     "input_schema": {"type": "object", "properties": {"country": {"type": "string", "description": "ISO code, e.g. PT"}, "rental_company": {"type": "string"},
                                                       "days": {"type": "integer"}}, "required": ["country", "rental_company"]}},
    {"name": "accident", "description": (
        "The accident playbook, one step at a time. Start it when they say they've had an accident (country, place, rental company if it's a "
        "rental). SAFETY FIRST: the first question is 'Is anyone hurt?' and nothing else comes until it's answered; if yes or not sure, tell "
        "them to call 112 now. Pass each answer of theirs ('no', 'yes', 'not sure', 'help is on the way', 'done') and the facts they give. "
        "Say each step's `say` as given. Never fill a fault box, never sign, never argue who's at fault. Injuries, a disputed fault, police "
        "charges or a claim against them: add the flag and say the hand-off line as given."),
     "input_schema": {"type": "object", "properties": {"answer": {"type": "string"}, "country": {"type": "string"}, "place": {"type": "string"},
                                                       "rental_company": {"type": "string"}, "card": {"type": "string"},
                                                       "flags": {"type": "array", "items": {"type": "string", "enum": ["injuries", "fault_disputed", "police_charges", "claim_against_me"]}},
                                                       "facts": {"type": "object"}}}},
    {"name": "accident_notify", "description": (
        "Tell the rental company about the accident with the photos and the statement's facts. The FIRST call returns the read-back — read it "
        "back and ask; call again only after they say yes, in a later turn."), "input_schema": {"type": "object", "properties": {}}},
    {"name": "file_claim", "description": (
        "File the card-insurance claim the accident (or a claim they started) prepared. The FIRST call returns the read-back — read it back "
        "and ask; call again only after they say yes, in a later turn."), "input_schema": {"type": "object", "properties": {}}},
    {"name": "claim_status", "description": "Their latest card claim: its state, deadlines, what's still missing and what the insurer replied.",
     "input_schema": {"type": "object", "properties": {}}},
]
_ACCIDENT: Dict[str, str] = {}     # account → the open accident case
_CLAIM: Dict[str, str] = {}        # account → the latest claim case
_PEND: Dict[str, dict] = {}        # account|op → {read_back_id, at} — the read-back said; their yes comes next turn

_IMAGES: Dict[str, dict] = {}      # card_image_ref → {account, media_type, b64, at} — memory only, 10 minutes, read once
_USERS: Dict[str, str] = {}        # account → AgAPI end_user
IMAGE_TTL_S, MAX_BYTES = 600, 5_000_000
MEDIA = {"image/png", "image/jpeg", "image/webp", "image/heic"}


def via() -> str:
    return "live" if os.getenv("SASHA_FINE_PRINT_VIA", "sandbox").strip().lower() == "live" else "sandbox"


def keep_image(account: str, raw: bytes, media_type: str) -> str:
    if media_type not in MEDIA:
        raise ValueError("a card is added from a photo or a screenshot")
    if len(raw) > MAX_BYTES:
        raise ValueError("the image is too large (5 MB at most)")
    now = time.time()
    for k in [k for k, v in _IMAGES.items() if now - v["at"] > IMAGE_TTL_S]:
        _IMAGES.pop(k, None)
    ref = "ci_" + secrets.token_urlsafe(12)
    _IMAGES[ref] = {"account": account, "media_type": media_type, "b64": base64.b64encode(raw).decode(), "at": now}
    return ref


async def _agapi(op: str, body: dict, approval: Optional[str] = None) -> Dict[str, Any]:
    import httpx
    live = via() == "live"
    url = (os.getenv("SASHA_AGAPI_URL", "https://agapi-live-production.up.railway.app") if live
           else os.getenv("SASHA_AGAPI_TEST_URL", "https://agapi-sandbox-production.up.railway.app")).rstrip("/")
    key = os.getenv("SASHA_AGAPI_KEY" if live else "SASHA_AGAPI_TEST_KEY", "").strip()
    if not key:
        return {"ok": False, "error": {"code": "not_configured", "message": "card fine print isn't switched on yet"}}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0)) as c:
            h = {"Authorization": f"Bearer {key}", "content-type": "application/json", "Idempotency-Key": "s2fp_" + secrets.token_hex(12)}
            if approval:
                h["AgAPI-Approval-Id"] = approval
            r = await c.post(f"{url}/v1/{op}", headers=h, content=json.dumps(body))
        return r.json()
    except Exception as e:
        return {"ok": False, "error": {"code": "unreachable", "message": type(e).__name__}}


CALL: Callable[..., Awaitable[Dict[str, Any]]] = _agapi   # tests replace it


async def _end_user(account: str) -> Optional[str]:
    if account in _USERS:
        return _USERS[account]
    r = await CALL("users.register", {"external_ref": f"sasha:{account}"})
    if r.get("ok"):
        _USERS[account] = r["result"]["end_user_id"]
        return _USERS[account]
    return None


def _fail(r: dict) -> Dict[str, Any]:
    e = r.get("error") or {}
    return {"ok": False, "error": {"code": e.get("code") or "unavailable", "message": e.get("message") or "card fine print didn't answer"}}


def _words(s: str) -> set:
    return {w for w in re.findall(r"[a-z]+", (s or "").lower()) if w not in {"my", "the", "card", "credit", "visa", "mastercard"}}


async def _card_item(uid: str, words: str) -> Optional[str]:
    mine = await CALL("cards.mine", {"end_user": uid})
    cards = (mine.get("result") or {}).get("cards") or []
    want = _words(words or "")
    pick = [c for c in cards if want and want <= _words(f"{c['issuer']} {c['product']}")] if want else (cards if len(cards) == 1 else [])
    return pick[0]["item_id"] if len(pick) == 1 else None


async def _with_yes(ctx, key: str, op: str, body: dict) -> Dict[str, Any]:
    """AgAPI's read-back first; their OWN words in a LATER turn are the yes (sandbox: AgAPI's rules decide; live: their tap)."""
    pend = _PEND.get(key)
    if pend and pend["at"] < ctx.started.timestamp():
        if via() == "sandbox":
            a = await CALL("sandbox.simulate_approval", {"read_back_id": pend["read_back_id"], "said": ctx.user_said or ""})
            if not a.get("ok"):
                return {"ok": False, "error": {"code": (a.get("error") or {}).get("code") or "no_explicit_yes",
                                               "message": "that wasn't a clear yes — ask them again before sending"}}
            apv = a["result"]["approval_id"]
        else:
            st = await CALL("approvals.status", {"read_back_id": pend["read_back_id"]})
            ap = ((st.get("result") or {}).get("approval") or {}) if st.get("ok") else {}
            if not ap.get("approval_id") or ap.get("state") != "valid":
                return {"ok": True, "result": {"status": "waiting_for_their_tap"}}
            apv = ap["approval_id"]
        r = await CALL(op, body, approval=apv)
        if r.get("ok"):
            _PEND.pop(key, None)
        return r
    r = await CALL(op, body)
    e = r.get("error") or {}
    if e.get("code") == "approval_required":
        d = e.get("details") or {}
        _PEND[key] = {"read_back_id": d["read_back_id"], "at": time.time()}
        if via() == "live":
            await CALL("approvals.request", {"read_back_id": d["read_back_id"], "channel": "link_sms"})
        lines = (d.get("read_back") or {}).get("lines") or []
        return {"ok": True, "result": {"status": "awaiting_yes", "read_back": lines, "ask": "Read this back and ask; it goes only on their yes, in their next message.",
                                       "render": {"kind": "read_back", "read_back": lines, "what": "email", "status": "ready"}}}
    return r


def _view(v: dict) -> dict:
    return {"kind": "accident", "view": v}


async def run_tool(ctx, name: str, args: dict) -> Dict[str, Any]:
    uid = await _end_user(ctx.account)
    if not uid:
        return {"ok": False, "error": {"code": "unavailable", "message": "card fine print didn't answer"}}
    if name == "rental_cover":
        r = await CALL("cards.rental_cover", {"end_user": uid, "country": str(args.get("country") or "").upper()[:2], "rental_company": args.get("rental_company") or "",
                                              **({"days": int(args["days"])} if args.get("days") else {})})
        if not r.get("ok"):
            return _fail(r)
        c = r["result"]
        first = (c["counter"]["decline"] or c["counter"]["check"] or c["counter"]["keep"] or [{"say": ""}])[0]["say"]
        return {"ok": True, "result": {"say": first, "card_to_use": c.get("card"), "framing": c["framing"], "how": SAY_AS_GIVEN,
                                       "render": {"kind": "counter_card", "card": c}}}
    if name == "accident":
        cid = _ACCIDENT.get(ctx.account)
        if not cid or (args.get("country") and args.get("place") and not args.get("answer")):
            item = await _card_item(uid, args.get("card") or "")
            r = await CALL("cards.accident_start", {"end_user": uid, "country": str(args.get("country") or "ES").upper()[:2], "place": args.get("place") or "",
                                                    "rental_company": args.get("rental_company") or "", **({"card_item_id": item} if item else {})})
            if not r.get("ok"):
                return _fail(r)
            _ACCIDENT[ctx.account] = r["result"]["case_id"]
            return {"ok": True, "result": {"say": r["result"]["say"], "step": "safety", "render": _view(r["result"])}}
        r = await CALL("cards.accident_step", {"end_user": uid, "case_id": cid, **({"answer": args["answer"]} if args.get("answer") else {}),
                                               **({"flags": args["flags"]} if args.get("flags") else {}), **({"facts": args["facts"]} if args.get("facts") else {})})
        if not r.get("ok"):
            return _fail(r)
        v = r["result"]
        return {"ok": True, "result": {"say": v.get("say"), "step": v["step"], **({"handoff": v["handoff"]} if v.get("handoff") else {}),
                                       "how": "Say `say` as given; then the hand-off line if there is one.", "render": _view(v)}}
    if name == "accident_notify":
        cid = _ACCIDENT.get(ctx.account)
        if not cid:
            return {"ok": False, "error": {"code": "no_accident", "message": "there's no accident case open"}}
        r = await _with_yes(ctx, f"{ctx.account}|accident_notify", "cards.accident_notify", {"end_user": uid, "case_id": cid})
        if r.get("ok") and (r["result"].get("claim_case_id")):
            _CLAIM[ctx.account] = r["result"]["claim_case_id"]
        if r.get("ok") and r["result"].get("state"):
            v = r["result"]
            return {"ok": True, "result": {"status": v["state"], "say": v.get("say"), "render": _view(v)}}
        return r if r.get("ok") else _fail(r)
    if name == "file_claim":
        cid = _CLAIM.get(ctx.account)
        if not cid:
            return {"ok": False, "error": {"code": "no_claim", "message": "there's no claim prepared yet"}}
        r = await _with_yes(ctx, f"{ctx.account}|file_claim", "cards.claim_file", {"end_user": uid, "case_id": cid})
        if r.get("ok") and r["result"].get("state"):
            return {"ok": True, "result": {"status": r["result"]["state"], "render": {"kind": "claim_status", "claim": r["result"]}}}
        return r if r.get("ok") else _fail(r)
    if name == "claim_status":
        cid = _CLAIM.get(ctx.account)
        if not cid:
            return {"ok": True, "result": {"say": "There's no claim open."}}
        r = await CALL("cards.claim_status", {"end_user": uid, "case_id": cid})
        if not r.get("ok"):
            return _fail(r)
        c = r["result"]
        return {"ok": True, "result": {"state": c["state"], "deadlines": [d["say"] for d in c["deadlines"]],
                                       "missing": [e["item"] for e in c["evidence"] if e.get("missing")], "replies": len(c.get("replies") or []),
                                       "render": {"kind": "claim_status", "claim": c}}}
    if name == "my_cards":
        r = await CALL("cards.mine", {"end_user": uid})
        if not r.get("ok"):
            return _fail(r)
        cards = r["result"]["cards"]
        return {"ok": True, "result": {"cards": [{"card": c["masked"], "status": c["status"]} for c in cards],
                                       "render": {"kind": "my_cards", "cards": [{"product": c["product"], "network": c["network"], "status": c["status"]} for c in cards]}}}
    if name == "add_card":
        ref = args.get("card_image_ref")
        if ref:
            img = _IMAGES.pop(ref, None)                                  # read once, then gone
            if not img or img["account"] != ctx.account:
                return {"ok": False, "error": {"code": "image_unknown", "message": "that picture isn't here any more — ask them to add it again"}}
            r = await CALL("cards.intake", {"end_user": uid, "image": {"media_type": img["media_type"], "content_base64": img["b64"]}})
            img = None
            if not r.get("ok"):
                return _fail(r)
            res = r["result"]
            return {"ok": True, "result": {"added": res.get("masked") or res["card"]["product"], "terms": "read" if res.get("terms") else "not read yet",
                                           "note": res["note"]}}
        if not args.get("issuer") or not args.get("product"):
            return {"ok": False, "error": {"code": "need_card", "message": "ask which card: the bank and the card's name, or a photo of it"}}
        r = await CALL("keep.put", {"end_user": uid, "type": "card_product",
                                    "value": {"issuer": args["issuer"], "product": args["product"], "network": args.get("network") or "other"}})
        if not r.get("ok"):
            return _fail(r)
        return {"ok": True, "result": {"added": r["result"]["masked"], "note": "Only the card's product was kept — never a number."}}
    if name == "card_cover":
        mine = await CALL("cards.mine", {"end_user": uid})
        if not mine.get("ok"):
            return _fail(mine)
        cards = mine["result"]["cards"]
        if not cards:
            return {"ok": True, "result": {"say": "I don't know your cards yet — add one with a photo or its name.", "answer": "no_cards"}}
        want = _words(args.get("card") or "")
        pick = [c for c in cards if want and want <= _words(f"{c['issuer']} {c['product']}")] if want else (cards if len(cards) == 1 else [])
        if len(pick) != 1:
            return {"ok": True, "result": {"answer": "which_card", "ask": "Which card?", "cards": [c["masked"] for c in cards]}}
        r = await CALL("cards.ask", {"end_user": uid, "card_item_id": pick[0]["item_id"], "question": args["question"]})
        if not r.get("ok"):
            return _fail(r)
        a = r["result"]
        return {"ok": True, "result": {"say": a["text"], "answer": a["answer"], "card": a["card"],
                                       "sources": sorted({q["source_url"] for q in a.get("quotes") or []}), "how": SAY_AS_GIVEN}}
    # which_card
    amt = args.get("amount")
    try:
        minor = int(round(float(amt) * 100))
    except (TypeError, ValueError):
        return {"ok": False, "error": {"code": "need_amount", "message": "ask how much it is, and in which currency"}}
    r = await CALL("cards.which", {"end_user": uid, "purchase": {"amount_minor": max(1, minor), "currency": str(args.get("currency") or "EUR").upper()[:3],
                                                                  "kind": args.get("kind") or "other"}})
    if not r.get("ok"):
        return _fail(r)
    w = r["result"]
    return {"ok": True, "result": {"framing": w["framing"], "cards": [{"card": c["card"], "reasons": [x["text"] for x in c["reasons"]]} for c in w["cards"]],
                                   "net_view": w["net_view"], **({"not_compared": [s["card"] for s in w["skipped"]]} if w.get("skipped") else {}),
                                   **({"say": w["text"]} if w.get("text") else {})}}


def wrap(base: Callable[..., Awaitable[Dict[str, Any]]]) -> Callable[..., Awaitable[Dict[str, Any]]]:
    """/s2's runner: fine print's four tools here; every other tool exactly as `base` runs it."""
    async def run(ctx, name: str, args: dict) -> Dict[str, Any]:
        if name in TOOL_NAMES:
            return await run_tool(ctx, name, args)
        return await base(ctx, name, args)
    return run


async def accident_photo(account: str, shot: str, media_type: str, b64: str) -> Dict[str, Any]:
    """/s2's photo button on the accident card: straight to AgAPI (sealed, hashed evidence) — never through the chat or the model."""
    uid = await _end_user(account)
    cid = _ACCIDENT.get(account)
    if not uid or not cid:
        return {"ok": False, "error": {"code": "no_accident", "message": "there's no accident case open"}}
    return await CALL("cards.accident_photo", {"end_user": uid, "case_id": cid, "shot": shot, "media_type": media_type, "content_base64": b64})


async def moment(account: str, event: dict) -> Dict[str, Any]:
    """CR 75 · for Sasha's proactive loop (S-83, standing consent): ask AgAPI whether to speak up for this event (rental_booked ·
    pickup_tomorrow · which_card · rental_returned). → {speak, line, card} — say the line and show the card only when speak is true;
    AgAPI keeps it to one per event and honours the person's off switch."""
    uid = await _end_user(account)
    if not uid:
        return {"speak": False, "why_silent": "card fine print didn't answer"}
    r = await CALL("cards.moment", {"end_user": uid, "event": event})
    return r["result"] if r.get("ok") else {"speak": False, "why_silent": (r.get("error") or {}).get("message") or "unavailable"}


RENDER_KINDS = ("counter_card", "my_cards", "accident", "claim_status")


__all__ = ["TOOLS", "TOOL_NAMES", "wrap", "keep_image", "via", "accident_photo", "moment", "RENDER_KINDS"]
