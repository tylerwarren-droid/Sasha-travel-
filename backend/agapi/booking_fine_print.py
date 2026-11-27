"""Sasha 301 · THE FINE PRINT, ASKED AND TOLD — the two tools (/s2, voice and WhatsApp: the one brain's list, app/agent/s2.py).

  booking_fine_print  "What's the fine print on Friday?" / "Can I cancel?" → the itinerary's rows that day (agapi/itinerary.of: THE ONE
                      itinerary). Sasha 424 · NO TERM WITHOUT A FACT: a booking's terms (a deposit, cancelling, a deadline, a fee) are
                      AgAPI's facts (facts.answer) or they are not said — Sasha composes none, so each booking is said as having no
                      confirmed terms on record. The loyalty numbers / card perks from his Keep that apply are said "as you told me".
                      `say` is built HERE — the model says it as given; it never adds a term or a perk.
  keep_note           what he tells her about his loyalty memberships (programme + number) and his cards (name, the LAST FOUR only, a
                      perk in his words and what it's for) → his Keep (agapi/s2_keep: the ONE place they live). A full card number
                      never reaches her (the chat guard withholds it before the model) and is refused by the Keep in any field.
"""
from __future__ import annotations

import re
from datetime import date
from typing import List

#: Sasha 424 · the ONE sentence about a booking's terms while AgAPI holds no fact for it — never a guess, never a placeholder
NO_TERMS = "I have no confirmed terms on record for this booking"
HOW = ("Say `say` as given. Sasha holds no booking terms of her own: never state or guess a deposit, a cancellation rule, a deadline, "
       "a fee or whether it can be refunded or cancelled for free. A perk or loyalty line is from his own Keep, as he told her.")


def _when_words(i: dict) -> str:
    from booking_signer import sentences as SN
    w = str(i.get("when") or "")
    return " ".join(x for x in (SN.day_words(w[:10]) if w else "", w[11:16]) if x)


def _item_say(i: dict) -> str:
    head = f"{i.get('title')}, {_when_words(i)}".rstrip(", ")
    perks = [p["line"] for p in i.get("perks") or []]
    return f"{head}: {NO_TERMS}." + "".join(" " + (l if l.endswith((".", "!", "?")) else l + ".") for l in perks)


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
    shown = [{k: i[k] for k in ("kind", "title", "when", "status_words", "id", "perks") if i.get(k)} for i in items[:8]]
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
            "that day (on=YYYY-MM-DD) or that venue, each said with the terms on record for it (none confirmed yet: say so, never guess "
            "one) and the loyalty numbers / card perks from their Keep that apply. Say `say` as given."),
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
