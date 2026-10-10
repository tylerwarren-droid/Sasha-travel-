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


async def _agapi(op: str, body: dict) -> Dict[str, Any]:
    import httpx
    live = via() == "live"
    url = (os.getenv("SASHA_AGAPI_URL", "https://agapi-live-production.up.railway.app") if live
           else os.getenv("SASHA_AGAPI_TEST_URL", "https://agapi-sandbox-production.up.railway.app")).rstrip("/")
    key = os.getenv("SASHA_AGAPI_KEY" if live else "SASHA_AGAPI_TEST_KEY", "").strip()
    if not key:
        return {"ok": False, "error": {"code": "not_configured", "message": "card fine print isn't switched on yet"}}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0)) as c:
            r = await c.post(f"{url}/v1/{op}", headers={"Authorization": f"Bearer {key}", "content-type": "application/json"}, content=json.dumps(body))
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


async def run_tool(ctx, name: str, args: dict) -> Dict[str, Any]:
    uid = await _end_user(ctx.account)
    if not uid:
        return {"ok": False, "error": {"code": "unavailable", "message": "card fine print didn't answer"}}
    if name == "my_cards":
        r = await CALL("cards.mine", {"end_user": uid})
        if not r.get("ok"):
            return _fail(r)
        return {"ok": True, "result": {"cards": [{"card": c["masked"], "status": c["status"]} for c in r["result"]["cards"]]}}
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


__all__ = ["TOOLS", "TOOL_NAMES", "wrap", "keep_image", "via"]
