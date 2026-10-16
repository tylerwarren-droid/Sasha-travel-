"""AgAPI v0 — THE CONTRACT. Every tool an agent (Sasha's, or any outside client later: REST, MCP) may call, in ONE place:
its agent, its input/output JSON schemas, its errors, and the guards that hold whatever the caller says.

    Magellan  finds        search_flights · search_stays · search_venues · prepare_trip · propose_trip · swap_stay
    Sherlock  checks       check_offer · read_booking_route
    Austen    acts         choose_offer · save_travellers · hold_booking · book   (idempotency_key required; book needs a yes)
    Pacioli   records      get_status · get_trip · get_total

Rules of the contract (they live HERE, not in any prompt):
  · Scope: every call runs for ONE account — the caller's authenticated account (Ctx.account), never an id in the input.
  · Mode: "test" only in v0 (Duffel TEST, Stripe TEST, TEST hotels). A "live" Ctx is refused: mode_not_available.
  · Austen's calls carry an idempotency_key: the same key twice returns the first result, never a second action.
  · book needs approval.said = the person's OWN words in the current turn, an explicit yes. Sasha's agent fills it from the
    real user message — the model cannot supply it.
  · Prices and totals come only from these results; booked / paid / confirmed only from Pacioli (get_status).
  · Every error is {"ok": false, "error": {"code", "message"}} — honest, for the caller to explain.

docs/agapi/api-v0.md is GENERATED from TOOLS (scripts/agapi_doc.py).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

log = logging.getLogger("agapi.v0")
VERSION = "v0"
from booking_signer import fx as _FX   # noqa: E402 · Sasha 249 · ONE RATE (fx.py, dated) for every conversion into euros


@dataclass
class Ctx:
    account: str                       # the authenticated account — the only scope
    mode: str = "test"                 # v0: "test" only
    user_said: Optional[str] = None    # the person's own words this turn (Sasha's agent fills it; REST: approval.said)
    session: Optional[str] = None
    calls: List[dict] = field(default_factory=list)   # what was called this turn (for the caller's guards and logs)
    started: datetime = field(default_factory=lambda: datetime.now(timezone.utc))   # Sasha 210 · when this turn began
    idem: Optional[str] = None         # Sasha 215 · the acting call's durable key (call() sets it; claim() takes it once)
    surface: str = "s1"                # Sasha 221 · "s2" only from /s2 (its proxy's header); everything else is S1, as before
    claimed: Optional[str] = None      # the claim this call holds, released if the act is refused before anything is sent
    act_name: Optional[str] = None     # CR 76 · /s2: the act this call is (claim() runs THE ONE YES RULE on it)
    act_said: Optional[str] = None     # CR 76 · /s2: the person's words this turn, as the act was called
    space: str = "sasha"               # Sasha 249 · the account's space (products/space.py), read at the start of sasha.turn


class ToolError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


# Sasha 215 · CR 56 #4 — an OUTSIDE SERVICE DOWN is said as an outage, in these words, never as a fact about the person ("no
# trip", "no hotels", "can't find your city"). The agent loop has her say the message as it stands (never improvised round).
UNREACHABLE = {
    "store_unreachable": "I can't reach your saved trip right now — our records aren't answering. Nothing was changed; try me again in a minute.",
    "airline_unreachable": "I can't reach the airline's booking system right now. Your flights are unchanged; try me again in a minute.",
    "stays_unreachable": "The hotel search is down right now, so I can't show you places to stay. Try me again in a minute.",
    "venues_unreachable": "The search for places is down right now. Try me again in a minute.",
    "payments_unreachable": "I can't reach the payment system right now, so no payment link was sent. Try me again in a minute.",
}


def unreachable(code: str) -> ToolError:
    return ToolError(code, UNREACHABLE[code])


_CLAIMED: set = set()   # only when NO database is configured at all (a unit test, a laptop) — production always claims in Postgres


async def claim(ctx: "Ctx") -> None:
    """Sasha 215 · EU 200 — DURABLE IDEMPOTENCY: an act (a payment sent, a booking or cancellation sent) runs once for its key,
    across restarts and workers: the key is claimed in Postgres (basket_events is unique on source + event_id) BEFORE the act.
    Already claimed → already_done; the records unreachable → nothing is sent."""
    if ctx.surface == "s2" and ctx.act_name:   # CR 76 · THE ONE YES RULE (agapi/yes_one, AgAPI 1.3): read-back → a later-turn yes → this act
        from agapi import yes_gate as YG
        got, why = YG.check(ctx, ctx.act_name, ctx.act_said)
        if got != "valid":
            raise ToolError(got, YG.SAY.get(got, "ask them, then act") + (f" ({why})" if why else ""))
    if not ctx.idem:
        return
    from booking_signer import basket as BK
    eid = hashlib.sha256(ctx.idem.encode()).hexdigest()[:40]
    if BK._run() is None:
        if eid in _CLAIMED:
            raise ToolError("already_done", "this was already sent once and is never sent twice — get_status says where it stands")
        _CLAIMED.add(eid)
        ctx.claimed = eid
        return
    try:
        new = await BK.event("agapi", eid, "claim", {"key": ctx.idem}, verified=True)
    except Exception as e:
        log.error("[agapi] claim not recorded — nothing sent: %s: %s", type(e).__name__, e)
        raise ToolError("store_unreachable", "I can't reach our booking records right now, so I haven't sent anything. Try me again in a minute.")
    if not new:
        raise ToolError("already_done", "this was already sent once and is never sent twice — get_status says where it stands")
    ctx.claimed = eid


async def _unclaim(ctx: "Ctx") -> None:
    eid, ctx.claimed = ctx.claimed, None
    if not eid:
        return
    from booking_signer import basket as BK
    if BK._run() is None:
        _CLAIMED.discard(eid)
        return
    try:
        await BK.unclaim("agapi", eid)
    except Exception as e:
        log.error("[agapi] claim not released (the next yes will say already_done): %s: %s", type(e).__name__, e)


ERR = {"type": "object", "properties": {"ok": {"const": False}, "error": {"type": "object", "properties": {
    "code": {"type": "string"}, "message": {"type": "string"}}, "required": ["code", "message"]}}}
IDEM = {"type": "string", "minLength": 8, "maxLength": 128, "description": "Idempotency key: the same key returns the first result."}
DATE = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
FLIGHT = {"type": "object", "properties": {
    "offer_id": {"type": "string"}, "airline": {"type": "string"}, "flights": {"type": "string"}, "from": {"type": "string"},
    "to": {"type": "string"}, "departs": {"type": "string"}, "arrives": {"type": "string"}, "stops": {"type": "integer"},
    "duration_minutes": {"type": "integer"}, "price_eur": {"type": "number"}, "test": {"const": True}}}
TOTAL = {"type": "object", "properties": {"total_eur": {"type": "number"}, "items": {"type": "integer"},
                                          "price_sources": {"type": "array", "items": {"type": "string"}}}}

_CANCEL_WORD = re.compile(r"(?i)\bcancel\w*")


# CR 61 · the yes is AgAPI v1.0's AP6 (agapi/v1.py, EU's frozen lists — English and Spanish), plus Sasha's own deliberate, additive
# choices (reported to EU as proposed additions; none contradicts a v1.0 vector — scripts/agapi_v1_conformance.py checks 38/38):
#   · "cancel" (es "cancela") vetoes a general yes (EU's vectors) but not yes_to_cancel — "yes, cancel it" confirms a cancellation
#   · a few more affirmatives Sasha's people say ("book the whole trip", "send me their page")
#   · a few more vetoes (refund/cost/price/fees/details/compare/explain/instead/other/else/first …): stricter is always safe
_SASHA_YES = ("book the whole trip", "book my whole trip", "book our whole trip", "send it", "send me it", "send me their page",
              "send me the page", "send me the link", "send their page", "send the page", "send the link")
_SASHA_VETO = re.compile(r"(?i)\b(?:whether|alternatives?|polic(?:y|ies)|refund\w*|cost\w*|price\w*|fees?|charges?|show|look|"
                         r"explain|compare|details?|more about|instead|other|else|first)\b")


_RAW_QUESTION = re.compile(r"[?¿]")   # Sasha 217 · read on the RAW words (normalisation strips the mark)
ACTS_FILE = Path(__file__).resolve().parent / "spec" / "approval-language-acts.json"   # AgAPI 1.1 · EU's act-aware AP6 file
ACTS_SHA256 = "e8c8c2edc71ee93965a0fa2476f73107b843a0521e0bdc82ec6e455faf03dd5f"


def _exempt(act_kind: Optional[str]) -> set:
    """AgAPI 1.1 · the negations that stop vetoing for this act (cancel: "cancel", "cancela") — EU's file, sha256-pinned."""
    if not act_kind:
        return set()
    raw = ACTS_FILE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ACTS_SHA256:
        raise RuntimeError("agapi/spec/approval-language-acts.json is not EU's file — refusing to judge a yes with other lists")
    acts = json.loads(raw.decode("utf-8")).get("acts", {}).get(act_kind) or {}
    return {w for L in acts.values() for w in L.get("exempt_negations", [])}


