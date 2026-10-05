"""S-36 · the ladder's routes — included into /api/booking by routes.py.

    POST /api/booking/venues/read              name, city (country, website) → what Magellan read + the rungs + her sentence
    GET  /api/booking/venues/read/{read_id}    the same read, with the rungs recomputed against today's configuration
    POST /api/booking/emails                   read_id + particulars → the exact email, read back (nothing is sent)
    POST /api/booking/emails/{email_id}/send   the yes → claim → Resend → record EXACTLY what Resend answered
    GET  /api/booking/emails/{email_id}        the email as it stands, and every reply, word for word
    POST /api/booking/email/inbound            Resend's inbound webhook — svix-verified, matched by address

The phone rung is call_routes.py: `POST /api/booking/calls` now also takes `read_id`, and the number is the one READ.

⚠ Nobody signs in (account.py). A read makes this server fetch a public web page (robots first, public hosts only,
never a booking platform); an email is capped at SASHA_EMAILS_PER_DAY (default 5) across everyone, as calls are at 3.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import calls as C
from . import emailing as E
from . import ladder as L
from . import optins as O
from . import places_terms as PT
from . import reservation as RS
from . import slot_link as SL
from . import stop as S
from . import venue_read as V
from . import yes as YS
from .account import account_for
from .call_store import cap_window
from .store import AlreadyRecorded, StorageUnavailable, UnknownTrip

log = logging.getLogger("sasha.booking_ladder")
router = APIRouter(tags=["booking-ladder"])
APPROVAL_WINDOW = timedelta(minutes=15)

# ── injectable for tests ──────────────────────────────────────────────────────────────────────
LADDER_STORE: Any = None


async def HTTP(method: str, url: str, headers: dict, json: Optional[dict] = None):
    from .http_pool import request   # Sasha 149 · one pooled, kept-alive client (no new TLS handshake per call)
    return await request(method, url, timeout=15.0, headers=headers, json=json)


RESOLVE = V._resolve


def NOW() -> datetime:
    return datetime.now(timezone.utc)


def email_cap() -> int:
    try:
        return max(0, int(os.getenv("SASHA_EMAILS_PER_DAY", "5")))
    except ValueError:
        return 5


def account_email_cap() -> int:
    """S-62 step 2 · emails per ACCOUNT per 24 h, as well as the server's cap (SASHA_EMAILS_PER_ACCOUNT_PER_DAY, default 5)."""
    try:
        return max(0, int(os.getenv("SASHA_EMAILS_PER_ACCOUNT_PER_DAY", "5")))
    except ValueError:
        return 5


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


async def _json(request: Request) -> Optional[dict]:
    try:
        body = await request.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


def status() -> dict:
    """For /api/booking/health."""
    return {"places_configured": bool(V.places_key()), "emails": L.emails_ready() or "ready",
            "calls": L.calls_ready() or "ready", "sasha_number_set": C.sasha_number() is not None,
            "emails_per_day": email_cap(), "emails_per_account_per_day": account_email_cap()}


def read_reuse_hours() -> float:
    try:
        return float(os.getenv("SASHA_READ_REUSE_H", "") or 6)
    except ValueError:
        return 6.0


def _read_view(row: dict, read: Optional[dict] = None) -> dict:
    """`read`: the read with its listing re-read (places_terms.hydrate_read) — shown, never stored."""
    read = read if read is not None else row["read"]
    chosen = L.choose(read, account=row.get("account_id"))
    return {"read_id": row["read_id"], "venue": read["name"], "country": read.get("country"), "listing": read.get("listing"),
            "facts": [{k: f[k] for k in ("kind", "value", "source_label", "source_url", "snippet", "fetched_at")} for f in read["facts"]],
            "sources": read["sources"], "rungs": chosen["rungs"], "say": chosen["say"],
            **({"listing_reread": read["listing_reread"]} if read.get("listing_reread") else {})}


# ── reading a venue ───────────────────────────────────────────────────────────────────────────

