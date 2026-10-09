"""DIVE's rules — pure, no I/O: canonical JSON + sha256 (AgAPI Part 1 §4.1), ids, untrusted text (EU's patterns, vendored), the
customer's explicit yes (AP6 as in 1.1, EU's lists vendored byte for byte), the SUPPLIER-REPLY parser (yes | no | unclear, EN/EL/ES)
and the BUNDLE state with its customer sentences (EU 212 bundles.md §3). Every list is a vendored or DIVE spec file, sha-checked."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SPEC = Path(__file__).resolve().parent / "spec"
VENDOR = SPEC / "vendor"
_B32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
PREFIXES = ("opr", "sup", "chn", "prd", "pkg", "bnd", "leg", "opk", "rb", "apv", "evd", "req", "drf", "vfy")   # EU 212's 8 + DIVE's own


class Refused(ValueError):
    pass


# ── canonical JSON (AgAPI Part 1 §4.1, restricted) ──────────────────────────────────────────────────────────────────────

def _check(v: Any) -> None:
    if isinstance(v, bool) or v is None or isinstance(v, str):
        if isinstance(v, str) and re.search(r"[\ud800-\udfff]", v):
            raise Refused("lone surrogate")
        return
    if isinstance(v, int):
        if abs(v) > 2 ** 53 - 1:
            raise Refused("integer out of range")
        return
    if isinstance(v, float):
        raise Refused("floats are refused: money is integer minor units")
    if isinstance(v, list):
        for x in v:
            _check(x)
        return
    if isinstance(v, dict):
        for k, x in v.items():
            if not isinstance(k, str) or not re.fullmatch(r"[a-z0-9_]+", k):
                raise Refused(f"key {k!r}")
            _check(x)
        return
    raise Refused(f"type {type(v).__name__}")


def canonical(v: Any) -> str:
    _check(v)
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(v: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(v).encode()).hexdigest()


def text_sha256(s: str) -> str:
    return "sha256:" + hashlib.sha256((s or "").encode()).hexdigest()


def new_id(prefix: str) -> str:
    assert prefix in PREFIXES, prefix
    t = int(time.time() * 1000)
    head = "".join(_B32[(t >> (45 - 5 * i)) & 31] for i in range(10))
    tail = "".join(_B32[b & 31] for b in os.urandom(16))
    return f"{prefix}_{head}{tail}"


# ── vendored lists (sha-checked) ────────────────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=None)
def _vendored(name: str) -> dict:
    sums = dict(reversed(l.split()) for l in (VENDOR / "SHA256SUMS").read_text().splitlines() if l.strip())
    raw = (VENDOR / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != sums[name]:
        raise RuntimeError(f"dive_service/spec/vendor/{name} is not EU's file")
    return json.loads(raw)


@lru_cache(maxsize=1)
def _patterns() -> List[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in _vendored("untrusted-patterns.json")["patterns"]]


_STRIP = re.compile("[\u0000-\u0008\u000b-\u001f\u007f-\u009f​-‍‪-‮⁦-⁩﻿]")


def wrap(text: str, source: str, retrieved_at: str, cap: int = 2000) -> Dict[str, Any]:
    """Text from outside (a website, a supplier's reply) → untrusted_text: cleaned, capped, FLAGGED — data, never instructions."""
    t = unicodedata.normalize("NFC", _STRIP.sub("", str(text)))
    out: Dict[str, Any] = {"text": t[:cap], "source": source, "retrieved_at": retrieved_at}
    if len(t) > cap:
        out["truncated"] = True
    if any(p.search(t) for p in _patterns()):
        out["instruction_like"] = True
    return out


# ── the customer's yes (AP6, 1.1) ───────────────────────────────────────────────────────────────────────────────────────

def _norm(s: str, apostrophe: str = "") -> str:
    s = unicodedata.normalize("NFC", s or "").lower()
    s = re.sub(r"['‘’]", apostrophe, s)
    s = re.sub(r"[¡¿!?.,;:\"“”()—–]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _has(t: str, p: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", t) is not None


def explicit_yes(said: Optional[str], lang: str = "en", act_kind: Optional[str] = None) -> bool:
    """AgAPI 1.1 AP6 on EU's own lists: an affirmative after fillers, no veto in either apostrophe form (bar the act's exemptions)."""
    L = _vendored("approval-language.json")["languages"][lang]
    ex = set(_vendored("approval-language-acts.json")["acts"].get(act_kind, {}).get(lang, {}).get("exempt_negations", [])) if act_kind else set()
    t = _norm(said or "")
    forms = (t, _norm(said or "", " "))
    if not t or any(_has(f, n) for n in [x for x in L["negations"] if x not in ex] + L.get("questions_and_requests", []) for f in forms):
        return False
    rest, changed = t, True
    while changed:
        changed = False
        for f in sorted(L["fillers"], key=len, reverse=True):
            if rest == f or rest.startswith(f + " "):
                rest, changed = rest[len(f):].strip(), True
    return any(rest == a or rest.startswith(a + " ") for a in sorted(L["affirmatives"], key=len, reverse=True))


def explicit_yes_any(said: Optional[str], act_kind: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    langs = _vendored("approval-language.json")["languages"]
    for code, L in langs.items():
        ex = set(_vendored("approval-language-acts.json")["acts"].get(act_kind, {}).get(code, {}).get("exempt_negations", [])) if act_kind else set()
        forms = (_norm(said or ""), _norm(said or "", " "))
        if any(_has(f, n) for n in [x for x in L["negations"] if x not in ex] + L.get("questions_and_requests", []) for f in forms):
            return False, None
    for code in langs:
        if explicit_yes(said, code, act_kind):
            return True, code
    return False, None


# ── the supplier's reply: yes | no | unclear ───────────────────────────────────────────────────────────────────────────

def _fold(s: str, apostrophe: str = "") -> str:
    """NFD, combining marks (accents, Greek tonos) dropped, lower case, apostrophes deleted/split, punctuation → spaces."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"['‘’]", apostrophe, s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def _reply_lists() -> Dict[str, Dict[str, List[str]]]:
    d = json.loads((SPEC / "supplier-reply-language.json").read_text(encoding="utf-8"))["languages"]
    return {lang: {k: sorted({_fold(x) for x in v}, key=len, reverse=True) for k, v in L.items()} for lang, L in d.items()}


@lru_cache(maxsize=1)
def _phrases() -> List[Tuple[str, str]]:
    seen = {}
    for L in _reply_lists().values():
        for kind in ("yes", "no", "conditions"):
            for p in L[kind]:
                seen.setdefault(p, kind)
    return sorted(seen.items(), key=lambda x: (-len(x[0]), x[0]))


_GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")


def supplier_reply(text: str) -> Dict[str, Any]:
    """→ {"parse": yes|no|unclear, "why": …}. Emoji never decide; a question or a condition is never a yes; both is unclear."""
    raw = text or ""
    if not re.search(r"[^\W\d_]", raw):
        return {"parse": "unclear", "why": "no words (an emoji or a sign never decides)"}
    if "?" in raw or "¿" in raw or (";" in raw and _GREEK.search(raw)):
        return {"parse": "unclear", "why": "a question"}
    found = {"yes": False, "no": False, "conditions": False}
    for form in (_fold(raw), _fold(raw, " ")):
        t = f" {form} "
        for p, kind in _phrases():                            # longest first, whatever its kind: "no problem" (yes) before "no",
            pat = f" {p} "                                    # "fully booked" (no) before "booked" (yes)
            if pat in t:
                found[kind] = True
                t = t.replace(pat, " ")
    if found["yes"] and found["no"]:
        return {"parse": "unclear", "why": "both a yes and a no"}
    if found["no"]:
        return {"parse": "no", "why": "a no"}
    if found["yes"] and found["conditions"]:
        return {"parse": "unclear", "why": "a yes with a condition"}
    if found["yes"]:
        return {"parse": "yes", "why": "a yes"}
    return {"parse": "unclear", "why": "neither a yes nor a no"}


# ── bundles: leg states → the bundle state + the customer's sentence (EU 212 bundles.md §3) ───────────────────────────────

LEG_STATES = ("pending", "held", "requested", "confirmed", "declined", "no_answer", "unreachable", "released", "cancelled", "booked")
FINAL_BAD = ("declined", "no_answer")
LEG_MOVES = {"pending": {"requested", "held", "confirmed", "unreachable", "released", "declined"},
             "held": {"booked", "released"},
             "requested": {"confirmed", "declined", "no_answer", "unreachable", "released"},
             "unreachable": {"requested", "unreachable", "released", "confirmed", "declined"},
             "confirmed": {"released", "cancelled"},
             "booked": {"cancelled"},
             "declined": set(), "no_answer": set(), "released": set(), "cancelled": set()}


def can_move(a: str, b: str) -> bool:
    return b in LEG_MOVES.get(a, set())


def bundle_view(legs: List[Dict[str, Any]], ctx: Dict[str, str], *, deadline_passed: bool = False,
                cancelled: bool = False) -> Tuple[str, str]:
    """legs: [{supplier, title, required, state}] · ctx: {operator, date, total, …} → (bundle state, the customer's sentence).
    An unreachable leg is NEVER 'unavailable': before the deadline it's 'trying again', at the deadline it 'couldn't be reached'."""
    if cancelled:
        return "cancelled", "Your booking is cancelled. Nothing more will be charged."
    req = [l for l in legs if l["required"]]
    for l in req:
        if l["state"] == "declined":
            return "failed", f"{l['supplier']} can't take your group on {ctx['date']}. Nothing has been charged. {ctx['operator']} will offer you another time."
        if l["state"] == "no_answer":
            return "failed", f"{l['supplier']} didn't confirm in time. Nothing has been charged. {ctx['operator']} is following up."
        if l["state"] == "unreachable" and deadline_passed:
            return "failed", (f"We couldn't reach {l['supplier']} in time. This isn't a no. Nothing has been charged. "
                              f"{ctx['operator']} is following up.")
    unreach = [l for l in legs if l["state"] == "unreachable"]
    if unreach:
        return "in_progress", f"We couldn't reach {unreach[0]['supplier']} just now. This isn't a no. We're trying again."
    waiting = [l for l in legs if l["state"] in ("pending", "requested")]
    if waiting:
        names = [l["supplier"] for l in waiting]
        who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        return "in_progress", f"Waiting for {who} to confirm. Nothing is charged until they do."
    opt_no = [l for l in legs if not l["required"] and l["state"] in FINAL_BAD]
    if opt_no:
        l = opt_no[0]
        return "in_progress", (f"Everything is confirmed except {l['title'].lower()}: {l['supplier']} can't take it. Your total would be "
                               f"{ctx['total_without']}. Confirm without it?")
    if all(l["state"] in ("confirmed", "booked") for l in req) and not any(l["state"] == "held" for l in legs):
        return "confirmed", "All confirmed. Here's your plan."
    return "in_progress", "Confirming with the suppliers. Nothing is charged until they do."


# ── one read-back over every leg; one approval; void if any leg's terms change (EU 212 bundles.md §1, AP1) ─────────────────

def read_back_sha256(operator_id: str, bundle_id: str, lines: List[str], payload_sha256: str) -> str:
    return sha256({"account": operator_id, "intent_id": bundle_id, "operation": "bookings.confirm", "lines": lines,
                   "payload_sha256": payload_sha256})


def decide_bundle(approval: Optional[Dict[str, Any]], current: Dict[str, Any], operator_id: str, now: str) -> Tuple[str, Optional[str]]:
    """approval: {bundle_id, read_back_sha256, payload_sha256, state, expires_at} · current: {bundle_id, lines, payload} → decision."""
    if not approval:
        return "approval_required", None
    if approval["state"] == "consumed":
        return "approval_consumed", None
    if now > approval["expires_at"]:
        return "approval_expired", None
    if approval["bundle_id"] != current["bundle_id"]:
        return "approval_void", "intent_changed"
    if sha256(current["payload"]) != approval["payload_sha256"]:
        return "approval_void", "payload_changed"
    if read_back_sha256(operator_id, current["bundle_id"], current["lines"], sha256(current["payload"])) != approval["read_back_sha256"]:
        return "approval_void", "read_back_changed"
    return "valid", None
