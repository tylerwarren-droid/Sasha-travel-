"""Sasha 169 (6) · PICK BY VOICE on the voice page (/voice): the voice page only speaks the conductor's sentence, so a search there
ended at "Here are the best-rated…" with nothing to pick. A booking, a search or an open booking question now runs WhatsApp's own
flow (guest_whatsapp — the cards, "the second one" / its name / "the one by the river", the read-back, the yes) on the voice
page's own state (key "voice:<account>"), and comes back as words to SAY plus the cards' photos to SHOW. Nothing is sent to
WhatsApp from here: the channel is None, so no streaming, no late photos, no message.
Anything else returns None and the conductor answers as before.

Sasha 321 · A VENUE BOOKING HERE IS THE ONE BRAIN'S (option (c), Tyler's go): a venue booking or cancellation on the voice avatar
or the REST chat runs the agent WhatsApp and /s2 run (wa_agent.agent_turn → search_venues / hold_venue / book_venue → AgAPI's send,
venues._via_agapi), never guest_whatsapp's venue rungs (Sasha 319 retired them: they could only say "I'll hand this to Tyler").
The yes is AgAPI's: the person's own signed-in session from THIS request (venue_submit.session_of → TAP, approvals.in_app_tap),
or on the sandbox (a test person) simulate_approval with their words. Tyler is said only when AgAPI has no route. Flights, hotels
and the trip stay on guest_whatsapp's flow (they never handed to Tyler).
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


#: Sasha 321 · after the agent answered a venue turn here, the next words are its too ("the third one", "Handle it", "yes") for this long
AGENT_OPEN_MIN = 30


def travel_ask(t: str) -> bool:
    """A flight, a hotel stay or the trip — guest_whatsapp's flow, even right after a venue turn."""
    from . import guest_whatsapp as GW, itinerary_q as IQ
    return bool(GW.FLIGHT.search(t or "") or GW.HOTEL.search(t or "") or IQ.TRIP.search(t or ""))


def venue_ask(transcript: str, now) -> bool:
    """Sasha 321 · a venue booking or cancellation said plainly (a place to book with a where, or "cancel my … booking") — never a
    flight, a hotel stay or the trip (those stay on guest_whatsapp's flow)."""
    from . import guest_whatsapp as GW, handoff as HO
    t = transcript or ""
    if not t.strip() or travel_ask(t):
        return False
    try:
        h = HO.booking_handoff(t, [], now)
    except Exception as e:   # a detector's failure never takes the turn
        log.warning("[voice_turn] venue_ask failed: %s", type(e).__name__)
        return False
    bookable = HO._BOOKABLE.search(t) or GW.CUISINE.search(t) or HO._LOOSE_ASK.search(t)
    from agapi import test_venues as TV
    if bookable and TV.names_test_venue(t):   # "a table for two at the Sasha Test Venue in Madrid…" (the hand-off reads no "where" there)
        return True
    return bool(h and (h.get("booking_cancel") or ((h.get("booking_find") or {}).get("where") and bookable)))


def _agent_open(st: dict, now) -> bool:
    from datetime import datetime
    from . import wa_agent as WA
    at = WA.agent_state(st).get("voice_venue")
    try:
        return bool(at) and (now - datetime.fromisoformat(at)).total_seconds() < AGENT_OPEN_MIN * 60
    except (TypeError, ValueError):
        return False


async def _agent(account: str, key: str, transcript: str, st: dict, now, tap: Optional[dict]):
    """The one brain's turn (surface "wa": S2's tools and the one-yes rule) on the voice page's own row, its messages as GW.Out
    items. tap: this request's own signed-in session — the person's yes is then AgAPI's in_app_tap."""
    from agapi import venue_submit as VS
    from . import guest_whatsapp as GW, wa_agent as WA
    out = GW.Out()
    tok = VS.TAP.set(tap) if tap else None
    try:
        await WA.agent_turn({"account_id": account, "wa_id_sha256": key}, transcript, "", st, out, now)
    finally:
        if tok is not None:
            VS.TAP.reset(tok)
    WA.set_agent_state(st, voice_venue=now.isoformat())
    return out


async def turn(account: Optional[str], transcript: str, history: list, tap: Optional[dict] = None, venues_only: bool = False) -> Optional[dict]:
    """venues_only (the REST chat, Sasha 321): only a venue turn is taken here; everything else is the conductor's, as before."""
    from . import guest_whatsapp as GW, wa_brain as WB
    if not account:
        return None
    from agapi import person_access as PA
    await PA.warm(account)   # Sasha 254 · the one record, fresh for this turn's sync checks
    key = voice_key(account)
    try:
        st = await GW.STORE.get_state(key)
    except Exception as e:   # no store: the conductor answers, as before
        log.info("[voice_turn] no booking state: %s", type(e).__name__)
        return None
    now = GW.NOW()
    venue = venue_ask(transcript, now) or (_agent_open(st, now) and not st.get("pending") and not travel_ask(transcript))
    if venues_only and not venue:
        return None
    if not venue and not st.get("pending") and not WB.sasha_clear(transcript, [], now):
        return None
    st["last_inbound_at"] = now
    if venue:   # Sasha 321 · a venue: the one brain → AgAPI's send (its history is kept by agent_turn itself)
        st["pending"] = None
        try:
            out = await _agent(account, key, transcript, st, now, tap)
        except Exception as e:
            log.error("[voice_turn] the agent turn failed: %s: %s", type(e).__name__, e)
            return None
    else:
        out = GW.Out()
        ctx = {"account": account, "ch": None, "frm": None, "st": st, "now": now, "out": out, "button_text": "", "wa_number": None,
               "no_test_card": False, "photo_wait": 4.0}
        try:
            if not await GW._answer_pending(ctx, transcript, ""):
                await GW._new_request(ctx, transcript)
            # Sasha 194 · no automatic switching: spaces change only by their word
        except Exception as e:
            log.error("[voice_turn] the booking turn failed: %s: %s", type(e).__name__, e)
            return None
        st["history"] = ((st.get("history") or []) + [{"role": "user", "content": transcript}, {"role": "assistant", "content": out.said()}])[-GW.HISTORY_KEEP:]
        from . import wa_agent as WA
        WA.set_agent_state(st, voice_venue=None)   # not a venue turn: the next words are not the agent's by default
    await GW.STORE.put_state(key, st)
    words, photos = _spoken(out.items)
    if not words:
        return None
    return {"response": words, "photos": photos, "intents": ["booking"],
            "messages": list(history or []) + [{"role": "user", "content": transcript}, {"role": "assistant", "content": words}]}


__all__ = ["turn", "voice_key", "venue_ask"]
