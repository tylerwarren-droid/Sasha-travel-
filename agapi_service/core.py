"""The AgAPI sandbox's rules, independent of HTTP: keys, metering, offers, holds, the Approval object, bookings, cancellation,
and the proof log. Pacioli is the only writer of a booking's status (via _event)."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from . import config, providers as PV
from .store import Store, dumps, iso, now


class ApiError(Exception):
    """{type, code, message, retryable} → the HTTP status. `unavailable` is an outage, never a "no"."""

    STATUS = {"invalid_request": 400, "authentication": 401, "not_found": 404, "conflict": 409, "approval_required": 409,
              "refused": 422, "budget": 429, "unavailable": 503}

    def __init__(self, type_: str, code: str, message: str, retryable: bool = False, **extra):
        super().__init__(message)
        self.type, self.code, self.message, self.retryable, self.extra = type_, code, message, retryable, extra

    @property
    def status(self) -> int:
        return self.STATUS.get(self.type, 400)

    def body(self) -> dict:
        return {"error": {"type": self.type, "code": self.code, "message": self.message, "retryable": self.retryable, **self.extra}}


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(10)}"


def sha256_of(obj: Any) -> str:
    from booking_signer.canonical import canonical_bytes   # Sasha's canonical JSON (byte-exact with the booking helper's)
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _when(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


# ── keys (hashed at rest) ──────────────────────────────────────────────────────────────────────────────────────────────

def _key_hash(secret: str) -> str:
    return hmac.new(config.pepper(), secret.encode(), hashlib.sha256).hexdigest()


def create_key(db: Store, customer: str) -> str:
    """→ the key, shown ONCE: agk_test_<id>_<secret>. Only the id and an HMAC of the secret are stored."""
    kid, secret = secrets.token_hex(6), secrets.token_urlsafe(24)
    db.x("insert into api_keys (id, customer, secret_sha256, created_at) values (?, ?, ?, ?)", kid, customer, _key_hash(secret), iso(now()))
    return f"agk_test_{kid}_{secret}"


def authenticate(db: Store, header: Optional[str]) -> dict:
    m = re.fullmatch(r"Bearer (agk_(test|live)_([0-9a-f]{12})_([A-Za-z0-9_\-]{20,64}))", (header or "").strip())
    if not m:
        raise ApiError("authentication", "key_missing", "send Authorization: Bearer agk_test_…")
    if m.group(2) != "test":
        raise ApiError("authentication", "live_key_refused", "this is the sandbox: test keys only (agk_test_…)")
    row = db.one("select * from api_keys where id = ?", m.group(3))
    if not row or row["revoked_at"] or not hmac.compare_digest(row["secret_sha256"], _key_hash(m.group(4))):
        raise ApiError("authentication", "key_invalid", "that key isn't valid (or was revoked)")
    return row


# ── metering + daily budget ────────────────────────────────────────────────────────────────────────────────────────────

def meter(db: Store, key_id: str, find: bool = False) -> dict:
    day = now().date().isoformat()
    with db.tx():
        db.x("insert into usage (key_id, day) values (?, ?) on conflict (key_id, day) do nothing", key_id, day)
        u = db.one("select * from usage where key_id = ? and day = ?", key_id, day)
        if u["calls"] >= config.DAILY_CALLS or (find and u["finds"] >= config.DAILY_FINDS):
            which = "finds" if find and u["finds"] >= config.DAILY_FINDS else "calls"
            raise ApiError("budget", "daily_budget_reached", f"this key's daily {which} budget is used up (resets 00:00 UTC)",
                           retryable=True, limit={"calls": config.DAILY_CALLS, "finds": config.DAILY_FINDS})
        db.x("update usage set calls = calls + 1, finds = finds + ? where key_id = ? and day = ?", 1 if find else 0, key_id, day)
    return db.one("select calls, finds from usage where key_id = ? and day = ?", key_id, day)


def usage(db: Store, key_id: str) -> dict:
    day = now().date().isoformat()
    u = db.one("select calls, finds from usage where key_id = ? and day = ?", key_id, day) or {"calls": 0, "finds": 0}
    return {"day": day, "used": u, "limit": {"calls": config.DAILY_CALLS, "finds": config.DAILY_FINDS}}


# ── find (Magellan) ────────────────────────────────────────────────────────────────────────────────────────────────────

async def find(db: Store, key: dict, body: dict) -> dict:
    kind = body.get("kind")
    try:
        if kind == "flights":
            for f in ("origin", "destination", "date"):
                if not body.get(f):
                    raise ApiError("invalid_request", "missing_input", f"missing: {f}")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(body["date"])):
                raise ApiError("invalid_request", "date_invalid", "date is YYYY-MM-DD")
            found = await PV.find_flights(body["origin"], body["destination"], body["date"], max(1, min(int(body.get("adults") or 1), 9)))
        elif kind in ("venues", "stays"):
            if not body.get("where") or (kind == "venues" and not body.get("what")):
                raise ApiError("invalid_request", "missing_input", "missing: " + ("where" if body.get("what") or kind == "stays" else "what"))
            found = await PV.find_places("hotel" if kind == "stays" else body["what"], body["where"], body.get("country"),
                                         "stay" if kind == "stays" else "venue")
        else:
            raise ApiError("invalid_request", "kind_invalid", "kind is one of: flights, venues, stays")
    except PV.Unavailable as e:
        raise ApiError("unavailable", f"{e.service}_unreachable", e.message, retryable=True, service=e.service)
    except PV.Refused as e:
        raise ApiError("refused", e.code, e.message)
    results = []
    for f in found:
        oid = _id("off")
        db.x("insert into offers (id, key_id, kind, data, created_at) values (?, ?, ?, ?, ?)", oid, key["id"], f["kind"], dumps(f), iso(now()))
        results.append({"offer_id": oid, **{k: v for k, v in f.items() if not k.startswith("_")}})
    return {"object": "list", "kind": kind, "results": results, "test_mode": True,
            "sources": [{"label": "Duffel TEST (recorded fixtures)" if kind == "flights" else "Google Places (fictional fixtures)"}]}


# ── hold (Austen: prepare; nothing is sent) ────────────────────────────────────────────────────────────────────────────

def _fmt_money(p: dict) -> str:
    return f"{p['currency']} {p['amount_minor'] // 100}.{p['amount_minor'] % 100:02d}"


def _read_back_offer(o: dict, body: dict) -> dict:
    if o["kind"] == "flight":
        d = datetime.fromisoformat(o["departs"])
        lines = [f"Book {o['title']}, {o.get('from_city') or o['from']} ({o['from']}) → {o.get('to_city') or o['to']} ({o['to']}), "
                 f"{d.strftime('%a %-d %b %Y %H:%M')}–{o['arrives'][11:16]}, {o['adults']} adult{'s' if o['adults'] != 1 else ''}.",
                 f"Total {_fmt_money(o['price'])}, paid once you approve (sandbox: Stripe test, simulated — no money moves).",
                 "Cancellation: under the airline's fare rules (sandbox: allowed, nothing refunded because nothing was charged)."]
        facts = {"kind": "flight", "title": o["title"], "from": o["from"], "to": o["to"], "departs": o["departs"],
                 "adults": o["adults"], "price": o["price"]}
        return {"lines": lines, "facts": facts}
    at, party = body.get("at"), body.get("party")
    if not at or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", str(at)):
        raise ApiError("invalid_request", "at_invalid", "at is the local date-time wanted, YYYY-MM-DDTHH:MM")
    if not isinstance(party, int) or not 1 <= party <= 20:
        raise ApiError("invalid_request", "party_invalid", "party is a whole number, 1–20")
    name, addr = (o.get("name") or {}).get("text"), (o.get("address") or {}).get("text")
    when = datetime.fromisoformat(at).strftime("%a %-d %b %Y, %H:%M")
    what = "a stay" if o["kind"] == "stay" else f"a table for {party}"
    lines = [f"Request {what} at {name}, {addr} — {when}.",
             "Sandbox: the venue is NOT contacted; the request and its answer are simulated.",
             "Nothing is charged."]
    return {"lines": lines, "facts": {"kind": o["kind"], "place_id": o.get("place_id"), "name": name, "at": at, "party": party}}


def create_hold(db: Store, key: dict, body: dict) -> dict:
    if body.get("cancel_booking_id"):
        b = db.one("select * from bookings where id = ? and key_id = ?", body["cancel_booking_id"], key["id"])
        if not b:
            raise ApiError("not_found", "booking_not_found", "no such booking for this key")
        if b["status"] not in ("confirmed", "requested"):
            raise ApiError("conflict", f"booking_{b['status']}", f"that booking is {b['status']}")
        data = _loads(b["data"])
        what = re.sub(r"^(?:Book|Request)\s+", "", data["read_back"]["lines"][0])
        rb = {"lines": [f"Cancel your booking: {what}",
                        "Sandbox: the cancellation is simulated — no provider is contacted."],
              "facts": {"kind": "cancel", "booking_id": b["id"]}}
        kind, offer_id, booking_id = "cancel", None, b["id"]
    else:
        o = db.one("select * from offers where id = ? and key_id = ?", body.get("offer_id") or "", key["id"])
        if not o:
            raise ApiError("not_found", "offer_not_found", "no such offer for this key — find first")
        rb = _read_back_offer(_loads(o["data"]), body)
        kind, offer_id, booking_id = o["kind"], o["id"], None
    hid, sha = _id("hold"), sha256_of(rb)
    exp = now() + timedelta(seconds=config.HOLD_TTL_S)
    db.x("insert into holds (id, key_id, kind, offer_id, booking_id, read_back, read_back_sha256, status, expires_at, created_at) "
         "values (?, ?, ?, ?, ?, ?, ?, 'held', ?, ?)", hid, key["id"], kind, offer_id, booking_id, dumps(rb), sha, iso(exp), iso(now()))
    return hold_out(db.one("select * from holds where id = ?", hid))


def hold_out(h: dict) -> dict:
    status = "expired" if h["status"] == "held" and _when(h["expires_at"]) < now() else h["status"]
    return {"object": "hold", "id": h["id"], "kind": h["kind"], "status": status, "offer_id": h["offer_id"],
            "booking_id": h["booking_id"], "read_back": _loads(h["read_back"]), "read_back_sha256": h["read_back_sha256"],
            "expires_at": h["expires_at"], "created_at": h["created_at"]}


# ── the Approval object (EU 200 §2 shape; EU 201 Part 1 replaces this draft) ───────────────────────────────────────────

_YES = re.compile(r"(?i)^\s*(?:(?:ok(?:ay)?|right|so|then|great|perfect)[,!. ]+)*(?:yes|yeah|yep|sure|go ahead|do it|approve|book it|"
                  r"confirm|cancel it)\b")
_NOT_A_YES = re.compile(r"(?i)\?|\b(?:no|not|don'?t|wait|hold on|later|maybe|what|how|which|when|why|can|could|would|should|"
                        r"options?|terms?|policy|polic(?:y|ies)|cost|price|find|search|show|look(?:\s+up)?|tell me|list)\b")


def strict_yes(said: Optional[str]) -> bool:
    """A typed answer on the approval page counts only if it is a plain yes — never a question, never a request for options
    (CR 56: "Yes — what are my cancellation terms?" and "Sure, find me dinner options" are not a yes)."""
    t = (said or "").strip()
    return bool(t) and len(t) <= 60 and bool(_YES.search(t)) and not _NOT_A_YES.search(t)


def _mask(phone: str) -> str:
    d = re.sub(r"\D", "", phone or "")
    return ("+" if (phone or "").strip().startswith("+") else "") + "•" * max(0, len(d) - 2) + d[-2:]


def request_approval(db: Store, key: dict, body: dict) -> dict:
    h = db.one("select * from holds where id = ? and key_id = ?", body.get("hold_id") or "", key["id"])
    if not h:
        raise ApiError("not_found", "hold_not_found", "no such hold for this key")
    if hold_out(h)["status"] != "held":
        raise ApiError("conflict", "hold_not_active", f"that hold is {hold_out(h)['status']} — hold again")
    phone = ((body.get("end_user") or {}).get("phone") or "").strip()
    if not re.fullmatch(r"\+?[0-9 ()\-]{7,20}", phone):
        raise ApiError("invalid_request", "end_user_phone_invalid", "end_user.phone is the end user's mobile, e.g. +34 600 000 000")
    db.x("update approvals set status = 'void', void_reason = 'superseded' where hold_id = ? and status = 'pending'", h["id"])
    aid, token = _id("apr"), secrets.token_urlsafe(24)
    exp = now() + timedelta(seconds=config.APPROVAL_TTL_S)
    db.x("insert into approvals (id, key_id, hold_id, token_sha256, read_back_sha256, status, end_user, created_at, expires_at) "
         "values (?, ?, ?, ?, ?, 'pending', ?, ?, ?)", aid, key["id"], h["id"], hashlib.sha256(token.encode()).hexdigest(),
         h["read_back_sha256"], dumps({"phone_masked": _mask(phone)}), iso(now()), iso(exp))
    out = approval_out(db, db.one("select * from approvals where id = ?", aid))
    out["approve_url"] = f"{config.PUBLIC_URL}/sandbox/approve/{token}"     # shown once; only its hash is stored
    out["delivery"] = {"channel": "sandbox_page", "sent": False,
                       "note": "test mode: no SMS/WhatsApp is sent — open approve_url as the end user would on their phone"}
    return out


def _approval_status(a: dict) -> str:
    if a["status"] == "pending" and _when(a["expires_at"]) < now():
        return "expired"
    if a["status"] == "approved" and not a["consumed_at"] and _when(a["expires_at"]) < now():
        return "expired"
    return a["status"]


def approval_out(db: Store, a: dict) -> dict:
    return {"object": "approval", "id": a["id"], "hold_id": a["hold_id"], "status": _approval_status(a),
            "read_back_sha256": a["read_back_sha256"], "end_user": _loads(a["end_user"]), "created_at": a["created_at"],
            "presented_at": a["presented_at"], "decided_at": a["decided_at"], "expires_at": a["expires_at"],
            "decision": _loads(a["decision"]) if a["decision"] else None, "consumed_at": a["consumed_at"],
            "void_reason": a["void_reason"]}


def by_token(db: Store, token: str) -> Optional[dict]:
    return db.one("select * from approvals where token_sha256 = ?", hashlib.sha256((token or "").encode()).hexdigest())


def present(db: Store, a: dict) -> dict:
    """The end user's page shows the read-back: presented_at is set the first time (a yes before it is impossible)."""
    if _approval_status(a) == "pending" and not a["presented_at"]:
        db.x("update approvals set presented_at = ? where id = ? and presented_at is null", iso(now()), a["id"])
    return db.one("select * from approvals where id = ?", a["id"])


