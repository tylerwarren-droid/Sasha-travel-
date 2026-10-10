"""AgAPI v1's pure rules — no I/O, no state. Each function mirrors a numbered rule in EU's v1 spec (spec/v1/, vendored from the AD
repo's docs/agapi/v1) and is checked against its Part 3/4 vectors (tests/test_vectors.py):

    canonical / sha256 / read_back_sha256   Part 1 §4.1–4.2          vectors/canonical.json
    explicit_yes                            Part 1 AP6 + approval-language.json   vectors/explicit-yes.json
    wrap (untrusted_text)                   Part 2 §3 + untrusted-patterns.json   vectors/untrusted.json
    decide (the act-time Approval check)    Part 1 AP1–AP9, Part 3 §3 order       vectors/approval.json
    classify (outage ≠ no results)          Part 1 §5.1                            vectors/outage.json
    evidence_body_sha256                    Part 2 §4                              vectors/evidence.json
    webhook_signature / webhook_verify      Part 4 §4                              vectors/webhook-signature.json
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SPEC = Path(__file__).resolve().parent / "spec" / "v1"
MAX_INT = 2**53 - 1
_KEY = re.compile(r"^[a-z0-9_]+$")


class Refused(ValueError):
    """A value canonical JSON refuses (§4.1) — an error, never coerced."""


# ── §4.1 canonical JSON ───────────────────────────────────────────────────────────────────────────────────────────────

def _norm_num(v: Any) -> Any:
    """An integer-VALUED number becomes the integer (1.0 → 1, -0.0 → 0, 1e3 → 1000); a fractional one stays (refused next)."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            raise Refused("non-finite number")
        return int(v) if v.is_integer() else v
    if isinstance(v, list):
        return [_norm_num(x) for x in v]
    if isinstance(v, dict):
        return {k: _norm_num(x) for k, x in v.items()}
    return v


def _check(v: Any) -> None:
    if v is None or isinstance(v, bool):
        return
    if isinstance(v, int):
        if abs(v) > MAX_INT:
            raise Refused("integer out of range")
        return
    if isinstance(v, float):
        raise Refused("float")
    if isinstance(v, str):
        if any(0xD800 <= ord(c) <= 0xDFFF for c in v):
            raise Refused("lone surrogate")
        return
    if isinstance(v, (list, tuple)):
        for x in v:
            _check(x)
        return
    if isinstance(v, dict):
        for k, x in v.items():
            if not isinstance(k, str) or not _KEY.match(k):
                raise Refused("key charset")
            _check(x)
        return
    raise Refused(f"type {type(v).__name__}")


def canonical(v: Any) -> str:
    v = _norm_num(v)
    _check(v)
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(v: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(v).encode("utf-8")).hexdigest()


def read_back_sha256(account: str, intent_id: str, operation: str, lines: List[str], payload_sha256: str) -> str:
    return sha256({"account": account, "intent_id": intent_id, "operation": operation, "lines": lines, "payload_sha256": payload_sha256})


def request_sha256(operation: str, input_: dict) -> str:
    return sha256({"operation": operation, "input": input_})


# ── AP6 the explicit yes ──────────────────────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _lang() -> dict:
    return json.loads((SPEC / "vectors" / "approval-language.json").read_text(encoding="utf-8"))["languages"]


