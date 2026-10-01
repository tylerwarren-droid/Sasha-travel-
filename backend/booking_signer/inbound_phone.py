"""S-70 · SASHA'S OWN NUMBER ANSWERS: a venue's SMS or voicemail lands on the reservation it is about.

  POST /api/booking/twilio/sms        an SMS — or a WhatsApp message (S-71: Twilio posts both here, a WhatsApp sender as
                                      `whatsapp:+…`) — to Sasha's number → recorded on the reservation, read with the field checks
  POST /api/booking/twilio/voice      a call to Sasha's number → a short greeting, then the venue's message is recorded
  POST /api/booking/twilio/recording  Twilio's note that the recording is ready → filed with that call

  · Twilio-signed (X-Twilio-Signature, HMAC-SHA1 with the auth token over the exact public URL and the sorted form
    fields); an unsigned or wrongly signed request is refused, nothing recorded. Exempt from the booking key (gate.py).
  · Matched by the SENDER'S NUMBER to the most recent call Sasha placed to it (its digits, or — for a Google Maps
    listing number, Sasha 64 — the hash it is stored as). Never by guessing from the words.
  · Never stores a number's digits: the sender is kept as its sha256 key (places_terms.number_key).
  · A WhatsApp message follows exactly the SMS rules; only its channel (and the stop's `said_on`) says WhatsApp.
  · Never replies by itself. An SMS that restates the day, time and number with a clear yes CONFIRMS; another time is a
    PROPOSAL; a stop ends every channel (S-56); anything else is recorded and shown as written.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional
from xml.sax.saxutils import escape

from fastapi import APIRouter, Request
from fastapi.responses import Response

from . import places_terms as PT
from .store import StorageUnavailable, _row, _uuid_or_none

log = logging.getLogger("booking_signer.inbound_phone")
router = APIRouter(prefix="/twilio", tags=["booking-phone-inbound"])
MATCH_WINDOW = timedelta(days=30)
NOW = lambda: datetime.now(timezone.utc)

_GREETING = ("Hola, ha llamado a Sasha, la concierge de inteligencia artificial de Kanoe. Si llama por una reserva, "
             "deje su mensaje después de la señal: queda grabado y llega a la reserva.",
             "Hello, you've reached Sasha, Kanoe's AI concierge. If you're calling about a booking, leave a message after "
             "the tone: it is recorded and goes to the booking.")


def public_base() -> str:
    return os.getenv("TWILIO_WEBHOOK_BASE", "https://sasha-travel-production.up.railway.app").rstrip("/")


def signature_ok(url: str, params: Mapping[str, str], signature: Optional[str], token: Optional[str] = None) -> bool:
    """Twilio's scheme: base64(HMAC-SHA1(auth token, url + every POST field name+value, sorted by name))."""
    token = token if token is not None else os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    if not (token and signature):
        return False
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    want = base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(want, signature)


def _channel_and_number(sender: str):
    """Twilio writes a WhatsApp sender as `whatsapp:+447…`; an SMS sender is the bare number."""
    if sender.lower().startswith("whatsapp:"):
        return "whatsapp", sender[len("whatsapp:"):].strip()
    return "sms", sender


_ATTEMPT = {"email": ("email", "their email to Sasha's own address after the call, read with the field checks (Sasha 90)"),
            "sms": ("phone", "their SMS to Sasha's number, read with the field checks (S-70)"),
            "whatsapp": ("whatsapp", "their WhatsApp message to Sasha's number, read with the field checks (S-71)")}


def _twiml(inner: str = "") -> Response:
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{inner}</Response>', media_type="text/xml")


async def _verified(request: Request, path: str) -> Optional[Dict[str, str]]:
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    if not signature_ok(f"{public_base()}/api/booking/twilio/{path}", params, request.headers.get("x-twilio-signature")):
        return None
    return params


# ── the store: Memory for tests, Postgres (sql/016) for real ────────────────────────────────────────────────────────

