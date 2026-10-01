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
from .account import account_for
from .call_store import cap_window
from .store import AlreadyRecorded, StorageUnavailable, UnknownTrip

log = logging.getLogger("sasha.booking_ladder")
router = APIRouter(tags=["booking-ladder"])
APPROVAL_WINDOW = timedelta(minutes=15)

# ── injectable for tests ──────────────────────────────────────────────────────────────────────
LADDER_STORE: Any = None


async def HTTP(method: str, url: str, headers: dict, json: Optional[dict] = None):
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0), follow_redirects=False) as client:
        return await client.request(method, url, headers=headers, json=json)


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


def _read_view(row: dict, read: Optional[dict] = None) -> dict:
    """`read`: the read with its listing re-read (places_terms.hydrate_read) — shown, never stored."""
    read = read if read is not None else row["read"]
    chosen = L.choose(read)
    return {"read_id": row["read_id"], "venue": read["name"], "country": read.get("country"), "listing": read.get("listing"),
            "facts": [{k: f[k] for k in ("kind", "value", "source_label", "source_url", "snippet", "fetched_at")} for f in read["facts"]],
            "sources": read["sources"], "rungs": chosen["rungs"], "say": chosen["say"],
            **({"listing_reread": read["listing_reread"]} if read.get("listing_reread") else {})}


# ── reading a venue ───────────────────────────────────────────────────────────────────────────

@router.post("/venues/read")
async def read_venue(request: Request):
    body = await _json(request)
    if body is None:
        return _refuse(400, "read_malformed", "send {name, city, country?, website?} as a JSON object")
    if any(k in body for k in ("phone", "number", "phone_number", "email", "to")):
        return _refuse(422, "contact_from_request", "a venue's contact details are READ from what it publishes, never taken from the request")
    now = NOW()
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


@router.post("/venues/find")
async def find_venues(request: Request):
    """S-65 · "Find venues": {what, where, country?} → up to twenty Google listings (S-68), not stored. Search only — nothing is contacted."""
    body = await _json(request)
    if body is None:
        return _refuse(400, "find_malformed", "send {what, where, country?} as a JSON object")
    try:
        return await V.find_venues(HTTP, what=body.get("what"), where=body.get("where"), country=body.get("country"), now=NOW(),
                                   near=body.get("near"), open_at=body.get("open_at"))   # S-68 steps 3–4
    except V.ReadRefused as e:
        return _refuse(503 if e.rule in ("places_not_configured", "places_unreachable", "places_refused") else 422, e.rule, str(e))


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

async def call_venue_from_read(account: str, read_id: Any, fact_index: Any = None) -> C.CallVenue:
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
    _, _, lang, tz = V.COUNTRIES[country]
    return C.CallVenue(key=f"read:{row['read_id']}", name=read["name"], number_env="", language=lang, timezone=tz,
                       number=f["value"], source=f["source_label"], venue_ids=tuple(O.venue_ids_of(read)),
                       number_kind=f.get("source_kind"), place_id=PT.place_id_of(read))


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
    # S-66 (EU) step 6 · a yes TYPED in the chat counts too — with the guest's exact words, kept with the approval
    if a.get("how") not in ("button", "voice", "chat") or (a.get("how") in ("voice", "chat") and not str(a.get("said") or "").strip()):
        return _refuse(422, "approval_void", "an approval is by button, or by voice or typed in the chat with the words said")
    if E.email_sha256(e["email"]) != e["email_sha256"]:
        return _refuse(409, "email_changed", "the stored email no longer matches what was read back; nothing was sent")
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
                "read_back_sha256": e["read_back_sha256"], "email_sha256": e["email_sha256"]}
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
            # Sasha 90 (a) · a written confirmation she asked for on the call, sent to her own address: onto its booking
            from . import inbound_phone as _IP
            if _IP.STORE is not None:
                text, _ = await _reply_text(pid)
                try:
                    if await _IP.on_written_email(pid, sender, data.get("subject"), text, now):
                        return {"ok": True, "matched": True, "as": "written confirmation after a call"}
                except StorageUnavailable as ex:   # it is still kept: quarantined below, and the reason logged
                    log.error("[inbound] %s could not be matched to a call (%s); quarantined instead", pid, ex.detail)
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
        link = SL.build(read, p.on, p.at, p.party)
    except (C.CallRefused, SL.LinkRefused) as e:
        return _refuse(422, e.rule, str(e))
    link_id = str(uuid.uuid4())
    forward_to = E.act_address(link_id) if inbound_ready() else None
    lines = SL.read_back(read["name"], link, p.on, p.at, p.party, forward_to)
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
    said = {"how": body.get("how") if body.get("how") in ("button", "voice", "chat") else "button", "said": body.get("said")}
    try:
        r = await LADDER_STORE.guest_booked(account, link_id, said, NOW())
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if r == "unknown":
        return _refuse(404, "link_unknown", "no link with that id for this account")
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