def _norm_said(s: str, apostrophe: str = "") -> str:
    """EU's normalisation. apostrophe="" DELETES it ("don't" → "dont": 1.0.1, the CR 61 errata); apostrophe=" " SPLITS it
    ("what's" → "what s": 1.1). A veto is checked in BOTH forms (1.1), affirmatives in the deleted form."""
    s = unicodedata.normalize("NFC", s).lower()
    s = re.sub(r"['‘’]", apostrophe, s)
    s = re.sub(r"[¡¿!?.,;:\"“”()—–]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def _acts() -> dict:
    return json.loads((SPEC / "vectors" / "approval-language-acts.json").read_text(encoding="utf-8"))["acts"]


def _vetoed(said: str, L: dict, exempt) -> bool:
    """1.1: any negation (bar the act's exemptions) or question/request, in EITHER apostrophe form — "Yes, but what's the
    refund?" is NOT a yes (1.0.1 let "what's" through: "whats" matched no veto)."""
    forms = (_norm_said(said or ""), _norm_said(said or "", " "))
    for neg in [n for n in L["negations"] if n not in exempt] + L.get("questions_and_requests", []):
        if any(re.search(r"(?<!\w)" + re.escape(neg) + r"(?!\w)", f) for f in forms):
            return True
    return False


def _exempt(act_kind: Optional[str], lang: str) -> set:
    """1.1 AP6 act-aware (CR 61): for a cancellation's own yes, its own word ("cancel" / "cancela") stops vetoing."""
    return set(_acts().get(act_kind, {}).get(lang, {}).get("exempt_negations", [])) if act_kind else set()


def explicit_yes(said: Optional[str], lang: str = "en", act_kind: Optional[str] = None) -> bool:
    """AP6 (v1.1), server-side, never a model: an affirmative phrase (after leading fillers) and NO negation, question or request for
    options anywhere — every list read from approval-language.json (byte-identical since 1.0), the act's exemptions from
    approval-language-acts.json, the vetoes matched in both apostrophe forms."""
    L = _lang()[lang]
    t = _norm_said(said or "")
    if not t or _vetoed(said, L, _exempt(act_kind, lang)):
        return False
    rest, changed = t, True
    while changed:
        changed = False
        for f in sorted(L["fillers"], key=len, reverse=True):
            if rest == f or rest.startswith(f + " "):
                rest, changed = rest[len(f):].strip(), True
    return any(rest == a or rest.startswith(a + " ") for a in sorted(L["affirmatives"], key=len, reverse=True))


def explicit_yes_any(said: Optional[str], act_kind: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """No language given (the sandbox's simulate_approval): a yes in some language AND no veto in ANY of them (1.1 rules)."""
    for code, L in _lang().items():
        if _vetoed(said or "", L, _exempt(act_kind, code)):
            return False, None
    for code in _lang():
        if explicit_yes(said, code, act_kind):
            return True, code
    return False, None


# ── Part 2 §3 untrusted text ──────────────────────────────────────────────────────────────────────────────────────────

_STRIP = re.compile("[\u0000-\u0008\u000b-\u001f\u007f-\u009f​-‍‪-‮⁦-⁩﻿]")


@lru_cache(maxsize=1)
def _patterns() -> List[re.Pattern]:
    p = json.loads((SPEC / "vectors" / "untrusted-patterns.json").read_text(encoding="utf-8"))["patterns"]
    return [re.compile(x, re.IGNORECASE) for x in p]


def wrap(text: str, source: str, retrieved_at: str, cap: int = 2000) -> Dict[str, Any]:
    """Fetched text → {text, source, retrieved_at[, truncated][, instruction_like]}: cleaned, capped, FLAGGED — never removed."""
    t = unicodedata.normalize("NFC", _STRIP.sub("", str(text)))
    out: Dict[str, Any] = {"text": t[:cap], "source": source, "retrieved_at": retrieved_at}
    if len(t) > cap:
        out["truncated"] = True
    if any(p.search(t) for p in _patterns()):
        out["instruction_like"] = True
    return out


# ── AP1–AP9 at act time, in the normative order (Part 3 §3) ───────────────────────────────────────────────────────────

TRUSTED_CHANNELS = ("link", "sdk", "sasha_voice", "sasha_chat")


def decide(case: dict, *, test_mode: bool = False) -> Tuple[str, Optional[str]]:
    """case: {account, lang, now, acts_in_request, read_back{presented_to, presented_at, presented_turn_id, expires_at},
    approval{account, intent_id, read_back_sha256, payload_sha256, method, said?, approved_by, approved_at, approved_turn_id,
    device{channel, attestation?}, expires_at, irreversible, state}, current{intent_id, operation, lines, payload}}
    → (decision, void_reason). `sandbox_simulated` is a trusted channel ONLY in test mode (Part 4 §5)."""
    a, rb, cur, now = case["approval"], case["read_back"], case["current"], case["now"]
    channels = TRUSTED_CHANNELS + (("sandbox_simulated",) if test_mode else ())
    if a is None or a["account"] != case["account"]:
        return "approval_not_found", None
    if a["device"]["channel"] not in channels or a["approved_by"] != rb["presented_to"]:
        return "approval_untrusted_origin", None
    if a["device"]["channel"] == "sdk" and not a["device"].get("attestation"):
        return "approval_untrusted_origin", None
    if a["state"] == "consumed":
        return "approval_consumed", None
    if rb["presented_at"] is None or a["approved_turn_id"] == rb["presented_turn_id"] or not (a["approved_at"] > rb["presented_at"]):
        return "approval_same_turn", None
    if a["method"] == "voice" or (a["device"]["channel"] == "sasha_chat" and a.get("said") is not None):
        if not explicit_yes(a.get("said"), case.get("lang", "en"), case.get("act_kind")):
            return "no_explicit_yes", None
    if a["approved_at"] > rb["expires_at"] or now > a["expires_at"]:
        return "approval_expired", None
    if a["irreversible"] and case.get("acts_in_request", 1) > 1:
        return "approval_void", "irreversible_batch"
    if cur["intent_id"] != a["intent_id"]:
        return "approval_void", "intent_changed"
    if sha256(cur["payload"]) != a["payload_sha256"]:
        return "approval_void", "payload_changed"
    if read_back_sha256(case["account"], cur["intent_id"], cur["operation"], cur["lines"], sha256(cur["payload"])) != a["read_back_sha256"]:
        return "approval_void", "read_back_changed"
    return "valid", None


# ── §5.1 outage ≠ no results ──────────────────────────────────────────────────────────────────────────────────────────

TRANSIENT = ["upstream_unreachable", "upstream_timeout", "upstream_rate_limited", "upstream_failed"]


def classify(sources: List[dict]):
    """[{source, ok, code?, items}] → ("ok", coverage, n) | ("error", code). [] is a claim only when every source answered."""
    answered = [s["source"] for s in sources if s["ok"]]
    failed = [{"source": s["source"], "code": s["code"]} for s in sources if not s["ok"]]
    if not answered:
        codes = [f["code"] for f in failed]
        if codes and all(c == "upstream_refused" for c in codes):
            return "error", "upstream_refused"
        for c in TRANSIENT:
            if c in codes:
                return "error", c
        return "error", "upstream_failed"
    n = sum(len(s.get("items", [])) for s in sources if s["ok"])
    return "ok", {"complete": not failed, "answered": answered, "unavailable": failed}, n


# ── Part 2 §4 evidence, Part 4 §4 webhooks ────────────────────────────────────────────────────────────────────────────

def evidence_body_sha256(evidence: dict) -> str:
    return sha256({k: v for k, v in evidence.items() if k != "body_sha256"})


def webhook_signature(secret: str, t: int, raw_body: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), f"{t}.{raw_body}".encode("utf-8"), hashlib.sha256).hexdigest()
    return f"t={t},v1={mac}"


def webhook_verify(secret: str, header: str, raw_body: str, received_at: Optional[int] = None, tolerance_s: int = 300):
    """→ (valid, reason). Over the RAW body, constant-time, and stale after 5 minutes even if the MAC matches (W-3)."""
    m = re.fullmatch(r"t=(\d+),v1=([0-9a-f]{64})", (header or "").strip())
    if not m:
        return False, "malformed"
    t = int(m.group(1))
    want = webhook_signature(secret, t, raw_body).split("v1=")[1]
    if not hmac.compare_digest(want, m.group(2)):
        return False, "mismatch"
    if (received_at if received_at is not None else int(time.time())) - t > tolerance_s:
        return False, "stale"
    return True, None


# ── ids (Part 1 §2): <prefix>_<ULID> ──────────────────────────────────────────────────────────────────────────────────

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id(prefix: str) -> str:
    n = (int(time.time() * 1000) << 80) | secrets.randbits(80)
    return f"{prefix}_" + "".join(_CROCKFORD[(n >> (5 * i)) & 31] for i in reversed(range(26)))


# ── CR 76 · THE ONE YES RULE ─────────────────────────────────────────────────────────────────────────────────────────
# The approvals now come from ONE generated module (agapi_service/yes_one/yes_one.py, from the AgAPI 1.3 contract) — byte for byte the
# module Sasha's S2 and AD vendor (AD as yes_one.ts). Every act's check (engine._check_and_consume → decide) and every yes
# (sandbox.simulate_approval → explicit_yes_any) runs through it; the names above stay so nothing calling them changes.
from .yes_one import yes_one as YES_ONE   # noqa: E402

Refused = YES_ONE.Refused
canonical, sha256 = YES_ONE.canonical, YES_ONE.sha256
read_back_sha256, request_sha256 = YES_ONE.read_back_sha256, YES_ONE.request_sha256
explicit_yes, explicit_yes_any = YES_ONE.explicit_yes, YES_ONE.explicit_yes_any


def decide(case: dict, *, test_mode: bool = False) -> Tuple[str, Optional[str]]:   # noqa: F811 — the one rule
    return YES_ONE.decide(case, test_mode=test_mode)