@router.post("/venues/read")
async def read_venue(request: Request):
    from .limits import check
    over = check(account_for(request), "read")   # Sasha 120
    if over:
        return over
    body = await _json(request)
    if isinstance(body, dict) and body.get("place_id") == REHEARSAL_ID:   # Sasha 121 · the rehearsal card: OUR test venue's own page
        from .form_rung import test_venue_url
        body = {"name": "Sasha Test Venue", "city": body.get("city") or "Madrid", "country": "ES", "website": test_venue_url()}
    if body is None:
        return _refuse(400, "read_malformed", "send {name, city, country?, website?} as a JSON object")
    if any(k in body for k in ("phone", "number", "phone_number", "email", "to")):
        return _refuse(422, "contact_from_request", "a venue's contact details are READ from what it publishes, never taken from the request")
    now = NOW()
    # Sasha 140 · this account read this listing's site recently: reuse OUR read (the venue's own site's facts), with the
    # listing's facts re-read from Google now (places_terms) — a read is seconds of fetching; a reuse is one listing call
    if body.get("place_id") and hasattr(LADDER_STORE, "recent_read") and read_reuse_hours() > 0:
        try:
            row = await LADDER_STORE.recent_read(account_for(request), str(body["place_id"]), now - timedelta(hours=read_reuse_hours()))
        except StorageUnavailable:
            row = None
        if row:
            return _read_view(row, await PT.hydrate_read(HTTP, row["read"], now))
    try:
        read = await V.read_venue(HTTP, name=body.get("name"), city=body.get("city"), country=body.get("country"),
                                  website=body.get("website") or None, now=now, resolve=RESOLVE,
                                  place_id=body.get("place_id") or None,   # S-65 · the listing picked in "Find venues"
                                  asked_for=body.get("asked_for") if isinstance(body.get("asked_for"), str) else None)
    except V.ReadRefused as e:
        return _refuse(422, e.rule, str(e))
    # Sasha 64 · A · stored WITHOUT the listing's content: a name picked from the Google Maps cards is the listing's, so
    # only the guest's own words ("asked_for") are kept with the place_id; the full read is shown once, now
    keys = ("city", "country", "website", "place_id", "asked_for") if body.get("place_id") else ("name", "city", "country", "website")
    row = {"read_id": str(uuid.uuid4()), "account_id": account_for(request),
           "query": {k: body.get(k) for k in keys},
           "venue_name": read.name, "country": read.country, "read": PT.storable_read(read.to_json()), "created_at": now}
    try:
        await LADDER_STORE.put_read(row)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return _read_view(row, {**read.to_json(), "listing": {**(read.listing or {}), "attribution": "Google Maps"} if read.listing else None})


@router.post("/draft")
async def draft_route(request: Request):
    """S-66 step 7 · the parts of reservation/1 a text states, worded for the venue's country — the chat's booking card
    asks only for what is missing. Deterministic (chat_request.draft); nothing is contacted, nothing is stored."""
    body = await _json(request)
    if body is None:
        return _refuse(400, "draft_malformed", "send {text, country?} as a JSON object")
    from .chat_request import draft
    country = str(body.get("country") or "").upper()
    lang = V.COUNTRIES[country][2] if country in V.COUNTRIES else "en"
    return draft(str(body.get("text") or "")[:500], NOW(), lang)


REHEARSAL_ID = "sasha-test-venue"


def _with_rehearsal(account: str, out: dict) -> dict:
    """Sasha 121 · rehearsing (SASHA_REHEARSAL=1, the founder's account only): our test venue is the THIRD card on every
    surface (the web chat as WhatsApp), named as what it is — booking it contacts no one."""
    from .guest_whatsapp import rehearsal
    from .form_rung import test_venue_url
    if not rehearsal(account) or not isinstance(out, dict):
        return out
    card = {"place_id": REHEARSAL_ID, "name": "Sasha Test Venue (ours — rehearsal, not a real restaurant)", "country": "ES",
            "website": test_venue_url(), "rating": None, "rating_count": None, "distance_m": None}
    rk = dict(out.get("ranking") or {})
    rk["orders"] = {k: list(v)[:2] + [REHEARSAL_ID] + list(v)[2:] for k, v in (rk.get("orders") or {}).items()}
    return {**out, "candidates": list(out.get("candidates") or []) + [card], "ranking": rk}


@router.post("/venues/find")
async def find_venues(request: Request):
    """S-65 · "Find venues": {what, where, country?} → up to twenty Google listings (S-68), not stored. Search only — nothing is contacted."""
    from .limits import check
    over = check(account_for(request), "find")   # Sasha 120 · each search is a paid Places request
    if over:
        return over
    body = await _json(request)
    if body is None:
        return _refuse(400, "find_malformed", "send {what, where, country?} as a JSON object")
    try:
        _rehearse = _with_rehearsal if not re.search(r"\b(hotel|room|stay|hostel|homestay)\b", str(body.get("what") or ""), re.I) \
            else (lambda a, out: out)   # Sasha 132 · our test RESTAURANT is never offered as a hotel
        out = await V.find_venues(HTTP, what=body.get("what"), where=body.get("where"),
                                  country=body.get("country"), now=NOW(), near=body.get("near"), open_at=body.get("open_at"))   # S-68 steps 3–4
        await _with_google_photos(out)
        return _rehearse(account_for(request), out)
    except V.ReadRefused as e:
        return _refuse(503 if e.rule in ("places_not_configured", "places_unreachable", "places_refused") else 422, e.rule, str(e))