def _split(said: str) -> str:
    """AgAPI 1.1 · the apostrophe's OTHER form: split ("what's" → "what s"), so a veto matches either way."""
    import unicodedata as _u
    s = _u.normalize("NFC", said or "").lower()
    s = re.sub(r"['‘’]", " ", s)
    s = re.sub(r"[¡¿!?.,;:\"“”()—–]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def explicit_yes(said: Optional[str], lang: Optional[str] = None, act_kind: Optional[str] = None) -> bool:
    """An explicit yes in the person's own words — "Yes, book it", "Then book it.", "Sí, adelante", "go ahead" — with no negation,
    and never a question or a request for options: AgAPI 1.1's AP6 (EU's lists; vetoes in both apostrophe forms; act-aware —
    act_kind "cancel" exempts "cancel"/"cancela" only) + Sasha's additions (a "?" vetoes anything longer than a bare yes like
    "¿sí?"; more vetoes; a few more affirmatives). `lang` None: any language (a veto in either language vetoes)."""
    from agapi import v1 as V1
    t = V1.normalise(said or "")
    if not t or _SASHA_VETO.search(t) or _SASHA_VETO.search(_split(said or "")):
        return False
    if _RAW_QUESTION.search(said or "") and len(t.split()) > 2:
        return False
    exempt = _exempt(act_kind)
    langs = V1.languages()
    use = [lang] if lang else list(langs)
    forms = {t, _split(said or "")}
    for code in use:
        L = langs[code]
        if any(V1._has(f, n) for f in forms for n in L["negations"] + L.get("questions_and_requests", []) if n not in exempt):
            return False
    return any(V1.affirmative(t, langs[code], _SASHA_YES if code == "en" else ()) for code in use)


def yes_to_cancel(said: Optional[str]) -> bool:
    """Sasha 215 / AgAPI 1.1 · "yes, cancel it" / "sí, cancela" confirms a CANCELLATION that was read back — only there."""
    return explicit_yes(said, act_kind="cancel")


def yes_to_book(said: Optional[str]) -> bool:
    """A yes to BOOK: an explicit yes that isn't about cancelling ("yes, cancel it" never books)."""
    return explicit_yes(said) and not _CANCEL_WORD.search(said or "")


READ_BACK_TTL_S = 900   # Sasha 215 · a prepared booking or cancellation is acted on within 15 minutes of its read-back, never later


def stale(at: Optional[datetime]) -> bool:
    return at is None or (datetime.now(timezone.utc) - at).total_seconds() > READ_BACK_TTL_S


# ── shared reads ─────────────────────────────────────────────────────────────────────────────────────────────────────────

async def _latest(ctx: Ctx) -> Optional[dict]:
    """The account's plan, or None when it has none — and an OUTAGE (the store not answering) said as one, never as "no trip"."""
    from booking_signer import plan_store as PS
    try:
        return await PS.latest(ctx.account, strict=True)
    except PS.StoreDown:
        raise unreachable("store_unreachable")


async def _plan(ctx: Ctx) -> dict:
    from booking_signer import plan_store as PS
    p = await _latest(ctx)
    if not p:
        raise ToolError("no_trip", "there is no trip on this account yet — propose_trip first")
    return p


def _party(p: dict, rows: Optional[List[dict]] = None) -> Optional[int]:
    """Sasha 249 · ONE PARTY: the plan's party, else its basket rows', else None — the caller ASKS (never a silent 2)."""
    from booking_signer import basket as BK
    return BK._party_of(p, rows or [])


def _flight_out(r_or_card: dict, row: Optional[dict] = None) -> dict:
    from booking_signer import basket as BK
    c = r_or_card
    eur = BK.card_eur(c) if c.get("amount") is not None or c.get("price_eur") is not None else None   # Sasha 249 · in euros, one rate
    if eur is None and row is not None:
        eur = BK.eur_of(row)
    return {"offer_id": c.get("id") or (row or {}).get("provider_ref"), "airline": c.get("owner"), "flights": c.get("flights"),
            "from": c.get("from"), "to": c.get("to"), "departs": str(c.get("departs") or ""), "arrives": str(c.get("arrives") or ""),
            "stops": int(c.get("stops") or 0), "duration_minutes": int(c.get("minutes") or 0),
            "price_eur": round(float(eur or 0), 2), "test": True,
            **({"fare": {"amount": c.get("amount"), "currency": c.get("currency"), "rate_as_of": (c.get("fx") or {}).get("as_of")}}
               if isinstance(c.get("fx"), dict) else {}),   # Sasha 249 · a fare in another currency: the airline's own figure beside it
            **({"state": row["state"]} if row else {})}


# Sasha 249 · ONE TOTAL — her instruction travels in the tool RESULT (S1's schemas and prompt stay byte-identical)
TOTAL_HOW = ("total_eur is THE trip total — the same figure on the Trip tab and in the read-back. When you state the trip's total, "
             "say exactly this figure (\"about €X\" may round it to the euro); never add, round or restate an earlier total.")


async def _total(ctx: Ctx, p: dict) -> dict:
    """The whole trip's total — Sasha 249 · basket.trip_figures(): the basket's rows as they stand, READ ONLY (no re-search, no
    re-price, no swap — refresh() runs only in hold_booking). The same figure the Trip tab shows and the read-back says."""
    from booking_signer import basket as BK
    f = await BK.trip_figures(ctx.account, p["trip_id"], p)
    if f["total_eur"] is None:
        raise ToolError("not_priced", "nothing in this trip is priced yet — propose_trip first")
    to_book = [l for l in f["lines"] if l["state"] in ("suggested", "chosen")]
    return {**f, "items": len(f["lines"]), "flights_chosen": sum(1 for l in to_book if l["kind"] == "flight"),
            "price_sources": sorted({l.get("source") or "unpriced" for l in f["lines"]}), "how": TOTAL_HOW}


def breakdown(rows: List[dict], total: float) -> dict:
    """Sasha 212 · ONE TOTAL, its parts on the card only: the flights (quoted) and the stays (an estimate or a test rate) —
    for the card, never for her to say as separate totals (the model never sees it). Sasha 249 · basket.breakdown (one place)."""
    from booking_signer import basket as BK
    return BK.breakdown(rows, total)


_LEG_BACK = re.compile(r"(?i)\b(?:home|back|return(?:ing)?|inbound)\b")


def leg_said(said: Optional[str]) -> Optional[str]:
    """Sasha 249 · the leg in the person's own words: "home" / "back" / "return" → "back"; anything else → None (not said)."""
    return "back" if _LEG_BACK.search(said or "") else None


def hhmm(t: Any) -> Optional[str]:
    """Sasha 249 · a time as said or tapped → "HH:MM": "17:48", "17.48", "5:48pm", "5.48 p.m.", "1748", "9am"; else None."""
    s = str(t or "").strip().lower().replace(".", ":").replace(" ", "")
    s = s.replace("p:m:", "pm").replace("a:m:", "am").replace("p:m", "pm").replace("a:m", "am")
    m = re.fullmatch(r"(\d{1,2})(?::?(\d{2}))?(am|pm|h)?", s)
    if not m:
        return None
    h, mm, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return f"{h:02d}:{mm:02d}" if h < 24 and mm < 60 else None


# Sasha 203 · where each place in a trip flies from: its airport (a plan can end in the Mekong Delta, which has none)
AIRPORT = {"hanoi": "HAN", "ha long bay": "HAN", "halong bay": "HAN", "sapa": "HAN", "ninh binh": "HAN", "cat ba": "HAN", "ha giang": "HAN",
           "ho chi minh city": "SGN", "saigon": "SGN", "mekong delta": "SGN", "mui ne": "SGN", "can tho": "VCA",
           "hoi an": "DAD", "da nang": "DAD", "hue": "HUI", "phu quoc": "PQC", "nha trang": "CXR", "da lat": "DLI",
           "con dao": "VCS", "phong nha": "VDH"}


def airport_of(place: str) -> str:
    """A trip's city → the airport to fly from/to (its IATA code), else the place as said."""
    p = (place or "").split(",")[0].strip()
    return AIRPORT.get(p.lower(), p)


def _best(cards: List[dict], earliest: str = "07:00") -> Optional[dict]:
    """Magellan's pick: direct if there is one, a sensible departure (earliest–21:00), then the best price."""
    def hh(c):
        return str(c.get("departs") or "")[11:16] or "12:00"
    sensible = [c for c in cards if earliest <= hh(c) <= "21:00"]
    direct = [c for c in sensible if not c.get("stops")]
    pool = direct or sensible or cards
    return min(pool, key=lambda c: float(c.get("price_eur") or c.get("amount") or 9e9)) if pool else None


def _options(cards: List[dict], chosen: Optional[dict], n: int = 5, stored: Optional[Dict[str, str]] = None) -> List[dict]:
    """Sasha 210 · the proposal's range of flights for a leg: the one chosen (Sasha's pick), the cheapest, the fastest, then the
    next by price — up to n, each tagged; the chosen one marked. Sasha 249 · OFFERED == BOOKABLE: given `stored` (offer id → its
    basket row), only offers already in the basket are shown, each with its option_id."""
    if stored is not None:
        cards = [c for c in cards if c.get("id") in stored]
    if not cards:
        return []
    picks: List[tuple] = []
    if chosen:
        picks.append((chosen, "Sasha's pick"))
    picks.append((min(cards, key=lambda c: float(c.get("price_eur") or c.get("amount") or 9e9)), "Cheapest"))
    picks.append((min(cards, key=lambda c: int(c.get("minutes") or 9e9)), "Fastest"))
    picks += [(c, "") for c in sorted(cards, key=lambda c: float(c.get("price_eur") or c.get("amount") or 9e9))]
    out, seen = [], set()
    for c, tag in picks:
        if c.get("id") in seen:
            continue
        seen.add(c.get("id"))
        out.append({**_flight_out(c), "tag": tag, "chosen": bool(chosen) and c.get("id") == chosen.get("id"),
                    **({"option_id": stored[c["id"]]} if stored and c.get("id") in stored else {})})
        if len(out) >= n:
            break
    return out


async def _search_healed(origin: str, dest: str, day: str, party: int, limit: int = 12) -> tuple:
    """Sasha 210 · a leg's search that resolves its own problems: tried again once, then the nearest days (±1, ±2).
    → (result, the day used)."""
    from booking_signer import travel as T
    d0 = date.fromisoformat(day)
    r = {}
    for k, shift in enumerate((0, 0, 1, -1, 2, -2)):
        d = (d0 + timedelta(days=shift)).isoformat()
        try:
            r = await T.search(origin, dest, d, adults=party, limit=limit)
        except Exception as e:
            r = {"why": f"{type(e).__name__}"}
        if "why" not in r and _in_eur(r.get("cards") or []):   # Sasha 249 · any fare priceable in euros (converted), not EUR only
            return r, d
        if k == 0 and "why" in r and "token" in r["why"]:
            break   # not configured: no retry will help
        if r.get("outage"):
            return r, day   # Sasha 215 · Duffel not answering (already retried): said as an outage, never "the nearest day"
    return r if "why" in r else {"why": "no flights in euros"}, day


def _in_eur(cards: List[dict]) -> List[dict]:
    """Sasha 249 · CONVERTED AT INGESTION (basket.in_eur): the offers in euros — EUR fares first, as before; a search with none in
    EUR gives its fares converted at fx.py's one dated rate (said in each one's `fare`), never the planner's $ estimate."""
    from booking_signer import basket as BK
    eur = [c for c in cards or [] if c.get("currency") == "EUR"]
    return BK.in_eur(eur or cards or [])


async def _offer_flights(ctx: Ctx, a: dict, cards: List[dict], leg: str, party: int) -> dict:
    """Sasha 249 · OFFERED == BOOKABLE — the ONE way a flight search (Sasha's own, or /s2's AgAPI source) reaches her: the offers
    STORED in the trip's basket first (the leg's earlier options marked superseded, never deleted in this turn), THEN shown, each
    with its option_id. No trip yet → shown, and said: none can be booked until propose_trip."""
    p = await _latest(ctx)
    stored: Optional[Dict[str, str]] = None
    if p:   # the flights shown are the trip's suggestions (the basket), so choose_offer can take any of them
        ids = await _suggest_flights(ctx, p["trip_id"], cards, a["origin"], a["destination"], a["date"], party, leg)
        stored = {c["id"]: i for c, i in zip(cards, ids or [])} if ids and len(ids) == len(cards) else None
    shown = [{**_flight_out(c), **({"option_id": stored[c["id"]]} if stored and c.get("id") in stored else {})} for c in cards]
    return {"leg": leg, "date": a["date"], "flights": shown, "note": "Duffel TEST fares — nothing is held until book",
            "stored": bool(p), **({} if p else {"how": "No trip yet, so none of these can be booked: propose_trip first, then pick one."})}


async def _suggest_flights(ctx: Ctx, trip_id: str, cards: List[dict], origin: str, dest: str, day: str, party: int,
                           leg: str = "out") -> List[str]:
    from booking_signer import basket as BK
    sk = f"{leg}:{origin}→{dest} {day}"   # the leg first: choosing a flight replaces only that leg's
    return await BK.suggest(ctx.account, trip_id, "flight", [{
        "provider": "duffel", "provider_ref": c["id"], "slice_key": sk, "day": day, "party": party, "expires_at": c.get("expires_at"),
        "price_amount": float(c["amount"]), "price_currency": c["currency"], "price_source": "quoted",
        "snapshot": {**c, "name": c.get("owner")}} for c in cards], slice_key=sk)


# ── Magellan ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def search_flights(ctx: Ctx, a: dict) -> dict:
    from booking_signer import travel as T
    party = int(a.get("passengers") or 2)
    leg = a.get("leg") or leg_said(ctx.user_said) or "out"   # Sasha 249 · "flights home" is the back leg, said or not by the model
    r, day = await _search_healed(airport_of(a["origin"]), airport_of(a["destination"]), a["date"], party)
    if r.get("outage"):
        raise unreachable("airline_unreachable")
    if "why" in r:
        raise ToolError("no_flights", r["why"])
    a = {**a, "date": day}   # Sasha 210 · the nearest day with flights, when the day asked had none
    cards = _in_eur(r["cards"])   # Sasha 249 · in euros at ingestion (before: any currency shown as if euros)
    if not cards:
        raise ToolError("no_flights", "no fares that can be priced in euros")
    pref = (a.get("preferences") or "").lower()
    if "direct" in pref or "nonstop" in pref:
        cards = [c for c in cards if not c.get("stops")] or cards
    if "morning" in pref:
        cards = [c for c in cards if str(c.get("departs"))[11:13] < "12"] or cards
    elif "evening" in pref:
        cards = [c for c in cards if str(c.get("departs"))[11:13] >= "17"] or cards
    cards = cards[:6]
    return await _offer_flights(ctx, a, cards, leg, party)   # Sasha 249 · stored, then shown


_STAYS: Dict[str, Dict[str, List[dict]]] = {}   # account → city → the Google hotels last shown (swap_stay picks from them)


async def search_stays(ctx: Ctx, a: dict) -> dict:
    from app.services.hotels_db import VIETNAM_HOTELS
    city = next((k for k in VIETNAM_HOTELS if k.lower() == (a.get("city") or "").strip().lower()), None)
    if not city:   # Sasha 211 · anywhere: real hotels from Google, the nightly price an ESTIMATE (labelled)
        from app.services.world_itinerary import StaysDown, hotels_in
        p = await _latest(ctx)
        pl = (p or {}).get("plan") or {}
        want = (a.get("city") or "").strip()
        try:
            hs = await hotels_in(ctx.account, want, pl.get("country") or "", pl.get("country_code"), (a.get("preference") or "")[:30], strict=True)
        except StaysDown:   # Sasha 215 · the hotel search down is never "no hotels"
            raise unreachable("stays_unreachable")
        if not hs:
            raise ToolError("no_stays", f"no hotels found in {want}")
        _STAYS.setdefault(ctx.account, {})[want.lower()] = hs
        return {"city": want, "stays": [{"name": h["name"], "about": h.get("address"), "rating": h.get("rating"),
                                         "reviews": h.get("rating_count"), "estimate_eur_per_night": h["est_eur"]} for h in hs],
                "prices": "nightly prices are estimates"}
    pref = (a.get("preference") or "").lower()
    hs = VIETNAM_HOTELS[city]
    if pref:
        hs = sorted(hs, key=lambda h: -sum(w in f"{h['name']} {h.get('blurb', '')}".lower() for w in re.findall(r"[a-z]{4,}", pref)))
    return {"city": city, "stays": [{"name": h["name"], "stars": h.get("stars"), "about": h.get("blurb"),
                                     "estimate_eur_per_night": round(_FX.to_eur(h.get("price_from") or 0, "USD") or 0)} for h in hs[:5]],   # Sasha 249 · fx.py's one rate
            "note": "estimates from Sasha's hotel list; a booking is a TEST booking (no hotel contacted)"}


_LAST_FIND: Dict[str, tuple] = {}   # account → (the search, when, its result): a place already on the cards is never searched again


async def search_venues(ctx: Ctx, a: dict) -> dict:
    key = ((a.get("what") or "").strip().lower(), (a.get("where") or "").strip().lower(), a.get("open_at"))
    last = _LAST_FIND.get(ctx.account)
    if last and last[0][:2] == key[:2] and time.time() - last[1] < 1200 \
            and not any(c.get("test") for c in (last[2].get("preset") or {}).get("cards") or []):   # Sasha 256 · a test card: asked again (the mode decides)
        # Sasha 212 · the same search again: the cards stand
        from agapi import venue_truth as VT, venues as VN
        cards = (last[2].get("preset") or {}).get("cards") or []
        sited = [c for c in cards if c.get("website")]   # only a card with a site can learn more from the venue engine
        if sited:   # Sasha 248 · the same cards — with their facts as the venue engine has them NOW (a read finished since)
            await VT.enrich(sited)
            last[2]["venues"] = [VN.card_for_model(c) for c in cards]
            VN.remember_cards(ctx.account, cards)
        from app.agent.sasha import s1_parity   # Sasha 249 · /next under parity too (248: a repeat within 20 min showed no cards there)
        if (ctx.surface == "s2" or s1_parity()) and last[2].get("preset"):   # Sasha 221 · /s2: a fresh page (a reload, a rehearsal) shows those SAME cards again — still no new search
            return {**{k: last[2][k] for k in ("venues", "find", "preset", "ribbon") if k in last[2]},
                    "note": "these are already on their cards — pick from them; no new search"}
        return {"venues": last[2]["venues"], "note": "these are already on their cards — pick from them; no new search"}
    res = await _search_venues(ctx, a)
    _LAST_FIND[ctx.account] = (key, time.time(), res)
    return res


async def _search_venues(ctx: Ctx, a: dict) -> dict:
    """Sasha 213 · ONE SOURCE: the same booking API search the cards read (/venues/find: its cache, its ranking, the day and
    time asked), and exactly the cards that will be SHOWN — the model is given those and nothing else, so she can only name
    what is on screen. The render event carries the same cards (the card never searches again) and the ribbon line."""
    from booking_signer import guest_whatsapp as GW
    from agapi import venues as VN
    picked = VN.named_on_screen(ctx.account, a.get("what"))
    if picked:   # Sasha 217 · a place already on their cards is PICKED, never searched for again (it brought other places)
        raise ToolError("already_on_screen", f"{picked.get('name')} is on their screen — that's their pick: call read_booking_route "
                                             f"with place_id {picked.get('place_id')} (never search for it again)")
    from agapi import test_venues as TV
    tv = await TV.search(ctx, a)   # Sasha 256 · a TEST person who names Kanoe's test venue: its card, no Places call
    if tv is not None:
        return tv
    body = {k: v for k, v in {"what": a["what"], "where": a["where"], "country": a.get("country"), "open_at": a.get("open_at"),
                              "near": a.get("near")}.items() if v}
    status, r = await GW.api(ctx.account, "POST", "/api/booking/venues/find", body)
    if status != 200:
        raise ToolError((r or {}).get("rule") or "find_failed", GW.refusal_words(r or {}, status))
    luxe = VN.one_path(ctx) and GW.luxe_of(a.get("what"))   # Sasha 253 · G14 — "luxury": €€€ and up first (the old flow's rule)
    shown = VN.shown_cards(r, luxe=luxe)
    if shown:
        await VN.photos_for(shown, budget=1.2)   # the top results' photos, prefetched (cached); the rest load lazily
    VN.remember_cards(ctx.account, shown)
    ribbon = VN.ribbon_line(a, shown, r) + (" (€€€ and up first)" if luxe and shown else "")
    return {"venues": [VN.card_for_model(c) for c in shown], "ribbon": ribbon,
            "on_screen": "these are EXACTLY the cards on their screen — name only these; nothing contacted",
            "find": {k: v for k, v in {"what": a["what"], "where": a["where"], "country": a.get("country"), "open_at": a.get("open_at"),
                                       "party": a.get("party")}.items() if v},
            "preset": {"all": r.get("candidates") or [], "ranking": r.get("ranking"), "show": r.get("show") or 5,
                       "near": r.get("near"), "cards": shown}}


# ── Sasha 205 · the prefetch: the slow work starts while she's still chatting ──────────────────────────────────────────────
_PREP: Dict[str, dict] = {}   # account → {"key", "origin", "itin": Task, "flights": {origin: Task}, "at"}


def _prep_key(a: dict) -> tuple:
    return ((a.get("destination") or "").strip().lower(), a.get("start_date"), int(a.get("nights") or 7), int(a.get("party") or 2))


def is_vietnam(destination: str) -> bool:
    """Sasha 211 · Vietnam has its own curated planner; every other country is planned by the world planner."""
    from app.services.hotels_db import VIETNAM_HOTELS
    d = (destination or "").strip().lower()
    return "vietnam" in d or any(d.startswith(c.lower()) for c in VIETNAM_HOTELS)


async def _build(a: dict, account: Optional[str] = None) -> dict:
    start = date.fromisoformat(a["start_date"])
    nights, party = int(a.get("nights") or 7), int(a.get("party") or 2)
    msg = (f"Plan a {nights + 1}-day trip to {a['destination']} from {start.day} {start.strftime('%B %Y')} for {party} people."
           + (f" Interests: {a['interests']}." if a.get("interests") else ""))
    if not is_vietnam(a.get("destination") or ""):   # Sasha 211 · ANY country: real Google hotels, estimates labelled
        from app.services.world_itinerary import build_world
        return {"itin": await build_world(a, account), "msg": msg}
    from app.services.itinerary_agent import build_itinerary
    itin = await build_itinerary(msg, [])
    return {"itin": itin, "msg": msg}


async def _search_legs(origin: str, days: List[dict], out_day: str, back_day: str, party: int, airports: Optional[dict] = None) -> dict:
    """Both legs searched ON the days given — Sasha 251 · the trip record's (plan_store.leg_days), never computed here (before:
    the out leg was `start - 1 day`, so a Saturday trip flew out on Friday). `asked` says which days were asked for."""
    import asyncio as _aio
    first_city = (next((d.get("city") for d in days if d.get("city")), "") or "").split(",")[0]
    last_city = (next((d.get("city") for d in reversed(days) if d.get("city")), first_city) or "").split(",")[0]
    ap = airports or {}   # Sasha 211 · the world planner names the airports (a last night by the sea has none of its own)
    legs = [("out", origin, ap.get("arrive") or airport_of(first_city), out_day),
            ("back", ap.get("depart") or airport_of(last_city), origin, back_day)]
    got = await _aio.gather(*[_search_healed(o, d, day, party) for _, o, d, day in legs])
    asked = {leg: day for leg, _, _, day in legs}
    legs = [(leg, o, d, used) for (leg, o, d, _), (_, used) in zip(legs, got)]
    return {"legs": legs, "found": [r for r, _ in got], "asked": asked}


def _moved(leg: str, asked: str, used: str) -> Optional[str]:
    """Sasha 251 · a leg flown on another day than the trip's is SAID, never silent: None when it's the trip's own day."""
    if not asked or not used or asked == used:
        return None
    a, u = date.fromisoformat(asked), date.fromisoformat(used)
    words = lambda d: f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"
    side = "earlier" if u < a else "later"
    n = abs((u - a).days)
    return (f"{'there' if leg == 'out' else 'home'}: no flight on {words(a)}, the trip's day — this one is on {words(u)}, "
            f"{n} day{'s' if n != 1 else ''} {side}; say so")


# Sasha 215 (f) · "BOOK IT" NEVER RE-PLANS (voice loop run 20, Portugal: on "book it" she proposed again — a new route, a
# second total in the booking turn). A turn whose words only ask to book what's proposed can't plan: what's on screen is booked.
_BOOK_WORDS = re.compile(r"(?i)\b(?:book|reserve|pay)\b")
_YES_ONLY = re.compile(r"(?i)^\s*(?:(?:ok(?:ay)?|right|so|then|great|perfect|lovely)[,!. ]+)*(?:yes|yeah|yep|sure|go ahead|do it|"
                       r"please do|let'?s do it|confirm)(?:[,!. ]+(?:please|thanks|thank you|go ahead))*[.! ]*$")
_CHANGE_ASK = re.compile(r"(?i)\b(?:change|instead|but|another|different|other|add|remove|swap|more|fewer|less|three|four|five|six|"
                         r"\d+|of us|people|nights?|days?|dates?|from|to|in|cheaper|earlier|later|first|second|table|dinner|lunch)\b")


def book_only(said: Optional[str]) -> bool:
    """The person's words this turn ask to BOOK, and nothing else ("Book it.", "Yes, book the whole trip", "Let's book")."""
    t = (said or "").strip()
    return bool(t) and len(t.split()) <= 8 and bool(_BOOK_WORDS.search(t)) and not _CHANGE_ASK.search(t)


async def _never_replan(ctx: Ctx) -> None:
    """Refused: a plan already on the account and words that only ask to book it — or a bare yes answering its read-back."""
    said = ctx.user_said or ""
    if (_YES_ONLY.match(said) and ctx.account in _HELD) or (book_only(said) and await _latest(ctx)):
        raise ToolError("book_not_replan", "they asked to BOOK what's proposed — never plan again: call hold_booking (and book "
                                           "on their yes); the trip and its total stay exactly as they heard them")


async def prepare_trip(ctx: Ctx, a: dict) -> dict:
    """Start the itinerary (and, once the origin is known, both legs' flight searches) in the background; returns at once."""
    import asyncio as _aio
    await _never_replan(ctx)
    try:
        date.fromisoformat(a["start_date"])
    except (KeyError, ValueError):
        raise ToolError("start_date_invalid", "start_date is YYYY-MM-DD")
    key = _prep_key(a)
    p = _PREP.get(ctx.account)
    if not p or p["key"] != key:
        p = _PREP[ctx.account] = {"key": key, "itin": _aio.create_task(_build(a, ctx.account)), "flights": {}, "args": dict(a)}
    origin = (a.get("origin") or "").strip()
    if origin and origin.lower() not in p["flights"]:
        async def legs(itin_task=p["itin"], o=origin):
            from booking_signer import plan_store as PS
            built = await itin_task
            itin = built.get("itin") or {}
            dd = PS.dates_for(a["start_date"], int(a.get("nights") or 7))   # Sasha 251 · the trip's own days (propose_trip re-checks them)
            return await _search_legs(o, itin.get("days") or [], dd["start"], dd["end"], int(a.get("party") or 2), itin.get("airports"))
        p["flights"][origin.lower()] = _aio.create_task(legs())
    return {"preparing": ["itinerary"] + (["flights"] if origin else []), "note": "keep chatting; propose_trip will pick this up"}


async def propose_trip(ctx: Ctx, a: dict) -> dict:
    """The itinerary with somewhere to stay each night AND a flight that fits, chosen — and the total. Nothing booked."""
    from app.services.itinerary_agent import build_itinerary
    from booking_signer import basket as BK, basket_book as BB, plan_store as PS, travel as T
    await _never_replan(ctx)
    try:
        start = date.fromisoformat(a["start_date"])
    except (KeyError, ValueError):
        raise ToolError("start_date_invalid", "start_date is YYYY-MM-DD")
    nights, party = int(a.get("nights") or 7), int(a.get("party") or 2)
    if not 1 <= nights <= 30 or not 1 <= party <= 9:
        raise ToolError("size_invalid", "nights 1–30, party 1–9")
    origin = a.get("origin") or "Madrid"
    t_pt, laps = time.perf_counter(), {}   # Sasha 257 · where propose_trip's 14–17 s goes (row 863), logged per phase
    def lap(k: str) -> None:
        laps[k] = int((time.perf_counter() - t_pt) * 1000) - sum(laps.values())
    prep = _PREP.get(ctx.account)
    used_prefetch = {"itinerary": False, "flights": False}
    built, legs_task = None, None
    if prep and prep["key"] == _prep_key(a):   # Sasha 205 · the work prepared during the intake
        try:
            built = await prep["itin"]
            used_prefetch["itinerary"] = True
            if origin.lower() not in prep["flights"]:
                await prepare_trip(ctx, {**prep["args"], "origin": origin})
            legs_task = prep["flights"][origin.lower()]
        except Exception as e:   # a prepared task failed: build it now instead
            log.info("[agapi] prefetch unusable (%s) — building now", type(e).__name__)
            _PREP.pop(ctx.account, None)
            built, legs_task = None, None
    if built is None:
        built = await _build(a, ctx.account)
    lap("itinerary")
    itin, msg = built["itin"], built["msg"]
    if not itin or not itin.get("days"):
        raise ToolError("plan_failed", "the itinerary couldn't be built just now — try again")
    itin["party"] = party
    # Sasha 251 · RIGHT DATES: decided once (plan_store.dates_for), carried by the plan, written on the trip record as they are;
    # each day of the plan dated from the first (the stays check in and out on them)
    itin["dates"] = PS.dates_for(a["start_date"], nights)
    for i, d in enumerate(itin["days"]):
        d["date"] = (start + timedelta(days=i)).isoformat()
    trip_id = await PS.save(ctx.account, itin, msg, datetime.now(timezone.utc))
    if not trip_id:
        raise ToolError("plan_not_saved", "the itinerary couldn't be saved on the account")
    # Sasha 251 · the flights read the ONE trip record: there ON its first day, home ON its last (plan_store.leg_days)
    rec = await PS.by_id(ctx.account, trip_id) or {"start": itin["dates"]["start"], "end": itin["dates"]["end"]}
    out_day, back_day = PS.leg_days(rec)
    want = {"out": out_day, "back": back_day}
    days = itin["days"]
    first_city = (next((d.get("city") for d in days if d.get("city")), a["destination"]) or "").split(",")[0]
    await BK.unchoose_flights(ctx.account, trip_id)
    flights, why = {}, []
    searched = None
    if legs_task is not None:
        try:
            searched = await legs_task
            used_prefetch["flights"] = True
        except Exception as e:
            log.info("[agapi] prefetched flights unusable (%s) — searching now", type(e).__name__)
    if searched is not None and searched.get("asked") != want:   # Sasha 251 · prefetched on other days than the record's: searched again
        log.info("[agapi] prefetched flights were for %s, the trip is %s — searching now", searched.get("asked"), want)
        searched, used_prefetch["flights"] = None, False
    if searched is None:
        searched = await _search_legs(origin, days, out_day, back_day, party, itin.get("airports"))
    lap("save+flight_search")
    options: Dict[str, List[dict]] = {}
    for (leg, o, d, day), r in zip(searched["legs"], searched["found"]):   # out AND back: a flight that fits on each leg (home after midday)
        if "why" in r:   # Sasha 210 · a prepared search that failed is searched again (and the nearest days) before saying so
            r, day = await _search_healed(o, d, want[leg], party)   # Sasha 251 · from the trip's own day
        if "why" in r:
            why.append(f"{leg}: {r['why']}")
            continue
        moved = _moved(leg, want[leg], day)   # Sasha 251 · another day than the trip's only when that day had none — and said
        if moved:
            why.append(moved)
        cards = _in_eur(r["cards"])   # Sasha 249 · in euros at ingestion (converted, never dropped to the $ estimate)
        if not cards:
            why.append(f"{leg}: no fares that can be priced in euros")
            continue
        ids = await _suggest_flights(ctx, trip_id, cards, o, d, day, party, leg)   # Sasha 249 · STORED before they're shown
        best = _best(cards, "12:00" if leg == "back" else "07:00")
        await BK.choose(ctx.account, ids[cards.index(best)])
        flights[leg] = _flight_out(best)
        options[leg] = _options(cards, best, stored={c["id"]: i for c, i in zip(cards, ids)})
    # Sasha 249 · ONE TOTAL: the stays priced at their provider once, as they arrive (store_prices — no airline called, nothing
    # swapped), then the figures READ from the basket: the figure she says now is the Trip tab's and the read-back's
    lap("flights_stored")
    why_priced = await BB.store_prices(ctx.account)
    fig = await BK.trip_figures(ctx.account, trip_id, {"trip_id": trip_id, "plan": itin})
    lap("prices+total")
    log.warning("[agapi] propose_trip ms %s prefetched=%s", laps, used_prefetch)   # Sasha 257 · visible in production's log
    q = {"eur": fig["total_eur"]} if fig["total_eur"] is not None else {"why": (why_priced or {}).get("why") or "nothing in this trip is priced yet"}
    hotel = lambda d: (d.get("hotel") or {}).get("name") if isinstance(d.get("hotel"), dict) else d.get("hotel")
    return {**({"breakdown": fig["breakdown"]} if "eur" in q else {}), "trip_id": trip_id, "title": itin.get("title"),
            "days": [{"day": d.get("day"), "city": d.get("city"), "stay": hotel(d), "title": d.get("title")} for d in days],
            "flight_out": flights.get("out"), "flight_back": flights.get("back"), **({"flight_note": "; ".join(why)} if why else {}),
            "flight_options": options, "party": party,
            "dates": {"start": out_day, "end": back_day, "nights": nights},   # Sasha 251 · the trip record's days, as she should say them
            "total_eur": q.get("eur") if "eur" in q else None, **({"total_note": q.get("why")} if "why" in q else {}),
            **({"how_total": TOTAL_HOW} if "eur" in q else {}),
            "prices": "stays at the TEST hotel rate, the flight at its Duffel TEST fare — nothing is booked", "prefetched": used_prefetch,
            **({"keep": kn} if flights and (kn := await _s1_passport(ctx, trip_id, bind=False)) else {})}   # Sasha 228 · said up front


HANDOFF_LINE = "Add your passport from your phone and I'll apply it."   # Sasha 228 · founder's words, 10 Oct
from agapi.s2_status import HELD as _ST_HELD   # noqa: E402 · Sasha 249 · a read-back's status, in the one status's words


async def _s1_passport(ctx: Ctx, trip_id: Optional[str], bind: bool = True) -> Optional[dict]:
    """Sasha 228 · S1 (/next, where SASHA_KEEP_S1 has the Keep on): a plan or hold with a FLIGHT needs the passport.
    In the Keep → bound to this booking (the read-back names it; the value opens only after their yes, at payment) and said up
    front: "I have your passport (ES ••••456) and will apply it." Not in it → the read-back as always, PLUS "Add your passport from
    your phone and I'll apply it." with the "Add from your phone" card (a one-time code) — never blocking: booking works without it.
    The Keep closed or unreachable → None: the booking goes on exactly as before. The mask only, ever."""
    from agapi.keep_gate import s1_on
    if ctx.surface == "s2" or not s1_on(ctx.account) or not trip_id:
        return None
    from booking_signer import basket as BK
    if not any(r.get("kind") == "flight" for r in await BK.items(ctx.account, trip_id, ("suggested", "chosen"))):
        return None
    try:
        pp = next((i for i in await _KEEP.list_(ctx.account) if i["type"] == "passport"), None)
    except _KEEP.KeepError:
        return None
    if pp is None:
        if not bind:
            return None   # the plan says nothing yet: the hold asks for it
        from agapi import keep_handoff as HO
        h = HO.mint(ctx.account, "passport")
        return {"handoff": {"code": h["code"], "kind": "passport", "expires_at": h["expires_at"]}, "say_first": HANDOFF_LINE,
                "note": "The 'Add from your phone' card (QR + short link) is on their screen beside the read-back. Booking works without "
                        "it — read back and take their yes as always. Never ask for the number in the chat."}
    short = re.sub(r"(?i)^passport\s+", "", pp["masked"]).strip()
    if bind:
        from agapi import keep as K
        if K.use_line(pp["masked"]) not in await _KEEP.lines(ctx.account):
            try:
                await _KEEP.bind(ctx.account, pp["item_id"], "fill")
            except _KEEP.KeepError:
                return None
    return {"masked": pp["masked"], "say_first": f"I have your passport ({short}) and will apply it."}


async def _swap_world(ctx: Ctx, p: dict, city: str, name: str) -> dict:
    """Sasha 211 · a world plan's hotel in one city → the chosen Google hotel (from the last search there, else searched by name)."""
    from app.services.world_itinerary import StaysDown, hotels_in, hotel_entry
    from booking_signer import plan_store as PS
    plan = json.loads(json.dumps(p.get("plan") or {}, default=str))
    try:
        shown = _STAYS.get(ctx.account, {}).get(city.lower()) or await hotels_in(ctx.account, city, plan.get("country") or "",
                                                                                 plan.get("country_code"), strict=True)
    except StaysDown:
        raise unreachable("stays_unreachable")
    h = next((x for x in shown if x["name"].lower() == name.lower()), None) or next((x for x in shown if name.lower() in x["name"].lower()), None)
    if h is None:
        raise ToolError("stay_not_found", f"{name} isn't among the hotels found in {city} — search_stays first")
    days = plan.get("days") or []
    for i, d in enumerate(days[:-1]):
        if (d.get("city") or "").lower().startswith(city.lower()):
            d["hotel"] = hotel_entry(h, d.get("city") or city)
    start = p.get("start")
    start = date.fromisoformat(str(start)[:10]) if start else None
    msg = (f"Plan a {len(days)}-day trip to {plan.get('country') or city} from {start.day} {start.strftime('%B %Y')} for {plan.get('party') or 2} people."
           if start else f"change the hotel in {city}")
    await PS.save(ctx.account, plan, msg, datetime.now(timezone.utc))
    from booking_signer import basket_book as BB
    await BB.store_prices(ctx.account)   # Sasha 249 · the new stay priced once, as it arrives
    return {"city": city, "stay": h["name"], "estimate_eur_per_night": h["est_eur"], **(await _total(ctx, await _plan(ctx)))}


async def swap_stay(ctx: Ctx, a: dict) -> dict:
    from app.services.itinerary_agent import build_itinerary
    from booking_signer import plan_store as PS
    p = await _plan(ctx)
    plan = p.get("plan") or {}
    city = a["city"]
    if not any((d.get("city") or "").lower().startswith(city.lower()) for d in plan.get("days") or []):
        raise ToolError("city_not_in_trip", f"{city} isn't in this trip")
    if plan.get("planner") == "world":
        return await _swap_world(ctx, p, city, a["stay_name"])
    new = await build_itinerary(f"change the hotel in {city} to {a['stay_name']}", [], current_itinerary=plan,
                                hotel_swap={"name": a["stay_name"], "city": city})
    if not new or not new.get("days"):
        raise ToolError("swap_failed", "the stay couldn't be changed just now")
    new["party"] = plan.get("party")
    await PS.save(ctx.account, {**new, "title": plan.get("title") or new.get("title")}, f"change the hotel in {city}", datetime.now(timezone.utc))
    from booking_signer import basket_book as BB
    await BB.store_prices(ctx.account)   # Sasha 249 · the new stay priced once, as it arrives
    p = await _plan(ctx)
    return {"city": city, "stay": a["stay_name"], **(await _total(ctx, p))}


# ── Sherlock ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def check_offer(ctx: Ctx, a: dict) -> dict:
    from booking_signer import travel as T
    try:
        st, j = await T.call_duffel("GET", f"/air/offers/{a['offer_id']}")
    except T.DuffelDown:   # Sasha 215 · not answering is not "unavailable"
        raise unreachable("airline_unreachable")
    if st != 200:
        return {"available": False, "reason": T._err(j, st)}
    o = j["data"]
    eur = _FX.to_eur(o["total_amount"], o["total_currency"])   # Sasha 249 · in euros at fx.py's one rate (before: any currency as euros)
    return {"available": True, "price_eur": eur, "currency": o["total_currency"], "expires_at": o.get("expires_at"),
            **({"fare": {"amount": o["total_amount"], "currency": o["total_currency"], "rate_as_of": _FX.as_of()}}
               if str(o["total_currency"]).upper() != "EUR" else {})}


async def read_booking_route(ctx: Ctx, a: dict) -> dict:
    from agapi import venues as VN   # Sasha 211 · through the booking API (its read_id is what the routes book from)
    return await VN.read_booking_route(ctx, a)


# ── Austen ───────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def choose_offer(ctx: Ctx, a: dict) -> dict:
    from booking_signer import basket as BK
    p = await _plan(ctx)
    row = await BK.by_ref(ctx.account, p["trip_id"], a["offer_id"]) if a.get("offer_id") else await _find_option(ctx, p, a)
    if not row:   # Sasha 253 · never a bare "couldn't find": what IS on that leg travels with the refusal
        raise ToolError("offer_not_in_trip", await _not_an_option(ctx, p, a))
    row, moved = await _still_offered(ctx, p, row)   # Sasha 253 · a fare that went away is said, with what's there now
    leg = (row.get("slice_key") or "out:").split(":", 1)[0]
    for other in await BK.items(ctx.account, p["trip_id"], ("chosen",)):   # one flight per LEG (searches of the leg may differ)
        if other["kind"] == "flight" and other["id"] != row["id"] and (other.get("slice_key") or "").split(":", 1)[0] == leg:
            async def fn(conn, oid=other["id"]):
                import uuid as _u
                await conn.execute("update trip_basket_items set state = 'suggested', updated_at = now() where id = $1", _u.UUID(oid))
            await BK._go(fn)
    try:
        row = await BK.choose(ctx.account, row["id"])
    except BK.BasketError as e:
        raise ToolError("not_choosable", str(e))
    return {"chosen": _flight_out(row.get("snapshot") or {}, row), **({"price_moved": moved} if moved else {}), **(await _total(ctx, p))}


def _said_hhmm(v: Any) -> Optional[str]:
    """Sasha 253 · a time as the model passes it → "HH:MM": as hhmm() reads it ("5:48pm", "17.48"), or the HH:MM inside a longer
    string ("2026-11-02T20:05", "20:05 one") — before, an ISO departure was cut to "2026-" and matched nothing."""
    t = hhmm(v)
    if t:
        return t
    m = re.search(r"(?<!\d)([01]?\d|2[0-3])[:.h]([0-5]\d)(?!\d)", str(v or ""))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def _option_line(r: dict) -> str:
    s = r.get("snapshot") or {}
    dep, arr = str(s.get("departs") or "")[11:16], str(s.get("arrives") or "")[11:16]
    day = str(s.get("departs") or r.get("day") or "")[:10]
    eur = r.get("price_amount")
    route = f" {s['from']}→{s['to']}" if s.get("from") and s.get("to") else ""
    return (f"{s.get('owner') or 'a flight'}{route} on {day}, departs {dep}" + (f", lands {arr}" if arr else "")
            + (f" (€{float(eur):.2f})" if eur is not None else ""))


def _leg_options(rows: List[dict], leg: Optional[str]) -> List[str]:
    """Sasha 253 · the options she can book on a leg (stored, choosable), one line each, by departure — no duplicates."""
    out, seen = [], set()
    pick = [r for r in rows if r["kind"] == "flight" and (leg is None or _row_leg(r) in (leg, None))]
    for r in sorted(pick, key=lambda r: str((r.get("snapshot") or {}).get("departs") or "")):
        line = _option_line(r)
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out[:10]


async def _not_an_option(ctx: Ctx, p: dict, a: dict) -> str:
    """Sasha 253 · OFFERED == BOOKABLE, the refusal: a flight she never offered is said to be "not one of the options", and the
    options on that leg go with it (never "couldn't find" alone). No options stored on that leg: search it first, as before."""
    from booking_signer import basket as BK
    leg = leg_said(ctx.user_said) or a.get("leg")
    rows = [r for r in await BK.items(ctx.account, p["trip_id"], ("suggested", "chosen")) if r["kind"] == "flight"]
    opts = _leg_options(rows, leg)
    if not opts:
        return "no flight like that among this trip's options — search_flights for that leg first"
    what = " ".join(x for x in (a.get("airline") or "", f"at {a['departs']}" if a.get("departs") else "") if x).strip() or "like that"
    return (f"no flight {what} is one of this trip's options. Say so plainly in one line (it's not one of the options), then offer "
            f"these — each can be put in with choose_offer by its departure time: " + "; ".join(opts))


def _expired(r: dict) -> bool:
    at = r.get("expires_at") or (r.get("snapshot") or {}).get("expires_at")
    if not at:
        return False
    try:
        t = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        return False
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)) <= datetime.now(timezone.utc)


