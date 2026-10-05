"""S-68 / Sasha 64 · GOOGLE MAPS CONTENT IS NEVER STORED — the safe reading of the Maps terms until counsel answers
(docs/sasha/S-68-step1-places-terms.md, "Counsel questions").

The founder's rule (Sasha 64):
  A · store only the `place_id` (the terms allow it) and what we read on the venue's OWN site or what the venue itself
      said. A listing's name, address, phone, website, hours are re-read from Google, transiently, when needed;
  B · a call never SPEAKS listing text (the brief's spoken parts are the guest's words — tests hold that), the venue's
      own number is preferred, a listing number is used only to DIAL, and which source was used is recorded;
  C · (style tags, S-68 step 9) from the venue's own site only.

How a call on a listing number works, end to end:
  · the read-back never shows the digits: "I'll phone Calma on the number its Google Maps listing gives";
  · the stored brief holds no number — `number_ref: {source: "places", place_id, sha256}` — and `dialled_number` is
    "sha256:<hex>", so the call log, the one-call-at-a-time check and a venue's stop still match on it;
  · at the dial the listing is re-read, its number hashed, and the call is placed ONLY if it is the number the guest
    approved. A changed or missing number is not dialled, and says why.
Reversible: every place this rule touches calls this module; reverting it restores the old storage.
"""
from __future__ import annotations

import copy
import hashlib
import re
from datetime import datetime
from typing import Any, Dict, Mapping, Optional

from . import venue_read as V

LISTING_LABEL = "their Google Maps listing"
WITHHELD = "re-read from the Google Maps listing when needed; never stored"
NUMBER_SHOWN = " on the number its Google Maps listing gives"
NUMBER_HIDDEN = "⟨the listing's number⟩"


class ListingUnavailable(Exception):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


def number_key(number: str) -> str:
    """What is STORED for a listing number: its hash, never its digits."""
    return "sha256:" + hashlib.sha256(number.encode()).hexdigest()


def same_number(number: Optional[str], stored: Optional[str]) -> bool:
    """A number against a stored `dialled_number` — the digits (the venue's own site) or a listing number's hash."""
    if not number or not stored:
        return False
    return number_key(number) == stored if stored.startswith("sha256:") else number == stored


def place_id_of(read: Mapping[str, Any]) -> Optional[str]:
    return (read.get("listing") or {}).get("place_id")


# ── A · the venue read: what is stored, and what is re-read ─────────────────────────────────────────────────────

def storable_read(read: Mapping[str, Any]) -> dict:
    """The read as it may be STORED: every listing fact keeps its kind, its place and its index (a rung names a fact by
    index) — its value, words and label do not. The listing keeps only its place_id."""
    out = copy.deepcopy(dict(read))
    pid = place_id_of(read)
    facts = []
    for f in out.get("facts") or []:
        if f.get("source_kind") == "places":
            f = {"kind": f["kind"], "value": None, "source_kind": "places", "source_url": f.get("source_url"),
                 "source_label": LISTING_LABEL, "snippet": "", "fetched_at": f.get("fetched_at"), "sha256": f.get("sha256"),
                 "detail": {"place_id": pid, "withheld": WITHHELD}}
        facts.append(f)
    out["facts"] = facts
    out["listing"] = {"place_id": pid} if pid else None
    out["sources"] = [({k: s[k] for k in ("url", "result", "sha256", "fetched_at") if k in s}
                       if str(s.get("url", "")).startswith("https://places.googleapis.com") else s)
                      for s in out.get("sources") or []]
    return out


async def hydrate_read(http, read: Mapping[str, Any], now: datetime) -> dict:
    """The stored read with its listing facts RE-READ from Google — for this response or this call only, never stored.
    A fact the listing no longer gives stays None (the ladder skips it), and `listing_reread` says what happened."""
    out = copy.deepcopy(dict(read))
    withheld = [i for i, f in enumerate(out.get("facts") or []) if f.get("source_kind") == "places" and f.get("value") is None]
    pid = place_id_of(read)
    if not withheld or not pid:
        return out
    key = V.places_key()
    if not key:
        out["listing_reread"] = "not re-read — GOOGLE_PLACES_API_KEY is not set"
        return out
    facts, sources, listing, _c, _w = await V.read_place_id(http, key, pid, now)
    if listing is None:
        out["listing_reread"] = f"not re-read — {(sources or [{}])[0].get('result', 'no answer')}"
        return out
    fresh = {}
    for f in facts:
        fresh.setdefault(f.kind, f)
    for i in withheld:
        f = fresh.get(out["facts"][i]["kind"])
        if f is not None:
            out["facts"][i] = {**out["facts"][i], "value": f.value, "snippet": f.snippet, "fetched_at": f.fetched_at,
                               "sha256": f.sha256, "detail": {**f.detail, "place_id": pid, "transient": True}}
    out["listing"] = {**listing, "attribution": "Google Maps"}
    out["listing_reread"] = f"re-read at {now.isoformat()}"
    return out


