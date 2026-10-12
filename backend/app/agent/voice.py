"""Sasha 249 · HER VOICE, IN ONE PLACE (EU 246's demo path §2) — the persona rules every surface's prompt carries, the sentences the
tools hand her word for word, and the transcript check the deploy gate runs. Nothing else in the code words these.

  RULES        → appended to /s2's system text (WhatsApp shares it) and /next's under S1 parity (parity off: /next unchanged)
  ASK_BOOK     → the one booking question, when a venue has a form AND another way (agapi.venue_truth.ASK_FILL is this)
  CHOICES      → its two answers, as buttons / a list
  done_form()  → the confirmation once a prefilled form is on their screen
  SENT         → the confirmation once a request has gone to the venue
  faults()     → a transcript's breaches: a channel named, or a second question for the same detail
"""
from __future__ import annotations

import re
from typing import Iterable, List, Sequence, Tuple

ASK_BOOK = "I'll book it. Want a prefilled form you just confirm, or shall I handle it and let you know?"
CHOICES = ({"title": "Prefilled form", "route": "page"}, {"title": "Handle it", "route": None})
DONE_FORM = "Done — it's on your screen, tap to confirm."
DONE_FORM_WA = "Done — it's below, tap to confirm."   # WhatsApp: the card arrives as the next message, not "on your screen"
SENT = "Sent. I'll tell you when they reply."

# the channels she never names (EU 246 §2 rule 1), and the booking platforms the code knows by name
CHANNEL_NAMES = ("WhatsApp", "Instagram", "Booksy", "SevenRooms", "CoverManager", "FareHarbor", "Restaurantic", "TheFork", "OpenTable",
                 "Resy", "Fresha", "Treatwell", "Rover", "Bookeo", "Checkfront", "Mindbody", "Tock")
_CHANNEL = re.compile(r"\b(" + "|".join(CHANNEL_NAMES) + r")\b|\bweb form\b|\bAPI\b|\brungs?\b|\bthe ladder\b", re.I)
_API_CASE = re.compile(r"\bAPI\b")   # "api" only as the acronym (never "rapid", never a lowercase URL path)

# the details a booking asks for: one question each, ever
DETAILS = {
    "name": re.compile(r"\b(what name|which name|whose name|under what name|name (should|shall) (it|i|we) (be|put)|your (full )?name)\b", re.I),
    "time": re.compile(r"\b(what|which) time\b", re.I),
    "day": re.compile(r"\b(what|which) (day|date)\b", re.I),
    "party": re.compile(r"\bhow many (people|of you|guests|travell?ers)\b", re.I),
    "email": re.compile(r"\b(email address|your email|which email)\b", re.I),
    "phone": re.compile(r"\b(phone|mobile) number\b", re.I),
    "nationality": re.compile(r"\b(nationality|which passport|what passport)\b", re.I),
}

RULES = f"""

## Her voice (every surface)

- Never name how a booking travels: no WhatsApp, Instagram, booking-platform names, "web form", "API", "rung" or "ladder". Say
  what you'll do for them ("I'll send them the request"), never the pipe it goes down.
- When a place can take a prefilled form AND you could handle it for them, ask exactly this, word for word: "{ASK_BOOK}"
- Ask for every missing detail once, together, up front ("For two on Thursday at 9 — what name should it be under?"). Never ask
  again for something you have — from their Keep, what you remember, or earlier in this chat.
- Confirm short: one or two sentences, then the card. "{DONE_FORM}" / "{SENT}"
"""


def done_form(surface: str = "s2") -> str:
    return DONE_FORM_WA if surface == "wa" else DONE_FORM


def channel_words(text: str) -> List[str]:
    """The channel words in one thing she says (case-insensitive, except "API", which is only the acronym)."""
    found = []
    for m in _CHANNEL.finditer(text or ""):
        w = m.group(0)
        if w.lower() == "api" and not _API_CASE.fullmatch(w):
            continue
        found.append(w)
    return found


def _questions(text: str) -> List[str]:
    return [q.strip() for q in re.findall(r"[^.?!\n]*\?", text or "")]


def faults(transcript: Iterable[Tuple[str, str]]) -> List[str]:
    """A transcript of (role, text) turns → what breaks her voice: a channel named in anything she says, or a second question (in a
    later turn of hers) for a detail she has already asked for."""
    out: List[str] = []
    asked: dict = {}
    for i, (role, text) in enumerate(transcript):
        if role != "assistant":
            continue
        for w in channel_words(text):
            out.append(f"turn {i}: names the channel {w!r}")
        for q in _questions(text):
            for d, rx in DETAILS.items():
                if rx.search(q):
                    if d in asked and asked[d] != i:
                        out.append(f"turn {i}: asks for the {d} again (first asked in turn {asked[d]})")
                    asked.setdefault(d, i)
    return out


def check(lines: Sequence[str]) -> List[str]:
    """faults() for a single run of her lines (each one a turn of hers)."""
    return faults(("assistant", x) for x in lines)


__all__ = ["ASK_BOOK", "CHOICES", "DONE_FORM", "DONE_FORM_WA", "SENT", "CHANNEL_NAMES", "DETAILS", "RULES", "done_form", "channel_words",
           "faults", "check"]