async def _still_offered(ctx: Ctx, p: dict, row: dict) -> tuple:
    """Sasha 253 · a fare she offered whose Duffel offer has expired is re-checked at the swap (Sherlock, basket_book's one check):
    still offered (maybe a new price) → that row, refreshed, and the move said; gone → refused in plain words with what's there now,
    from a fresh search STORED FIRST (so every time she then names can be booked); Duffel not answering → kept as it is (hold_booking
    re-checks before any payment). An unexpired fare is put in as it stands (no call). → (row, the price move or "")."""
    if not _expired(row):
        return row, ""
    from booking_signer import basket_book as BB
    party = _party(p, [row])
    if party is None:
        return row, ""
    v = await BB._validate_flight(ctx.account, row, party)
    if v.get("outage") or "row" in v:
        return v.get("row") or row, (v.get("note") or "").strip(" ()")
    c = BB._card(row)
    gone = f"{c.get('owner') or 'that flight'} at {str(c.get('departs') or '')[11:16]}"
    leg, rest = (str(row.get("slice_key") or "out:").split(":", 1) + [""])[:2]
    route, _, day = rest.rpartition(" ")
    origin, _, dest = route.partition("→")
    origin, dest = origin or c.get("from") or "", dest or c.get("to") or ""
    day = day if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day or "") else str(c.get("departs") or row.get("day") or "")[:10]
    now: List[str] = []
    try:
        res, used = await _search_healed(airport_of(origin), airport_of(dest), day, party)
        cards = [] if "why" in res else _in_eur(res.get("cards") or [])[:6]
        if cards:   # stored first, then said: what she offers next is in the basket
            await _suggest_flights(ctx, p["trip_id"], cards, origin, dest, used, party, leg or "out")
            now = [_option_line({"snapshot": x, "price_amount": x.get("price_eur")}) for x in
                   sorted(cards, key=lambda x: str(x.get("departs") or ""))]
    except Exception as e:   # the search failing never turns "gone" into "chosen"
        log.warning("[agapi] after a gone fare, the leg's search failed: %s: %s", type(e).__name__, e)
    raise ToolError("not_choosable", f"the {gone} fare is no longer offered by the airline, so it wasn't put in — the trip's flight on "
                    "that leg is unchanged. Say that plainly in one line, then " + (
                        "offer what's there now (each can be put in with choose_offer by its departure time): " + "; ".join(now)
                        if now else "say there's nothing else that day just now and offer to look at another day"))