def decide(db: Store, a: dict, decision: str, said: Optional[str], device: str) -> dict:
    """ONLY from the end user's page — the partner's API key can never approve."""
    if _approval_status(a) != "pending":
        raise ApiError("conflict", f"approval_{_approval_status(a)}", f"this approval is {_approval_status(a)}")
    if not a["presented_at"]:
        raise ApiError("approval_required", "not_presented", "the read-back must be shown before it can be approved")
    h = db.one("select * from holds where id = ?", a["hold_id"])
    if h["read_back_sha256"] != a["read_back_sha256"] or hold_out(h)["status"] != "held":
        db.x("update approvals set status = 'void', void_reason = 'read_back_changed_or_expired' where id = ?", a["id"])
        raise ApiError("conflict", "approval_void", "what was approved has changed or expired — the partner must hold again")
    if decision == "said":
        decision = "approve" if strict_yes(said) else "unclear"
    if decision == "unclear":
        return {"approval": approval_out(db, a), "said": said, "outcome": "not_a_yes"}
    status = {"approve": "approved", "decline": "declined"}.get(decision)
    if not status:
        raise ApiError("invalid_request", "decision_invalid", "approve or decline")
    db.x("update approvals set status = ?, decided_at = ?, decision = ? where id = ? and status = 'pending'", status, iso(now()),
         dumps({"how": "typed" if said else "tap", "said": said, "device_sha256": hashlib.sha256(device.encode()).hexdigest()}), a["id"])
    a2 = db.one("select * from approvals where id = ?", a["id"])
    _event(db, a2["key_id"], a2["hold_id"], "approval_" + status, "end_user", {"approval_id": a2["id"], "read_back_sha256": a2["read_back_sha256"]})
    return {"approval": approval_out(db, a2), "outcome": status}


