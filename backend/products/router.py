"""Sasha 315 · THE ROUTER: which space answers a WhatsApp message that no space's word or button claimed (Tyler: "the agent should know what
I'm talking about" — one assistant, no modes to remember). Called from ONE place, products/whatsapp.product_turn, in Sasha's own space (travel).

By meaning, as classes — never a word list per case:
  · AD's: a case AD itself lists for this number (AgAPI's door kind case_list, CR 139 — read, never copied), or investigation language
    (a case, investigate, due diligence / DD, a questionnaire, an interview, "add this to <case>").
  · travel's: Sasha's own detector (products/whatsapp.for_sasha), and the money-back / insurance words her claims answer.
  · AD's and not travel → handed to AD with ONE line (LINE), the space unchanged; both → ONE question; else travel, as before.
After a hand-over AD has asked last: his next message is AD's too, unless it is travel (then Sasha has asked last again).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger("products.router")

LINE = "In Applied Diligence:"   # said first; AD's own answer follows from Kanoe's number (AgAPI sends it)
ASK = "Is this for Applied Diligence or for your travel?"
ASK_AD, ASK_TRAVEL = "Applied Diligence", "Travel"
AD_TURN = timedelta(minutes=15)   # AD asked last within this: a reply that isn't travel is AD's
CASES_TTL_S = 120

_CASE = re.compile(r"(?i)\bcases?\b")
_NOT_A_CASE = re.compile(r"(?i)(?:\b(?:suit|brief|phone|pencil|pillow|show|book|display|glasses|camera|guitar|lower|upper|nut|head|worst|"
                         r"best|in|just\s+in|any)[\s-]*cases?\b|\bcases?\s+of\s+(?!the\b|my\b|our\b)\w+)")
_INVESTIGATION = re.compile(r"(?i)\b(?:investigat\w*|due[\s-]+diligence|kyc|questionnaires?|interview(?:s|ed|ing)?|contradictions?|"
                            r"red\s+flags?|adverse\s+media|sanctions?\s+(?:check|screen\w*)|add\s+(?:this|these|that|it|them)\s+to\b)")
_DD = re.compile(r"(?:\bDD\b|(?i:\bdd\s+(?:on|for|report|check)\b))")
_CLAIMS = re.compile(r"(?i)\b(?:claims?|compensation|refunds?|money[\s-]+back|insurance|insured|eu\s*261|chargeback|lost\s+(?:luggage|bags?)|"
                     r"delayed\s+(?:flight|bag)|receipts?|subscriptions?)\b")
_CASES: Dict[tuple, tuple] = {}   # (number, message) → (at, AgAPI's answer): this process's 2-minute read of AD's answer, never a store


def named(text: str, cases: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """Sasha 318 · CR 148: the case the message names, AS AGAPI READ IT (messages.ad_cases {from, text} → named: AD's door's one reading,
    ad_door.names_in). Sasha never matches a case name itself; no answer from AgAPI → no case (the message stays where it is)."""
    return next((c for c in cases or [] if c.get("named") is True), None)


def investigation(text: str) -> bool:
    t = str(text or "")
    if _INVESTIGATION.search(t) or _DD.search(t):
        return True
    return bool(_CASE.search(_NOT_A_CASE.sub(" ", t)))


def travel(text: str, history: list, now) -> bool:
    from . import whatsapp as PW
    return bool(_CLAIMS.search(text or "")) or PW.for_sasha(text, history, now)


def classify(text: str, history: list, now, cases: Optional[List[Dict[str, Any]]] = None) -> str:
    """→ "diligence" · "sasha" · "ask"."""
    if not str(text or "").strip():
        return "sasha"
    ad = bool(named(text, cases)) or investigation(text)
    tr = travel(text, history, now)
    if ad and tr:
        return "ask"
    return "diligence" if ad else "sasha"


async def cases_for(number: Optional[str], text: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """AD's own list of this number's cases, through AgAPI (None: AD gave none — then nothing is guessed). Sasha 318 · with the message, AgAPI
    also says which of them it names (AD's door's reading); cached 2 minutes per (number, message)."""
    if not number:
        return None
    key = (number, " ".join(str(text or "").lower().split()))
    hit = _CASES.get(key)
    if hit and time.monotonic() - hit[0] < CASES_TTL_S:
        return hit[1]
    from agapi import venue_submit as VS
    try:
        got = await VS.ad_cases(number, text)
    except Exception as e:
        log.warning("[router] AD's case list not read: %s", type(e).__name__)
        got = None
    _CASES[key] = (time.monotonic(), got)
    return got


def held(st: dict, key: str):
    """The router's own marks (AD asked last · the one question asked) ride with the brain's state: guest_wa_state keeps only its columns."""
    from booking_signer import wa_agent as WA
    return WA.agent_state(st).get(key)


def hold(st: dict, **kw) -> None:
    from booking_signer import wa_agent as WA
    WA.set_agent_state(st, **kw)


def _ad_asked_last(st: dict, now) -> bool:
    try:
        return now - datetime.fromisoformat(held(st, "ad_at")) <= AD_TURN
    except (TypeError, ValueError):
        return False


async def decide(ch: dict, body: str, st: dict, now, sashas_question: bool) -> str:
    """THE ONE ROUTING of a message no space claimed → "diligence" · "sasha" · "ask". Travel's answers clear AD's turn."""
    history = st.get("history") or []
    if not body.strip():
        return "sasha"
    tr = travel(body, history, now)
    if not tr and not sashas_question and _ad_asked_last(st, now):
        return "diligence"                               # AD asked last ("Send me a contact…", "Yes/No"): his answer is AD's
    got = classify(body, history, now, None)
    if got == "sasha" and not tr:                        # no investigation words: does it name one of his cases? AD's list says
        got = classify(body, history, now, await cases_for(ch.get("number_e164"), body))
    if got == "diligence" and sashas_question and not investigation(body):
        got = "ask"                                      # Sasha asked something: a bare case name answering it is asked about, once
    if got == "sasha":
        hold(st, ad_at=None)
    return got