async def _find_option(ctx: Ctx, p: dict, a: dict) -> Optional[dict]:
    """Sasha 210 · a flight among the trip's options (the proposal's cards, a search's) by what the person said or tapped:
    the leg, and the airline and/or departure time ("the British Airways flight out at 08:30"), or the cheapest / fastest.
    Sasha 249 · OFFERED == BOOKABLE (the 17:48 fault: "Move our flight home to the 17:48" — offered, then "couldn't find": the leg
    defaulted to "out" and the time had to be typed HH:MM). Matched on (leg, time): the leg from the person's own words first
    ("home" / "back" / "return" = back), else the one given, else either leg when the time names one flight; the time as said
    ("5:48pm", "17.48"); every option shown earlier still matches (superseded rows too — the newest preferred)."""
    from booking_signer import basket as BK
    said_leg, given_leg = leg_said(ctx.user_said), a.get("leg")
    every = [r for r in await BK.items(ctx.account, p["trip_id"], ("suggested", "chosen")) if r["kind"] == "flight"]
    snap = lambda r: r.get("snapshot") or {}

    # Sasha 253 · the time as said or passed (an ISO departure too), matched on the departure — else on the LANDING time: she
    # names both ("at 20:05, landing at 22:20"), so "the 22:20 one" is that flight, never "couldn't find"
    hh = _said_hhmm(a["departs"]) if a.get("departs") else None

    def described(rows: List[dict], when: str = "departs") -> List[dict]:
        if a.get("airline"):
            rows = [r for r in rows if (a["airline"].lower() in str(snap(r).get("owner") or "").lower())]
        if a.get("departs"):
            rows = [r for r in rows if str(snap(r).get(when) or "")[11:16] == hh]
        return rows

    rows: List[dict] = []
    for when in ("departs", "arrives") if hh else ("departs",):
        for leg in [x for x in (said_leg, given_leg) if x] or ([None] if a.get("departs") else ["out"]):   # no leg, no time: out, as before
            rows = described([r for r in every if leg is None or _row_leg(r) in (leg, None)], when)
            if rows:
                break
        if not rows and a.get("departs"):   # the time names exactly one flight, on whichever leg it is
            anywhere = described(every, when)
            rows = anywhere if len({_row_leg(r) for r in anywhere}) == 1 else []
        if rows:
            break
    if not rows:
        return None
    fresh = [r for r in rows if not BK.superseded(r)]
    rows = fresh or rows   # the newest search's row first; an earlier one still books
    if hh and len({r.get("slice_key") for r in rows}) > 1 and all(r.get("created_at") for r in rows):
        newest = max(rows, key=lambda r: str(r["created_at"]))["slice_key"]   # Sasha 253 · the same time on two searched days:
        rows = [r for r in rows if r.get("slice_key") == newest]               # the one she listed last
    if a.get("pick") == "fastest":
        return min(rows, key=lambda r: int(snap(r).get("minutes") or 9e9))
    return min(rows, key=lambda r: float(r.get("price_amount") or 9e9))   # "cheapest", or the cheapest of the ones described


