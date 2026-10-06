"""Sasha 169 (6) · PICK BY VOICE on the voice page (/voice): the voice page only speaks the conductor's sentence, so a search there
ended at "Here are the best-rated…" with nothing to pick. A booking, a search or an open booking question now runs WhatsApp's own
flow (guest_whatsapp — the cards, "the second one" / its name / "the one by the river", the read-back, the yes) on the voice
page's own state (key "voice:<account>"), and comes back as words to SAY plus the cards' photos to SHOW. Nothing is sent to
WhatsApp from here: the channel is None, so no streaming, no late photos, no message.
Anything else returns None and the conductor answers as before.
"""
from __future__ import annotations

import logging
from typing import List, Optional

log = logging.getLogger("booking_signer.voice_turn")


def _unlabel(s: str) -> str:
    from .switching import strip_label
    return strip_label(s)


def _spoken(items: List[tuple]) -> tuple:
    """(the words to say, the photos to show) from a turn's messages."""
    said, photos, n = [], [], 0
    for it in items:
        if it[0] == "text":
            said.append(_unlabel(it[1]))
        elif it[0] == "media":
            n += 1
            said.append(f"{n}. {it[1].replace('Sasha' + chr(39) + 's pick · ', '')}")
            photos.append({"url": it[2], "thumb": it[2], "description": it[1], "photographer": "", "location": it[1]})
        elif it[0] == "ask":
            titles = [t for t, _ in it[2]]
            opts = (", ".join(titles[:-1]) + " or " + titles[-1]) if len(titles) > 1 else (titles[0] if titles else "")
            body = _unlabel(it[1])
            said.append(f"{body} ({opts})" if body.startswith("Which one") and opts else body)
    return "\n".join(s for s in said if s), photos


def voice_key(account: str) -> str:
    """The voice page's own conversation row (guest_wa_state keys are sha256 hex, like a WhatsApp number's)."""
    import hashlib
    return hashlib.sha256(f"voice:{account}".encode()).hexdigest()


async def turn(account: Optional[str], transcript: str, history: list) -> Optional[dict]:
    from . import guest_whatsapp as GW, wa_brain as WB
    if not account:
        return None
    key = voice_key(account)
    try:
        st = await GW.STORE.get_state(key)
    except Exception as e:   # no store: the conductor answers, as before
        log.info("[voice_turn] no booking state: %s", type(e).__name__)
        return None
    now = GW.NOW()
    if not st.get("pending") and not WB.sasha_clear(transcript, [], now):
        return None
    out = GW.Out()
    st["last_inbound_at"] = now
    ctx = {"account": account, "ch": None, "frm": None, "st": st, "now": now, "out": out, "button_text": "", "wa_number": None,
           "no_test_card": False, "photo_wait": 4.0}
    from . import switching as SW   # Sasha 179 · the avatar switches as WhatsApp does: one spoken line (no label in speech)
    sw = SW.on(account)
    mode0 = SW.before(st, now) if sw else None
    try:
        if not await GW._answer_pending(ctx, transcript, ""):
            await GW._new_request(ctx, transcript)
        if sw:
            cur = SW.announce(out.items, mode0, await SW.after(account, transcript, st), 0)
            if cur:   # the mode rides in the history, as on WhatsApp
                SW.label_first(out.items, cur)
    except Exception as e:
        log.error("[voice_turn] the booking turn failed: %s: %s", type(e).__name__, e)
        return None
    st["history"] = ((st.get("history") or []) + [{"role": "user", "content": transcript}, {"role": "assistant", "content": out.said()}])[-GW.HISTORY_KEEP:]
    await GW.STORE.put_state(key, st)
    words, photos = _spoken(out.items)
    if not words:
        return None
    return {"response": words, "photos": photos, "intents": ["booking"],
            "messages": list(history or []) + [{"role": "user", "content": transcript}, {"role": "assistant", "content": words}]}


__all__ = ["turn", "voice_key"]