async def _with_google_photos(out: dict, budget: float = 0.7) -> None:
    """Sasha 156 · the cards shown first (every chip's top ones) arrive WITH their Google photo's URL, so the picture loads
    as the card appears; whatever misses the budget is fetched by the chat afterwards (/venues/gphotos)."""
    import asyncio
    orders = ((out.get("ranking") or {}).get("orders") or {})
    show = int(out.get("show") or V.SHOW_MAX)
    want = {pid for order in orders.values() for pid in (order or [])[:show]} or {c["place_id"] for c in out.get("candidates", [])[:show]}
    cards = [c for c in out.get("candidates") or [] if c.get("place_id") in want and (c.get("gphoto") or {}).get("name")][:12]
    if not cards:
        return
    tasks = {c["place_id"]: asyncio.ensure_future(V.google_photo_uri(HTTP, c["gphoto"]["name"])) for c in cards}
    done, pending = await asyncio.wait(tasks.values(), timeout=budget)
    for t in pending:
        t.cancel()
    for c in cards:
        t = tasks[c["place_id"]]
        if t in done and not t.cancelled() and t.exception() is None and t.result():
            c["gphoto"] = {**c["gphoto"], "uri": t.result()}


@router.post("/venues/gphotos")
async def venue_google_photos(request: Request):
    """Sasha 156 · {names: [the cards' Google photo names, ≤ 8], width?} → {photos: {name: a short-lived public URL}}: the
    fallback picture for a card whose venue's own site names none. The key stays here; nothing is stored."""
    import asyncio
    body = await _json(request) or {}
    names = [n for n in (body.get("names") or []) if isinstance(n, str) and V.PHOTO_NAME.fullmatch(n)][:8]
    try:
        width = int(body.get("width") or 480)
    except (TypeError, ValueError):
        width = 480
    uris = await asyncio.gather(*(V.google_photo_uri(HTTP, n, width) for n in names))
    return {"photos": {n: u for n, u in zip(names, uris) if u}}


STYLER = None   # S-68 step 9 · tests inject one; None is the model (style.anthropic_styler)


@router.post("/venues/style")
async def venue_style(request: Request):
    """S-68 step 9 · style tags for the 3–5 cards shown, from each venue's OWN website (robots first), AI-summarised and
    quoted; never Google reviews; nothing stored. {what, venues: [{place_id, website}]} → {styles: {place_id: …}}."""
    from . import style as ST
    body = await _json(request)
    venues = body.get("venues") if body else None
    if not isinstance(venues, list) or not all(isinstance(v, dict) for v in venues):
        return _refuse(400, "style_malformed", "send {what, venues: [{place_id, website}]} as a JSON object")
    if len(venues) > ST.MAX_SITES:
        return _refuse(422, "style_too_many", f"style is read for the cards shown — at most {ST.MAX_SITES} sites")
    return {"styles": await ST.styles(HTTP, venues, str(body.get("what") or ""), resolve=RESOLVE, styler=STYLER)}


@router.get("/venues/read/{read_id}")
async def get_read(read_id: str, request: Request):
    try:
        row = await LADDER_STORE.get_read(account_for(request), read_id)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if row is None:
        return _refuse(404, "read_unknown", "no venue read with that id for this account")
    return _read_view(row, await PT.hydrate_read(HTTP, row["read"], NOW()))


async def _optin_refusal(venue_ids, channel: str, scope: Optional[str] = None):
    """S-54 · the refusal check as a response, or None. ⚠ Fails CLOSED: if the opt-in record cannot be read, nothing is sent."""
    try:
        r = await O.refusal_for(venue_ids, channel, scope)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, f"{e.detail}; the venue's opt-in record could not be checked, so nothing was sent")
    return _refuse(403, r.rule, f"{r.message} Nothing was sent.") if r else None


# ── the phone rung's venue, from a read (used by call_routes) ─────────────────────────────────

async def call_venue_from_read(account: str, read_id: Any, fact_index: Any = None, speak: Any = None) -> C.CallVenue:
    row = await LADDER_STORE.get_read(account, str(read_id))
    if row is None:
        raise C.CallRefused("read_unknown", "no venue read with that id for this account")
    read = await PT.hydrate_read(HTTP, row["read"], NOW())   # Sasha 64 · a listing number is re-read, not stored
    phones = [(i, f) for i, f in enumerate(read["facts"]) if f["kind"] == "phone" and f.get("value")]
    if isinstance(fact_index, int):
        phones = [(i, f) for i, f in phones if i == fact_index]
    if not phones:
        raise C.CallRefused("no_phone_read", "no phone number was read for this venue"
                            + (f" ({read['listing_reread']})" if read.get("listing_reread", "").startswith("not") else ""))
    # B · the venue's OWN number first (the read lists its site's facts first); the listing's only when it has none
    _, f = sorted(phones, key=lambda x: x[1].get("source_kind") != "site")[0]
    country = read.get("country")
    if country not in V.COUNTRIES:
        raise C.CallRefused("venue_country_unknown", "the venue's country is not known, so neither its language nor its day can be")
    _, _, country_lang, tz = V.COUNTRIES[country]
    lang, why = C.spoken_language(country_lang, speak if isinstance(speak, str) else None)   # Sasha 128 · English abroad
    return C.CallVenue(key=f"read:{row['read_id']}", name=read["name"], number_env="", language=lang, timezone=tz,
                       number=f["value"], source=f["source_label"], venue_ids=tuple(O.venue_ids_of(read)),
                       number_kind=f.get("source_kind"), place_id=PT.place_id_of(read), language_why=why)