def _row_leg(r: dict) -> Optional[str]:
    """Sasha 249 · a flight row's leg from its slice ("out:…" / "back:…"); None for a slice with no leg (the cheapest-fare pick)."""
    sk = str(r.get("slice_key") or "")
    return "back" if sk.startswith("back:") else "out" if sk.startswith("out:") else None


async def save_travellers(ctx: Ctx, a: dict) -> dict:
    from booking_signer import passengers as PX
    people, bad = [], []
    for t in a.get("travellers") or []:
        try:
            born = date.fromisoformat(t["date_of_birth"])
        except (KeyError, ValueError):
            bad.append(f"{t.get('given_name', '?')} {t.get('family_name', '')}: date_of_birth YYYY-MM-DD"); continue
        title = (t.get("title") or "").lower().strip(".")
        if title not in ("mr", "ms", "mrs", "miss", "dr"):
            bad.append(f"{t.get('given_name')}: title mr/ms/mrs/miss/dr"); continue
        gender = {"mr": "m", "ms": "f", "mrs": "f", "miss": "f"}.get(title) or {"male": "m", "female": "f"}.get((t.get("gender") or "").lower())
        if not gender:
            bad.append(f"{t.get('given_name')}: gender"); continue
        if not (t.get("given_name") and t.get("family_name")):
            bad.append("a full name (given and family)"); continue
        people.append({"given_name": t["given_name"].strip().title(), "family_name": t["family_name"].strip().title(),
                       "born_on": born, "title": title, "gender": gender})
    n = await PX.save(ctx.account, people) if people else 0
    return {"saved": n, "travellers_on_file": len(await PX.saved(ctx.account)), "invalid": bad}


