"""CR 61 · AgAPI v1.0's rules in Sasha's runtime — pure, no I/O beyond reading the pinned language file. EU's frozen contract
(Applied Diligence docs/agapi/v1, EU 205) is the authority; scripts/agapi_v1_conformance.py runs its vectors against THIS module
(canonical 15, explicit-yes 38, approval 17, outage 7) and refuses if the pinned language file differs from EU's.

    canonical / sha256 / read_back_sha256   Part 1 §4.1–4.2   (booking_signer.canonical stays the booking helper's own contract)
    explicit_yes(said, lang)                Part 1 AP6, the lists in spec/approval-language.json (EU's frozen file, sha256-pinned)
    decide(case)                            Part 1 AP1–AP9 in Part 3 §3's order — the first failing rule wins
    classify(sources)                       Part 1 §5.1 — an upstream failure is never "no results"
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional, Tuple

SPEC = Path(__file__).resolve().parent / "spec"
LANGUAGE_FILE = SPEC / "approval-language.json"
LANGUAGE_SHA256 = "b4992034e2757c96d1bf074d964546d133bb5e7a7b0fdab7b01e571b27da3dfd"   # EU's frozen v1.0 file, byte for byte (unchanged in 1.1)
ACTS_SHA256 = "e8c8c2edc71ee93965a0fa2476f73107b843a0521e0bdc82ec6e455faf03dd5f"   # 1.1 (EU 211): approval-language-acts.json, byte for byte
MAX_INT = 2**53 - 1
_KEY = re.compile(r"^[a-z0-9_]+$")


class Refused(ValueError):
    pass


# ── §4.1 canonical JSON ───────────────────────────────────────────────────────────────────────────────────────────────

def _norm_num(v: Any) -> Any:
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


# ── AP6 the explicit yes ──────────────────────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def languages() -> dict:
    raw = LANGUAGE_FILE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != LANGUAGE_SHA256:
        raise RuntimeError("agapi/spec/approval-language.json is not EU's frozen v1.0 file — refusing to judge a yes with other lists")
    return json.loads(raw.decode("utf-8"))["languages"]


def normalise(s: str, apostrophe: str = "") -> str:
    """EU's normalisation. apostrophe="" DELETES it ("don't" → "dont": 1.0.1, the CR 61 errata EU adopted); apostrophe=" " SPLITS it
    ("what's" → "what s": 1.1). A veto is checked in BOTH forms (vetoed()); affirmatives in the deleted form."""
    s = unicodedata.normalize("NFC", s or "").lower()
    s = re.sub(r"['‘’]", apostrophe, s)
    s = re.sub(r"[¡¿!?.,;:\"“”()—–]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _has(t: str, phrase: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", t) is not None


def affirmative(t: str, L: dict, extra: Tuple[str, ...] = ()) -> bool:
    rest, changed = t, True
    while changed:
        changed = False
        for f in sorted(L["fillers"], key=len, reverse=True):
            if rest == f or rest.startswith(f + " "):
                rest, changed = rest[len(f):].strip(), True
    return any(rest == a or rest.startswith(a + " ") for a in sorted(list(L["affirmatives"]) + list(extra), key=len, reverse=True))


def acts() -> dict:
    """1.1 · approval-language-acts.json (EU's file, sha256-pinned): the words a given act's own yes may contain."""
    raw = (SPEC / "approval-language-acts.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != ACTS_SHA256:
        raise RuntimeError("agapi/spec/approval-language-acts.json is not EU's 1.1 file")
    return json.loads(raw)["acts"]


def exempt(act_kind: Optional[str], lang: str) -> set:
    """1.1 AP6 act-aware: for a cancellation's own yes ("cancel"), its own word stops vetoing. None → nothing exempt (1.0.1)."""
    return set(acts().get(act_kind, {}).get(lang, {}).get("exempt_negations", [])) if act_kind else set()


def vetoed(said: str, L: dict, skip=frozenset()) -> bool:
    """1.1: any negation (bar `skip`) or question/request, in EITHER apostrophe form — "Yes, but what's the refund?" is not a yes."""
    forms = (normalise(said or ""), normalise(said or "", " "))
    return any(_has(f, n) for n in [x for x in L["negations"] if x not in skip] + L.get("questions_and_requests", []) for f in forms)


def explicit_yes(said: Optional[str], lang: str = "en", act_kind: Optional[str] = None) -> bool:
    """AP6 as in 1.1: an affirmative (after leading fillers), and NO veto in either apostrophe form (bar the act's exemptions)."""
    L = languages()[lang]
    t = normalise(said or "")
    if not t or vetoed(said, L, exempt(act_kind, lang)):
        return False
    return affirmative(t, L)


# ── AP1–AP9 at act time, in Part 3 §3's order ─────────────────────────────────────────────────────────────────────────

def decide(case: dict, test_mode: bool = False) -> Tuple[str, Optional[str]]:
    a, rb, cur, now = case["approval"], case["read_back"], case["current"], case["now"]
    channels = ("link", "sdk", "sasha_voice", "sasha_chat") + (("sandbox_simulated",) if test_mode else ())
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
    """[{source, ok, code?, items}] → ("ok", coverage, n_items) | ("error", code). [] is a claim only when every source answered."""
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
    return "ok", {"complete": not failed, "answered": answered, "unavailable": failed}, sum(len(s.get("items", [])) for s in sources if s["ok"])
