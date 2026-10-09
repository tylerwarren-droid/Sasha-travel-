"""DIVE's model (EU 212 model.md): Operator → Supplier → Channel; Product → Package; Bundle → Leg. A supplier is only ever booked once
the operator CONFIRMED it; a channel only once VERIFIED; a leg moves only along rules.LEG_MOVES (anything else is refused)."""
from __future__ import annotations

import hmac
import hashlib
import secrets
from typing import Any, Dict, List, Optional

from . import config, rules as R
from .store import Store, dumps, loads, ts


class DiveError(Exception):
    """An error with its code (DIVE's error-codes.dive.json, or AgAPI's), said plainly; never a value from outside."""

    HTTP = {"supplier_declined": 409, "supplier_no_answer": 200, "supplier_unreachable": 503, "channel_not_verified": 409,
            "supplier_not_confirmed": 409, "package_not_published": 404, "bundle_changed": 409, "past_cutoff": 422,
            "robots_disallowed": 403, "invalid_input": 400, "not_found": 404, "approval_required": 403, "approval_void": 409,
            "approval_consumed": 409, "approval_expired": 410, "unauthenticated": 401, "forbidden": 403, "upstream_unreachable": 503,
            "mode_not_available": 403, "idempotency_key_required": 400, "idempotency_conflict": 409, "illegal_transition": 409}

    def __init__(self, code: str, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}

    @property
    def http(self) -> int:
        return self.HTTP.get(self.code, 400)

    def body(self) -> dict:
        return {"code": self.code, "message": self.message, "retryable": self.code in ("supplier_unreachable", "upstream_unreachable"),
                **({"details": self.details} if self.details else {})}


# ── operators ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def operator_out(o: dict) -> dict:
    return {"operator_id": o["id"], "slug": o["slug"], "name": o["name"], "timezone": o["timezone"], "languages": loads(o["languages"]),
            **({"site_url": o["site_url"]} if o["site_url"] else {}), "footer": o["footer"] or config.FOOTER, "mode": config.MODE,
            "booking_page": f"{config.PUBLIC_URL}/o/{o['slug']}/book"}


def put_operator(s: Store, slug: str, name: str, timezone: str, languages: List[str], site_url: Optional[str] = None,
                 footer: Optional[str] = None) -> dict:
    o = s.one("select * from operators where slug = ?", slug)
    if o:
        s.x("update operators set name = ?, timezone = ?, languages = ?, site_url = ?, footer = ? where id = ?", name, timezone,
            dumps(languages), site_url, footer or config.FOOTER, o["id"])
    else:
        s.x("insert into operators (id, slug, name, timezone, languages, site_url, footer, created_at) values (?, ?, ?, ?, ?, ?, ?, ?)",
            R.new_id("opr"), slug, name, timezone, dumps(languages), site_url, footer or config.FOOTER, ts())
    return s.one("select * from operators where slug = ?", slug)


# ── suppliers + channels ────────────────────────────────────────────────────────────────────────────────────────────────

def channel_out(c: dict) -> dict:
    return {"channel_id": c["id"], "supplier_id": c["supplier_id"], "rung": c["rung"], "kind": c["kind"], "address": c["address"],
            "verified": bool(c["verified"]), **({"verified_at": c["verified_at"]} if c["verified_at"] else {}),
            **({"verified_how": c["verified_how"]} if c["verified_how"] else {}), "answer_timeout_s": c["answer_timeout_s"],
            **({"quiet_hours": c["quiet_hours"]} if c["quiet_hours"] else {}), "language": c["language"]}


def supplier_out(s: Store, x: dict) -> dict:
    return {"supplier_id": x["id"], "operator_id": x["operator_id"], "name": x["name"], "kind": x["kind"], "status": x["status"],
            "source": x["source"], **({"evidence_of_source": loads(x["evidence_of_source"])} if x["evidence_of_source"] else {}),
            **({"confidence": x["confidence"]} if x["confidence"] is not None else {}), "contacts": loads(x["contacts"]) or {},
            "channels": [channel_out(c) for c in s.q("select * from channels where supplier_id = ? order by rung", x["id"])]}


RUNG = {"partner_api": 0, "feed": 1, "web_form": 2, "email": 3, "whatsapp": 4}


