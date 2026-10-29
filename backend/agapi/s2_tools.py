"""CR 60 · S2's first powers as Sasha's own tools — the SAME contract as the AgAPI v1 sandbox operations messages.send_email and
calendar.add_event, and the SAME logic (agapi/powers.py, byte for byte the module the sandbox runs). Wiring into the agent is the
Sasha tab's (docs/sasha/s2-powers-wiring.md); nothing here is imported by the agent loop yet.

    send_email      [Austen]  from Sasha's own address (SASHA_EMAIL_FROM — never the person's mailbox) to one person they name.
                    First call: the exact message read back (awaiting_yes). A LATER turn, the person's explicit yes (the loop fills
                    approval.said from their real words; a question is never a yes), the SAME message, within 15 minutes → sent once.
                    Any change to to/subject/body → a new read-back. TEST mode: captured (OUTBOX), never sent.
    add_to_calendar [Pacioli] a CONFIRMED booking (a table, a flight) → an .ics + Google/Outlook/Apple links. Free, no yes: nothing
                    leaves the person's account.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from agapi import powers as P

log = logging.getLogger("agapi.s2")
YES_WINDOW = timedelta(minutes=15)                         # AgAPI v1 AP4 for an irreversible act
_HELD: Dict[str, dict] = {}                                # account → the message read back (sha, when it was said, the message)
OUTBOX: List[dict] = []                                    # TEST mode: every email Sasha would have sent (never sent)

# CR 56 / CR 58: the v0 explicit_yes lets a question through ("Yes — what are my cancellation terms?"). For sending, a question
# word or a request for options vetoes the yes — the same list as the AgAPI sandbox (agapi_service/rules.py QUESTION_VETO).
_QUESTION = re.compile(r"(?i)\?|¿|\b(?:what|how|which|when|where|why|who|options?|terms|policy|find|search|show me|look up|tell me|"
                       r"can you|could you|would you|is it|are there|list|qué|cómo|cuál(?:es)?|cuándo|dónde|por qué|opciones|"
                       r"condiciones|política|busca(?:r)?|búscame|muéstrame|enséñame|dime|puedes|podrías)\b")


def live_for(account: Optional[str]) -> bool:
    """Sasha 216 · the founder's decision: an email really goes out only for a person whose record allows real sends (Sasha 254 ·
    the one record: mode live AND real_venue_sends on — Tyler and Jon); everyone else's is captured (OUTBOX), never sent.
    SASHA_S2_EMAIL_LIVE=0 stops every live send at once."""
    from booking_signer import guest_accounts as GA
    if os.getenv("SASHA_S2_EMAIL_LIVE", "1").strip() == "0" or not account:
        return False
    return GA.real_venue_sends(account)


def _sender() -> str:
    return os.getenv("SASHA_EMAIL_FROM", "").strip() or "Sasha <sasha@kanoe.ai>"


def strict_yes(said: Optional[str]) -> bool:
    from agapi.v0 import explicit_yes
    return explicit_yes(said) and not _QUESTION.search(said or "")


async def send_email(ctx, a: dict) -> dict:
    from agapi.v0 import ToolError
    to = a.get("to") or {}
    try:
        msg = P.email_message(_sender(), to.get("address", ""), to.get("name"), a.get("subject", ""), a.get("body", ""))
    except P.Refused as e:
        raise ToolError("invalid_input", e.message)
    sha, lines, now = P.sha256(msg), P.email_read_back(msg), datetime.now(timezone.utc)
    held = _HELD.get(ctx.account)
    said = ((a.get("approval") or {}).get("said")) or ""
    fresh = held and held["sha"] == sha and now - held["at"] <= YES_WINDOW
    if not fresh or held["at"] >= ctx.started:
        if not fresh:   # a new message, or the last read-back went stale: read THIS one back; nothing is sent
            _HELD[ctx.account] = {"sha": sha, "at": now, "msg": msg}
        return {"status": "awaiting_yes", "read_back": lines, "read_back_sha256": sha, "live": live_for(ctx.account),   # Sasha 216
                "say": "Read it back exactly, then ask: shall I send it?"}
    if not strict_yes(said):
        raise ToolError("no_explicit_yes", "sending needs their explicit yes to exactly this message — a question isn't a yes")
    from agapi.v0 import claim
    await claim(ctx)   # Sasha 216 · durable: this message is sent once, across restarts and workers
    _HELD.pop(ctx.account, None)
    sent_at = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    if not live_for(ctx.account):   # CR 61 · captured, and SAID so: never status "sent" for a message that didn't leave
        provider_id = "test_msg_" + secrets.token_hex(10)
        OUTBOX.append({"account": ctx.account, "message": msg, "provider_id": provider_id, "sent_at": sent_at})
        await _activity(ctx.account, "not_sent", msg, sha, said, None, sent_at)   # CR 62 · in the Activity view, as not sent
        return {"status": "not_sent", "outcome": {"kind": "NOT_SENT", "reference": provider_id,
                                                   "target_words": "Not sent: real email isn't open on this account yet. Nothing left Sasha."},
                "say": "Tell them plainly it was NOT sent: real email isn't open on their account yet. Never say it was sent.",
                "message": {"from": msg["from"], "to": msg["to"], "subject": msg["subject"], "body_sha256": P.email_body_sha256(msg)}}
    else:   # ⛔ live: only the founder and the allow-listed accounts (Sasha 216) — the S-36 rung's Resend send, its answer READ
        from booking_signer import emailing as EM
        from booking_signer.ladder_routes import HTTP
        got = await EM.send(HTTP, {"from": msg["from"], "to": msg["to"]["address"], "subject": msg["subject"], "text": msg["body"]})
        if not got.sent:
            await _activity(ctx.account, "failed", msg, sha, said, None, sent_at)
            raise ToolError("upstream_refused" if got.http_status else "upstream_unreachable", got.why or "the mail service didn't accept it")
        provider_id, words = got.provider_id, "Accepted for delivery by the mail service."
    try:
        from booking_signer import basket as BK      # Pacioli: the proof, in the same event log as every act
        await BK.event("agapi", hashlib.sha256(f"{ctx.account}:{provider_id}".encode()).hexdigest()[:40], "send_email",
                       {"provider_id": provider_id, "body_sha256": P.email_body_sha256(msg), "read_back_sha256": sha}, verified=True)
    except Exception as e:
        log.info("[s2] email proof not recorded: %s", type(e).__name__)
    await _activity(ctx.account, "done", msg, sha, said, provider_id, sent_at)
    return {"status": "sent", "outcome": {"kind": "CONFIRMED", "reference": provider_id, "target_words": words},
            "message": {"from": msg["from"], "to": msg["to"], "subject": msg["subject"], "body_sha256": P.email_body_sha256(msg),
                        "sent_at": sent_at}}


async def _activity(account: str, state: str, msg: dict, sha: str, said: str, provider_id: Optional[str], at: str) -> None:
    """CR 62 · the email's row in the Activity view, with its proof (never raises: the email's own outcome stands)."""
    try:
        from agapi import s2_records as REC
        await REC.record(account, "email", state, {"reference": provider_id, "at": at, "said": (said or "")[:300], "read_back_sha256": sha,
                                                   "body_sha256": P.email_body_sha256(msg), "subject": msg["subject"]},
                         msg["to"].get("name") or msg["to"]["address"])
    except Exception as e:
        log.info("[s2] email activity not recorded: %s", type(e).__name__)


def _offset_iso(day: str, hhmm: str, tz: str) -> str:
    return datetime.fromisoformat(f"{day}T{hhmm}").replace(tzinfo=ZoneInfo(tz)).isoformat()


async def add_to_calendar(ctx, a: dict) -> dict:
    """`booking_id`: a venue booking's trip_item_id (get_status → venues) or a booked flight's basket item id."""
    from agapi.v0 import ToolError
    bid, uid = str(a.get("booking_id") or ""), None
    ev = None
    from agapi import venues as VN
    GW = VN._API()
    status, j = await GW.api(ctx.account, "GET", "/api/booking/reservations")
    for r in ((j or {}).get("reservations") or []) if status == 200 else []:
        if str(r.get("id")) == bid:
            if r.get("status") != "confirmed":
                raise ToolError("not_confirmed", f"only a confirmed booking goes in the calendar — this one is {r.get('status')}")
            if not (r.get("date") and r.get("time") and r.get("timezone")):
                raise ToolError("no_time", "that booking has no confirmed date, time and time zone")
            ev = P.event_for_table(f"{bid}@sasha.kanoe", GW.plain_venue(r.get("venue")), r.get("address"),
                                   _offset_iso(r["date"], r["time"], r["timezone"]), int(r.get("party") or 2), r.get("booking_reference") or r.get("reference"))   # Sasha 217
    if ev is None:
        from booking_signer import basket as BK, plan_store as PS
        p = await PS.latest(ctx.account)
        for r in (await BK.live(await BK.items(ctx.account, p["trip_id"], ("booked",))) if p else []):   # Sasha 305 · the flight as it is now
            if str(r["id"]) == bid and r["kind"] == "flight":
                c = r.get("snapshot") or {}
                tz, mins = c.get("from_tz") or "UTC", int(c.get("minutes") or 0)
                dep = datetime.fromisoformat(c["departs"]).replace(tzinfo=ZoneInfo(tz))
                arr = (dep.astimezone(timezone.utc) + timedelta(minutes=mins)).isoformat()
                fn = [x.replace(" ", "") for x in str(c.get("flights") or "").split(" + ") if x]
                ev = P.event_for_flight(f"{bid}@sasha.kanoe", c.get("owner") or "", fn or ["FLIGHT"], c.get("from") or "", c.get("to") or "",
                                        dep.isoformat(), arr, r.get("booking_reference"))
    if ev is None:   # Sasha 259 · a table booked through AgAPI (its act_id, or its reference): the SAME record get_status reads
        for b in await VN.venue_bookings(ctx.account):
            if bid and bid in (str(b.get("act_id") or ""), str(b.get("reference") or ""), str(b.get("trip_item_id") or "")) and b.get("act_id"):
                if b.get("status") != "confirmed":
                    raise ToolError("not_confirmed", f"only a confirmed booking goes in the calendar — this one is {b.get('status')}")
                if not (b.get("date") and b.get("time")):
                    raise ToolError("no_time", "that booking has no confirmed date and time")
                from booking_signer import venue_read as VR
                tz = (VR.COUNTRIES.get(str(b.get("country") or "ES").upper()) or (None, None, None, "Europe/Madrid"))[3]
                ev = P.event_for_table(f"{b['act_id']}@sasha.kanoe", GW.plain_venue(b.get("venue")), None,
                                       _offset_iso(b["date"], b["time"], tz), int(b.get("party") or 2), b.get("reference"))
                break
    if ev is None:
        raise ToolError("booking_unknown", "no confirmed table or flight with that id — get_status lists them")
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    text = P.ics(ev, dtstamp, sequence=0)   # Sasha 312 · the first version of this booking's event (its UID: the booking's own id)
    token = ics_token(text)
    base = os.getenv("SASHA_PUBLIC_API_URL", "https://sasha-travel-production.up.railway.app").rstrip("/")
    try:   # CR 62 · in the Activity view: the event's sha256 is its proof (nothing left the account)
        from agapi import s2_records as REC
        # Sasha 217 · the same booking asked again (she offers it, then hears "put it in my calendar"): the same links, ONE row
        already = any(r.get("kind") == "calendar" and (r.get("proof") or {}).get("event_sha256") == P.sha256(ev)
                      for r in await REC.acts(ctx.account))
        if not already:
            await REC.record(ctx.account, "calendar", "done", {"reference": P.sha256(ev), "at": dtstamp, "event_sha256": P.sha256(ev),
                                                               "booking_id": bid, "uid": ev["uid"], "event": ev}, ev["title"])
    except Exception as e:
        log.info("[s2] calendar activity not recorded: %s", type(e).__name__)
    return {"event": ev, "event_sha256": P.sha256(ev), "ics": text, "links": P.calendar_links(ev, f"{base}/api/agent/ics/{token}.ics")}


async def calendar_update(account: str, ids, kind: str, changed_at: Optional[str], ev_now: Optional[dict] = None) -> Optional[dict]:
    """Sasha 312 · a booking that went in their calendar (its "calendar" act: the event's UID) was CANCELLED or CHANGED on its record → the
    SAME event updated: CANCEL (STATUS:CANCELLED) or REQUEST at its new time, a higher SEQUENCE (powers.sequence_of the record's own time).
    `ids`: the booking's ids as any surface names it (act / order / basket / trip item). None: never put in a calendar, or already
    updated for this version (its own act says so). Sasha keeps no calendar state: the event comes from the act that recorded it, the new
    time from the booking's record (ev_now)."""
    from agapi import s2_records as REC
    want = {str(x) for x in ids if x}
    try:
        acts = await REC.acts(account)
    except Exception as e:
        log.info("[s2] calendar acts not read: %s", type(e).__name__)
        return None
    added = next((a for a in acts if a.get("kind") == "calendar" and a.get("state") == "done"
                  and (str((a.get("proof") or {}).get("booking_id") or "") in want
                       or str((a.get("proof") or {}).get("uid") or "").split("@")[0] in want)), None)
    if not added or not isinstance((added.get("proof") or {}).get("event"), dict):
        return None
    ev0 = added["proof"]["event"]
    seq = P.sequence_of(changed_at)
    if any(a.get("kind") == "calendar" and (a.get("proof") or {}).get("uid") == ev0["uid"] and
           (a.get("proof") or {}).get("sequence") == seq for a in acts):
        return None   # this version already sent
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ev = {**ev0, **({k: ev_now[k] for k in ("starts_at", "ends_at", "title", "location") if ev_now.get(k)} if ev_now else {})}
    text = P.ics_cancel(ev, dtstamp, changed_at) if kind == "cancel" else P.ics_update(ev, dtstamp, changed_at)
    base = os.getenv("SASHA_PUBLIC_API_URL", "https://sasha-travel-production.up.railway.app").rstrip("/")
    url = f"{base}/api/agent/ics/{ics_token(text)}.ics"
    try:
        await REC.record(account, "calendar", "cancelled" if kind == "cancel" else "changed",
                         {"reference": P.sha256({"uid": ev["uid"], "sequence": seq}), "at": dtstamp, "uid": ev["uid"], "sequence": seq,
                          "booking_id": added["proof"].get("booking_id")}, ev["title"])
    except Exception as e:
        log.info("[s2] calendar update not recorded: %s", type(e).__name__)
    return {"kind": kind, "uid": ev["uid"], "sequence": seq, "ics": text, "url": url,
            "line": (CAL_CANCEL_LINE if kind == "cancel" else CAL_CHANGE_LINE)}


async def flight_event_now(account: str, item_id: str) -> Optional[dict]:
    """Sasha 312 · a booked flight's event AS DUFFEL'S ORDER HAS IT NOW (basket.live) — the same event add_to_calendar makes."""
    from booking_signer import basket as BK
    try:
        r = await BK.item(account, item_id) if item_id else None
        if not r or r.get("kind") != "flight":
            return None
        [r] = await BK.live([r])
    except Exception as e:   # the basket unreadable: no new time to give — the update waits (never a wrong time)
        log.info("[s2] flight for the calendar not read: %s", type(e).__name__)
        return None
    c = r.get("snapshot") or {}
    if not c.get("departs"):
        return None
    tz, mins = c.get("from_tz") or "UTC", int(c.get("minutes") or 0)
    dep = datetime.fromisoformat(str(c["departs"])).replace(tzinfo=ZoneInfo(tz))
    arr = (dep.astimezone(timezone.utc) + timedelta(minutes=mins or 60)).isoformat()
    fn = [x.replace(" ", "") for x in str(c.get("flights") or "").split(" + ") if x]
    return P.event_for_flight(f"{item_id}@sasha.kanoe", c.get("owner") or "", fn or ["FLIGHT"], c.get("from") or "", c.get("to") or "",
                              dep.isoformat(), arr, r.get("booking_reference"))


async def calendar_updates_due(account: str) -> List[dict]:
    """Sasha 312 · THE WHOLE CLASS for bookings whose answer comes later (a table, a stay — any route): every booking on AgAPI's record
    that reads CANCELLED or CHANGED since it went in their calendar → its calendar update, once per version (the record's own answer
    time is its SEQUENCE). Called where they're told: my_plans (any surface) and the WhatsApp tick (proactive)."""
    from agapi import itinerary as IT
    from booking_signer import venue_read as VR
    out: List[dict] = []
    try:
        rows = await IT.venue_rows(account, include_cancelled=True)
    except Exception as e:
        log.info("[s2] calendar updates not read: %s", type(e).__name__)
        return out
    for r in rows:
        if r.get("source") != "act":
            continue
        ids = [r.get("id"), r.get("act_id"), r.get("reference")]
        u = None
        if r.get("status") == "cancelled" and r.get("cancelled_at"):
            u = await calendar_update(account, ids, "cancel", r["cancelled_at"])
        elif (r.get("change_answer") or {}).get("state") == "confirmed" and r.get("changed_at") and r.get("date") and r.get("time"):
            tz = (VR.COUNTRIES.get(str(r.get("country") or "ES").upper()) or (None, None, None, "Europe/Madrid"))[3]
            st = r.get("stay") if isinstance(r.get("stay"), dict) else None
            ev_now = (P.event_for_stay("x", r.get("venue") or "", None, _offset_iso(st["check_in"], st.get("arrival") or r["time"], tz),
                                       int(st["nights"]), r.get("reference")) if st and st.get("check_in") and st.get("nights") else
                      P.event_for_table("x", r.get("venue") or "", None, _offset_iso(r["date"], r["time"], tz), int(r.get("party") or 2),
                                        r.get("reference")))
            u = await calendar_update(account, ids, "change", r["changed_at"], ev_now)
        if u:
            out.append({**u, "venue": r.get("venue")})
    return out


CAL_CANCEL_LINE = "To take it out of your calendar, open the calendar update below."
CAL_CHANGE_LINE = "To move it in your calendar, open the calendar update below."


def _ics_key() -> bytes:
    k = os.getenv("SASHA_ICS_KEY", "").strip() or os.getenv("SASHA_BOOKING_KEY", "").strip()
    return hashlib.sha256(("sasha-ics|" + k).encode()).digest()


def ics_token(text: str) -> str:
    """Sasha 216 · the .ics behind the "Apple / any calendar" link, IN the link (compressed) and signed — so it survives deploys and
    is served by any worker (CR 60's in-memory ICS was per process), and nobody can make our domain serve a file we didn't write."""
    import base64, hmac, zlib
    body = base64.urlsafe_b64encode(zlib.compress(text.encode(), 9)).decode().rstrip("=")
    return body + "." + hmac.new(_ics_key(), body.encode(), hashlib.sha256).hexdigest()[:32]


def ics_from_token(token: str) -> Optional[str]:
    import base64, hmac, zlib
    body, _, sig = (token or "").rpartition(".")
    if not body or not hmac.compare_digest(sig, hmac.new(_ics_key(), body.encode(), hashlib.sha256).hexdigest()[:32]):
        return None
    try:
        return zlib.decompress(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))).decode()
    except Exception:
        return None


