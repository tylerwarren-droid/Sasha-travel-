"""AgAPI v1 reference (Part 3). Small, dependency-free, for generating and checking conformance vectors.
NOT a product implementation. Each function mirrors a numbered rule in 01-core.md / 02-tools.md."""
import hashlib, json, re, unicodedata

MAX_INT = 2**53 - 1
KEY_RE = re.compile(r"^[a-z0-9_]+$")

class Refused(Exception):
    pass

def _check(v):
    if v is None or isinstance(v, bool): return
    if isinstance(v, int):
        if abs(v) > MAX_INT: raise Refused("integer out of range")
        return
    if isinstance(v, float): raise Refused("float")  # integral floats are normalised to int before _check (see _norm_num)
    if isinstance(v, str):
        if any(0xD800 <= ord(c) <= 0xDFFF for c in v): raise Refused("lone surrogate")
        return
    if isinstance(v, list):
        for x in v: _check(x)
        return
    if isinstance(v, dict):
        for k, x in v.items():
            if not isinstance(k, str) or not KEY_RE.match(k): raise Refused("key charset")
            _check(x)
        return
    raise Refused("type")

def _norm_num(v):
    """An integer-VALUED number is accepted and serialised as an integer (1.0 -> 1, -0.0 -> 0), because a
    JavaScript runtime cannot tell 1.0 from 1 after JSON.parse. A number with a fractional part is refused."""
    if isinstance(v, bool) or v is None: return v
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")): raise Refused("non-finite")
        if v.is_integer(): return int(v)
        return v
    if isinstance(v, list): return [_norm_num(x) for x in v]
    if isinstance(v, dict): return {k: _norm_num(x) for k, x in v.items()}
    return v

def canonical(v) -> str:
    """Part 1 §4.1: RFC 8785 restricted (integer-valued numbers only, ASCII [a-z0-9_] keys)."""
    v = _norm_num(v)
    _check(v)
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def sha256(v) -> str:
    return "sha256:" + hashlib.sha256(canonical(v).encode("utf-8")).hexdigest()

def read_back_sha256(account, intent_id, operation, lines, payload_sha256):
    return sha256({"account": account, "intent_id": intent_id, "operation": operation, "lines": lines, "payload_sha256": payload_sha256})

# ── AP6 explicit yes ────────────────────────────────────────────────────────────────────────
def _norm(s):
    s = unicodedata.normalize("NFC", s).lower()
    s = re.sub(r"[¡¿!?.,;:\"'“”‘’()—–]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def explicit_yes(said, lang):
    L = json.load(open(__file__.rsplit("/", 2)[0] + "/approval-language.json"))["languages"][lang]
    t = _norm(said or "")
    if not t: return False
    for neg in L["negations"] + L.get("questions_and_requests", []):
        if re.search(r"(?<!\w)" + re.escape(neg) + r"(?!\w)", t): return False
    rest = t
    changed = True
    while changed:
        changed = False
        for f in sorted(L["fillers"], key=len, reverse=True):
            if rest == f or rest.startswith(f + " "):
                rest = rest[len(f):].strip(); changed = True
    for a in sorted(L["affirmatives"], key=len, reverse=True):
        if rest == a or rest.startswith(a + " "): return True
    return False

# ── AP1–AP9 decision, in the normative order (03-conformance.md §3) ─────────────────────────
def decide(case):
    a, rb, cur, now = case["approval"], case["read_back"], case["current"], case["now"]
    if a is None or a["account"] != case["account"]: return ("approval_not_found", None)
    if a["device"]["channel"] not in ("link", "sdk", "sasha_voice", "sasha_chat") or a["approved_by"] != rb["presented_to"]:
        return ("approval_untrusted_origin", None)
    if a["device"]["channel"] == "sdk" and not a["device"].get("attestation"): return ("approval_untrusted_origin", None)
    if a["state"] == "consumed": return ("approval_consumed", None)
    if rb["presented_at"] is None or a["approved_turn_id"] == rb["presented_turn_id"] or not (a["approved_at"] > rb["presented_at"]):
        return ("approval_same_turn", None)
    if a["method"] == "voice" or (a["device"]["channel"] == "sasha_chat" and a.get("said") is not None):
        if not explicit_yes(a.get("said"), case.get("lang", "en")): return ("no_explicit_yes", None)
    if a["approved_at"] > rb["expires_at"] or now > a["expires_at"]: return ("approval_expired", None)
    if a["irreversible"] and case.get("acts_in_request", 1) > 1: return ("approval_void", "irreversible_batch")
    if cur["intent_id"] != a["intent_id"]: return ("approval_void", "intent_changed")
    if sha256(cur["payload"]) != a["payload_sha256"]: return ("approval_void", "payload_changed")
    if read_back_sha256(case["account"], cur["intent_id"], cur["operation"], cur["lines"], sha256(cur["payload"])) != a["read_back_sha256"]:
        return ("approval_void", "read_back_changed")
    return ("valid", None)

# ── §5.1 outage classification ──────────────────────────────────────────────────────────────
TRANSIENT = ["upstream_unreachable", "upstream_timeout", "upstream_rate_limited", "upstream_failed"]
def classify(sources):
    """sources: [{source, ok, code?, items}] → ('ok', coverage, n_items) | ('error', code)"""
    answered = [s["source"] for s in sources if s["ok"]]
    failed = [{"source": s["source"], "code": s["code"]} for s in sources if not s["ok"]]
    if not answered:
        codes = [f["code"] for f in failed]
        # all failed: the most informative transient code wins, in registry order; a refusal only if every source refused
        if all(c == "upstream_refused" for c in codes): return ("error", "upstream_refused")
        for c in TRANSIENT:
            if c in codes: return ("error", c)
    n = sum(len(s.get("items", [])) for s in sources if s["ok"])
    return ("ok", {"complete": not failed, "answered": answered, "unavailable": failed}, n)

# ── §3 untrusted wrapping ───────────────────────────────────────────────────────────────────
STRIP = re.compile("[\u0000-\u0008\u000b-\u001f\u007f-\u009f​-‍‪-‮⁦-⁩﻿]")
def wrap(text, source, retrieved_at, cap=2000):
    P = json.load(open(__file__.rsplit("/", 2)[0] + "/untrusted-patterns.json"))["patterns"]
    t = unicodedata.normalize("NFC", STRIP.sub("", text))
    out = {"text": t[:cap], "source": source, "retrieved_at": retrieved_at}
    if len(t) > cap: out["truncated"] = True
    if any(re.search(p, t, re.IGNORECASE) for p in P): out["instruction_like"] = True
    return out

# ── Part 4: evidence body hash and webhook signatures ──────────────────────────────────────
import hmac as _hmac
def evidence_body_sha256(evidence):
    """Part 2 §4: sha256(canonical(the evidence object without body_sha256))."""
    return sha256({k: v for k, v in evidence.items() if k != "body_sha256"})

def webhook_signature(secret: str, t: int, raw_body: str) -> str:
    """Part 4 §4: header AgAPI-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(secret, f"{t}.{raw_body}")>."""
    mac = _hmac.new(secret.encode("utf-8"), f"{t}.{raw_body}".encode("utf-8"), hashlib.sha256).hexdigest()
    return f"t={t},v1={mac}"
