"""CR 1 → CR 10 · ONE SASHA, NOT ROOMS: CampusMe, relocation and health are SKILLS inside Sasha's one conversation.

Who answers a message (product_turn; True = a product answered, False = Sasha's own flow runs, in the same chat):
  1. a product's own BUTTON (cm…, rx:, hx…) or its KEYWORD at the start ("campus…", "relocation…", "salud…") → that
     product — started, or RESUMED where it was;
  2. the product ASKED LAST (Sasha's `pending` holds the product marker): an answer to its own question (its claims())
     → the product; a request Sasha's own detectors claim (a booking, a cancel, receipts, flights, a hotel…) → SASHA,
     with the product's context added to her history in ONE line (minimum necessary: where, when, who — never a passport
     fact, never a health reason); anything else → the product re-asks, plainly — never a wall;
  3. SASHA asked last (her own `pending`) → Sasha;
  4. nobody is waiting: a product set aside within MODE_IDLE resumes only if the message answers its question.
A product's state lives in product_cases ("conversation" rows), so Sasha's flow may use `pending` freely and the product
picks up exactly where it was. EXIT still ends a product, but it is never advertised.

⚠ DEMO DEVICE: production needs one WhatsApp number per product (Meta: one display name per number; CR-1-spec.md §1).
Called from booking_signer/guest_whatsapp.turn() — the guarded block marked "CR 1 products".
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
_HEALTH = re.compile(r"^\s*(salud|health|sanidad|m[eé]dico\s+en\s+madrid)\b", re.I)
_EXIT = re.compile(r"^\s*(exit|sasha|back|back to sasha|quit|salir)\s*[.!]?\s*$", re.I)



PREFIX = {"campus": ("cm:", "cmyes:", "cmno:"), "relocation": ("rx:",), "health": ("hx:", "hxyes:", "hxno:", "hxv:", "hxvno:")}
_FLIGHT = re.compile(r"\b(flights?|fly(?:ing)? (?:to|from)|plane|airfare|vuelos?|volar|avi[oó]n|hotel|hostel|apartment|car hire|rent a car)\b", re.I)


def _module(product: str):
    if product == "campus":
        from .campus import turn as M
    elif product == "health":
        from .health import turn as M
    else:
        from .relocation import turn as M
    return M


def for_sasha(body: str, history: list, now) -> bool:
    """Sasha's OWN detectors (guest_whatsapp's scope gate), read-only: would her flow take this message?"""
    from booking_signer import guest_whatsapp as GW, handoff as HO
    t = body or ""
    try:
        if not t.strip():
            return False
        if GW.cancel_intent(t) is not None or GW._RECEIPTS.search(t) or _FLIGHT.search(t) or GW.COMBO.search(t):
            return True
        if HO.booking_handoff(t, history or []) is not None:
            return True
        from booking_signer.chat_request import booking_turn
        if booking_turn(t, history or []) is not None:
            return True
        return bool(GW.maybe_booking(t))
    except Exception as e:   # a detector failing never strands the message: Sasha's flow gets it
        log.error("[products] a Sasha detector failed (%s): handing the message to Sasha", type(e).__name__)
        return True


async def _set_aside(st: dict, ch: dict) -> Optional[dict]:
    """The product that asked last steps aside: its state is kept (product_cases), Sasha's `pending` is hers again, and
    ONE context line joins her history. Returns the context."""
    from . import store as ST
    pend = st.get("pending") or {}
    product = pend.get("product")
    if not product:
        return None
    await ST.STORE.put_conversation(ch["wa_id_sha256"], ch["account_id"], product, pend)
    c = _module(product).context(pend)
    st["history"] = ((st.get("history") or []) + [{"role": "assistant", "content": c["line"]}])[-20:]
    st["pending"] = None
    return c


async def _resume(ch: dict, product: str) -> Optional[dict]:
    from . import store as ST
    for r in await ST.STORE.conversations(ch["wa_id_sha256"]):
        if r["product"] == product:
            return r["state"].get("pending")
    return None


async def _waiting(ch: dict, now) -> list:
    """Set-aside products touched within MODE_IDLE, most recent first: (product, pending)."""
    from . import store as ST
    out = []
    for r in await ST.STORE.conversations(ch["wa_id_sha256"]):
        pend = r["state"].get("pending") or {}
        try:
            fresh = now - datetime.fromisoformat(pend.get("touched")) <= MODE_IDLE
        except (TypeError, ValueError):
            fresh = False
        if fresh and pend.get("step") not in (None, "done"):
            out.append((r["product"], pend))
    return out


def context(st_or_pend) -> Optional[dict]:
    """For Sasha's parsers: the product context of the conversation that asked last (or None)."""
    pend = (st_or_pend or {}).get("pending", st_or_pend) or {}
    return _module(pend["product"]).context(pend) if pend.get("kind") == "product" and pend.get("product") else None