def _plan_of(body: Any) -> Optional[str]:
    """Sasha 132 · a plan line, only in the shape escalation.plan_line makes (it names that it is covered by the yes)."""
    from . import escalation as ESC
    p = body.get("plan_line") if isinstance(body, dict) else None
    return p.strip() if isinstance(p, str) and ESC.MARK in p and len(p) <= 400 else None


# ── the email rung ────────────────────────────────────────────────────────────────────────────

@router.post("/emails")
async def prepare_email(request: Request):
    why = L.emails_ready()
    if why:
        return _refuse(422, "emails_disabled", f"{why}; nothing was written")
    body = await _json(request)
    if body is None:
        return _refuse(400, "email_malformed", "send {read_id, date, time, party, name, email} as a JSON object")
    account = account_for(request)
    try:
        row = await LADDER_STORE.get_read(account, str(body.get("read_id")))
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if row is None:
        return _refuse(404, "read_unknown", "no venue read with that id for this account")
    read = row["read"]
    chosen = L.best_email(read["facts"])
    if not chosen:
        return _refuse(422, "no_email_read", "no email address was read for this venue")
    refused = await _optin_refusal(O.venue_ids_of(read), "email")
    if refused:
        return refused
    try:
        p = E.parse_email_particulars(body, C.parse_call_particulars)
    except (E.EmailRefused, C.CallRefused) as e:
        return _refuse(422, e.rule, str(e))
    country = read.get("country")
    lang, tz = (V.COUNTRIES[country][2], V.COUNTRIES[country][3]) if country in V.COUNTRIES else ("en", "UTC")
    email_id = str(uuid.uuid4())
    f = chosen[1]
    email = E.compose(lang, read["name"], f["value"], p, email_id)
    lines = E.read_back(email, read["name"], f["source_label"])
    plan = _plan_of(body)   # Sasha 132 · the escalation the guest's ONE yes covers, said before the yes, in its hash
    if plan:
        lines.insert(len(lines) - 1, plan)
    if lang not in E.TEMPLATE_LANGS:   # Sasha 130 · e.g. Vietnam: written in English, and said so before the yes
        from .i18n import emails as I18N   # CR 7 i18n · …unless an i18n template is usable: then it says THAT
        lines.insert(1, I18N.read_back_line(lang, f["value"])
                     or f"I'll write in English: I have no {C.LANGUAGE_NAMES.get(lang, repr(lang))} template.")
    rec = {"request": RS.try_from_particulars(p, account_id=account, venue_name=read["name"], timezone=tz, lang=lang,
                                              venue_ids=O.venue_ids_of(read), read_id=str(row["read_id"])),   # S-64 step 3
           "email_id": email_id, "account_id": account, "read_id": row["read_id"], "email": email,
           "email_sha256": E.email_sha256(email), "read_back_lines": lines, "read_back_sha256": C._sha256hex("\n".join(lines)),
           "created_at": NOW(), "venue_name": read["name"], "local_date": p.on, "local_time": p.at, "local_timezone": tz,
           "party_size": p.party}
    try:
        item = await LADDER_STORE.put_email(rec, None)
    except UnknownTrip:
        return _refuse(404, "trip_unknown", "no such trip")
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"email_id": email_id, "trip_item_id": item, "read_back": {"lines": lines, "sha256": rec["read_back_sha256"]}}