class MemoryInboundStore:
    def __init__(self, calls_store) -> None:
        self.rows: Dict[str, dict] = {}
        self.calls = calls_store

    async def call_for_number(self, number: str, since: datetime) -> Optional[dict]:
        keys = {number, PT.number_key(number)}
        found = [c for c in self.calls.calls.values() if c.get("dialled_number") in keys and c.get("created_at") and c["created_at"] >= since
                 and c.get("status") in ("placed", "answered", "not_reached")]
        return dict(max(found, key=lambda c: c["created_at"])) if found else None

    async def put(self, row: dict) -> bool:
        if row["provider_id"] in self.rows:
            return False
        self.rows[row["provider_id"]] = dict(row)
        return True

    async def get(self, provider_id: str) -> Optional[dict]:
        return dict(self.rows[provider_id]) if provider_id in self.rows else None

    async def set_recording(self, provider_id: str, url: str, seconds: Optional[int]) -> bool:
        r = self.rows.get(provider_id)
        if not r:
            return False
        r.update(recording_url=url, recording_seconds=seconds)
        return True

    async def set_reading(self, provider_id: str, reading: dict) -> None:
        self.rows[provider_id]["reading"] = reading

    async def outcome(self, trip_item_id: str, trip_status: str, attempt_status: str, text: str, now: datetime, channel: str = "sms") -> None:
        self.calls.trip_items[trip_item_id]["status"] = trip_status
        self.calls.attempts.append({"trip_item_id": trip_item_id, "method": _ATTEMPT[channel][0], "status": attempt_status,
                                    "response_received": text, "observed_by": _ATTEMPT[channel][1]})

    async def request_of(self, trip_item_id: str) -> Optional[dict]:
        return (self.calls.trip_items.get(trip_item_id) or {}).get("request")

    async def booking_calls_since(self, since: datetime) -> List[dict]:
        return [dict(c) for c in self.calls.calls.values() if c.get("created_at") and c["created_at"] >= since
                and (c.get("brief") or {}).get("purpose", "book") == "book" and c.get("status") in ("answered", "placed")]


class PostgresInboundStore:
    def __init__(self, base) -> None:
        self._base = base

    async def _run(self, fn):
        try:
            return await self._base._run(fn)
        except StorageUnavailable as e:
            raise e.rehint("016_inbound_phone.sql") from None

    async def call_for_number(self, number, since):
        return _row(await self._run(lambda c: c.fetchrow(
            "select * from booking_calls where dialled_number = any($1::text[]) and created_at >= $2 "
            "and status in ('placed','answered','not_reached') order by created_at desc limit 1",
            [number, PT.number_key(number)], since)))

    async def put(self, row):
        r = await self._run(lambda c: c.fetchval(
            "insert into booking_inbound (provider_id, channel, from_key, to_number, body_text, call_id, trip_item_id, received_at) "
            "values ($1,$2,$3,$4,$5,$6,$7,$8) on conflict (provider_id) do nothing returning provider_id",
            row["provider_id"], row["channel"], row["from_key"], row.get("to_number"), row.get("body_text"),
            _uuid_or_none(row.get("call_id")), _uuid_or_none(row.get("trip_item_id")), row["received_at"]))
        return r is not None

    async def get(self, provider_id):
        return _row(await self._run(lambda c: c.fetchrow("select * from booking_inbound where provider_id = $1", provider_id)))

    async def set_recording(self, provider_id, url, seconds):
        n = await self._run(lambda c: c.execute("update booking_inbound set recording_url = $2, recording_seconds = $3 where provider_id = $1",
                                                provider_id, url, seconds))
        return n.endswith(" 1")

    async def set_reading(self, provider_id, reading):
        await self._run(lambda c: c.execute("update booking_inbound set reading = $2 where provider_id = $1", provider_id, reading))

    async def outcome(self, trip_item_id, trip_status, attempt_status, text, now, channel="sms"):
        method, observed_by = _ATTEMPT[channel]

        async def fn(conn):
            async with conn.transaction():
                await conn.execute("update trip_items set status = $2, updated_at = now() where id = $1", uuid_(trip_item_id), trip_status)
                await conn.execute("insert into booking_attempts (trip_item_id, method, attempted_at, status, response_received, response_at, observed_by) "
                                   "values ($1, $5, $2, $3, $4, $2, $6)",
                                   uuid_(trip_item_id), now, attempt_status, text[:4000], method, observed_by)
        await self._run(fn)

    async def request_of(self, trip_item_id):
        return await self._run(lambda c: c.fetchval("select request from trip_items where id = $1", uuid_(trip_item_id)))

    async def booking_calls_since(self, since):
        return [_row(r) for r in await self._run(lambda c: c.fetch(
            "select call_id, trip_item_id, brief, status, created_at from booking_calls where created_at >= $1 "
            "and coalesce(brief->>'purpose', 'book') = 'book' and status in ('answered', 'placed')", since))]