async def hold_booking(ctx: Ctx, a: dict) -> dict:
    """The read-back: every item re-checked (Sherlock) and priced; no money moves. book() binds the yes to its sha256."""
    from booking_signer import basket as BK, basket_book as BB, passengers as PX
    p = await _plan(ctx)
    before = await BK.trip_figures(ctx.account, p["trip_id"], p)   # Sasha 249 · the figure she has said, before the re-check
    have, need = len(await PX.saved(ctx.account)), before["party"]
    if need is None:   # Sasha 249 · ONE PARTY: never a silent 2 — asked once
        raise ToolError("party_unknown", "how many are travelling isn't on the trip — ask them once (e.g. “Just to check — how many of "
                                         "you are going?”), then read it back")
    if have < need:
        raise ToolError("travellers_missing", f"the airline needs each traveller's full name, title and date of birth — {have} of {need} on file")
    kept = await _s1_passport(ctx, p.get("trip_id"))   # Sasha 228 · S1: the passport, up front (never blocks)
    held = _HELD.get(ctx.account)
    if held and held.get("result") and (datetime.now(timezone.utc) - held["at"]).total_seconds() < 120:   # Sasha 205 · just checked
        import hashlib as _h
        cur = await BB.current(ctx.account)
        if cur and _h.sha256("\n".join(BB.lines_of(cur["rows"], cur["party"])).encode()).hexdigest() == held["sha"] and \
                (kept or {}).get("masked") == (held["result"].get("keep") or {}).get("masked"):   # Sasha 228 · a passport added since: read again
            return {**held["result"], "reused": "checked under two minutes ago and nothing has changed"}
    q = await BB.quote(ctx.account, a.get("origin") or "Madrid")
    if q.get("outage"):   # Sasha 215 · CR 56 #3 — the airline not answering: said, and the chosen flights are never swapped
        raise unreachable("airline_unreachable")
    changed: List[str] = []
    if "why" in q and "no longer offered" in q["why"]:   # Sasha 210 · a flight gone: the closest one on that leg put in, then said
        changed = await _replace_gone_flights(ctx, p)
        q = await BB.quote(ctx.account, a.get("origin") or "Madrid")
        if q.get("outage"):
            raise unreachable("airline_unreachable")
    if "why" in q:
        raise ToolError("not_bookable", q["why"])
    est = any(l.rstrip(")").endswith("(estimate") for l in q["lines"])   # Sasha 211 · real hotels priced as estimates
    rows_now = BK.to_book(await BK.items(ctx.account, p["trip_id"], ("suggested", "chosen")))
    after = await BK.trip_figures(ctx.account, p["trip_id"], p)   # Sasha 249 · ONE TOTAL: the figures after the re-check
    res = {"breakdown": breakdown(rows_now, q["eur"]),   # Sasha 215 · the re-quote reaches the page: the pill and the total card refresh
           **({"changed": changed} if changed else {}), **({"stays_are_estimates": True} if est else {}), "read_back": [l for l in q["lines"] if not l.startswith("Note:")], "notes": [l for l in q["lines"] if l.startswith("Note:")],
            "read_back_sha256": q["sha256"], "total_eur": q["eur"], "status": _ST_HELD,   # Sasha 249 · the one status's words
            "trip_total_eur": after["total_eur"] if after["total_eur"] is not None else q["eur"], "party": after["party"] or need, "how": TOTAL_HOW}
    was, now = before.get("total_eur"), res["trip_total_eur"]
    if was and now is not None and abs(float(was) - float(now)) >= 0.005:   # Sasha 249 · the re-check moved it: said once, by her
        res["total_changed"] = {"from": was, "to": now,
                                "say": f"The prices moved when I re-checked them: it's €{now:,.2f} now, not €{was:,.2f}."}
        res["how_total_changed"] = "Say total_changed.say as it is, once, before the read-back."
    if q.get("spoken_flights"):   # Sasha 246 · the spoken read-back names BOTH flights, the outbound first — this line, as it is
        res["say_flights"] = q["spoken_flights"]
        res["how_flights"] = "When you sum it up, say say_flights as it is (both flights, the outbound first)."   # in the result: S1's schema unchanged
    from agapi.keep_gate import keep_on
    if keep_on(ctx.account, ctx.surface):   # Sasha 224 · CR 63 — a bound passport is NAMED in what she reads out (where the Keep is on)
        res["read_back"] += await _KEEP.lines(ctx.account)
    if kept:   # Sasha 228 · said in this turn, before the read-back — the mask only
        res["keep"] = kept
    prev = _HELD.get(ctx.account)   # Sasha 210 · the same words read back again keep the time they were first said
    at = prev["at"] if prev and prev.get("sha") == q["sha256"] else datetime.now(timezone.utc)
    _HELD[ctx.account] = {"sha": q["sha256"], "at": at, "result": res}   # Sasha 205 · book() uses it as is
    return res


async def _replace_gone_flights(ctx: Ctx, p: dict) -> List[str]:
    """Each chosen flight Duffel no longer offers → the closest departure on the same leg and day, chosen in its place.
    → one plain line per change ("Iberia at 10:35 is gone — Iberia at 11:50 is in its place.")."""
    from booking_signer import basket as BK, basket_book as BB
    chosen_rows = [x for x in await BK.items(ctx.account, p["trip_id"], ("chosen",)) if x["kind"] == "flight"]
    party, out = _party(p, chosen_rows), []   # Sasha 249 · ONE PARTY (refresh() refused before this when it's unknown)
    if party is None:
        return out
    for r in chosen_rows:
        v = await BB._validate_flight(ctx.account, r, party)
        if "why" not in v or v.get("outage"):   # Sasha 215 · only a flight Duffel SAID is gone is ever replaced
            continue
        c = BB._card(r)
        day = str(c.get("departs") or r.get("day") or "")[:10]
        res, used = await _search_healed(c.get("from") or "", c.get("to") or "", day, party)
        cards = _in_eur(res.get("cards") or [])   # Sasha 249 · converted at ingestion, as every search
        if not cards:
            continue
        want = str(c.get("departs") or "")[11:16] or "12:00"
        mins = lambda hhmm: int(hhmm[:2]) * 60 + int(hhmm[3:5]) if len(hhmm) >= 5 else 720
        near = min(cards, key=lambda x: abs(mins(str(x.get("departs") or "")[11:16]) - mins(want)))
        leg, rest = ((r.get("slice_key") or "out:").split(":", 1) + [""])[:2]
        ids = await _suggest_flights(ctx, p["trip_id"], [near], c.get("from") or "", c.get("to") or "", used, party, leg or "out")
        await choose_offer(ctx, {"offer_id": near["id"]})
        out.append(f"{c.get('owner')} at {want} is gone — {near.get('owner')} at {str(near.get('departs') or '')[11:16]} is in its place.")
    return out


# Sasha 220 · WHERE THEY PAY — "here" (a card in the conversation: Stripe Embedded Checkout, Apple Pay / Google Pay where the
# device has them) or "phone" (the WhatsApp link, exactly as before). Read from the person's OWN words in code, never the model's;
# asked once when they have WhatsApp (no WhatsApp → here, never a dead end); remembered for the conversation; switchable.
_HERE = re.compile(r"(?i)\b(?:(?:pay\s+)?here|right here|on here|this (?:screen|device|page|phone|laptop|computer)|in (?:the )?chat|"
                   r"on (?:the|this) (?:laptop|computer|screen)|on screen)\b")
_PHONE = re.compile(r"(?i)\b(?:(?:on|to) my (?:phone|mobile)|my phone|whatsapp|text me|(?:send|text) (?:it|me) (?:to my phone|the link)|"
                    r"on (?:the )?phone)\b")
_PAY_CHOICE: Dict[tuple, str] = {}    # (account, conversation) → "here" | "phone"
_PAY_ASKED: Dict[str, dict] = {}      # account → {sha, at}: "Pay here, or on your phone?" asked after their yes, awaiting the answer
PAY_ASK = "Pay here, or on your phone?"
_PAY_NOT = re.compile(r"(?i)\b(?:no|not|don'?t|do not|wait|hold on|later|stop|cancel\w*)\b")   # "not here", "wait" — never the answer


def pay_words(said: Optional[str]) -> Optional[str]:
    """ "here" / "phone" when the words choose (this device first: "on this phone" is HERE), else None."""
    t = said or ""
    if _HERE.search(t):
        return "here"
    if _PHONE.search(t):
        return "phone"
    return None


async def _whatsapp_linked(account: str) -> bool:
    try:
        from booking_signer import guest_whatsapp as GW
        return bool(GW.STORE and await GW.STORE.channel_of_account(account))
    except Exception:
        return False


async def book(ctx: Ctx, a: dict) -> dict:
    """The yes → ONE Stripe TEST payment for exactly the read-back — here (an embedded checkout) or on their phone (the WhatsApp
    link). Booked only after payment (Pacioli: get_status)."""
    from booking_signer import basket_book as BB
    said = ((a.get("approval") or {}).get("said")) or ""
    chose = pay_words(said)
    key = (ctx.account, ctx.session or "-")
    asked = _PAY_ASKED.get(ctx.account)
    answering = bool(asked and chose and not stale(asked["at"]) and not _PAY_NOT.search(said) and "?" not in said)
    switching = bool(chose and not answering and await BB.in_progress(ctx.account))
    if not (yes_to_book(said) or answering or switching):
        raise ToolError("no_explicit_yes", "booking needs the person's explicit yes in this turn — ask them, then call book")
    linked = await _whatsapp_linked(ctx.account)
    if chose == "phone" and not linked:   # no WhatsApp: never "on your phone" — here, and said why
        if switching:
            return {"status": "no_whatsapp", "booked": False, "say": "There's no WhatsApp linked to this account, so the payment stays "
                    "here on their screen. They can link WhatsApp to pay on their phone."}
        chose = "here"
    if switching:   # a payment under way, moved to the other place (or the same one again): never a second payment
        got = await BB.pay(ctx.account, "", chose)
        _PAY_CHOICE[key] = chose
        return await _paid_out(ctx, got, chose)
    sha = a.get("read_back_sha256") or ""
    held = _HELD.get(ctx.account)
    if not answering:
        if held and (not sha or sha == held["sha"]) and held["at"] >= ctx.started:   # Sasha 210 · the yes answers a read-back they HEARD
            raise ToolError("read_back_first", "say the read-back's total and ask them to go ahead; book once they say yes")
    # Sasha 215 · the yes is bound to a read-back they heard in the last 15 minutes — never to an older one, never to none
    if not held or (sha and sha != held["sha"]) or (answering and asked["sha"] != held["sha"]):
        raise ToolError("no_read_back", "call hold_booking first — the yes is bound to a read-back they've just heard")
    if stale(held["at"]):
        _HELD.pop(ctx.account, None)
        raise ToolError("read_back_stale", "that read-back is over 15 minutes old — call hold_booking again and read it back before booking")
    sha = held["sha"]   # pay() still refuses if anything changed since
    where = chose or _PAY_CHOICE.get(key)
    if where is None:
        if linked:   # asked ONCE; their answer (next turn) pays — the yes is already given
            _PAY_ASKED[ctx.account] = {"sha": sha, "at": datetime.now(timezone.utc), "said": said}
            return {"status": "choose_payment", "ask": PAY_ASK, "booked": False,
                    "say": "Ask exactly this, once, and wait: their answer pays (no yes needed again)."}
        where = "here"   # no WhatsApp: here, never a dead end
    _PAY_ASKED.pop(ctx.account, None)
    _PAY_CHOICE[key] = where
    await claim(ctx)   # Sasha 215 · durable: this payment is sent once, across restarts and workers
    got = await BB.pay(ctx.account, sha, where)
    from agapi.keep_gate import keep_on
    if got.get("session_id") and "why" not in got and keep_on(ctx.account, ctx.surface):   # Sasha 224 · CR 63 — this yes, this payment
        try:
            await _KEEP.approve(ctx.account, held["result"]["read_back"], ((asked or {}).get("said") if answering else None) or said, got["session_id"])
        except Exception as e:
            log.warning("[keep] approve skipped: %s", type(e).__name__)
    return await _paid_out(ctx, got, where)


