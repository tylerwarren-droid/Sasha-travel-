"""Sasha 326 · ONE CONVERSATION, THE RIGHT CHANNEL (Tyler 2 Nov 16:02: "the booking form also shows in WhatsApp — not necessary… but I need
to refer in WhatsApp to reservations I started in S2"). THE ONE place that decides which channel hears what — S2, WhatsApp and voice read
it (docs/sasha/S-326-one-conversation.md):

  used(account, ch)          the one entry (sasha.turn) records the channel of every turn: "s2" (the page, its voice) or "wa"
  from_request(ctx)          where THIS request came from: "wa" (ctx.via) or "s2"
  wip_on_phone(ctx)          WORK IN PROGRESS (a form, a hand-over page, a question, "tap here") goes to WhatsApp ONLY when the request came
                             from WhatsApp — on S2 it is S2's card
  outcome_channel(account)   OUTCOMES (confirmed / declined / changed / cancelled / reminder / delay / no answer) go to ONE channel: S2 when
                             an S2 page is open now and their last turn was there; else WhatsApp when linked; else S2's kept news
  tell(account, text, …)     THE ONE SEND of an outcome: that channel only (WhatsApp unreachable → S2's news, never lost, never both)
  progress(account, door, t)  Sasha 366 · a server job's stage, to WhatsApp only when the job came from WhatsApp
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger("booking_signer.channel")

S2, WA = "s2", "wa"
KIND = "last_channel"
_LAST: Dict[str, Tuple[str, float]] = {}   # account → (channel, at) — this process's copy of the kept value


async def used(account: Optional[str], ch: str) -> None:
    if not account or ch not in (S2, WA):
        return
    prev = _LAST.get(account)
    _LAST[account] = (ch, time.time())
    if prev and prev[0] == ch:
        return   # kept only when it changes: one write per switch, never per turn
    try:
        from agapi import s2_memory as M
        await M.put_kind(account, KIND, {"ch": ch, "at": time.time()})
    except Exception as e:
        log.warning("[channel] last channel not kept: %s", type(e).__name__)


async def last(account: str) -> Optional[str]:
    if account in _LAST:
        return _LAST[account][0]
    try:
        from agapi import s2_memory as M
        v = await M.kind(account, KIND)
        if isinstance(v, dict) and v.get("ch") in (S2, WA):
            _LAST[account] = (v["ch"], float(v.get("at") or 0))
            return v["ch"]
    except Exception as e:
        log.warning("[channel] last channel not read: %s", type(e).__name__)
    return None


def from_request(ctx) -> str:
    return WA if getattr(ctx, "via", "page") == "wa" else S2


def wip_on_phone(ctx) -> bool:
    """A work-in-progress step goes to their WhatsApp only when the request came from WhatsApp."""
    return from_request(ctx) == WA


def s2_open(account: str) -> bool:
    from . import live_events as LE
    return bool(LE._SUBS.get(account))


async def _wa_linked(account: str) -> bool:
    from . import live_events as LE
    if LE.WA_SEND is not None:
        return True
    try:
        from . import guest_whatsapp as GW
        return bool(GW.STORE is not None and await GW.STORE.channel_of_account(account))
    except Exception:
        return False


async def outcome_channel(account: str) -> str:
    if s2_open(account) and await last(account) != WA:
        return S2
    return WA if await _wa_linked(account) else S2


async def progress(account: str, door: str, text: str) -> Optional[str]:
    """Sasha 366 · WORK IN PROGRESS of a job the server carries (a group trip's stages): on their WhatsApp only when the job was asked for
    there (the wip rule); the S2 page draws its own live line. → what WhatsApp answered, or None (not this door)."""
    if door != WA:
        return None
    from . import live_events as LE
    return await LE._tell_whatsapp(account, text)


async def tell(account: str, text: str, *, event: Optional[dict] = None, wa_text: Optional[str] = None,
               news_key: Optional[str] = None, news_url: Optional[str] = None) -> Dict[str, Any]:
    """An outcome, said on ONE channel. → {to: s2|wa, wa: what WhatsApp answered, event}."""
    from . import live_events as LE
    to = await outcome_channel(account)
    out: Dict[str, Any] = {"to": to}
    if to == WA:
        res = await LE._tell_whatsapp(account, wa_text or text)
        out["wa"] = res
        if "sent" in str(res) and "not" not in str(res):
            log.info("[channel] outcome → WhatsApp")
            return out
        out["to"] = S2   # WhatsApp couldn't take it (outside its window, unlinked): S2, kept for their return — never lost
        log.info("[channel] outcome → S2 (WhatsApp: %s)", res)
    out["event"] = LE.publish(account, {"type": "proactive", "say": text, **(event or {})})
    if news_key and not s2_open(account):   # nobody on S2 now: said on their return
        await LE.keep_news(account, news_key, text, url=news_url)
    return out


__all__ = ["used", "last", "from_request", "wip_on_phone", "s2_open", "outcome_channel", "tell", "progress", "S2", "WA"]