def _consume(db: Store, key: dict, hold_id: str, approval_id: str) -> tuple:
    """The approval this action rides on: this key's, this hold's, approved by the end user after it was presented, unexpired,
    unused, and for exactly the read-back the hold still has. Consumed atomically (one approval = one action)."""
    h = db.one("select * from holds where id = ? and key_id = ?", hold_id or "", key["id"])
    if not h:
        raise ApiError("not_found", "hold_not_found", "no such hold for this key")
    a = db.one("select * from approvals where id = ? and key_id = ?", approval_id or "", key["id"])
    if not a or a["hold_id"] != h["id"]:
        raise ApiError("approval_required", "approval_missing", "this action needs the end user's approval of this hold — request_approval first")
    st = _approval_status(a)
    if st != "approved":
        raise ApiError("approval_required", f"approval_{st}", {"pending": "the end user hasn't approved yet",
                       "declined": "the end user declined", "expired": "the approval expired — request a new one",
                       "void": "the approval is void — hold and request again", "consumed": "that approval was already used"}.get(st, st))
    if a["consumed_at"]:
        raise ApiError("approval_required", "approval_consumed", "that approval was already used")
    if a["read_back_sha256"] != h["read_back_sha256"]:
        raise ApiError("approval_required", "approval_mismatch", "the approval is for a different read-back")
    if not a["presented_at"] or _when(a["decided_at"]) < _when(a["presented_at"]):
        raise ApiError("approval_required", "approval_before_read_back", "the approval came before the read-back was shown")
    if hold_out(h)["status"] != "held":
        raise ApiError("conflict", "hold_not_active", f"that hold is {hold_out(h)['status']}")
    with db.tx():
        n = db.x("update approvals set consumed_at = ?, status = 'consumed' where id = ? and consumed_at is null", iso(now()), a["id"])
        if n != 1:
            raise ApiError("approval_required", "approval_consumed", "that approval was already used")
        db.x("update holds set status = 'used' where id = ?", h["id"])
    return h, a


