"""S-75 step 1 · WHAT COUNTS AS A TYPED "YES" — one pattern for the web chat and WhatsApp.

The web chat's copy is frontend/lib/chat-booking-bus.ts (`YES`); tests/test_s75_server_rules.py fails unless the two
pattern strings are identical. A yes only ever binds to ONE pending confirmation (the newest, within the approval
window) — this module says whether the words were a yes, never what they approve.
"""
from __future__ import annotations

import re

PATTERN = r"^\s*(yes|yeah|yep|go ahead|ok(ay)?|s[ií]|vale|claro|sim|oui|ja|confirm(ed)?)(?!\w)"
YES = re.compile(PATTERN, re.I)


def is_yes(text: str) -> bool:
    return bool(YES.match(text or ""))


#: S-75 step 2 · how a yes may arrive. A button (the app's, or WhatsApp's quick-reply) needs no words; anything spoken or
#: typed — in the chat or on WhatsApp — must carry the words said, which are stored with the approval
HOWS = ("button", "voice", "chat", "whatsapp_button", "whatsapp_text")
_SAID_NEEDED = ("voice", "chat", "whatsapp_text")
APPROVAL_VOID = "an approval is by button (in the app or on WhatsApp), or spoken or typed with the words said"


def approval_ok(a) -> bool:
    if not isinstance(a, dict) or a.get("how") not in HOWS:
        return False
    return a["how"] not in _SAID_NEEDED or bool(str(a.get("said") or "").strip())


__all__ = ["PATTERN", "YES", "is_yes", "HOWS", "APPROVAL_VOID", "approval_ok"]