def tools() -> List[dict]:
    """CR 60's two tools in Sasha's v0 table shape (agapi/v0.py _t). CR 62's send_whatsapp and get_activity are registered by the
    wiring note (s2_whatsapp.tools(), activity.tools()), with their renderers."""
    from agapi.v0 import _t
    msg_props = {"to": {"type": "object", "additionalProperties": False, "required": ["address"],
                        "properties": {"address": {"type": "string", "maxLength": 254}, "name": {"type": "string", "maxLength": 120}}},
                 "subject": {"type": "string", "minLength": 1, "maxLength": 200}, "body": {"type": "string", "minLength": 1, "maxLength": 5000},
                 "approval": {"type": "object", "properties": {"said": {"type": "string"}},
                              "description": "the person's own words (filled by the caller from the real message)"}}
    return [
        _t("send_email", "Austen", send_email, "Email someone the person names, FROM SASHA'S OWN ADDRESS (never their mailbox). The first call "
           "returns the exact message to read back; say it, ask 'shall I send it?', and call again with the SAME message after their yes "
           "in a later turn. Any change is a new read-back. A question is never a yes.", msg_props, ["to", "subject", "body"],
           {"type": "object", "properties": {"status": {"enum": ["awaiting_yes", "sent", "not_sent"]}}}, ["invalid_input", "no_explicit_yes",
                                                                                              "upstream_refused", "upstream_unreachable"], austen=True),
        _t("add_to_calendar", "Pacioli", add_to_calendar, "Put a CONFIRMED booking (a table or a flight; ids from get_status) in the person's "
           "calendar: returns 'Add to calendar' links (Google, Outlook, Apple) and an .ics. No yes needed — nothing leaves their account.",
           {"booking_id": {"type": "string"}}, ["booking_id"], {"type": "object", "properties": {"links": {"type": "object"}}},
           ["booking_unknown", "not_confirmed", "no_time"]),
    ]