@router.post("/emails/{email_id}/send")
async def send_email(email_id: str, request: Request):
    why = L.emails_ready()
    if why:
        return _refuse(422, "emails_disabled", f"{why}; nothing was sent")
    body = await _json(request)
    if body is None:
        return _refuse(400, "approval_void", "send {read_back_sha256, approval: {how, said}} as a JSON object")
    account = account_for(request)
    try:
        e = await LADDER_STORE.get_email(account, email_id)
    except StorageUnavailable as ex:
        return _refuse(503, ex.rule, ex.detail)
    if e is None:
        return _refuse(404, "email_unknown", "no email with that id was prepared for this account")
    if body.get("read_back_sha256") != e["read_back_sha256"]:
        return _refuse(422, "approval_void", "the approval was given to different words from this email's read-back")
    a = body.get("approval") if isinstance(body.get("approval"), dict) else {}
    if a.get("how") == "escalation_plan":   # Sasha 132 · under the guest's ONE yes to the whole plan — verified from our records
        from . import escalation as ESC
        why_not = await ESC.verify(account, a, str(e.get("read_id")))
        if why_not:
            return _refuse(422, "approval_void", why_not)
    # S-66 (EU) step 6 · a yes TYPED in the chat counts too — with the guest's exact words, kept with the approval
    elif not YS.approval_ok(a):   # S-75 step 2 · WhatsApp's button and typed yes too (yes.py)
        return _refuse(422, "approval_void", YS.APPROVAL_VOID)
    if E.email_sha256(e["email"]) != e["email_sha256"]:
        return _refuse(409, "email_changed", "the stored email no longer matches what was read back; nothing was sent")
    from .guest_accounts import real_contact_refusal   # Sasha 153 · a real venue's inbox: the founder's account only, for now
    to = str((e.get("email") or {}).get("to") or "").lower()
    no = real_contact_refusal(account, to.endswith("kanoe.ai") or to.endswith("@" + os.getenv("SASHA_INBOUND_DOMAIN", "booking.kanoe.ai").lower()))
    if no is not None:
        return no
    # S-54 · checked again at the send: a venue can withdraw between the read-back and the yes
    try:
        r = await LADDER_STORE.get_read(account, str(e["read_id"])) if e.get("read_id") else None
    except StorageUnavailable as ex:
        return _refuse(503, ex.rule, ex.detail)
    refused = await _optin_refusal(O.venue_ids_of(r["read"]) if r else None, "email")
    if refused:
        return refused
    now = NOW()
    approval = {"by": account, "how": a["how"], "said": a.get("said"), "at": now.isoformat(),
                "read_back_sha256": e["read_back_sha256"], "email_sha256": e["email_sha256"],
                **({"from": a.get("from")} if a.get("how") == "escalation_plan" else {})}   # Sasha 132 · which yes covered it
    try:
        claimed = await LADDER_STORE.claim_email(account, email_id, approval, now, now - APPROVAL_WINDOW, email_cap(), cap_window(now),
                                                 account_email_cap())
    except StorageUnavailable as ex:
        return _refuse(503, ex.rule, ex.detail)
    if claimed == "taken":
        return _refuse(409, "email_already_sent", "this email was already approved; another is a new read-back and a new yes")
    if claimed == "stale":
        return _refuse(422, "read_back_expired", "that read-back is more than 15 minutes old; prepare the email again")
    if claimed == "cap":
        return _refuse(429, "daily_email_limit", f"{email_cap()} emails have been sent in the last 24 hours, the most this server allows")
    if claimed == "account_cap":
        return _refuse(429, "account_daily_email_limit", f"this account has sent {account_email_cap()} emails in the last 24 hours, the most one account may")
    if claimed != "claimed":
        return _refuse(404, "email_unknown", "no email with that id was prepared for this account")
    sent = await E.send(HTTP, e["email"])
    try:
        await LADDER_STORE.mark_sent(email_id, sent, NOW())
    except (StorageUnavailable, AlreadyRecorded) as ex:
        log.error("[booking_ladder] email %s: Resend answered sent=%s (%s) but it could not be recorded: %s", email_id, sent.sent, sent.provider_id, ex)
        return _refuse(503, getattr(ex, "rule", "not_recorded"), f"the mail service answered {'accepted' if sent.sent else 'not accepted'}, but it could not be recorded: {ex}")
    if not sent.sent:
        return {"ok": False, "status": "not_sent", "rule": "email_not_sent", "why": sent.why, "say": f"I couldn't send it: {sent.why}"}
    # Sasha 99 · the guest's receipt after the email booking, too
    from . import guest_receipt as GR
    read = await LADDER_STORE.get_read(account, str(e.get("read_id"))) if e.get("read_id") else None
    log.info("[booking_ladder] email %s guest receipt: %s", email_id, await GR.send_for_route(
        account, (read or {}).get("venue_name") or e["email"]["to"], f"an email from Sasha to {e['email']['to']}",
        "Requested — waiting for their reply", {"their_words": None, "trip_item_id": e.get("trip_item_id")}))
    return {"ok": True, "status": "sent",
            "say": f"Sent to {e['email']['to']} — our mail service accepted it. I'll show you their reply the moment it arrives."}


@router.get("/emails/{email_id}")
async def get_email(email_id: str, request: Request):
    try:
        e = await LADDER_STORE.get_email(account_for(request), email_id)
        replies = await LADDER_STORE.replies_for(email_id) if e else []
    except StorageUnavailable as ex:
        return _refuse(503, ex.rule, ex.detail)
    if e is None:
        return _refuse(404, "email_unknown", "no email with that id was prepared for this account")
    say = {"awaiting_approval": None, "sent": ("Sent — no reply yet." if not replies else "They replied — here are their words."),
           "not_sent": f"I couldn't send it: {e.get('not_sent_why')}",
           "sending": "I asked the mail service to send it but never recorded its answer, so I can't tell you whether it went. I won't send it again on my own."}[e["status"]]
    return {"email_id": email_id, "status": e["status"], "email": e["email"], "why": e.get("not_sent_why"), "say": say,
            "replies": [{"from": r["from_addr"], "subject": r["subject"], "text": r["body_text"], "note": r["note"],
                         "received_at": r["received_at"].isoformat() if hasattr(r["received_at"], "isoformat") else r["received_at"]} for r in replies]}