def uuid_(v):
    return _uuid_or_none(str(v))


STORE: Any = None


# ── the routes ──────────────────────────────────────────────────────────────────────────────────────────────────────

@router.post("/sms")
async def sms(request: Request):
    p = await _verified(request, "sms")
    if p is None:
        return Response("not a verified request from Twilio", status_code=403)
    channel, sender = _channel_and_number(p.get("From", ""))
    body, sid = p.get("Body", ""), p.get("MessageSid") or p.get("SmsSid")
    if not sid:
        return Response("no message id", status_code=400)
    now = NOW()
    try:
        call = await STORE.call_for_number(sender, now - MATCH_WINDOW) if sender else None
        row = {"provider_id": sid, "channel": channel, "from_key": PT.number_key(sender) if sender else "unknown",
               "to_number": _channel_and_number(p.get("To", ""))[1] or None,
               "body_text": body, "call_id": str(call["call_id"]) if call else None,
               "trip_item_id": str(call["trip_item_id"]) if call else None, "received_at": now}
        fresh = await STORE.put(row)
        if fresh and call:
            await _read_sms(row, call, body, now)
    except StorageUnavailable as e:
        log.error("[inbound_phone] %s %s not recorded: %s", channel, sid, e.detail)
        return Response(e.detail, status_code=503)   # non-2xx: Twilio retries, nothing is lost
    return _twiml()   # never an automatic reply


async def _read_sms(row: dict, call: dict, body: str, now: datetime) -> None:
    from . import followup as FU, stop as S
    brief = call.get("brief") or {}
    if S.STOP_STORE is not None and S.detect(body):
        await S.on_venue_words(brief.get("venue_ids"), row["channel"], row["from_key"], body,
                               {"provider_id": row["provider_id"], "call_id": row["call_id"]}, now)
        return
    o = (brief.get("followup") or {}).get("request") or await STORE.request_of(row["trip_item_id"])
    if not isinstance(o, dict):
        return
    r = FU.reply_reading(body, o)
    await STORE.set_reading(row["provider_id"], r)
    status = {"confirmed": "confirmed", "proposed": "proposed", "declined": "unclear"}.get(r["result"])
    if status:
        await STORE.outcome(row["trip_item_id"], status, "confirmed" if status == "confirmed" else "unclear", body, now, row["channel"])
    log.info("[inbound_phone] %s %s on reservation %s read as %s", row["channel"], row["provider_id"], row["trip_item_id"], r["result"])


@router.post("/voice")
async def voice(request: Request):
    p = await _verified(request, "voice")
    if p is None:
        return Response("not a verified request from Twilio", status_code=403)
    sender, sid = p.get("From", ""), p.get("CallSid")
    now = NOW()
    try:
        call = await STORE.call_for_number(sender, now - MATCH_WINDOW) if sender else None
        await STORE.put({"provider_id": sid, "channel": "voicemail", "from_key": PT.number_key(sender) if sender else "unknown",
                         "to_number": p.get("To"), "body_text": None, "call_id": str(call["call_id"]) if call else None,
                         "trip_item_id": str(call["trip_item_id"]) if call else None, "received_at": now})
    except StorageUnavailable as e:
        log.error("[inbound_phone] call %s not recorded: %s", sid, e.detail)
    es, en = _GREETING
    cb = escape(f"{public_base()}/api/booking/twilio/recording")
    return _twiml(f'<Say language="es-ES">{escape(es)}</Say><Say language="en-GB">{escape(en)}</Say>'
                  f'<Record maxLength="120" playBeep="true" recordingStatusCallback="{cb}" recordingStatusCallbackMethod="POST"/>'
                  f'<Say language="es-ES">Gracias.</Say>')