def _release(db: Store, h: dict, a: dict) -> None:
    """An outage after consuming: give the approval and hold back (nothing happened), so the end user needn't approve twice."""
    db.x("update approvals set consumed_at = null, status = 'approved' where id = ?", a["id"])
    db.x("update holds set status = 'held' where id = ?", h["id"])


# ── book / cancel (Austen, after the yes) and status/proof (Pacioli) ───────────────────────────────────────────────────

async def book(db: Store, key: dict, body: dict) -> dict:
    h, a = _consume(db, key, body.get("hold_id"), body.get("approval_id"))
    if h["kind"] == "cancel":
        _release(db, h, a)
        raise ApiError("invalid_request", "hold_is_a_cancellation", "that hold is a cancellation — POST /v1/bookings/{id}/cancel")
    o = _loads(db.one("select data from offers where id = ?", h["offer_id"])["data"])
    rb = _loads(h["read_back"])
    bid = _id("bk")
    if h["kind"] == "flight":
        try:
            got = await PV.order_flight(o["_card"])
        except PV.Unavailable as e:
            _release(db, h, a)
            raise ApiError("unavailable", f"{e.service}_unreachable", e.message, retryable=True, service=e.service)
        except PV.Refused as e:
            _release(db, h, a)   # nothing happened: the end user's yes stays theirs to use (the partner holds again)
            raise ApiError("refused", e.code, e.message)
        status, provider, ref = "confirmed", "duffel_test", got.get("booking_reference")
        data = {"read_back": rb, "payment": {"provider": "stripe_test", "mode": "simulated", "status": "succeeded",
                                             "amount": o["price"]}, "order_id": got.get("order_id")}
    else:
        status, provider, ref = "requested", "sandbox_venue", None
        data = {"read_back": rb, "contacted": False, "note": "sandbox: the venue was not contacted"}
    db.x("insert into bookings (id, key_id, hold_id, approval_id, kind, status, provider, provider_ref, data, created_at, updated_at) "
         "values (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)", bid, key["id"], h["id"], a["id"], h["kind"], provider, ref, dumps(data),
         iso(now()), iso(now()))
    _event(db, key["id"], bid, "approved", "end_user", {"approval_id": a["id"], "read_back_sha256": a["read_back_sha256"],
                                                         "decided_at": a["decided_at"]})
    if h["kind"] == "flight":
        _event(db, key["id"], bid, "payment_succeeded", "stripe_test_simulated", data["payment"])
    _event(db, key["id"], bid, status, provider, {"provider_ref": ref, "order_id": data.get("order_id")}, status=status)
    return booking_out(db, db.one("select * from bookings where id = ?", bid))