@router.post("/email/inbound")
async def inbound(request: Request):
    raw = await request.body()
    if not E.verify_svix(os.getenv("RESEND_WEBHOOK_SECRET", "").strip(), {k.lower(): v for k, v in request.headers.items()}, raw):
        return _refuse(401, "signature_invalid", "not a verified delivery from the mail service")
    try:
        import json as _j
        event = _j.loads(raw)
    except ValueError:
        return _refuse(400, "event_malformed", "the body is not JSON")
    if event.get("type") != "email.received":
        return {"ok": True, "ignored": event.get("type")}
    data = event.get("data") or {}
    pid = data.get("email_id") or data.get("id")
    if not isinstance(pid, str) or not pid:
        return _refuse(400, "event_malformed", "an inbound event carries the received email's id")
    now = NOW()
    # Sasha 74 · Resend's webhooks are account-wide: mail for another product's domain arrives here too. It is not Sasha's
    # to keep — ignored, nothing stored (not even quarantined).
    ours = os.getenv("SASHA_INBOUND_DOMAIN", "").strip().lower()
    to_list = data.get("to") if isinstance(data.get("to"), list) else [data.get("to")]
    if not ours or not any((_address(a) or "").endswith("@" + ours) for a in to_list):
        return {"ok": True, "ignored": "not addressed to Sasha's domain"}
    act = E.act_id_of(data.get("to"))
    sender = _address(data.get("from"))
    if act is None and sender:
        # rule 1 · a reply to Sasha's OWN address (given on the phone, or a reply-all): the venue Sasha last emailed from
        # that very address — matched by the sender, never by guessing from the words
        try:
            act = await LADDER_STORE.email_for_sender(sender)
        except StorageUnavailable as ex:
            return _refuse(503, ex.rule, ex.detail)
    try:
        if act is not None and not await LADDER_STORE.email_exists(act) and await LADDER_STORE.link_exists(act):
            return await _link_confirmation(act, pid, data, now)
        if act is None:
            # Sasha 90 (a) · a written confirmation sent to her own address: onto its booking. Sasha 118 · any booking she made
            # (call, form, email) — and a GUEST forwarding the venue's confirmation from their account's own address (written.py)
            from . import inbound_phone as _IP, written as W
            if _IP.STORE is not None:
                text, _ = await _reply_text(pid)
                try:
                    guest = await W.account_of_email(sender)
                    got = await W.file(pid, "email", sender, data.get("subject"), text, now, account=guest, forwarded=bool(guest))
                    if got:
                        return {"ok": True, "matched": True, "as": "a confirmation the guest forwarded" if guest else "written confirmation"}
                except StorageUnavailable as ex:   # it is still kept: quarantined below, and the reason logged
                    log.error("[inbound] %s could not be matched to a booking (%s); quarantined instead", pid, ex.detail)
                except Exception as ex:   # e.g. sql/027 not yet applied: booking_inbound refuses 'email' — kept, quarantined
                    log.error("[inbound] %s matched but not filed (%s: %s); quarantined instead", pid, type(ex).__name__, ex)
        if act is None or not await LADDER_STORE.email_exists(act):
            await LADDER_STORE.quarantine({"provider_id": pid, "to_addrs": data.get("to"), "from_addr": data.get("from"),
                                           "subject": data.get("subject"), "received_at": now,
                                           "reason": "not addressed to any email Sasha sent" if act is None else "addressed to an unknown email id"})
            # S-56 · a stop sent to the wrong address still counts, if it comes from a venue Sasha wrote to
            sender = _address(data.get("from"))
            known = await S.STOP_STORE.address_venue(sender) if sender and S.STOP_STORE is not None else None
            if known:
                text, _ = await _reply_text(pid)
                await _stop_by_email(known, sender, text, pid, data, now)
            return {"ok": True, "matched": False}
        text, note = await _reply_text(pid)
        fresh = await LADDER_STORE.add_reply({"provider_id": pid, "email_id": act, "from_addr": data.get("from"),
                                      "subject": data.get("subject"), "body_text": text, "note": note, "received_at": now})
        await _stop_by_email(act, _address(data.get("from")), text, pid, data, now)
        # Sasha 74 · rule 3 · a reply to the email after a call: read with the field checks; it moves the reservation only
        # as far as its words go (confirmed / proposed), and is always shown as written
        from . import followup as _FU
        reading = await _FU.on_reply(act, text, now) if fresh else None   # a redelivery is read once
        if reading:
            log.info("[followup] reply to %s read as %s: %s", act, reading["result"], reading["why"])
        # S-66 · a reply to the request emailed while they were closed: the scheduled call is no longer needed
        from . import call_routes as _CR
        for cid in await _CR.CALL_STORE.scheduled_for_email(act):
            await _CR.CALL_STORE.cancel_scheduled(cid, "they replied by email before the call, so no call was made — their reply is with the email")
    except StorageUnavailable as ex:
        return _refuse(503, ex.rule, ex.detail)   # a non-2xx makes the mail service retry — nothing is lost
    return {"ok": True, "matched": True}


def _address(v: Any) -> Optional[str]:
    m = E._EMAIL.search(str(v or ""))
    return m.group(0).lower() if m else None