async def product_turn(ch: dict, frm: str, p: Dict[str, str], st: dict, out, now, early=None) -> bool:
    """True: a product answered (the caller stores the state and delivers `out`). False: Sasha's own flow answers."""
    body = (p.get("Body") or "").strip()
    payload = (p.get("ButtonPayload") or "").strip()
    media = _media(p)
    pend = st.get("pending") or {}
    asked_last = pend.get("product") if pend.get("kind") == "product" else None
    if asked_last:
        try:
            if now - datetime.fromisoformat(pend.get("touched")) > MODE_IDLE:
                asked_last, st["pending"] = None, None
        except (TypeError, ValueError):
            pass
    # 1 · a product's button or keyword
    target, entering = None, False
    for prod, prefixes in PREFIX.items():
        if payload.startswith(prefixes):
            target = prod
    for prod, rx in (("campus", _CAMPUS), ("relocation", _RELOC), ("health", _HEALTH)):
        if not target and rx.match(body):
            target, entering = prod, True
    if asked_last and _EXIT.match(body) and not payload:
        from . import store as ST
        await ST.STORE.drop_conversation(ch["wa_id_sha256"], asked_last)
        st["pending"] = None
        out.text("OK.")
        return True
    if not target and asked_last:
        # 2 · the product asked last: its answer, Sasha's request, or a plain re-ask
        if _module(asked_last).claims(pend, body, payload, media):
            target = asked_last
        elif for_sasha(body, st.get("history") or [], now):
            await _set_aside(st, ch)
            return False
        else:
            target = asked_last
    if not target and not st.get("pending"):
        # 4 · nobody is waiting: a set-aside product resumes only on an answer to its own question
        for prod, saved in await _waiting(ch, now):
            if _module(prod).claims(saved, body, payload, media):
                target = prod
                break
    if not target:
        return False                                            # 3 · Sasha asked last, or nothing of ours
    from booking_signer.vault import guard as G
    if body and G.looks_like_secret(body):
        out.text(G.CARD_REPLY if G.looks_like_secret(body) == "card" else G.SECRET_REPLY)
        return True
    if asked_last and asked_last != target:
        await _set_aside(st, ch)                                # another product steps in: the first one is kept
    if not (st.get("pending") or {}).get("product") == target:
        saved = await _resume(ch, target)
        if saved:
            st["pending"] = {**saved, "kind": "product", "product": target}
            words = {"campus": _CAMPUS, "relocation": _RELOC, "health": _HEALTH}[target].sub("", body, count=1).strip(" :,-")
            if entering and not words and not payload:          # "relocation" alone: where we were, said again
                st["pending"]["touched"] = now.isoformat()
                out.text(_welcome_back(target, saved))
                return True
            entering = False if not words else entering
        else:
            st["pending"] = {"kind": "product", "product": target, "step": None, "since": now.isoformat()}
    st["pending"]["touched"] = now.isoformat()
    rest = body
    if entering:
        rest = {"campus": _CAMPUS, "relocation": _RELOC, "health": _HEALTH}[target].sub("", body, count=1).strip(" :,-")
        rest = body if rest and not re.match(r"^(me|mode)\b", rest, re.I) else rest   # "campus visits at Yale…": all of it
    ctx = {"account": ch["account_id"], "ch": ch, "frm": frm, "st": st, "now": now, "out": out, "media": media,
           "early": early or _no_early}
    handled = await _module(target).turn(ctx, rest, payload, entering=entering)
    if handled is False and not out.items:                      # the product says it isn't its message: Sasha's
        await _set_aside(st, ch)
        return False
    from . import store as ST
    if (st.get("pending") or {}).get("step") in (None, "done"):   # finished, or never begun: nothing is kept
        await ST.STORE.drop_conversation(ch["wa_id_sha256"], target)
        st["pending"] = None
        return True
    if st.get("pending"):
        st["pending"]["touched"] = now.isoformat()
        if out.items:                                             # its last question, to say again on resuming
            st["pending"]["last_said"] = str(out.items[-1][1])[:600]
        from . import store as ST
        await ST.STORE.put_conversation(ch["wa_id_sha256"], ch["account_id"], target, st["pending"])
    return True


_RESUME_Q = {"relocation": "Back to your EX-01.", "campus": "Back to your campus visits.", "health": "Back to your health appointment."}


def _welcome_back(product: str, saved: dict) -> str:
    """Resuming: where we were, in one line — the product's last question, said again."""
    last = (saved.get("last_said") or "").strip()
    return f"{_RESUME_Q[product]} {last}" if last else _RESUME_Q[product]


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
