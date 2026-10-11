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
import logging
import os
import re
import secrets
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

log = logging.getLogger("agapi.fine_print")

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
# CR 78 · the facts' own keys, named for the model (CR 75's bare object let it guess keys AgAPI refused, so nothing landed)
FACTS = {"type": "object", "properties": {
    "date": {"type": "string", "description": "YYYY-MM-DD"}, "time": {"type": "string", "description": "HH:MM, 24-hour"},
    "place": {"type": "string", "description": "where it happened, in their words"},
    "other_vehicle_plate": {"type": "string", "description": "the OTHER car's number plate, as they said it"},
    "your_plate": {"type": "string", "description": "their own (rental) car's plate"},
    "your_insurer": {"type": "string"}, "injuries": {"type": "string"},
    "witnesses": {"type": "array", "items": {"type": "string"}}}}
_HHMM = re.compile(r"\b([01]?\d|2[0-3])[:h]([0-5]\d)\b")


def _card_name(c: dict) -> str:
    """'Example Bank Travel Visa', not 'Example Bank Example Bank Travel Visa'."""
    return c["product"] if (c.get("product") or "").startswith(c.get("issuer") or "\0") else f"{c.get('issuer')} {c.get('product')}"


def flight_number(airline: Optional[str], number: Optional[str]) -> Optional[str]:
    """Sasha 236 · the number without the airline's code in front ("EX" + "EX123" → "123"): AgAPI puts the code back, and the
    read-back said "EXEX123" (found live)."""
    n = str(number or "").strip().replace(" ", "")
    a = str(airline or "").strip().upper()
    return n[len(a):] if a and n.upper().startswith(a) and n[len(a):].isdigit() else (n or None)


def agapi_facts(given: Optional[dict], said: str = "") -> Dict[str, Any]:
    """CR 78 · the model's facts → AgAPI's keys (other_vehicle / your_vehicle objects). A time they typed ("14:00") is taken from their
    own words when the model left it out — a plate never is (theirs or the other car's can't be told apart from the words alone)."""
    g = dict(given or {})
    out: Dict[str, Any] = {k: str(g[k])[:120] for k in ("date", "time", "place", "your_insurer", "injuries") if g.get(k)}
    if g.get("other_vehicle_plate"):
        out["other_vehicle"] = {"plate": str(g["other_vehicle_plate"])[:60]}
    if g.get("your_plate"):
        out["your_vehicle"] = {"plate": str(g["your_plate"])[:60]}
    if g.get("witnesses"):
        out["witnesses"] = [str(w)[:120] for w in g["witnesses"]][:4]
    if "time" not in out:
        m = _HHMM.search(said or "")
        if m:
            out["time"] = f"{int(m.group(1)):02d}:{m.group(2)}"
    if out.get("date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", out["date"]):
        out.pop("date")
    if out.get("time") and not re.fullmatch(r"\d{2}:\d{2}", out["time"]):
        out.pop("time")
    return out
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
        "charges or a claim against them: add the flag and say the hand-off line as given. EVERY fact they give — the time, the place, the "
        "other car's plate — goes in `facts` the moment they say it, at any step (\"14:00, Rotunda do Marquês, AA-00-ZZ\" → time 14:00, place "
        "Rotunda do Marquês, other_vehicle_plate AA-00-ZZ). The card they paid with goes in `card` whenever they name it; if the step "
        "asks which card, ask it as given. The dates it gives are said, never offered for a calendar."),
     "input_schema": {"type": "object", "properties": {"answer": {"type": "string"}, "country": {"type": "string"}, "place": {"type": "string"},
                                                       "rental_company": {"type": "string"}, "card": {"type": "string"},
                                                       "flags": {"type": "array", "items": {"type": "string", "enum": ["injuries", "fault_disputed", "police_charges", "claim_against_me"]}},
                                                       "new_accident": {"type": "boolean", "description": "true only for a SECOND, different accident"},
                                                       "facts": FACTS}}},
    {"name": "accident_notify", "description": (
        "Tell the rental company about the accident with the photos and the statement's facts. The FIRST call returns the read-back — read it "
        "back and ask; call again only after they say yes, in a later turn."), "input_schema": {"type": "object", "properties": {}}},
    {"name": "file_claim", "description": (
        "File the card-insurance claim the accident (or a claim they started) prepared. The FIRST call returns the read-back — read it back "
        "and ask; call again only after they say yes, in a later turn."), "input_schema": {"type": "object", "properties": {}}},
    {"name": "claim_status", "description": "Their latest card claim: its state, deadlines, what's still missing and what the insurer replied.",
     "input_schema": {"type": "object", "properties": {}}},
]
# ── CR 78 · money back (EU261): the check, then the claim to the airline's own address, read back, filed on their yes ──────────────────
TOOL_NAMES = TOOL_NAMES + ("flight_money_back", "file_flight_claim")
TOOLS += [
    {"name": "flight_money_back", "description": (
        "Money back for a flight that was delayed, cancelled or where they were denied boarding (EU rules): whether it's owed and how much, "
        "each rule quoted from the Regulation's own text. Ask only for what's missing: the airline and flight number, the date, from and to "
        "(airport codes), what happened and how late it arrived (or the days' notice of a cancellation). Say `say` as given; never name an "
        "amount it didn't give. If it's owed, ask whether to claim it."),
     "input_schema": {"type": "object", "properties": {
         "airline": {"type": "string", "description": "IATA code, e.g. IB"}, "number": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD"},
         "from": {"type": "string", "description": "IATA airport, e.g. MAD"}, "to": {"type": "string"},
         "what": {"type": "string", "enum": ["delayed", "cancelled", "denied_boarding"]},
         "arrival_delay_minutes": {"type": "integer"}, "notice_days": {"type": "integer"},
         "airline_said_extraordinary": {"type": "boolean"}, "booking_reference": {"type": "string"},
         "passengers": {"type": "array", "items": {"type": "string"}}}, "required": ["airline", "date", "from", "to", "what"]}},
    {"name": "file_flight_claim", "description": (
        "File the flight compensation claim flight_money_back prepared, to the airline's own address — or, when the airline takes claims only "
        "on its own web form, prepare every field for that form (status form_prepared: they press submit on the airline's site; never say it's "
        "filed). Needs the booking reference and every "
        "passenger's name (ask if missing). The FIRST call returns the read-back — read it back and ask; call again only after they say yes, "
        "in a later turn."),
     "input_schema": {"type": "object", "properties": {"booking_reference": {"type": "string"}, "passengers": {"type": "array", "items": {"type": "string"}}}}},
]
_MONEY: Dict[str, str] = {}        # account → the latest money-back case