async def _paid_out(ctx: Ctx, got: dict, where: str) -> dict:
    if got.get("unrecorded"):   # Sasha 215 · CR 56 #2 — no record, no link: said as it is
        raise ToolError("payments_unreachable", got["why"])
    if got.get("already_paid"):   # Sasha 220 · one payment per basket: never charged twice
        return {"status": "already_paid", "booked": False, "session_id": got.get("session_id"),
                "say": "It's already paid — nothing more to pay. It's booked once Stripe's confirmation is recorded (get_status says)."}
    if "why" in got:
        raise ToolError("read_back_changed" if "different words" in got["why"] else "not_bookable", got["why"])
    if where == "here":
        return {"status": "awaiting_payment", "payment": "here", "session_id": got["session_id"], "total_eur": got["eur"], "booked": False,
                "checkout": {k: got.get(k) for k in ("client_secret", "url", "session_id")},   # for the page; never shown to the model
                "say": "The card is on their screen: they pay there (Apple Pay / Google Pay where their device has them)."}
    sent = str(got.get("phone") or "").startswith("sent")
    return {"status": "awaiting_payment", "payment": "sent_to_phone" if sent else "link", **({} if sent else {"payment_url": got["url"]}),
            "session_id": got["session_id"], "total_eur": got["eur"], "booked": False}


# ── Pacioli ──────────────────────────────────────────────────────────────────────────────────────────────────────────────

STATUS_HOW = ("line is THE status, the same words as the Trip tab. Say every part of it — what's booked AND what's \"Chosen, not "
              "booked yet\" or still a request — in your own short words; never leave a not-booked item out, never call it booked.")


async def get_status(ctx: Ctx, a: dict) -> dict:
    """Sasha 249 · ONE STATUS: agapi.s2_status.status_of is the one place a booking's status is decided (the Trip banner, the /s2
    card and the WhatsApp line read it too). Its keys as before, plus its state and line. Sasha 259 · + how (S2 item 12: "what's
    coming up" said the booked table and left the trip's chosen flights out, though the line carried them — once in three runs)."""
    from agapi import s2_status as ST
    return {**await ST.status_of(ctx.account), "how": STATUS_HOW}


async def hold_venue(ctx: Ctx, a: dict) -> dict:
    from agapi import venues as VN
    return await VN.hold_venue(ctx, a)


async def book_venue(ctx: Ctx, a: dict) -> dict:
    from agapi import venues as VN
    return await VN.book_venue(ctx, a)


async def cancel_venue(ctx: Ctx, a: dict) -> dict:
    from agapi import venues as VN
    return await VN.cancel_venue(ctx, a)


READ_BACK_HOW = ("This is the trip as it stands. When you read it back, end with total_eur — the trip's ONE total, the same figure "
                 "as the chat and the Trip tab — said exactly (\"about €X\" may round it to the euro); if estimates is set, say the "
                 "stays are estimates. Never add up the items yourself. The dates are start and end, as on the trip.")


async def get_trip(ctx: Ctx, a: dict) -> dict:
    """The trip as it stands, from the ONE trip record (its dates) and the ONE total — Sasha 251 · the read-back carries
    basket.trip_figures()' total (found live 12 Oct: she read the items back and gave no total). Read only."""
    from booking_signer import basket as BK
    p = await _plan(ctx)
    rows = await BK.items(ctx.account, p["trip_id"])
    fig = await BK.trip_figures(ctx.account, p["trip_id"], p)   # Sasha 251 · the same figures get_total, the Trip tab and the guard read
    hotel = lambda d: (d.get("hotel") or {}).get("name") if isinstance(d.get("hotel"), dict) else d.get("hotel")
    est = [l["what"] for l in fig.get("estimate_lines") or []]
    return {"trip_id": p["trip_id"], "title": p.get("title"), "start": str(p.get("start") or ""), "end": str(p.get("end") or ""),
            "party": fig.get("party") if fig.get("party") is not None else _party(p, rows),
            "days": [{"day": d.get("day"), "city": d.get("city"), "stay": hotel(d)} for d in (p.get("plan") or {}).get("days") or []],
            "flights": [_flight_out(r.get("snapshot") or {}, r) for r in rows if r["kind"] == "flight" and r["state"] != "suggested"],
            "stays": [{"name": (r.get("snapshot") or {}).get("name"), "from": r.get("day"), "nights": (r.get("snapshot") or {}).get("nights"),
                       "state": r["state"], "price_eur": r.get("price_amount"), "price_source": r.get("price_source")} for r in rows if r["kind"] == "stay"],
            # Sasha 251 · the ONE total (EU 246 D5/T4), its instruction in the RESULT (S1's schemas and prompt stay byte-identical)
            "total_eur": fig["total_eur"], "currency": "EUR",
            **({"total_note": "nothing in this trip is priced yet"} if fig["total_eur"] is None else {}),
            **({"estimates": f"{', '.join(est)}: an estimate, not a quoted price"} if est else {}),
            **({"ask_party": fig["ask_party"]} if fig.get("ask_party") else {}),
            "how": READ_BACK_HOW + " " + TOTAL_HOW}


async def get_total(ctx: Ctx, a: dict) -> dict:
    """Sasha 249 · basket.trip_figures(), read only — the guard calls this at every turn's end, so it must never re-price."""
    return await _total(ctx, await _plan(ctx))


# ── the contract ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def _t(name: str, agent: str, fn: Callable[[Ctx, dict], Awaitable[dict]], description: str, props: dict, required: List[str],
       output: dict, errors: List[str], austen: bool = False) -> dict:
    inp = {"type": "object", "properties": {**props, **({"idempotency_key": IDEM} if austen else {})},
           "required": required + (["idempotency_key"] if austen else []), "additionalProperties": False}
    return {"name": name, "agent": agent, "fn": fn, "description": description, "input_schema": inp, "output_schema": output,
            "errors": errors, "idempotent": austen}


VENUE_PROPS = {"name": {"type": "string"}, "city": {"type": "string"}, "country": {"type": "string"}, "place_id": {"type": "string"},
               "website": {"type": "string"}, "type": {"type": "string", "description": "the card's type, e.g. Seafood restaurant"}}

