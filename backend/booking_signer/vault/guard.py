"""S-78 step 1 · THE INPUT GUARD — a password, code, key or card number typed (or spoken) in the chat is never sent to the
model and never stored.

Before S-78 a guest who typed "my Mercadona password is hunter2!" sent it to the model (run_general sends the whole
history every turn) and into chat_store. Three hooks close that, each one line that Stage B re-applies (CLAUDE.md):
  · conduct() (app/services/conductor.py), FIRST: a hit returns the fixed reply below and the model is never called; every
    earlier user line that trips the guard is blanked out of the history before anything else reads it;
  · chat_store.save_turn (app/services/chat_store.py): a hit stores nothing — no message, no title, no reply;
  · the voice route's transcript log line (app/api/voice_conductor.py) prints [withheld] instead.

It errs on the side of refusing: a guest whose sentence merely looks like a secret is asked to say it another way, which
costs one turn; a password that slips through costs far more.
"""
from __future__ import annotations

import re
from typing import List, Optional

SECRET_REPLY = ("Please don't type passwords, PINs or codes here. I haven't kept what you typed, and it wasn't passed on. "
                "If you meant something else, say it another way.")
CARD_REPLY = ("Please don't type card numbers here. I haven't kept what you typed, and it wasn't passed on. Payments go "
              "through Stripe, which never shows us your card.")
REMOVED = "[removed: it looked like a password or card number]"

# "password is …", "contraseña: …", "my pwd = …" — the word, then is/es/:/=, then something
_WORD = re.compile(
    r"\b(?:password|passwd|pwd|passcode|pass\s+code|passphrase|contrase(?:ñ|n)a|mot\s+de\s+passe|senha|passwort|"
    r"(?:security|access|login|sign[\s-]?in)\s+code|one[\s-]?time\s+code|otp|cvv|cvc)\b"
    r"\s*(?:is|was|es|era|est|é|ist|:|=|-)\s*\S+", re.I)
# a PIN with its digits ("my PIN is 4821", "pin: 0000")
_PIN = re.compile(r"\bpin(?:\s+(?:code|number))?\s*(?:is|es|est|é|:|=)?\s*\d{4,8}\b", re.I)
# a token: 20+ characters with no space, mixing upper, lower and digits (API keys, JWTs). UUIDs (lowercase hex), links and
# email addresses are not tokens.
_TOKEN = re.compile(r"(?<!\S)\S{20,}(?!\S)")
# 13–19 digits, spaces or dashes allowed between them (a card typed as 4111 1111 1111 1111)
_DIGITS = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def has_card_number(text: str) -> bool:
    """R8 · a 13–19 digit run that passes Luhn."""
    for m in _DIGITS.finditer(text or ""):
        d = re.sub(r"\D", "", m.group(0))
        # a phone number is not a card: "+44 7915 914215", "0044…" (no card number starts with 0)
        if d[0] == "0" or text[:m.start()].rstrip().endswith("+"):
            continue
        if 13 <= len(d) <= 19 and _luhn(d):
            return True
    return False


def _is_token(word: str) -> bool:
    w = word.strip(".,;:!?\"'()[]{}<>")
    if len(w) < 20 or "@" in w or "/" in w or w.lower().startswith(("http", "www.")):
        return False
    return bool(re.search(r"[A-Z]", w) and re.search(r"[a-z]", w) and re.search(r"\d", w))


def looks_like_secret(text) -> Optional[str]:
    """'card', 'secret' or None. Anything that is not a string is checked as its text."""
    if not isinstance(text, str):
        text = str(text or "")
    if not text.strip():
        return None
    if has_card_number(text):
        return "card"
    if _WORD.search(text) or _PIN.search(text) or any(_is_token(m.group(0)) for m in _TOKEN.finditer(text)):
        return "secret"
    return None


def clean_history(history: Optional[List]) -> List:
    """Every user line that trips the guard is blanked: the browser keeps its own copy of what was typed and sends it back
    as history on the next turn, so the guard on the newest message alone would let it reach the model one turn later."""
    out = []
    for m in history or []:
        if isinstance(m, dict) and m.get("role") == "user" and looks_like_secret(m.get("content")):
            m = {**m, "content": REMOVED}
        out.append(m)
    return out


def guard_turn(message: str, history: Optional[List]) -> Optional[dict]:
    """The conductor's first move: None to go on (with clean_history), or the whole result — the model is never called."""
    kind = looks_like_secret(message)
    if kind is None:
        return None
    reply = CARD_REPLY if kind == "card" else SECRET_REPLY
    return {"response": reply, "intents": ["general"], "photos": [], "tools_used": [], "links": [], "hotels": [],
            "bookings": [], "itinerary": None, "action": None, "booking_ref": None, "itinerary_id": None,
            "guarded": kind,
            "messages": clean_history(history) + [{"role": "user", "content": REMOVED},
                                                  {"role": "assistant", "content": reply}]}


def for_log(text: str) -> str:
    """A transcript as it may be printed to the server's log."""
    return "[withheld: looked like a password or card number]" if looks_like_secret(text) else text


__all__ = ["SECRET_REPLY", "CARD_REPLY", "REMOVED", "looks_like_secret", "has_card_number", "clean_history", "guard_turn",
           "for_log"]