# ── CR 81 · things to do, verified on each place's OWN site (AgAPI activities.*): an ActivityCard per place ───────────────────────────
TOOL_NAMES = TOOL_NAMES + ("suggest_activities",)
TOOLS += [
    {"name": "suggest_activities", "description": (
        "Things to do (museums, matches, concerts, exhibitions, tours, outdoors) in a city on a date. Each suggestion is checked on its own "
        "official site: the opening hours that day, a match or event that day, the price — quoted. Say `say` as given: every time, date and "
        "price comes from it; if a place says it couldn't be checked, say you couldn't check its official site. The card's button goes to the "
        "official site — never a reseller."),
     "input_schema": {"type": "object", "properties": {"city": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD"},
                                                       "interests": {"type": "array", "items": {"type": "string"}}}, "required": ["city", "date"]}},
]
VERIFY_TOP = 5

# ── CR 80 · money back for luggage; any money claim's status (deadlines, the airline's replies in their words) ──────────────────────
TOOL_NAMES = TOOL_NAMES + ("bag_money_back", "file_bag_claim", "money_claim_status")
TOOLS += [
    {"name": "bag_money_back", "description": (
        "Money back for a checked bag that was delayed, lost or damaged: whether they can claim and by when — the Montreal Convention's "
        "deadlines and the airline's own, quoted. Ask only for what's missing: airline + flight number, date, from and to (airport codes), "
        "what happened, the day they got the bag back, the PIR reference from the airport desk, and what the receipts add up to. Say `say` "
        "as given. The Convention's limit is a limit — never say it's what they're owed."),
     "input_schema": {"type": "object", "properties": {
         "airline": {"type": "string"}, "number": {"type": "string"}, "date": {"type": "string", "description": "the flight's date, YYYY-MM-DD"},
         "from": {"type": "string"}, "to": {"type": "string"}, "what": {"type": "string", "enum": ["delayed", "lost", "damaged"]},
         "received_on": {"type": "string", "description": "the day they got the bag back, YYYY-MM-DD"}, "pir_reference": {"type": "string"},
         "expenses": {"type": "number", "description": "the receipts' total"}, "currency": {"type": "string"}, "booking_reference": {"type": "string"},
         "passengers": {"type": "array", "items": {"type": "string"}}}, "required": ["airline", "date", "from", "to", "what"]}},
    {"name": "file_bag_claim", "description": (
        "File the bag claim bag_money_back prepared, to the airline's own address — or, when the airline takes them only on its own form, "
        "prepare every field for it (status form_prepared: they submit it themselves). Needs the PIR reference, the booking reference and every "
        "passenger's name (ask if missing). The FIRST call returns the read-back — read it back and ask; call again only after they say yes, "
        "in a later turn."),
     "input_schema": {"type": "object", "properties": {"pir_reference": {"type": "string"}, "booking_reference": {"type": "string"},
                                                       "passengers": {"type": "array", "items": {"type": "string"}}}}},
    {"name": "money_claim_status", "description": (
        "Their latest money-back claim (a flight or a bag): its state, the next date that matters, and what the airline replied — say the "
        "airline's reply as THEIR words, in quotes, never in yours."), "input_schema": {"type": "object", "properties": {}}},
]

