"""Sasha 301 · THE FINE PRINT, ASKED AND TOLD — the two tools (/s2, voice and WhatsApp: the one brain's list, app/agent/s2.py).

  booking_fine_print  "What's the fine print on Friday?" → the itinerary's rows that day (agapi/itinerary.of: THE ONE itinerary), each
                      with the venue's own terms (quoted, with the deadline they state) and the loyalty numbers / card perks from his
                      Keep that apply. `say` is built HERE, from the rows — the model says it as given; it never adds a term or a perk.
  keep_note           what he tells her about his loyalty memberships (programme + number) and his cards (name, the LAST FOUR only, a
                      perk in his words and what it's for) → his Keep (agapi/s2_keep: the ONE place they live). A full card number
                      never reaches her (the chat guard withholds it before the model) and is refused by the Keep in any field.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List

from agapi import booking_terms as BT

NO_TERMS = "nothing in their own words about a deposit, cancelling, a no-show or a time limit"
HOW = ("Say `say` as given. A venue's terms are THEIR words, in quotes, with the deadline they state; a perk or loyalty line is from his "
       "own Keep. Never add a term, a fee, a deadline or a perk that isn't in it, and never say a booking is free to cancel unless "
       "their own words say so.")


def _when_words(i: dict) -> str:
    from booking_signer import sentences as SN
    w = str(i.get("when") or "")
    return " ".join(x for x in (SN.day_words(w[:10]) if w else "", w[11:16]) if x)


def _item_say(i: dict) -> str:
    lines = [BT.line(t) for t in i.get("terms") or []] + [p["line"] for p in i.get("perks") or []]
    head = f"{i.get('title')}, {_when_words(i)}".rstrip(", ")
    if not lines:
        tail = NO_TERMS + "." if i.get("source") == "venue" else "no terms on its record here."
        return f"{head}: {tail}"
    return f"{head}: " + " ".join(l if l.endswith((".", "”", "!", "?")) else l + "." for l in lines)


async def booking_fine_print(ctx, a: dict) -> dict:
    from agapi import itinerary as IT, s2_manage as SM
    from agapi.v0 import ToolError
    items = await IT.of(ctx.account)
    day = str(a.get("on") or "").strip()[:10] or None
    if day:
        try:
            date.fromisoformat(day)
        except ValueError:
            raise ToolError("date_invalid", "on is YYYY-MM-DD")
        items = SM._on(items, day)
    name = re.sub(r"\s+", " ", str(a.get("venue") or "")).strip().lower()
    if name:
        items = [i for i in items if name in str(i.get("title") or "").lower()]
    shown = [{k: i[k] for k in ("kind", "title", "when", "status_words", "id", "terms", "perks") if i.get(k)} for i in items[:8]]
    if not items:
        say = "Nothing booked that day." if day else ("I can't find that booking." if name else "Nothing coming up.")
    else:
        say = " ".join(_item_say(i) for i in items[:8])
    return {"items": shown, "say": say, "how": HOW, **({"on": day} if day else {})}


async def keep_note(ctx, a: dict) -> dict:
    """Save what he TOLD her into his Keep. A card with the same name and last four replaces its earlier note (its perk kept unless
    he gave a new one): one card, one item."""
    from agapi import s2_keep as KEEP
    from agapi.v0 import ToolError
    kind = str(a.get("kind") or "").strip().lower()
    try:
        if kind == "loyalty":
            out = await KEEP.put(ctx.account, "loyalty", {"program": str(a.get("program") or "").strip(), "number": str(a.get("number") or "")})
        elif kind == "card":
            v = {k: str(a[k]).strip() for k in ("name", "last4", "perk", "perk_for", "perk_where") if a.get(k) not in (None, "")}
            from agapi import keep as K
            K.normalise("my_card", v)   # refused here (a full number, more than the last four) before anything is opened
            if v.get("perk") and not v.get("perk_for"):
                raise ToolError("perk_for_missing", "ask what the perk is for (hotels, restaurants, spas, flights, car rentals, anything) "
                                                    "— and, if it's one chain, which")
            same = [w for w in await KEEP.wallet(ctx.account) if w["type"] == "my_card"
                    and w.get("name", "").lower() == v.get("name", "").lower() and w.get("last4") == re.sub(r"\D", "", v.get("last4", ""))]
            for w in same:
                v = {**{k: w[k] for k in ("perk", "perk_for", "perk_where") if w.get(k)}, **v}
            out = await KEEP.put(ctx.account, "my_card", v)
            for w in same:
                if w["item_id"] != out["item_id"]:
                    await KEEP.delete(ctx.account, w["item_id"])
        else:
            raise ToolError("kind_invalid", "kind is loyalty (programme + number) or card (name + last four, a perk)")
    except KEEP.KeepError as e:
        raise ToolError(e.rule, e.message) from None
    except ToolError:
        raise
    except Exception as e:
        from agapi import keep as K
        if isinstance(e, K.Refused):
            raise ToolError(e.rule, e.message) from None
        raise
    what = (f"your {a.get('program')} number" if kind == "loyalty" else f"your {a.get('name')}").strip()
    # found live: "Saved in your Keep: Marriott Bonvoy ••••001" was spoken "Marriott Bonvoy ending one" — the line names it, the card shows the mask
    return {"saved": out["masked"], "say": f"Saved {what} in your Keep. I'll show it on the bookings it applies to.",
            "how": "Say `say` as given — never the number."}


def tools() -> List[dict]:
    from agapi.v0 import _t
    return [
        _t("booking_fine_print", "Pacioli", booking_fine_print, (
            "'What's the fine print on Friday?' / 'Is there a deposit at DiverXO?' / 'Can I cancel Saturday for free?' → the bookings "
            "that day (on=YYYY-MM-DD) or that venue: each one's terms in the VENUE's own words (a deposit, the cancellation deadline, a "
            "no-show charge, the time at the table) and the loyalty numbers / card perks from their Keep that apply. Say `say` as given."),
           {"on": {"type": "string", "description": "YYYY-MM-DD, one day"}, "venue": {"type": "string"}}, [],
           {"type": "object", "properties": {"say": {"type": "string"}, "items": {"type": "array"}}}, ["date_invalid"]),
        _t("keep_note", "Pacioli", keep_note, (
            "They TELL you a loyalty membership (kind loyalty: the programme, e.g. Marriott Bonvoy, and its number) or one of their cards "
            "(kind card: its name, e.g. Amex Gold, and its LAST FOUR digits only — never more; a perk it has in THEIR words, e.g. 'free "
            "breakfast', with what it's for: hotel / restaurant / spa / flight / car / any, and the chain if it's one, e.g. Marriott). "
            "Saved in their Keep; you get the mask back. Never ask for a full card number. Say `say` as given."),
           {"kind": {"enum": ["loyalty", "card"]}, "program": {"type": "string"}, "number": {"type": "string"},
            "name": {"type": "string"}, "last4": {"type": "string", "description": "the card's last four digits, nothing more"},
            "perk": {"type": "string", "description": "the perk in their words"},
            "perk_for": {"enum": ["hotel", "restaurant", "spa", "flight", "car", "any"]},
            "perk_where": {"type": "string", "description": "the chain or venue it's at, if they said one"}}, ["kind"],
           {"type": "object", "properties": {"saved": {"type": "string"}}},
           ["kind_invalid", "perk_for_missing", "never_card", "required", "length", "id", "type_not_open", "keep_closed", "keep_unreachable"]),
    ]


__all__ = ["booking_fine_print", "keep_note", "tools"]