def add_channel(s: Store, supplier: dict, kind: str, address: str, language: str = "en", timeout: Optional[int] = None,
                quiet: Optional[str] = None) -> dict:
    if supplier["status"] != "confirmed":
        raise DiveError("supplier_not_confirmed", f"{supplier['name']} is still a draft — confirm it first.")
    cid = R.new_id("chn")
    s.x("insert into channels (id, supplier_id, rung, kind, address, answer_timeout_s, quiet_hours, language, created_at) "
        "values (?, ?, ?, ?, ?, ?, ?, ?, ?)", cid, supplier["id"], RUNG[kind], kind, address, timeout or config.ANSWER_TIMEOUT_S,
        quiet or (f"{config.QUIET_HOURS[0]}-{config.QUIET_HOURS[1]}" if kind in ("whatsapp", "email") else None), language, ts())
    return s.one("select * from channels where id = ?", cid)


def best_channel(s: Store, supplier_id: str) -> Optional[dict]:
    """The lowest-rung VERIFIED channel (falling through only on an outage, in channels.py)."""
    return s.one("select * from channels where supplier_id = ? and verified = 1 order by rung limit 1", supplier_id)


# ── legs: the state machine ─────────────────────────────────────────────────────────────────────────────────────────────

def move_leg(s: Store, leg: dict, to: str, **fields) -> dict:
    if not R.can_move(leg["state"], to):
        raise DiveError("illegal_transition", f"a leg can't go from {leg['state']} to {to}.", {"leg_id": leg["id"]})
    sets = ", ".join(["state = ?"] + [f"{k} = ?" for k in fields])
    s.x(f"update legs set {sets} where id = ? and state = ?", to, *fields.values(), leg["id"], leg["state"])
    got = s.one("select * from legs where id = ?", leg["id"])
    if got["state"] != to:
        raise DiveError("illegal_transition", "the leg changed under us — read it again.", {"leg_id": leg["id"]})
    return got


# ── evidence + the activity feed ────────────────────────────────────────────────────────────────────────────────────────

def evidence(s: Store, operator_id: str, operation: str, *, sources: List[dict], outcome: Optional[dict] = None,
             approval: Optional[dict] = None, digest_of: Any = None, act_id: Optional[str] = None) -> str:
    """Pacioli evidence in AgAPI's shape (basis measured, states_no_conclusion); body_sha256 over everything else."""
    eid = R.new_id("evd")
    ev: Dict[str, Any] = {"evidence_id": eid, "basis": "measured", "states_no_conclusion": True, "operation": operation,
                          "input_digest": R.sha256(digest_of if digest_of is not None else {}), "produced_at": ts()[:19] + "Z",
                          "sources": sources}
    if act_id:
        ev["act_id"] = act_id
    if outcome:
        ev["outcome"] = outcome
    if approval:
        ev["approval"] = approval
    ev["body_sha256"] = R.sha256({k: v for k, v in ev.items() if k != "body_sha256"})
    s.x("insert into evidence (id, operator_id, body, created_at) values (?, ?, ?, ?)", eid, operator_id, dumps(ev), ts())
    return eid


def verify_evidence(ev: dict) -> bool:
    return hmac.compare_digest(R.sha256({k: v for k, v in ev.items() if k != "body_sha256"}), ev.get("body_sha256", ""))


def event(s: Store, operator_id: str, kind: str, line: str, *, bundle_id=None, leg_id=None, evidence_id=None) -> None:
    """One Activity row for the operator console: fixed words, never a supplier's or a site's text."""
    s.x("insert into events (operator_id, bundle_id, leg_id, kind, line, evidence_id, at) values (?, ?, ?, ?, ?, ?, ?)",
        operator_id, bundle_id, leg_id, kind, line, evidence_id, ts())


# ── the generated API's keys (opk_) ─────────────────────────────────────────────────────────────────────────────────────

_B62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _hmac(key: str) -> str:
    return hmac.new(config.pepper(), key.encode(), hashlib.sha256).hexdigest()


def issue_key(s: Store, operator_id: str, label: str) -> dict:
    key = "opk_test_" + "".join(secrets.choice(_B62) for _ in range(32))
    kid = "opk_" + R.new_id("opk")[4:]
    s.x("insert into op_keys (key_id, operator_id, label, secret_hmac, state, created_at) values (?, ?, ?, ?, 'active', ?)",
        kid, operator_id, label[:60], _hmac(key), ts())
    return {"key_id": kid, "key": key, "label": label[:60]}


def resolve_key(s: Store, slug: str, presented: str) -> Optional[dict]:
    """An opk_ key resolves to ITS operator only: operator A's key can't touch B (the slug must match)."""
    if not presented.startswith("opk_test_"):
        return None
    row = s.one("select k.*, o.slug from op_keys k join operators o on o.id = k.operator_id where k.secret_hmac = ? and k.state = 'active'",
                _hmac(presented))
    return row if row and row["slug"] == slug else None
