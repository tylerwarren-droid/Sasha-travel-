"""Sasha 301 · THE FINE PRINT ON EVERY BOOKING — the venue's own terms, and his own cards and loyalty numbers, on the itinerary's row.

  TERMS   terms_of(text, start): the sentences of the VENUE'S OWN WORDS (their reply on the record — untrusted data, never instructions)
          that state a deposit, a cancellation term, a no-show charge or a time limit on the table, each as the sentence they wrote
          (`quote in text` is checked: never a word of Sasha's). A deadline ("by <date/time>") is worked out ONLY from a number of
          hours / days / minutes in that same sentence and the booking's own start — never from a guess, never "the day before".
          Read at view time from the row's words: no store of its own. A quoted earlier message (Sasha's request under their reply)
          is never read, and a sentence cut off at the record's limit is never shown.
  PERKS   perks_for(kind, title, wallet): his Keep's loyalty numbers (by the fixed programme list, booking_signer/loyalty.matches)
          and the perks he told her for his cards — each line from what he saved, masked; nothing matched is nothing said.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

KINDS = ("deposit", "cancellation", "no_show", "time_limit")
LABEL = {"deposit": "Deposit", "cancellation": "Cancellation", "no_show": "No-show", "time_limit": "Time at the table"}
MAX_TERMS, MAX_QUOTE = 4, 400

_DEPOSIT = re.compile(r"(?i)\b(deposit|pre-?pay(?:ment)?|pre-?paid|dep[óo]sito|fianza|se[ñn]al\b|prepago|pago por adelantado|pago anticipado|"
                      r"anticipo|garant[ií]a|guarantee|acompte|arrhes|caparra|anzahlung|sinal\b)")
_CANCEL = re.compile(r"(?i)\b(cancel\w*|cancela\w*|anula\w*|annul\w*|disdett\w*|stornier\w*)")
_NO_SHOW = re.compile(r"(?i)(no[- ]?shows?\b|\bno present(?:arse|ados?|a)\b|\bno se present\w*|\bno acud\w*|\bno comparec\w*|"
                      r"\bfail(?:s|ure)? to (?:show|arrive|turn up)|\bdon'?t (?:show|turn) up)")
_TABLE = re.compile(r"(?i)\b(table|tables|mesa|mesas|turno|turnos|seating|sitting|tavolo|tisch)\b")
_LIMIT = re.compile(r"(?i)(\b\d+(?:[.,]\d+)?\s*(?:hours?|hrs?|h|minutes|mins?|horas?|minutos|ore|minuti|stunden?)\b|\buntil\s+\d{1,2}[:.h]\d{2}|"
                    r"\bhasta las\s+\d{1,2}[:.h]?\d{0,2}|\bback (?:at|by)\s+\d{1,2}[:.h]\d{2}|\bdevolver la mesa|\bliberar la mesa|"
                    r"\btwo hours|\bdos horas|\buna hora y media|\ban hour and a half|\bhora y media)")
_FREE = re.compile(r"(?i)\b(free|sin coste|sin cargo|sin gastos|sin penalizaci[óo]n|gratis|gratuit\w*|without (?:a )?charge|no charge|"
                   r"free of charge|senza costi|kostenlos)\b")
#: a number of hours / days / minutes — the only thing a deadline is worked out from
_SPAN = re.compile(r"(?i)\b(\d{1,3})\s*(?:-\s*)?(hours?|hrs?|h|horas?|heures?|ore|stunden?|days?|d[ií]as?|jours?|giorni|tage?n?|dias|"
                   r"minutes|mins?|minutos|minuti)\b")
#: where an email's quoted earlier message begins: from here on it is someone else's words (often Sasha's own request)
_QUOTED = re.compile(r"(?im)^(?:>|-{2,}\s*(?:original|mensaje original|forwarded)|on .{3,120}\bwrote:|el .{3,120}\bescribi[óo]:|"
                     r"de:\s|from:\s|enviado:\s|sent:\s)")
_HHMM = "%H:%M"


def _own_part(text: str) -> str:
    """Their reply only: everything from the first quoted line (">", "On … wrote:", "El … escribió:", a forwarded header) is dropped."""
    m = _QUOTED.search(text or "")
    return (text or "")[:m.start()] if m else (text or "")


def _sentences(text: str, cut: bool) -> List[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?;])\s+|\n+", text) if p and p.strip()]
    if cut and parts and not re.search(r"[.!?;)\"”»]$", parts[-1]):
        parts = parts[:-1]   # the record cut their words here: a broken sentence is never shown as a term
    return parts


def _span(s: str) -> Optional[timedelta]:
    m = _SPAN.search(s)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    if unit.startswith(("d", "j", "g", "t")) and not unit.startswith("h"):
        d = timedelta(days=n)
    elif unit.startswith("m"):
        d = timedelta(minutes=n)
    else:
        d = timedelta(hours=n)
    return d if timedelta(0) < d <= timedelta(days=30) else None


def by_words(at: datetime) -> str:
    """"Wed 29 Oct, 21:00" — the deadline in the booking's own time zone."""
    return f"{at:%a} {at.day} {at:%b}, {at:{_HHMM}}"