# ── CR 79 · entry documents (UK ETA, Thailand TDAC): needed or not, quoted; the application prepared — they submit on the official site ──
TOOL_NAMES = TOOL_NAMES + ("entry_documents", "prepare_entry")
TOOLS += [
    {"name": "entry_documents", "description": (
        "What they need to enter the countries on their trip (an ETA, an arrival card), from their saved passport and the government's own "
        "pages, quoted, with the date to apply by. Pass each destination's ISO country code and arrival date. Say `say` as given. Never say "
        "they're 'cleared' to enter, never name a fee or a site it didn't give."),
     "input_schema": {"type": "object", "properties": {"destinations": {"type": "array", "items": {"type": "object", "properties": {
         "country": {"type": "string", "description": "ISO code, e.g. GB, TH"}, "arrival_date": {"type": "string", "description": "YYYY-MM-DD"}},
         "required": ["country"]}}}, "required": ["destinations"]}},
    {"name": "prepare_entry", "description": (
        "Prepare their ETA or arrival-card application: which sections come from their Keep (masked) and their trip, which they fill in, and "
        "the official address. THEY submit and pay there — never offer to submit, pay, upload a photo or fill the site for them. Pass the "
        "flight, arrival date and where they're staying if the trip has them."),
     "input_schema": {"type": "object", "properties": {"country": {"type": "string"}, "flight": {"type": "string"}, "arrival_date": {"type": "string"},
                                                       "accommodation": {"type": "string"}}, "required": ["country"]}},
]

_ACCIDENT: Dict[str, str] = {}     # account → the open accident case
_ACCIDENT_CITY: Dict[str, str] = {}   # Sasha 234 · account → the place the case was opened with (never re-sent as the accident's place)
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