@router.post("/recording")
async def recording(request: Request):
    p = await _verified(request, "recording")
    if p is None:
        return Response("not a verified request from Twilio", status_code=403)
    sid, url = p.get("CallSid"), p.get("RecordingUrl")
    if not (sid and url):
        return Response("no call or recording", status_code=400)
    try:
        secs = int(p.get("RecordingDuration") or 0) or None
        if not await STORE.set_recording(sid, url, secs):
            log.error("[inbound_phone] a recording for unknown call %s: %s", sid, url)
    except StorageUnavailable as e:
        return Response(e.detail, status_code=503)
    return Response("", status_code=204)


# ── Sasha 90 (a) · a written confirmation EMAILED to Sasha's own address after a call ─────────────────────────────

WRITTEN_WINDOW = timedelta(days=14)


def _surname(brief: Mapping[str, Any]) -> str:
    words = str(brief.get("name") or "").split()
    return words[-1] if words else ""


async def match_written(subject: Optional[str], text: Optional[str], now: datetime) -> Optional[dict]:
    """The booking call an email to Sasha's own address is about — by HER reference (K-XXXX) when it is quoted, else by
    the guest's surname when exactly one recent call asked for a confirmation under it. Never by guessing: two
    candidates, or none, is None (the mail is quarantined, as before)."""
    import re
    hay = f"{subject or ''}\n{text or ''}"
    calls = [c for c in await STORE.booking_calls_since(now - WRITTEN_WINDOW) if (c.get("brief") or {}).get("sasha_email")]
    by_ref = [c for c in calls if (c["brief"].get("own_reference") or "") and re.search(rf"\b{re.escape(c['brief']['own_reference'])}\b", hay, re.I)]
    if len(by_ref) == 1:
        return by_ref[0]
    if by_ref:
        return None
    by_name = [c for c in calls if len(_surname(c["brief"])) >= 3 and re.search(rf"\b{re.escape(_surname(c['brief']))}\b", hay, re.I)]
    items = {str(c["trip_item_id"]) for c in by_name}
    return max(by_name, key=lambda c: c["created_at"]) if len(items) == 1 else None


async def on_written_email(provider_id: str, sender: Optional[str], subject: Optional[str], text: Optional[str], now: datetime) -> bool:
    """File a venue's email to Sasha's address on the booking it confirms, and read it like an SMS. False: not matched."""
    call = await match_written(subject, text, now)
    if call is None:
        return False
    key = "sha256:" + hashlib.sha256(sender.strip().lower().encode()).hexdigest() if sender else "unknown"   # the sender, hashed
    row = {"provider_id": provider_id, "channel": "email", "from_key": key,
           "to_number": None, "body_text": text, "call_id": str(call["call_id"]), "trip_item_id": str(call["trip_item_id"]),
           "received_at": now}
    if await STORE.put(row) and text:
        await _read_sms(row, call, text, now)
    return True


def status() -> dict:
    """For /api/booking/health: can Sasha's number receive? Never a secret, never the token."""
    return {"number": os.getenv("SASHA_PHONE_NUMBER") or None, "webhooks_verifiable": bool(os.getenv("TWILIO_AUTH_TOKEN", "").strip()),
            "account_set": bool(os.getenv("TWILIO_ACCOUNT_SID", "").strip())}


__all__ = ["router", "signature_ok", "MemoryInboundStore", "PostgresInboundStore", "status", "public_base"]