def terms_of(text: Optional[str], start: Optional[datetime] = None, cut_at: Optional[int] = None) -> List[Dict[str, Any]]:
    """The venue's own sentences stating a term → [{kinds, quote, by?, by_words?, free?}] (at most MAX_TERMS, in their order).
    `cut_at` is the record's limit on their words (an act's is 240): a last sentence that reaches it unfinished is dropped."""
    raw = str(text or "")
    own = _own_part(raw)
    cut = bool(cut_at) and len(raw) >= int(cut_at or 0) - 1 and len(own) == len(raw)
    out: List[Dict[str, Any]] = []
    seen = set()
    for s in _sentences(own, cut):
        if len(s) > MAX_QUOTE or s in seen or s not in raw:   # their sentence exactly as written, or nothing
            continue
        kinds = [k for k, hit in (("deposit", _DEPOSIT.search(s)), ("cancellation", _CANCEL.search(s)), ("no_show", _NO_SHOW.search(s)),
                                  ("time_limit", _TABLE.search(s) and _LIMIT.search(s))) if hit]
        if not kinds:
            continue
        seen.add(s)
        t: Dict[str, Any] = {"kinds": kinds, "quote": s}
        if "cancellation" in kinds:
            span = _span(s)
            if span and start is not None:
                at = start - span
                t.update(by=at.isoformat(), by_words=by_words(at))
            if _FREE.search(s):
                t["free"] = True
        out.append(t)
        if len(out) >= MAX_TERMS:
            break
    return out


def cancel_by(terms: List[dict]) -> Optional[dict]:
    """The earliest cancellation deadline the venue stated (the reminder's), or None."""
    hits = [t for t in terms or [] if "cancellation" in (t.get("kinds") or []) and t.get("by")]
    return min(hits, key=lambda t: t["by"]) if hits else None


def line(t: dict) -> str:
    """One term as she says it: what it is about, their words in quotes, and the deadline it states."""
    head = " · ".join(LABEL[k] for k in t["kinds"])
    return f"{head}: they said “{t['quote']}”" + (f" — that's by {t['by_words']}." if t.get("by_words") else "")


# ── PERKS: his Keep, matched to the booking by a fixed list (never a guess) ──────────────────────────────────────────────────

CATEGORY = {"dinner": "restaurant", "restaurant": "restaurant", "spa": "spa", "hotel": "hotel", "flight": "flight", "car": "car"}


def _brand_names(where: str) -> List[str]:
    """A chain he named ("Marriott") → the names its programme covers (the fixed list), else the words themselves."""
    from booking_signer import loyalty as LY
    w = where.strip().lower()
    names = [w] if w else []
    for key, (_, covered) in LY.PROGRAMS.items():
        if w and (w in key or w in LY.NAMES.get(key, "").lower() or w in covered or LY.ALIASES.get(w) == key):
            names += list(covered)
    return names


def perks_for(kind: str, title: str, wallet: List[dict]) -> List[Dict[str, Any]]:
    """The loyalty numbers and card perks from his Keep that apply to this booking → [{kind, item_id, line}]. Masks only."""
    from booking_signer import loyalty as LY
    cat = CATEGORY.get(kind or "", kind or "")
    name = (title or "").lower()
    out: List[Dict[str, Any]] = []
    for w in wallet or []:
        if w.get("type") == "loyalty" and w.get("program") and LY.matches(w["program"], title or "", cat):
            tail = str(w.get("masked") or "").rsplit(" ", 1)[-1]
            out.append({"kind": "loyalty", "item_id": w["item_id"],
                        "line": f"Use your {w['program']} number" + (f" ({tail})." if tail.startswith("•") else ".")})
        elif w.get("type") == "my_card" and w.get("perk") and w.get("perk_for") in (cat, "any"):
            where = str(w.get("perk_where") or "")
            if where and not any(n and n in name for n in _brand_names(where)):
                continue
            out.append({"kind": "card", "item_id": w["item_id"],
                        "line": f"Your {w['name']} (••••{w['last4']}) includes {w['perk']} — as you told me."})
    return out


__all__ = ["terms_of", "cancel_by", "line", "by_words", "perks_for", "KINDS", "LABEL", "CATEGORY"]