TOOLS: List[dict] = [
    _t("search_flights", "Magellan", search_flights, "Flights between two places on a day, cheapest first (TEST fares). Shown "
       "flights become the trip's suggestions for that leg.", {"origin": {"type": "string"}, "destination": {"type": "string"}, "date": DATE,
                                                  "leg": {"enum": ["out", "back"], "description": "out (there) or back (home); default out"},
                                                  "passengers": {"type": "integer", "minimum": 1, "maximum": 9},
                                                  "preferences": {"type": "string", "description": "e.g. direct, morning"}},
       ["origin", "destination", "date"], {"type": "object", "properties": {"flights": {"type": "array", "items": FLIGHT}}}, ["no_flights", "airline_unreachable"]),
    _t("search_stays", "Magellan", search_stays, "Places to stay in a city, best rated first: real hotels (Google), each with an ESTIMATED nightly price.",
       {"city": {"type": "string"}, "preference": {"type": "string", "description": "e.g. on the beach, boutique"}}, ["city"],
       {"type": "object", "properties": {"stays": {"type": "array"}}}, ["city_not_covered"]),
    _t("search_venues", "Magellan", search_venues, "Restaurants, spas or other places in a city (Google listings; nothing contacted). "
       "The person sees them as photo cards and picks one by tap or voice; booking it goes through that venue's own route.",
       {"what": {"type": "string"}, "where": {"type": "string"}, "country": {"type": "string", "pattern": "^[A-Z]{2}$"},
        "open_at": {"type": "string", "description": "the local date-time wanted, YYYY-MM-DDTHH:MM (on the trip's day)"},
        "party": {"type": "integer", "minimum": 1, "maximum": 20}}, ["what", "where"],
       {"type": "object", "properties": {"venues": {"type": "array"}}}, ["what_invalid", "where_invalid", "places_not_configured", "already_on_screen"]),
    _t("prepare_trip", "Magellan", prepare_trip, "Start getting the trip ready in the background the moment destination, dates "
       "and party are known (and again once the origin is): the itinerary, then both legs' flights. Returns at once — keep "
       "chatting; propose_trip with the same details picks it up.",
       {"destination": {"type": "string"}, "start_date": DATE, "nights": {"type": "integer", "minimum": 1, "maximum": 30, "description": "NIGHTS away: \"10 days\" is 9 nights, \"a week\" is 7"},
        "party": {"type": "integer", "minimum": 1, "maximum": 9}, "interests": {"type": "string"}, "origin": {"type": "string"}},
       ["destination", "start_date", "nights", "party"],
       {"type": "object", "properties": {"preparing": {"type": "array"}}}, ["start_date_invalid", "book_not_replan"]),
    _t("propose_trip", "Magellan", propose_trip, "THE PROPOSAL: a day-by-day itinerary with somewhere to stay each night, a flight "
       "that fits on each leg (there and back) already chosen, and the whole trip's total. Replaces the account's current proposal. Nothing is booked.",
       {"destination": {"type": "string"}, "start_date": DATE, "nights": {"type": "integer", "minimum": 1, "maximum": 30, "description": "NIGHTS away: \"10 days\" is 9 nights, \"a week\" is 7"},
        "party": {"type": "integer", "minimum": 1, "maximum": 9}, "interests": {"type": "string"},
        "origin": {"type": "string", "description": "where they fly from"}},
       ["destination", "start_date", "nights", "party", "origin"],
       {"type": "object", "properties": {"trip_id": {"type": "string"}, "days": {"type": "array"}, "flight_out": FLIGHT, "flight_back": FLIGHT,
                                         "total_eur": {"type": "number"}}},
       ["start_date_invalid", "size_invalid", "plan_failed", "plan_not_saved", "book_not_replan"]),
    _t("swap_stay", "Magellan", swap_stay, "Change where they stay in one city of the trip (take a name from search_stays). Returns the new total.",
       {"city": {"type": "string"}, "stay_name": {"type": "string"}}, ["city", "stay_name"], TOTAL, ["no_trip", "city_not_in_trip", "swap_failed", "not_priced"]),
    _t("check_offer", "Sherlock", check_offer, "Is this flight offer still available, and at what price?", {"offer_id": {"type": "string"}},
       ["offer_id"], {"type": "object", "properties": {"available": {"type": "boolean"}, "price_eur": {"type": "number"}}}, ["airline_unreachable"]),
    _t("read_booking_route", "Sherlock", read_booking_route, "How a venue takes bookings (its own form, a platform page, email, phone, "
       "WhatsApp) — read from its site and listing. Use the venue card's place_id.",
       {**VENUE_PROPS, "what": {"type": "string", "description": "what they want, e.g. dinner"}},
       ["name", "city"], {"type": "object", "properties": {"routes": {"type": "array"}, "how": {"type": "string"}}}, ["name_invalid", "city_invalid"]),
    _t("choose_offer", "Austen", choose_offer, "Put another flight into the trip, replacing the flight on that leg. Returns the new total. "
       "Give its offer_id, OR describe one of the trip's options (the proposal's flight cards, a search's): its leg and the airline "
       "and/or departure time a tap or the person named (\"the British Airways flight out at 08:30\"), or pick cheapest/fastest.",
       {"offer_id": {"type": "string"}, "leg": {"enum": ["out", "back"]}, "airline": {"type": "string"},
        "departs": {"type": "string", "description": "HH:MM"}, "pick": {"enum": ["cheapest", "fastest"]}}, [], {"type": "object", "properties": {"chosen": FLIGHT, **TOTAL["properties"]}},
       ["no_trip", "offer_not_in_trip", "not_choosable"], austen=True),
    _t("save_travellers", "Austen", save_travellers, "Save the travellers the airline needs (asked once, kept on the account).",
       {"travellers": {"type": "array", "items": {"type": "object", "properties": {
           "given_name": {"type": "string"}, "family_name": {"type": "string"}, "date_of_birth": DATE,
           "title": {"enum": ["mr", "ms", "mrs", "miss", "dr"]}, "gender": {"enum": ["male", "female"]}},
           "required": ["given_name", "family_name", "date_of_birth", "title"]}}}, ["travellers"],
       {"type": "object", "properties": {"saved": {"type": "integer"}, "travellers_on_file": {"type": "integer"}, "invalid": {"type": "array"}}},
       [], austen=True),
    _t("hold_booking", "Austen", hold_booking, "The read-back before booking: every item re-checked and priced, the total, and the "
       "sha256 the yes binds to. No money moves; nothing is booked.", {"origin": {"type": "string"}}, [],
       {"type": "object", "properties": {"read_back": {"type": "array"}, "read_back_sha256": {"type": "string"}, "total_eur": {"type": "number"}}},
       ["no_trip", "travellers_missing", "not_bookable", "airline_unreachable", "store_unreachable"], austen=True),
    _t("book", "Austen", book, "After the person's explicit yes in THIS turn: one payment (Stripe TEST) for exactly the read-back they "
       "just heard (the last hold_booking, unless read_back_sha256 is given), sent to their phone. Nothing is booked until it is paid — get_status says when.",
       {"read_back_sha256": {"type": "string"}, "approval": {"type": "object", "properties": {"said": {"type": "string"}},
                                                               "description": "the person's own words (filled by the caller from the real message)"}},
       [], {"type": "object", "properties": {"status": {"const": "awaiting_payment"}, "booked": {"const": False}}},
       ["no_explicit_yes", "no_read_back", "read_back_stale", "read_back_changed", "not_bookable", "already_done", "payments_unreachable",
        "store_unreachable"], austen=True),
    _t("hold_venue", "Austen", hold_venue, "Prepare a venue booking (a restaurant, a spa…) by its route: the ladder's own question "
       "first when it has one (status choose_route: ask it, then call again with the route they pick), else the read-back the "
       "yes binds to (status awaiting_yes: say it in a line and ask them to go ahead). A place that books only by a WhatsApp "
       "or Instagram message (status draft_message): read the drafted message and offer to send it to their phone — they "
       "send it; it is never booked until the place replies. Nothing is sent.",
       {**VENUE_PROPS, "what": {"type": "string", "description": "e.g. dinner, a table, a massage"}, "day": DATE,
        "time": {"type": "string", "description": "HH:MM, the venue's local time"}, "party": {"type": "integer", "minimum": 1, "maximum": 20},
        "route": {"enum": ["form", "page", "email", "call", "whatsapp", "instagram", "no"], "description": "the route they chose (from choose_route)"}},
       ["name", "city", "day", "time", "party"], {"type": "object", "properties": {"status": {"type": "string"}, "read_back": {"type": "array"}}},
       ["read_failed", "when_invalid", "contact_missing", "no_route"], austen=True),
    _t("book_venue", "Austen", book_venue, "After the person's explicit yes in THIS turn, to what hold_venue read back in an earlier "
       "turn: the booking, by its route — their form (any human step goes to their phone as Tap to finish), the platform's page "
       "to their phone, the email, or the call. Its status says what's true: confirmed only on the venue's own confirmation.",
       {"approval": {"type": "object", "properties": {"said": {"type": "string"}}}}, [],
       {"type": "object", "properties": {"status": {"type": "string"}}}, ["no_explicit_yes", "nothing_held", "read_back_first", "read_back_stale", "not_sent", "already_done", "store_unreachable",
        "hold_first"], austen=True),
    _t("cancel_venue", "Austen", cancel_venue, "Cancel a venue booking, back the way it was made. First call: the read-back (say it, ask); "
       "after their explicit yes in a LATER turn, call again to send it.",
       {"trip_item_id": {"type": "string"}, "venue": {"type": "string"}, "approval": {"type": "object", "properties": {"said": {"type": "string"}}}},
       [], {"type": "object", "properties": {"status": {"type": "string"}}}, ["booking_unknown", "no_explicit_yes", "not_cancelled", "already_done", "store_unreachable"], austen=True),
    _t("get_status", "Pacioli", get_status, "What is booked, failed, cancelled or awaiting payment — the ONLY source for booked/paid/confirmed.",
       {}, [], {"type": "object", "properties": {"booked": {"type": "array"}, "anything_booked": {"type": "boolean"}}}, ["no_trip"]),
    _t("get_trip", "Pacioli", get_trip, "The trip as it stands: days and stays, the chosen flights, each item's state.", {}, [],
       {"type": "object"}, ["no_trip"]),
    _t("get_total", "Pacioli", get_total, "The whole trip's total from the basket (what booking would charge).", {}, [], TOTAL, ["no_trip"]),
]
BY_NAME = {t["name"]: t for t in TOOLS}
from agapi import s2_tools as _S2   # noqa: E402 · CR 60 / Sasha 216 · email from Sasha's address + calendar (agapi/powers.py)
TOOLS += _S2.tools()
from agapi import s2_whatsapp as _WA, activity as _ACT   # noqa: E402 · CR 62 / Sasha 217 · WhatsApp to someone named + the Activity view
TOOLS += _WA.tools() + _ACT.tools()
BY_NAME.update({t["name"]: t for t in TOOLS})
# Sasha 224 · CR 63's Keep + the photo capture: callable, but NOT in TOOLS (S1's list) — the model is given them only where the Keep
# is on (agapi.keep_gate: /s2 always; /next only with SASHA_KEEP_S1=1 for the founder). S1 is exactly as before by default.
from agapi import s2_keep as _KEEP, keep_scan as _SCAN   # noqa: E402 · masks only
KEEP_TOOLS: List[dict] = _KEEP.tools() + _SCAN.tools()
BY_NAME.update({t["name"]: t for t in KEEP_TOOLS})
from agapi import s2_home as _HOME   # noqa: E402 · Sasha 225 · /s2 only: what she can do (a card) and what she can't YET (noted, masked)
HOME_TOOLS: List[dict] = _HOME.tools()
BY_NAME.update({t["name"]: t for t in HOME_TOOLS})
from agapi import s2_manage as _MANAGE   # noqa: E402 · Sasha 226 · /s2 only: my plans; change / cancel; running late
MANAGE_TOOLS: List[dict] = _MANAGE.tools()
BY_NAME.update({t["name"]: t for t in MANAGE_TOOLS})
from agapi import s2_hotel as _HOTEL   # noqa: E402 · Sasha 235 · /s2 only: a request to their hotel (upgrade my room) — not in TOOLS (S1)
MANAGE_TOOLS += _HOTEL.tools()
BY_NAME.update({t["name"]: t for t in MANAGE_TOOLS})
_HELD: Dict[str, dict] = {}   # account → the last read-back's sha256 (hold_booking), for book
_IDEM: Dict[str, dict] = {}   # the fast path in this process; claim() is the durable one (Sasha 215)
ACTS = {"book", "book_venue", "cancel_venue", "send_email", "send_whatsapp"}   # spend, send or cancel: claimed once, durably, before they act
READS = {"search_flights", "search_stays", "search_venues", "check_offer", "read_booking_route", "get_status", "get_trip", "get_total",
         "add_to_calendar", "get_activity", "keep_list"}
ACTS = ACTS | {"running_late", "change_booking", "cancel_booking"}   # Sasha 226 · claimed once, durably, before they act
READS = READS | {"my_plans"}


def _act_bound_to(account: str, name: str) -> Optional[str]:
    """Sasha 258 · the read-back an act answers (its sha), for the act's once-only key: book_venue → the held booking's, cancel_venue →
    the held cancellation's. None for other tools (their key is as it was)."""
    try:
        if name == "book_venue":
            from agapi import venues as _VN
            h = _VN._HELD.get(account) or {}
            return str(h.get("sha") or h.get("read_back_id") or "")[:24] or None
        if name == "cancel_venue":
            from agapi import venues as _VN
            h = _VN._CANCEL.get(account) or {}
            return str(h.get("sha") or h.get("read_back_id") or h.get("id") or "")[:24] or None
    except Exception:
        return None
    return None


async def call(ctx: Ctx, name: str, args: dict) -> dict:
    """The one entry: {"ok": true, "result": …} or {"ok": false, "error": {"code", "message"}}. Never raises."""
    t = BY_NAME.get(name)
    if not t:
        return {"ok": False, "error": {"code": "unknown_tool", "message": f"no tool {name} in AgAPI {VERSION}"}}
    if ctx.mode != "test":
        return {"ok": False, "error": {"code": "mode_not_available", "message": "AgAPI v0 runs in TEST mode only"}}
    args = dict(args or {})
    req = t["input_schema"]["required"]
    if name == "hold_venue":   # Sasha 253 · G7 / G8 — on the one path a request may have no time (venues.required_of)
        from agapi import venues as _VN
        req = _VN.required_of(ctx, name, req)
    miss = [k for k in req if args.get(k) in (None, "")]
    if miss:
        return {"ok": False, "error": {"code": "missing_input", "message": f"missing: {', '.join(miss)}"}}
    key = None
    t_call = time.perf_counter()
    if t["idempotent"]:
        key = f"{ctx.account}:{name}:{args['idempotency_key']}"
        bound = _act_bound_to(ctx.account, name)
        if bound:   # Sasha 258 · the once-only key belongs to the READ-BACK it answers — a model that reuses its key for a new booking
            key = f"{key}:{bound}"   # never gets "already done" (found on the scoreboard's account, which books the same venue every run)
        if key in _IDEM:
            return {**_IDEM[key], "replayed": True}
    ctx.idem, ctx.claimed = (key if name in ACTS else None), None
    ctx.act_name = ctx.act_said = None
    if ctx.surface == "s2" and name in ACTS:   # CR 76 · their words, heard as the approval if they answer an earlier read-back
        from agapi import yes_gate as YG
        ctx.act_name, ctx.act_said = name, ((args.get("approval") or {}).get("said")) or ctx.user_said
        YG.heard(ctx, name, ctx.act_said)
    try:
        from agapi import agapi_route as _AR
        with _AR.acting(ctx.account):   # Sasha 256 · every AgAPI call a tool makes is FOR this person (the venue engine's reads too)
            res = {"ok": True, "result": await t["fn"](ctx, args)}
    except ToolError as e:
        res = {"ok": False, "error": {"code": e.code, "message": e.message}}
        if e.code != "already_done":
            await _unclaim(ctx)   # refused before anything was sent: the next yes may act
    except Exception as e:
        log.error("[agapi] %s failed: %s: %s", name, type(e).__name__, e)
        # Sasha 215 · CR 56 #5 — "nothing was changed" only when it's TRUE: a read changes nothing; anything else may have
        # got partway (the plan replaced, a payment session opened, a message sent) and is checked before anything is said
        res = {"ok": False, "error": {"code": "internal", "message": (
            f"{name} failed ({type(e).__name__}) — a lookup only, so nothing was changed" if name in READS else
            f"{name} failed partway ({type(e).__name__}) — it may or may not have taken effect: check get_status / get_trip "
            "before saying anything was or wasn't done")}}
    ctx.idem = ctx.claimed = ctx.act_name = ctx.act_said = None
    out = res.get("result") if res["ok"] else None
    if ctx.surface == "s2" and res["ok"]:   # CR 76 · a read-back shown is recorded for THE ONE YES RULE
        from agapi import yes_gate as YG
        YG.shown(ctx, name, out)
    ctx.calls.append({"tool": name, "ok": res["ok"], "agent": t["agent"], "ms": int((time.perf_counter() - t_call) * 1000),
                      **({"status": out.get("status")} if isinstance(out, dict) and out.get("status") else {}),
                      **({"code": res["error"]["code"]} if not res["ok"] else {})})
    from agapi import measure as MS   # Sasha 275 · S1 measure — observation only: how far a booking got, and why it stopped
    MS.tool(ctx, name, args, res, ctx.calls[-1]["ms"])
    if key and res["ok"]:
        _IDEM[key] = res
        try:
            from booking_signer import basket as BK
            await BK.event("agapi", hashlib.sha256(key.encode()).hexdigest()[:40], name, {"args": {k: v for k, v in args.items() if k != "approval"}},
                           verified=True)
        except Exception as e:
            log.info("[agapi] idempotency not recorded: %s", type(e).__name__)
    return res


def schema_for_model(t: dict) -> dict:
    """The tool as the model sees it: no idempotency_key and no approval (the caller fills both, never the model)."""
    s = json.loads(json.dumps(t["input_schema"]))
    for k in ("idempotency_key", "approval"):
        s["properties"].pop(k, None)
        if k in s.get("required", []):
            s["required"].remove(k)
    return {"name": t["name"], "description": f"[{t['agent']}] {t['description']}", "input_schema": s}


__all__ = ["VERSION", "Ctx", "ToolError", "TOOLS", "BY_NAME", "call", "explicit_yes", "yes_to_cancel", "schema_for_model"]