async def cancel(db: Store, key: dict, booking_id: str, body: dict) -> dict:
    b = db.one("select * from bookings where id = ? and key_id = ?", booking_id, key["id"])
    if not b:
        raise ApiError("not_found", "booking_not_found", "no such booking for this key")
    h, a = _consume(db, key, body.get("hold_id"), body.get("approval_id"))
    if h["kind"] != "cancel" or h["booking_id"] != b["id"]:
        _release(db, h, a)
        raise ApiError("invalid_request", "hold_not_this_cancellation", "the hold must be this booking's cancellation (POST /v1/holds {cancel_booking_id})")
    _event(db, key["id"], b["id"], "cancel_approved", "end_user", {"approval_id": a["id"], "read_back_sha256": a["read_back_sha256"]})
    _event(db, key["id"], b["id"], "cancelled", b["provider"], {"simulated": True}, status="cancelled")
    return booking_out(db, db.one("select * from bookings where id = ?", b["id"]))


def venue_reply(db: Store, key: dict, booking_id: str, text: str) -> dict:
    """Sandbox control: simulate the venue's answer. Its words are UNTRUSTED data — read by fixed patterns, never followed."""
    b = db.one("select * from bookings where id = ? and key_id = ?", booking_id, key["id"])
    if not b or b["kind"] == "flight":
        raise ApiError("not_found", "booking_not_found", "no such venue booking for this key")
    t = (text or "")[:500]
    says = ("confirmed" if re.search(r"(?i)\b(confirm(ed)?|see you|booked|reserved)\b", t) and not re.search(r"(?i)\b(not|no|full|unable)\b", t)
            else "declined" if re.search(r"(?i)\b(full|unable|no availability|can'?t|cannot)\b", t) else None)
    _event(db, key["id"], b["id"], "venue_replied", "venue", {"words": PV.untrusted(t, "venue_reply"), "read_as": says or "unclear"},
           status=says if says and b["status"] == "requested" else None)
    return booking_out(db, db.one("select * from bookings where id = ?", b["id"]))