# ── B · a call on a listing number ──────────────────────────────────────────────────────────────────────────────

def seal_call(built: dict, venue) -> dict:
    """The built call as it may be STORED and shown. The venue's own number is kept as it is, with its source kind;
    a listing number leaves no digits in the brief or the read-back, only its hash and its place."""
    from . import calls as C
    built = copy.deepcopy(built)
    brief = built["brief"]
    kind = getattr(venue, "number_kind", None) or ("test_line" if venue.number is None else "site")
    brief["number_source_kind"] = kind
    if kind == "places":
        number = brief["number"]
        if not number:   # Sasha 147 · a listing with no number: refused in words (a None here crashed a cancel, CR 20)
            raise ListingUnavailable("venue_number_missing", "there is no number on record for this venue, so nothing was dialled")
        lines = [ln.replace(f", {number} — the number on {LISTING_LABEL}.", NUMBER_SHOWN + ".")
                   .replace(f", {number}.", NUMBER_SHOWN + ".").replace(number, NUMBER_HIDDEN) for ln in built["read_back_lines"]]
        brief["number"] = None
        brief["number_ref"] = {"source": "places", "place_id": venue.place_id, "sha256": number_key(number)[7:]}
        brief["number_source"] = LISTING_LABEL
        for k in ("task", "first_sentence", "recap", "check_sentence"):
            if number in str(brief.get(k) or ""):   # never: the spoken parts carry the guest's number, not the venue's
                raise ListingUnavailable("listing_text_spoken", f"the call's {k} would speak the listing's number")
        built["read_back_lines"] = lines
        built["read_back_sha256"] = C._sha256hex("\n".join(lines))
        built["dialled_number"] = number_key(number)
    else:
        built["dialled_number"] = brief["number"]
    built["brief_sha256"] = C._sha256hex(C._canonical(brief))
    return built


async def listing_number(http, number_ref: Mapping[str, Any], now: datetime) -> str:
    """Re-read the listing's number for the dial. ⛔ Only the number the guest approved (its hash) is ever returned."""
    pid = number_ref.get("place_id")
    key = V.places_key()
    if not pid or not key:
        raise ListingUnavailable("listing_unreadable", "the listing's number could not be re-read (no place id or no Places key), so nothing was dialled")
    facts, sources, listing, _c, _w = await V.read_place_id(http, key, pid, now)
    phone = next((f.value for f in facts if f.kind == "phone"), None)
    if listing is None or phone is None:
        raise ListingUnavailable("listing_number_gone", "the Google Maps listing no longer gives a number, so nothing was dialled")
    if number_key(phone)[7:] != number_ref.get("sha256"):
        raise ListingUnavailable("listing_number_changed", "the listing's number has changed since you approved the call, so "
                                                           "nothing was dialled — prepare it again to approve the new one")
    return phone


async def dialable(http, brief: Mapping[str, Any], now: datetime) -> dict:
    """The brief Bland is sent: the stored one, with a listing number re-read and checked. Never stored."""
    if brief.get("number") or not brief.get("number_ref"):
        return dict(brief)
    return {**brief, "number": await listing_number(http, brief["number_ref"], now)}


_DIALLED_KEYS = ("to", "phone_number", "short_to")


def scrub_bland(obj: Any, brief: Mapping[str, Any]) -> Any:
    """Bland's answers and call details, as stored: a listing number's digits are not kept — at ANY depth.
    ⚠ 1 Oct 2026 (call a1c85ca6): Bland echoes the dialled number inside `variables` (`to`, `phone_number`, and
    `short_to` without its country code); only the top level was scrubbed, so the digits were stored. Every string
    holding the number, in any of its forms, is now replaced."""
    if not (brief or {}).get("number_ref") or not isinstance(obj, dict):
        return obj
    forms = set()
    for d in (obj, obj.get("variables") if isinstance(obj.get("variables"), dict) else {}):
        for k in ("to", "phone_number"):
            digits = re.sub(r"\D", "", str(d.get(k) or ""))
            if len(digits) >= 7:
                forms |= {f"+{digits}", digits, digits[-10:], digits[-9:]}
    forms = sorted((f for f in forms if len(f.lstrip("+")) >= 9), key=len, reverse=True)

    def walk(v: Any, key: Optional[str] = None) -> Any:
        if isinstance(v, dict):
            return {k: walk(x, k) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, str):
            if key in _DIALLED_KEYS:
                return NUMBER_HIDDEN
            for f in forms:
                v = v.replace(f, NUMBER_HIDDEN)
        return v
    return walk(obj)


__all__ = ["storable_read", "hydrate_read", "seal_call", "dialable", "listing_number", "number_key", "same_number",
           "scrub_bland", "ListingUnavailable", "LISTING_LABEL"]
