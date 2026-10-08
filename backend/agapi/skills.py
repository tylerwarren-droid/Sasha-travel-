"""CR 54 · SASHA'S SKILLS — which skill is open, decided in CODE (strict spaces, Sasha 194), never by the model.

A skill opens only by its own word or a tap on its button, and closes only by "sasha" or its Back button. While a skill is open
the model is given ONLY that skill's tools (plus nothing else), so it cannot drift into another skill or into general travel;
outside every skill it gets Sasha's travel tools and cannot open a skill itself (it may offer one, as a button the person taps).

    resolve(account, message, tap)  → Turn(skill, said, consumed)
        skill     the skill open for this turn (None = Sasha)
        said      the one line to say when it opened or closed this turn ("Let's plan your campus tour."), else None
        consumed  True when the message was only the word (nothing else for the model to answer)
    tools(skill)                    → the tool list the model gets
    call(ctx, skill, name, args)    → the right tool module (v0 for Sasha, the skill's own otherwise)

The open skill is kept per account in the product store (the same store CampusMe's WhatsApp conversation uses), so it survives
a restart and is the same on every surface the agent serves.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from agapi import v0 as V0

SKILLS: Dict[str, dict] = {
    "campus": {"words": ("campus", "campusme", "campus me"), "tap": "skill:campus", "label": "CampusMe",
               "opened": "Let's plan your campus tour.", "closed": "Back to Sasha — your tour is kept."},
}
LEAVE_WORDS = ("sasha",)
LEAVE_TAP = "skill:sasha"
_KEY = "agent-skill:{account}"     # the agent's own key: never a WhatsApp or web conversation's
_PRODUCT = "campus"                # stored in that row (products/store.py PRODUCTS); the open skill is in it


@dataclass
class Turn:
    skill: Optional[str]
    said: Optional[str] = None
    consumed: bool = False


def _module(skill: Optional[str]):
    if skill == "campus":
        from agapi import campus
        return campus
    return None


def _word(message: str) -> str:
    return re.sub(r"[^\w ]", "", (message or "").strip().lower()).strip()


async def current(account: str) -> Optional[str]:
    from products import store as ST
    for r in await ST.STORE.conversations(_KEY.format(account=account)):
        if r.get("product") == _PRODUCT:
            s = (((r.get("state") or {}).get("pending")) or {}).get("skill")
            return s if s in SKILLS else None
    return None


async def _set(account: str, skill: Optional[str]) -> None:
    from products import store as ST
    await ST.STORE.put_conversation(_KEY.format(account=account), account, _PRODUCT, {"skill": skill})


async def resolve(account: str, message: str, tap: Optional[str] = None) -> Turn:
    """The skill for this turn. Only the person's own word or tap changes it; anything else keeps what is open."""
    now = await current(account)
    w = _word(message)
    if tap == LEAVE_TAP or (not tap and w in LEAVE_WORDS):
        if now:
            await _set(account, None)
            return Turn(None, SKILLS[now]["closed"], consumed=True)
        return Turn(None, None, consumed=False)
    for name, s in SKILLS.items():
        if tap == s["tap"] or (not tap and w in s["words"]):
            if now != name:
                await _set(account, name)
                return Turn(name, s["opened"], consumed=True)
            return Turn(name, None, consumed=True)
    return Turn(now)


def tools(skill: Optional[str]) -> List[dict]:
    """What the model may call: the open skill's tools only — or, in Sasha, her travel tools."""
    m = _module(skill)
    return m.tools_for_model() if m else [V0.schema_for_model(t) for t in V0.TOOLS]


async def call(ctx: V0.Ctx, skill: Optional[str], name: str, args: dict) -> dict:
    """A tool call, routed to the open skill's module; a tool outside the open skill is refused (never run)."""
    m = _module(skill)
    if m:
        return await m.call(ctx, name, args)
    if name not in V0.BY_NAME:
        return {"ok": False, "error": {"code": "unknown_tool", "message": f"no tool {name} here"}}
    return await V0.call(ctx, name, args)


def offer(skill: str) -> dict:
    """The button Sasha may show to OFFER a skill (she can't open it herself): the person's tap opens it."""
    s = SKILLS[skill]
    return {"title": f"Open {s['label']}", "payload": s["tap"]}