def _event(db: Store, key_id: str, subject: str, type_: str, actor: str, data: dict, status: Optional[str] = None) -> dict:
    """Pacioli: an append-only, hash-chained event; the ONLY writer of a booking's status."""
    with db.tx():
        last = db.one("select seq, sha256 from proof where subject = ? order by seq desc limit 1", subject)
        seq, prev = (last["seq"] + 1, last["sha256"]) if last else (1, "0" * 64)
        at = iso(now())
        sha = sha256_of({"subject": subject, "seq": seq, "at": at, "type": type_, "actor": actor, "data": _canon(data), "prev_sha256": prev})
        db.x("insert into proof (key_id, subject, seq, at, type, actor, data, prev_sha256, sha256) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
             key_id, subject, seq, at, type_, actor, dumps(_canon(data)), prev, sha)
        if status:
            db.x("update bookings set status = ?, updated_at = ? where id = ?", status, at, subject)
    return {"seq": seq, "sha256": sha}


def _canon(o: Any) -> Any:
    """Data as canonical JSON accepts it (integers only; floats never appear — money is in minor units)."""
    if isinstance(o, dict):
        return {str(k): _canon(v) for k, v in o.items() if v is not None}
    if isinstance(o, (list, tuple)):
        return [_canon(v) for v in o]
    if isinstance(o, float):
        return int(o) if o.is_integer() else str(o)
    return o


def booking_out(db: Store, b: dict) -> dict:
    data = _loads(b["data"])
    return {"object": "booking", "id": b["id"], "kind": b["kind"], "status": b["status"], "provider": b["provider"],
            "provider_ref": b["provider_ref"], "hold_id": b["hold_id"], "approval_id": b["approval_id"],
            "read_back": data.get("read_back"), "payment": data.get("payment"), "test_mode": True,
            "created_at": b["created_at"], "updated_at": b["updated_at"]}


def proof(db: Store, key: dict, booking_id: str) -> dict:
    b = db.one("select * from bookings where id = ? and key_id = ?", booking_id, key["id"])
    if not b:
        raise ApiError("not_found", "booking_not_found", "no such booking for this key")
    ev = db.q("select seq, at, type, actor, data, prev_sha256, sha256 from proof where subject = ? order by seq", booking_id)
    chain_ok, prev = True, "0" * 64
    for e in ev:
        e["data"] = _loads(e["data"])
        want = sha256_of({"subject": booking_id, "seq": e["seq"], "at": e["at"], "type": e["type"], "actor": e["actor"],
                          "data": e["data"], "prev_sha256": prev})
        chain_ok &= (e["prev_sha256"] == prev and e["sha256"] == want)
        prev = e["sha256"]
    return {"object": "proof", "booking_id": booking_id, "status": b["status"], "events": ev, "chain_valid": chain_ok,
            "how_to_verify": "sha256 of canonical JSON {subject, seq, at, type, actor, data, prev_sha256}; prev of the first is 64 zeros"}


def _loads(s: Optional[str]) -> Any:
    import json
    return json.loads(s) if s else None

