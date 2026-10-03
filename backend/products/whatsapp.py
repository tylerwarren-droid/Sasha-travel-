"""CR 1 · one sandbox WhatsApp number, three products, by MODE.

"campus…" enters CampusMe; "relocation…" (or "relocate", "EX-01") enters relocation; "exit" / "sasha" / "back" returns to
Sasha. While a mode is on, every message goes to that product — Sasha's booking path doesn't see it. Not in a mode and no
keyword: returns False at once and Sasha's turn runs exactly as before.

⚠ DEMO DEVICE ONLY. In production each product needs its OWN WhatsApp number: Meta ties one verified business display
name to one number, and a number's display name is what the user sees and opts into (docs/products/CR-1-spec.md §1).
The mode lives in the guest's `pending` ({"kind": "product", "product": …}), so it needs no new column; a mode left idle
for MODE_IDLE ends by itself, and the next message is Sasha's.

Called from booking_signer/guest_whatsapp.turn() — one guarded block marked "CR 1 products" — AFTER STOP, START and the
reminder words (so those always work) and BEFORE the media-only refusal (relocation reads documents sent as photos).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Optional

log = logging.getLogger("products.whatsapp")
MODE_IDLE = timedelta(hours=6)

_CAMPUS = re.compile(r"^\s*(campus\s*me|campusme|campus)\b", re.I)
_RELOC = re.compile(r"^\s*(relocation|relocate|relocating|reloc|ex-?01|residencia)\b", re.I)
_EXIT = re.compile(r"^\s*(exit|sasha|back|back to sasha|quit|salir)\s*[.!]?\s*$", re.I)

LEFT = "Back to Sasha — tell me what to book. (Say CAMPUS or RELOCATION to switch again.)"


async def product_turn(ch: dict, frm: str, p: Dict[str, str], st: dict, out, now, early=None) -> bool:
    """True: a product handled this message (the caller stores the state and delivers `out`). False: Sasha's turn."""
    body = (p.get("Body") or "").strip()
    payload = (p.get("ButtonPayload") or "").strip()
    pend = st.get("pending") or {}
    current = pend.get("product") if pend.get("kind") == "product" else None
    if current:
        try:
            if now - datetime.fromisoformat(pend.get("touched")) > MODE_IDLE:
                current, st["pending"] = None, None
        except (TypeError, ValueError):
            pass
    entering = None
    if _CAMPUS.match(body):
        entering = "campus"
    elif _RELOC.match(body):
        entering = "relocation"
    if not current and not entering:
        return False
    if current and _EXIT.match(body) and not payload:
        st["pending"] = None
        out.text(LEFT)
        return True
    from booking_signer.vault import guard as G
    if body and G.looks_like_secret(body):
        out.text(G.CARD_REPLY if G.looks_like_secret(body) == "card" else G.SECRET_REPLY)
        return True
    if entering and entering != current:
        st["pending"] = {"kind": "product", "product": entering, "step": None, "since": now.isoformat()}
    st["pending"]["touched"] = now.isoformat()
    product = st["pending"]["product"]
    rest = body
    if entering:
        rest = (_CAMPUS if entering == "campus" else _RELOC).sub("", body, count=1).strip(" :,-")
        # "campus visits at Yale…": the keyword is part of the sentence, so the product reads the whole of it
        rest = body if rest and not re.match(r"^(me|mode)\b", rest, re.I) else rest
    ctx = {"account": ch["account_id"], "ch": ch, "frm": frm, "st": st, "now": now, "out": out,
           "media": _media(p), "early": early or _no_early}
    if product == "campus":
        from .campus import turn as CT
        await CT.turn(ctx, rest, payload, entering=bool(entering))
    else:
        from .relocation import turn as RT
        await RT.turn(ctx, rest, payload, entering=bool(entering))
    if st.get("pending"):
        st["pending"]["touched"] = now.isoformat()
    return True


async def _no_early(text: str) -> None:
    return None


def _media(p: Dict[str, str]) -> list:
    """What the person sent besides words: [{url, type}] — Twilio's MediaUrlN / MediaContentTypeN."""
    try:
        n = int(p.get("NumMedia") or 0)
    except ValueError:
        n = 0
    return [{"url": p.get(f"MediaUrl{i}"), "type": p.get(f"MediaContentType{i}") or ""} for i in range(min(n, 5))
            if p.get(f"MediaUrl{i}")]
