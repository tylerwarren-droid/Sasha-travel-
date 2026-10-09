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
def _norm(s, apostrophe=""):
    """apostrophe="" deletes it ("don't" -> "dont", 1.0.1); apostrophe=" " splits it ("what's" -> "what s", 1.1)."""
    s = unicodedata.normalize("NFC", s).lower()
    s = re.sub(r"['‘’]", apostrophe, s)
    s = re.sub(r"[¡¿!?.,;:\"“”()—–]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def explicit_yes(said, lang, act_kind=None):
    L = json.load(open(__file__.rsplit("/", 2)[0] + "/approval-language.json"))["languages"][lang]
    exempt = set()
    if act_kind:  # v1.1 (CR 61): a cancellation's own yes may say "cancel"
        A = json.load(open(__file__.rsplit("/", 2)[0] + "/approval-language-acts.json"))["acts"]
        exempt = set(A.get(act_kind, {}).get(lang, {}).get("exempt_negations", []))
    t = _norm(said or "")
    if not t: return False
    # 1.1: a veto matches in EITHER form, so "don't" (dont) and "what's" (what s) both veto; affirmatives use t
    forms = (t, _norm(said or "", " "))
    for neg in [n for n in L["negations"] if n not in exempt] + L.get("questions_and_requests", []):
        if any(re.search(r"(?<!\w)" + re.escape(neg) + r"(?!\w)", f) for f in forms): return False
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


# ── 1.2 the Keep (CR 63): an independent EU reference for tiers, masks, the use gate and the use line ──────
# Written from the 1.2 rules (schemas/keep/keep.schema.json), not copied from CR's keep.py; generate.py checks it
# against CR's frozen vectors/keep.json. Normalisation and checksums are CR's (covered by keep.json's own run).
KEEP_TIER = {"preference": "free", "loyalty": "free", "home_address": "free",
             "passport": "yes", "national_id": "yes", "trusted_traveller": "yes", "visa_residence": "yes",
             "insurance_policy": "yes", "health_card": "yes",
             "booking_reference": "read_back", "door_code": "read_back", "wifi": "read_back", "esim": "read_back"}
_PROGRAM = {"global_entry": "Global Entry", "tsa_precheck": "TSA PreCheck", "nexus": "NEXUS", "sentri": "SENTRI",
            "dni": "DNI", "nie": "NIE", "other": "ID"}

def keep_tail(secret):
    """'••••' + at most a third of the value, never more than 4 characters."""
    n = min(4, len(secret) // 3)
    return "••••" + (secret[-n:] if n else "")

def keep_mask(kind, v):
    t = keep_tail
    if kind == "passport":          return f"Passport {v['country']} {t(v['number'])}"
    if kind == "national_id":       return f"{_PROGRAM[v['kind']]} ({v['country']}) {t(v['number'])}"
    if kind == "trusted_traveller": return f"{_PROGRAM[v['program']]} {t(v['number'])}"
    if kind == "visa_residence":    return f"Visa / residence {v['country']} {t(v['number'])}"
    if kind == "insurance_policy":  return f"{v['insurer']} policy {t(v['number'])}"
    if kind == "health_card":       return f"{v['issuer']} health card {t(v['number'])}"
    if kind == "loyalty":           return f"{v['program']} {t(v['number'])}"
    if kind == "booking_reference": return f"{v['provider']} booking {t(v['reference'])}"
    if kind == "home_address":      return f"Home address · {v['country']}"
    if kind == "preference":        return f"Preference: {v['topic']}"
    if kind == "door_code":         return f"Door code · {v['place']}"
    if kind == "wifi":              return f"Wi-Fi · {v['network']}"
    if kind == "esim":              return f"eSIM · {v['provider']}"
    raise Refused("unknown_type")

def keep_use_refusal(kind, purpose):
    """None if allowed; else the refusal rule. Any purpose other than fill/show is never_raw, whatever it is called."""
    p = (purpose or "").strip().lower()
    if p not in ("fill", "show"): return "never_raw"
    tier = KEEP_TIER[kind]
    if tier == "read_back" and p == "fill": return "read_back_only"
    if tier != "read_back" and p == "show": return "fill_only"
    return None

def keep_use_line(masked, purpose):
    return f"I'll use your saved {masked} for this booking." if purpose == "fill" else f"I'll show your saved {masked} on your phone."