async def _with_own_passport(account: str, v: dict) -> dict:
    """Sasha 242 (EU's walk) · the passport the person saved on /keep lives in SASHA's Keep; AgAPI's entry.prepare reads its own,
    so "fill my arrival card from my passport" said the passport "wasn't pulled in". Its Keep section takes the mask from the
    person's own Keep (the mask only — the number never leaves the Keep; they copy it from their phone), and the count is said again."""
    fields = list(v.get("fields") or [])
    if not any(f.get("from") == "your Keep" and not f.get("value") for f in fields):
        return v
    try:
        from agapi import s2_keep as KEEP
        pp = next((i for i in await KEEP.list_(account) if i.get("type") == "passport"), None)
    except Exception as e:
        log.info("[fine_print] own Keep not read: %s", type(e).__name__)
        return v
    if not pp:
        return v
    fields = [{**f, "value": pp["masked"], "note": "Your passport, from your Keep — the full number is on your phone, never in the chat."}
              if f.get("from") == "your Keep" and not f.get("value") else f for f in fields]
    n = sum(1 for f in fields if f.get("value"))
    say = re.sub(r"\d+ of (\d+) sections come from", f"{n} of \\1 sections come from", str(v.get("say") or ""), count=1)
    return {**v, "fields": fields, "say": say, "passport": {"masked": pp["masked"]}}


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
        # Sasha 234 · the facts' own place wins; a top-level place is a fact only when it isn't the city the case was opened with
        # (live: the model re-sent place "Lisbon" beside facts.place "Rotunda do Marquês", and Lisbon reached the read-back)
        again = cid and args.get("place") and str(args["place"]).strip().lower() != _ACCIDENT_CITY.get(ctx.account, "")
        facts = agapi_facts({**({"place": args["place"]} if again else {}), **(args.get("facts") or {})}, ctx.user_said or "")
        # CR 78 · an open case is never restarted by a later fact (CR 75 opened a new case whenever country + place came without an answer)
        if not cid or args.get("new_accident"):
            item = await _card_item(uid, args.get("card") or "") if args.get("card") else None
            r = await CALL("cards.accident_start", {"end_user": uid, "country": str(args.get("country") or "ES").upper()[:2], "place": args.get("place") or "",
                                                    "rental_company": args.get("rental_company") or "", **({"card_item_id": item} if item else {}),
                                                    **({"facts": facts} if facts else {})})
            if not r.get("ok"):
                return _fail(r)
            _ACCIDENT[ctx.account] = r["result"]["case_id"]
            _ACCIDENT_CITY[ctx.account] = str(args.get("place") or "").strip().lower()
            return {"ok": True, "result": {"say": r["result"]["say"], "step": "safety", "render": _view(r["result"])}}
        item = await _card_item(uid, args["card"]) if args.get("card") else None
        r = await CALL("cards.accident_step", {"end_user": uid, "case_id": cid, **({"answer": args["answer"]} if args.get("answer") else {}),
                                               **({"flags": args["flags"]} if args.get("flags") else {}), **({"facts": facts} if facts else {}),
                                               **({"card_item_id": item} if item else {})})
        if not r.get("ok"):
            return _fail(r)
        v = r["result"]
        if v.get("claim_case_id"):
            _CLAIM[ctx.account] = v["claim_case_id"]
        ask = v.get("ask_card")
        return {"ok": True, "result": {"say": v.get("say"), "step": v["step"], **({"handoff": v["handoff"]} if v.get("handoff") else {}),
                                       **({"ask": ask["say"], "cards": [_card_name(c) for c in ask["cards"]]} if ask else {}),
                                       "how": ("Say `say` as given; then the hand-off line if there is one." + (" Then ask `ask` as given." if ask else "")
                                               + " Never offer to put these dates in a calendar."), "render": _view(v)}}
    if name == "accident_notify":
        cid = _ACCIDENT.get(ctx.account)
        if not cid:
            return {"ok": False, "error": {"code": "no_accident", "message": "there's no accident case open"}}
        r = await _with_yes(ctx, f"{ctx.account}|accident_notify", "cards.accident_notify", {"end_user": uid, "case_id": cid})
        if r.get("ok") and (r["result"].get("claim_case_id")):
            _CLAIM[ctx.account] = r["result"]["claim_case_id"]
        if r.get("ok") and r["result"].get("state"):
            v = r["result"]
            ask = v.get("ask_card")   # CR 78 · notified with no card known: the claim waits for their answer
            return {"ok": True, "result": {"status": v["state"], "say": v.get("say"), "render": _view(v),
                                           **({"ask": ask["say"], "cards": [_card_name(c) for c in ask["cards"]],
                                               "how": "Then ask `ask` as given; their answer goes to `accident` as `card`."} if ask else {})}}
        return r if r.get("ok") else _fail(r)
    if name == "file_claim":
        cid = _CLAIM.get(ctx.account)
        if not cid and _ACCIDENT.get(ctx.account):   # CR 78 · an accident with no card named: ask, don't fail
            mine = await CALL("cards.mine", {"end_user": uid})
            cards = (mine.get("result") or {}).get("cards") or []
            return {"ok": True, "result": {"status": "which_card", "ask": "Which card did you pay the rental with?",
                                           "cards": [_card_name(c) for c in cards],
                                           "how": "Ask `ask` as given; their answer goes to `accident` as `card`, then file_claim again."}}
        if not cid:
            return {"ok": False, "error": {"code": "no_claim", "message": "there's no claim prepared yet"}}
        r = await _with_yes(ctx, f"{ctx.account}|file_claim", "cards.claim_file", {"end_user": uid, "case_id": cid})
        if r.get("ok") and r["result"].get("state"):
            return {"ok": True, "result": {"status": r["result"]["state"], "render": {"kind": "claim_status", "claim": r["result"]}}}
        return r if r.get("ok") else _fail(r)
    if name == "flight_money_back":
        flight = {k: args[k] for k in ("airline", "number", "date", "from", "to", "what", "arrival_delay_minutes", "notice_days", "airline_said_extraordinary")
                  if args.get(k) not in (None, "")}
        for k in ("airline", "from", "to"):
            flight[k] = str(flight.get(k) or "").upper()
        if flight.get("number"):
            flight["number"] = flight_number(flight["airline"], flight["number"])   # Sasha 236 · never "EXEX123"
        r = await CALL("money.flight_check", {"end_user": uid, "flight": flight, **({"booking_reference": args["booking_reference"]} if args.get("booking_reference") else {}),
                                              **({"passengers": args["passengers"]} if args.get("passengers") else {})})
        if not r.get("ok"):
            return _fail(r)
        v = r["result"]
        _MONEY[ctx.account] = v["case_id"]
        return {"ok": True, "result": {"say": v["say"], "verdict": v["verdict"], "amount": v.get("amount"),
                                       "quotes": [q["quote"] for x in v["rules"] for q in x["quotes"]][:4],
                                       "how": ("Say `say` as given: the amount is the Regulation's own sentence, quoted. Never name an amount it "
                                               "didn't give, never promise the airline will pay.")}}
    if name == "file_flight_claim":
        cid = _MONEY.get(ctx.account)
        if not cid:
            return {"ok": False, "error": {"code": "no_case", "message": "check the flight first (flight_money_back)"}}
        body = {"end_user": uid, "case_id": cid, **({"booking_reference": args["booking_reference"]} if args.get("booking_reference") else {}),
                **({"passengers": args["passengers"]} if args.get("passengers") else {})}
        r = await _with_yes(ctx, f"{ctx.account}|file_flight_claim", "money.flight_claim", body)
        if r.get("ok") and r["result"].get("state"):
            v = r["result"]
            return {"ok": True, "result": {"status": v["state"], "say": v.get("say"), **({"draft": v["draft"]} if v.get("draft") else {}),
                                           **({"form_url": v["form_url"], "fields": v["fields"]} if v.get("form_url") else {})}}   # CR 82
        return r if r.get("ok") else _fail(r)
    if name == "suggest_activities":
        import asyncio as _aio
        day = str(args.get("date") or "")[:10]
        r = await CALL("activities.suggest", {"city": str(args.get("city") or ""), "dates": {"from": day},
                                              **({"interests": [str(i) for i in args["interests"]][:8]} if args.get("interests") else {}), "limit": 8})
        if not r.get("ok"):
            return _fail(r)
        cands = r["result"]["candidates"]   # all of them are checked (each from its stored read); the first VERIFY_TOP readable ones are shown
        if not cands:
            return {"ok": True, "result": {"say": r["result"]["say"]}}
        got = await _aio.gather(*[CALL("activities.verify", {"candidate_id": c["candidate_id"], "date": day}) for c in cands])
        cards = [g["result"] for g in got if g.get("ok")]
        shown = [c for c in cards if c["confidence"] in ("verified", "partial")][:VERIFY_TOP]
        unread = [c for c in cards if c["confidence"] == "not_read"]
        say = " ".join([c["say"] for c in shown] + ([f"I couldn't check {', '.join(c['name'] for c in unread)} on their official sites."] if unread else []))
        return {"ok": True, "result": {"say": say or "I couldn't check any of them on their official sites today.",
                                       "how": "Say `say` as given — every time, date and price is quoted from the place's own site.",
                                       "render": {"kind": "activities", "cards": shown, "unread": [c["name"] for c in unread], "date": day}}}
    if name == "bag_money_back":
        bag = {k: args[k] for k in ("airline", "number", "date", "from", "to", "what", "received_on", "pir_reference", "currency") if args.get(k) not in (None, "")}
        if bag.get("number"):
            bag["number"] = flight_number(bag.get("airline"), bag["number"])   # Sasha 236 · found live: "EXEX123"
        for k in ("airline", "from", "to", "currency"):
            if bag.get(k):
                bag[k] = str(bag[k]).upper()
        if args.get("expenses"):
            try:
                bag["expenses_minor"] = int(round(float(args["expenses"]) * 100))
            except (TypeError, ValueError):
                pass
        r = await CALL("money.bag_check", {"end_user": uid, "bag": bag, **({"booking_reference": args["booking_reference"]} if args.get("booking_reference") else {}),
                                           **({"passengers": args["passengers"]} if args.get("passengers") else {})})
        if not r.get("ok"):
            return _fail(r)
        v = r["result"]
        _MONEY[ctx.account] = v["case_id"]
        return {"ok": True, "result": {"say": v["say"], "verdict": v["verdict"], "file_by": v.get("file_by"),
                                       "how": ("Say `say` as given: every deadline is quoted from its source. The limit is never what they're owed. "
                                               # Sasha 236 · found live: she described the claim from memory and asked again and again
                                               "When they want to claim, CALL file_bag_claim — its first call returns the read-back you "
                                               "read out; never describe a claim you haven't got back from it.")}}
    if name == "file_bag_claim":
        cid = _MONEY.get(ctx.account)
        if not cid:
            return {"ok": False, "error": {"code": "no_case", "message": "check the bag first (bag_money_back)"}}
        body = {"end_user": uid, "case_id": cid, **{k: args[k] for k in ("pir_reference", "booking_reference", "passengers") if args.get(k)}}
        r = await _with_yes(ctx, f"{ctx.account}|file_bag_claim", "money.bag_claim", body)
        if r.get("ok") and r["result"].get("state"):
            v = r["result"]
            return {"ok": True, "result": {"status": v["state"], "say": v.get("say"), **({"draft": v["draft"]} if v.get("draft") else {}),
                                           **({"form_url": v["form_url"], "fields": v["fields"]} if v.get("form_url") else {})}}   # CR 82
        return r if r.get("ok") else _fail(r)
    if name == "money_claim_status":
        cid = _MONEY.get(ctx.account)
        if not cid:
            return {"ok": True, "result": {"say": "There's no money-back claim open."}}
        r = await CALL("money.claim_status", {"end_user": uid, "case_id": cid})
        if not r.get("ok"):
            return _fail(r)
        v = r["result"]
        return {"ok": True, "result": {"say": v["say"], "state": v["state"], "next": v.get("next"),
                                       "replies": [x["their_words"]["text"] for x in v.get("replies") or []],
                                       "how": "Say `say` as given. The airline's reply is THEIR words: quote it, never paraphrase it or add to it."}}
    if name == "entry_documents":
        dests = [{"country": str(d.get("country") or "").upper()[:2], **({"arrival_date": d["arrival_date"]} if d.get("arrival_date") else {})}
                 for d in (args.get("destinations") or []) if d.get("country")]
        if not dests:
            return {"ok": False, "error": {"code": "need_destination", "message": "ask where they're going (and when they land)"}}
        r = await CALL("entry.check", {"end_user": uid, "destinations": dests})
        if not r.get("ok"):
            return _fail(r)
        v = r["result"]
        return {"ok": True, "result": {"say": v["say"], "passport": (v.get("passport") or {}).get("masked"),
                                       "destinations": [{"country": d["country"], "verdict": d["verdict"], **({"deadline": d["deadline"]} if d.get("deadline") else {})}
                                                        for d in v["destinations"]],
                                       "how": "Say `say` as given: every rule is the government's own sentence, quoted. Never say they're cleared to enter."}}
    if name == "prepare_entry":
        trip = {k: str(args[k]) for k in ("flight", "arrival_date", "accommodation") if args.get(k)}
        r = await CALL("entry.prepare", {"end_user": uid, "country": str(args.get("country") or "").upper()[:2], **({"trip": trip} if trip else {})})
        if not r.get("ok"):
            return _fail(r)
        v = await _with_own_passport(ctx.account, r["result"])
        return {"ok": True, "result": {"say": v["say"], "official_url": v["official_url"],
                                       "fields": [{"asks": f["asks"], "from": f["from"], "value": f["value"]} for f in v["fields"]],
                                       "you_do": v["you_do"],
                                       "how": "Say `say` as given and give the official address exactly. They submit and pay there; you never do."}}
    if name == "claim_status":
        cid = _CLAIM.get(ctx.account)
        if not cid:
            return {"ok": True, "result": {"say": "There's no claim open."}}
        r = await CALL("cards.claim_status", {"end_user": uid, "case_id": cid})
        if not r.get("ok"):
            return _fail(r)
        c = r["result"]
        return {"ok": True, "result": {"state": c["state"], "deadlines": [d["say"] for d in c["deadlines"]],
                                       "how": "Say the deadlines as dates. Never offer to put them in a calendar — the calendar is for confirmed bookings.",
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


RENDER_KINDS = ("counter_card", "my_cards", "accident", "claim_status", "activities")   # CR 81 · + the ActivityCard


__all__ = ["TOOLS", "TOOL_NAMES", "wrap", "keep_image", "via", "accident_photo", "moment", "RENDER_KINDS"]