async def reread_replies() -> int:
    """Sasha 76 · the sweeper fetches again every reply whose words could not be fetched (a key, an outage), then reads it
    with the field checks — a reply is never left unread because of a moment's failure. Returns how many were read."""
    from . import followup as _FU
    done = 0
    for r in await LADDER_STORE.unread_replies():
        text, note = await _reply_text(r["provider_id"])
        if text is None and note and "could not be fetched" in note:
            continue   # still failing: tried again next sweep
        await LADDER_STORE.set_reply_text(r["provider_id"], text, note)
        reading = await _FU.on_reply(str(r["email_id"]), text, NOW())
        log.info("[followup] reply %s re-read%s", r["provider_id"], f": {reading['result']} ({reading['why']})" if reading else "")
        done += 1
    return done


async def _reply_text(pid: str):
    try:
        full = await E.fetch_received(HTTP, pid)
        text = full.get("text") or None
        return text, ("the reply had no plain-text part; only HTML was sent" if text is None and full.get("html") else None)
    except Exception as ex:
        return None, f"the reply's body could not be fetched: {type(ex).__name__}"


async def _stop_by_email(email_id: str, sender: Optional[str], text: Optional[str], pid: str, data: dict, now: datetime) -> None:
    """S-56 · a reply that says stop: recorded, every channel ended, guests told — and ONE acknowledgement, by email."""
    if S.STOP_STORE is None or not S.detect(text):
        return
    v = await S.STOP_STORE.email_venue(email_id)
    stopped = await S.on_venue_words(v["venue_ids"] if v else None, "email", sender or "unknown",
                                     text, {"provider_id": pid, "email_id": email_id, "from": data.get("from"),
                                            "subject": data.get("subject")}, now)
    if not (stopped and stopped.first and sender):
        return   # not a stop, or already stopped: then nothing more
    if not (os.getenv("SASHA_RESEND_API_KEY", "").strip() and os.getenv("SASHA_EMAIL_FROM", "").strip()):
        log.error("[stop] %s said stop; recorded, but no acknowledgement could be sent (the mail service is not configured)", sender)
        return
    country = (v or {}).get("country")
    lang = V.COUNTRIES[country][2] if country in V.COUNTRIES else "en"
    subject = str(data.get("subject") or "").strip()
    sent = await E.send(HTTP, {"from": os.getenv("SASHA_EMAIL_FROM", "").strip(), "to": sender,
                               "subject": subject if subject.lower().startswith("re:") else f"Re: {subject or 'Sasha'}",
                               "text": S.ack_email_text(lang)})
    if sent.sent:
        log.info("[stop] acknowledgement sent to %s (%s)", sender, sent.provider_id)
    else:
        log.error("[stop] %s said stop; recorded, but the acknowledgement was not sent: %s", sender, sent.why)


# ── S-37 · the slot link ──────────────────────────────────────────────────────────────────────

def inbound_ready() -> bool:
    """Can a forwarded confirmation reach Sasha? Only the inbound half is needed — nothing is sent."""
    return bool(os.getenv("SASHA_INBOUND_DOMAIN", "").strip() and os.getenv("RESEND_WEBHOOK_SECRET", "").strip())


@router.post("/links")
async def prepare_link(request: Request):
    body = await _json(request)
    if body is None:
        return _refuse(400, "link_malformed", "send {read_id, date, time, party, name} as a JSON object")
    if any(k in body for k in ("url", "link", "platform_url")):
        return _refuse(422, "url_from_request", "the venue's platform page is READ from its own site, never taken from the request")
    account = account_for(request)
    try:
        row = await LADDER_STORE.get_read(account, str(body.get("read_id")))
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if row is None:
        return _refuse(404, "read_unknown", "no venue read with that id for this account")
    read = row["read"]
    try:
        p = C.parse_call_particulars(body)
        nights = body.get("nights") if isinstance(body.get("nights"), int) and 1 <= body.get("nights") <= 30 else None
        link = SL.build_hotel(read, p.on, nights, p.party) if nights else SL.build(read, p.on, p.at, p.party)   # Sasha 138 · a stay
    except (C.CallRefused, SL.LinkRefused) as e:
        return _refuse(422, e.rule, str(e))
    link_id = str(uuid.uuid4())
    forward_to = E.act_address(link_id) if inbound_ready() else None
    # Sasha 138 · the hotel's NAME (its listing), never its web page's title ("Contacto UMusic Hotels")
    lines = (SL.hotel_read_back((read.get("listing") or {}).get("name") or read["name"], link, p.on, nights, p.party, forward_to) if nights
             else SL.read_back(read["name"], link, p.on, p.at, p.party, forward_to))
    plan = _plan_of(body)   # Sasha 132 · the escalation the guest's ONE yes covers — this link is made only after that yes
    if plan:
        lines.append(plan)
    country = read.get("country")
    tz = V.COUNTRIES[country][3] if country in V.COUNTRIES else "UTC"
    lang = V.COUNTRIES[country][2] if country in V.COUNTRIES else "en"
    rec = {"request": RS.try_from_particulars(p, account_id=account, venue_name=read["name"], timezone=tz, lang=lang,
                                              venue_ids=O.venue_ids_of(read), read_id=str(row["read_id"])),   # S-64 step 3
           "link_id": link_id, "account_id": account, "read_id": row["read_id"], "platform": link.platform, "url": link.url,
           "slot_filled": link.slot_filled, "read_back_lines": lines, "read_back_sha256": C._sha256hex("\n".join(lines)),
           "created_at": NOW(), "venue_name": read["name"], "local_date": p.on, "local_time": p.at, "local_timezone": tz,
           "party_size": p.party}
    try:
        item = await LADDER_STORE.put_link(rec)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"link_id": link_id, "trip_item_id": item, "platform": link.platform, "slot_filled": link.slot_filled, "url": link.url,
            "prefill_tried": link.prefill_tried, "read_back": {"lines": lines},   # Sasha 138
            "forward_to": forward_to, "read_back": {"lines": lines, "sha256": rec["read_back_sha256"]}}


