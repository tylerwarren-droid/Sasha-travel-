"""CR 60 · S2's first powers as Sasha's own tools — the SAME contract as the AgAPI v1 sandbox operations messages.send_email and
calendar.add_event, and the SAME logic (agapi/powers.py, byte for byte the module the sandbox runs). Wiring into the agent is the
Sasha tab's (docs/sasha/s2-powers-wiring.md); nothing here is imported by the agent loop yet.

    send_email      [Austen]  from Sasha's own address (SASHA_EMAIL_FROM — never the person's mailbox) to one person they name.
                    First call: the exact message read back (awaiting_yes). A LATER turn, the person's explicit yes (the loop fills
                    approval.said from their real words; a question is never a yes), the SAME message, within 15 minutes → sent once.
                    Any change to to/subject/body → a new read-back. TEST mode: captured (OUTBOX), never sent.
    add_to_calendar [Pacioli] a CONFIRMED booking (a table, a flight) → an .ics + Google/Outlook/Apple links. Free, no yes: nothing
                    leaves the person's account.

CR 61 (Tyler's answers to CR 60):
    · personal emails go from SASHA_EMAIL_FROM for now (a separate mail subdomain later);
    · REAL sending only when SASHA_S2_EMAIL_LIVE=1 AND the account is the founder's or allow-listed (SASHA_S2_EMAIL_ACCOUNTS, else
      the existing real-contact list SASHA_REAL_CONTACT_ACCOUNTS — Jon's). Everyone else: captured, never sent, and SAID so
      (status "not_sent" — never "sent" for a message that didn't leave);
    · calendar links survive deploys: the sasha_calendar_links table (booking_signer/sql/036_calendar_links.sql); memory until it exists.
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
ICS: Dict[str, dict] = {}                                  # token hash → {account, ics, expires} — the fallback until 036 is applied
LINK_KEEP = timedelta(days=30)                             # a calendar link works until 30 days after the event ends

# CR 56 / CR 58: the v0 explicit_yes lets a question through ("Yes — what are my cancellation terms?"). For sending, a question
# word or a request for options vetoes the yes — the same list as the AgAPI sandbox (agapi_service/rules.py QUESTION_VETO).
_QUESTION = re.compile(r"(?i)\?|¿|\b(?:what|how|which|when|where|why|who|options?|terms|policy|find|search|show me|look up|tell me|"
                       r"can you|could you|would you|is it|are there|list|qué|cómo|cuál(?:es)?|cuándo|dónde|por qué|opciones|"
                       r"condiciones|política|busca(?:r)?|búscame|muéstrame|enséñame|dime|puedes|podrías)\b")


def _sender() -> str:
    return os.getenv("SASHA_EMAIL_FROM", "").strip() or "Sasha <sasha@kanoe.ai>"


def live_email(account: Optional[str]) -> bool:
    """CR 61 · a REAL send: the switch on, and the founder's account or an allow-listed one (Jon's). Off for everyone else."""
    if os.getenv("SASHA_S2_EMAIL_LIVE", "") != "1" or not account:
        return False
    from booking_signer import guest_accounts as GA
    listed = {a.strip().lower() for a in os.getenv("SASHA_S2_EMAIL_ACCOUNTS", "").split(",") if a.strip()} or GA.extra_accounts()
    return GA.founder(account) or account.lower() in listed


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
        return {"status": "awaiting_yes", "read_back": lines, "read_back_sha256": sha,
                "say": "Read it back exactly, then ask: shall I send it?"}
    if not strict_yes(said):
        raise ToolError("no_explicit_yes", "sending needs their explicit yes to exactly this message — a question isn't a yes")
    _HELD.pop(ctx.account, None)
    sent_at = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    if not live_email(ctx.account):   # CR 61: not the founder / Jon, or the switch is off → captured, and said plainly
        provider_id = "test_msg_" + secrets.token_hex(10)
        OUTBOX.append({"account": ctx.account, "message": msg, "provider_id": provider_id, "sent_at": sent_at})
        return {"status": "not_sent", "outcome": {"kind": "NOT_SENT", "reference": provider_id,
                                                   "target_words": "Not sent: real email isn't open on this account yet. Nothing left Sasha."},
                "say": "Tell them plainly it was NOT sent — real email is only open on the founder's account for now.",
                "message": {"from": msg["from"], "to": msg["to"], "subject": msg["subject"], "body_sha256": P.email_body_sha256(msg)}}
    else:   # ⛔ live: SASHA_S2_EMAIL_LIVE=1 and the founder's or Jon's account — the S-36 rung's Resend send, its answer READ
        from booking_signer import emailing as EM
        from booking_signer.ladder_routes import HTTP
        got = await EM.send(HTTP, {"from": msg["from"], "to": msg["to"]["address"], "subject": msg["subject"], "text": msg["body"]})
        if not got.sent:
            raise ToolError("upstream_refused" if got.http_status else "upstream_unreachable", got.why or "the mail service didn't accept it")
        provider_id, words = got.provider_id, "Accepted for delivery by the mail service."
    try:
        from booking_signer import basket as BK      # Pacioli: the proof, in the same event log as every act
        await BK.event("agapi", hashlib.sha256(f"{ctx.account}:{provider_id}".encode()).hexdigest()[:40], "send_email",
                       {"provider_id": provider_id, "body_sha256": P.email_body_sha256(msg), "read_back_sha256": sha}, verified=True)
    except Exception as e:
        log.info("[s2] email proof not recorded: %s", type(e).__name__)
    return {"status": "sent", "outcome": {"kind": "CONFIRMED", "reference": provider_id, "target_words": words},
            "message": {"from": msg["from"], "to": msg["to"], "subject": msg["subject"], "body_sha256": P.email_body_sha256(msg),
                        "sent_at": sent_at}}


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
                                   _offset_iso(r["date"], r["time"], r["timezone"]), int(r.get("party") or 2), r.get("reference"))
    if ev is None:
        from booking_signer import basket as BK, plan_store as PS
        p = await PS.latest(ctx.account)
        for r in (await BK.items(ctx.account, p["trip_id"], ("booked",)) if p else []):
            if str(r["id"]) == bid and r["kind"] == "flight":
                c = r.get("snapshot") or {}
                tz, mins = c.get("from_tz") or "UTC", int(c.get("minutes") or 0)
                dep = datetime.fromisoformat(c["departs"]).replace(tzinfo=ZoneInfo(tz))
                arr = (dep.astimezone(timezone.utc) + timedelta(minutes=mins)).isoformat()
                fn = [x.replace(" ", "") for x in str(c.get("flights") or "").split(" + ") if x]
                ev = P.event_for_flight(f"{bid}@sasha.kanoe", c.get("owner") or "", fn or ["FLIGHT"], c.get("from") or "", c.get("to") or "",
                                        dep.isoformat(), arr, r.get("booking_reference"))
    if ev is None:
        raise ToolError("booking_unknown", "no confirmed table or flight with that id — get_status lists them")
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    text, token = P.ics(ev, dtstamp), secrets.token_urlsafe(24)
    await _keep_link(hashlib.sha256(token.encode()).hexdigest(), ctx.account, P.sha256(ev), text,
                     datetime.fromisoformat(ev["ends_at"].replace("Z", "+00:00")) + LINK_KEEP)
    base = os.getenv("SASHA_PUBLIC_API_URL", "https://sasha-travel-production.up.railway.app").rstrip("/")
    return {"event": ev, "event_sha256": P.sha256(ev), "ics": text, "links": P.calendar_links(ev, f"{base}/api/agent/ics/{token}.ics")}


# ── CR 61 · calendar links that survive a deploy ───────────────────────────────────────────────────────────────────────────

def _db():
    from booking_signer import plan_store as PS
    return PS._run()


async def _keep_link(token_sha: str, account: str, event_sha: str, text: str, expires: datetime) -> None:
    """The table when it exists (036); otherwise memory, said in the log. Never raises: the links are returned inline either way."""
    run = _db()
    if run is not None:
        try:
            async def put(conn):
                await conn.execute("insert into sasha_calendar_links (token_sha256, account_id, event_sha256, ics, expires_at) "
                                   "values ($1, $2::uuid, $3, $4, $5) on conflict (token_sha256) do nothing",
                                   token_sha, account, event_sha, text, expires)
            await run(put)
            return
        except Exception as e:   # 036 not applied yet (UndefinedTable), or no database: memory, as CR 60
            log.info("[s2] calendar link kept in memory (%s)", type(e).__name__)
    ICS[token_sha] = {"account": account, "ics": text, "expires": expires}


async def ics_for(token: str) -> Optional[str]:
    """The .ics behind a link, or None (unknown or expired). The route in the wiring note serves it."""
    token_sha, now = hashlib.sha256((token or "").encode()).hexdigest(), datetime.now(timezone.utc)
    run = _db()
    if run is not None:
        try:
            async def get(conn):
                return await conn.fetchval("select ics from sasha_calendar_links where token_sha256 = $1 and expires_at > now()", token_sha)
            text = await run(get)
            if text:
                return text
        except Exception as e:
            log.info("[s2] calendar link lookup fell back to memory (%s)", type(e).__name__)
    f = ICS.get(token_sha)
    return f["ics"] if f and f["expires"] > now else None


def tools() -> List[dict]:
    """The two tools in Sasha's v0 table shape (agapi/v0.py _t) — appended by the wiring note, not here."""
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