@router.post("/links/{link_id}/opened")
async def link_opened(link_id: str, request: Request):
    """The guest pressed "Open their page": only now does the reservation read `link_sent`. Returns the URL to open."""
    body = await _json(request) or {}
    account = account_for(request)
    try:
        l = await LADDER_STORE.get_link(account, link_id)
        if l is None:
            return _refuse(404, "link_unknown", "no link with that id for this account")
        if body.get("read_back_sha256") != l["read_back_sha256"]:
            return _refuse(422, "approval_void", "that is not the read-back this link was offered with")
        await LADDER_STORE.open_link(account, link_id, NOW())
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"ok": True, "url": l["url"], "status": "link_sent"}


@router.post("/links/{link_id}/booked")
async def link_booked(link_id: str, request: Request):
    """The guest says they booked — recorded as THEIR word (`guest_booked`), never as the platform's confirmation."""
    body = await _json(request) or {}
    account = account_for(request)
    said = {"how": body.get("how") if body.get("how") in YS.HOWS else "button", "said": body.get("said")}
    try:
        r = await LADDER_STORE.guest_booked(account, link_id, said, NOW())
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if r == "unknown":
        return _refuse(404, "link_unknown", "no link with that id for this account")
    # Sasha 99 · the guest's receipt after a slot link, too — on their word until the platform's confirmation arrives
    from . import guest_receipt as GR
    try:
        l = await LADDER_STORE.get_link(account, link_id)
    except StorageUnavailable:
        l = None
    if l:
        log.info("[booking_ladder] link %s guest receipt: %s", link_id, await GR.send_for_route(
            account, l.get("venue_name") or "the venue", f"their {l.get('platform')} page — you made the final press",
            "Booked by you, on your word — not confirmed until the platform's confirmation arrives",
            {"when": f"{l.get('local_date')} at {str(l.get('local_time'))[:5]}" if l.get("local_date") else None, "party": l.get("party_size"),
             "trip_item_id": l.get("trip_item_id")}))
    return await get_link(link_id, request)


@router.get("/links/{link_id}")
async def get_link(link_id: str, request: Request):
    account = account_for(request)
    try:
        l = await LADDER_STORE.get_link(account, link_id)
        confs = await LADDER_STORE.confirmations_for(link_id) if l else []
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if l is None:
        return _refuse(404, "link_unknown", "no link with that id for this account")
    say = {"offered": None,
           "link_sent": f"{l['venue_name']} — link sent · not booked yet.",
           "guest_booked": f"Booked by you on {l['platform']} — " + ("forward the confirmation to add the reference." if inbound_ready() else "noted, on your word."),
           "confirmed": f"Confirmed — {l['platform']}'s confirmation is in your trip, word for word."}[l["status"]]
    return {"link_id": link_id, "status": l["status"], "url": l["url"], "platform": l["platform"], "slot_filled": l["slot_filled"],
            "say": say, "confirmations": [{"from": c["from_addr"], "subject": c["subject"], "text": c["body_text"],
                                            "counted": c["counted"], "note": c["note"]} for c in confs]}


async def _link_confirmation(link_id: str, pid: str, data: dict, now) -> dict:
    """A forwarded platform confirmation. ⚠ It COUNTS only if it names the venue or the platform: a forward of the
    wrong email is shown, never turned into a booking."""
    text, note = None, None
    try:
        full = await E.fetch_received(HTTP, pid)
        text = full.get("text") or None
        if text is None and full.get("html"):
            note = "the forwarded email had no plain-text part"
    except Exception as ex:
        note = f"its body could not be fetched: {type(ex).__name__}"
    venue, platform = await LADDER_STORE.link_venue(link_id)
    hay = f"{data.get('subject') or ''} {text or ''}".casefold()
    counted = bool(text) and (venue.casefold() in hay or platform.casefold() in hay)
    if not counted and note is None:
        note = f"it does not mention {venue} or {platform}, so it was kept but not counted as the confirmation"
    await LADDER_STORE.add_link_confirmation({"provider_id": pid, "link_id": link_id, "from_addr": data.get("from"),
                                              "subject": data.get("subject"), "body_text": text, "counted": counted,
                                              "note": note, "received_at": now})
    return {"ok": True, "matched": True, "counted": counted}
