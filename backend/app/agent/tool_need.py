"""Sasha 353 · ONLY WHAT THE TURN NEEDS — the tool families a turn offers, from its words and its conversation; and the system prompt's
rules about tools it doesn't offer, left out.

Measured (STEP 1, count_tokens on the requests the code built, 6 Nov): every step of every turn sent all 78 tool definitions (19,808 tokens,
75 % of the call) — the group movement's 13, the claims', cards' and subscriptions' 20, the messaging tools' — whatever was asked.

  select(tools, message, history, keep)   the families the words of THIS message and the last few lines ask for, + the core; nothing
                                          matched → core + finding a place; "book it" / "yes" → the booking the record is
                                          waiting on (a trip's, or a place's on their screen) (she tries first: any business). Tools not in a family are
                                          always offered (never dropped by omission); `keep` (the calls code makes this turn) always.
  system_for(text, offered)               a rule bullet whose subject — the first tool it names ("… → `tool`") — isn't offered is
                                          left out (it governs nothing this turn); every bullet that names no tool stays.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Set

FAMILIES: Dict[str, Iterable[str]] = {
    "core": ("what_i_can_do", "note_not_yet", "get_status", "my_plans", "remember_name", "save_contact"),
    "activity": ("get_activity", "keep_note"),
    # a trip's tools by what the turn is doing (Sasha 352's states): planning · booking · after it's booked
    "plan": ("prepare_trip", "propose_trip", "search_flights", "search_stays", "swap_stay", "choose_offer", "check_offer", "get_trip",
             "get_total", "hotel_request", "add_to_trip", "save_for_later", "time_between"),
    "book": ("save_travellers", "hold_booking", "book", "get_total", "remove_saved_card", "choose_offer"),
    "after": ("change_booking", "cancel_booking", "running_late", "note_rental", "file_confirmation", "booking_fine_print"),
    # a place's: finding · booking it
    "find": ("search_venues", "suggest_activities", "read_booking_route"),
    "reserve": ("read_booking_route", "hold_venue", "book_venue", "call_again", "cancel_venue"),
    "messages": ("send_email", "send_whatsapp", "add_to_calendar"),
    "keep": ("keep_list", "keep_use", "keep_add"),
    "cards": ("my_cards", "add_card", "which_card", "card_cover", "rental_cover"),
    "claims": ("accident", "accident_notify", "bag_money_back", "flight_money_back", "file_flight_claim", "file_bag_claim", "file_claim",
               "money_claim_status", "claim_status"),
    "entry": ("entry_documents", "prepare_entry"),
    "subscriptions": ("find_subscriptions", "cancel_subscription", "plan_cancel_subscription"),
    "group": ("group_start", "group_upload", "group_person_add", "group_choose", "group_open", "group_limits", "group_plan",
              "group_invite_vault", "group_book", "group_swap", "group_cancel", "group_invoice", "group_list"),
    "founder": ("booking_outcomes", "start_count"),
}
_W = lambda s: re.compile(r"(?i)\b(?:" + s + r")")
WORDS = {
    "activity": _W(r"activity|proof|what (?:have|did) you (?:do|done|send|sent)|note (?:that|this)|remember (?:that|this)"),
    "plan": _W(r"fl(?:y|ight|ights|ying|ew)|plane|hotel|stay|trip|holiday|itinerar|nights?\b|travel|vacation|airport|weekend|getaway|"
               r"go(?:ing)? to|from [A-Z]|to [A-Z]|days? in|week in|beach|total|price|cost|cheap|seat|visit|instead|another|other one|"
               r"the (?:first|second|third|last|cheapest|earlier|later) one|\bthe .{1,40} (?:flight|one)\b"),
    "book": _W(r"\bpay\b|payment|traveller|passenger|born|date of birth|\bmr\b|\bms\b|\bmrs\b|full name|on my phone|saved card|"
               r"book (?:the|my|our) (?:trip|flights?|hotel)|book (?:the )?whole"),
    "after": _W(r"\bchange\b|\bcancel|\blate\b|fine print|deposit|confirmation|rental|refund|move (?:it|my)"),
    "find": _W(r"restaurant|table|dinner|lunch|breakfast|brunch|spa|massage|bar\b|caf[eé]|tattoo|dentist|plumber|hair|salon|tour|"
               r"museum|ticket|activit|things to do|place|venue|dog|florist|taxi|gym|class|near (?:me|here)|open now|eat|drink"),
    "reserve": _W(r"reserv|book (?:a|me|us) (?:table|spa|massage|appointment|slot)|table for|handle it|\bform\b|"
                  r"their (?:page|site|website)|call (?:them|the)|cancel (?:the|my) (?:table|reservation)"),
    "messages": _W(r"e-?mail|whats ?app|message|text (?:them|her|him)|send (?:it|this|them|a)|calendar|remind"),
    "keep": _W(r"\bkeep\b|passport|loyalty|frequent.?flyer|id number|document"),
    "cards": _W(r"\bcards?\b|cover(?:ed|age)?|insurance|amex|visa card|mastercard|points|benefit|rental car|car hire"),
    "claims": _W(r"claim|accident|lost|bag(?:gage)? (?:delay|lost)|luggage|delay|cancell?ed flight|compensation|refund|money back|crash|damage"),
    "entry": _W(r"\bvisa\b|entry|esta\b|\beta\b|e-?visa|border|requirements?"),
    "subscriptions": _W(r"subscriptions?|netflix|spotify|membership|renew|direct debit"),
    "group": _W(r"group|team|workers?|employees?|company|roster|people|organi[sz]|master list|movement|invoice|book all|invite (?:every|them)|"
                r"swap|travellers? list|grade|per diem|limit"),
    "founder": _W(r"outcomes?|the count|real bookings?"),
}
#: "Book it", "yes", "go ahead": a booking — WHICH one is the record's (a trip waiting to be booked · a place on their screen), never guessed
GO_AHEAD = re.compile(r"(?i)\b(?:book(?:ing)?|yes|yeah|yep|go ahead|confirm|do it|here)\b")
HISTORY_LINES = 2   # the last exchange decides with the message ("Yes", "two of us" answer her last line)


def _text(c) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(str(b.get("text") or "") for b in c if isinstance(b, dict))
    return ""


def families(message: str, history: Optional[List[dict]] = None, trip: Optional[bool] = None, places: Optional[bool] = None) -> Set[str]:
    """trip: a trip on the record waiting for its next booking step (Sasha 352's state); places: places on their screen. Either None:
    unknown — then a go-ahead may mean either booking."""
    text = " ".join([message or ""] + [_text(m.get("content")) for m in (history or [])[-HISTORY_LINES:] if isinstance(m, dict)])
    got = {f for f, w in WORDS.items() if w.search(text)}
    if GO_AHEAD.search(text):
        if trip or (trip is None and not places):
            got.add("book")
        if places or (places is None and not trip):
            got.add("reserve")
    if "reserve" in got:   # a place is booked once found: reserving brings finding (found by the gate: "a table for two at the Sasha
        got.add("find")    # Test Venue…" offered no search_venues, and she asked for travellers' details instead)
    return ({"core"} | got) if got else {"core", "find"}   # nothing named: a place, if it's a business (she tries first)


def select(tools: List[dict], message: str, history: Optional[List[dict]] = None, keep: Iterable[str] = (),
           trip: Optional[bool] = None, places: Optional[bool] = None) -> List[dict]:
    fam = families(message, history, trip, places)
    member = {n: f for f, ns in FAMILIES.items() for n in ns}
    want = {n for f in fam for n in FAMILIES.get(f, ())} | set(keep)
    return [t for t in tools if t.get("name") not in member or t.get("name") in want]


_BULLET = re.compile(r"(?m)^- \*\*")
_TOOLNAME = re.compile(r"`([a-z_]+)`")


def system_for(text: str, offered: Iterable[str]) -> str:
    """The prompt's rule bullets ("- **…**" up to the next bullet or heading) whose subject tool isn't offered this turn, left out."""
    offered = set(offered)
    known = {n for ns in FAMILIES.values() for n in ns}
    out, i = [], 0
    for m in list(_BULLET.finditer(text)) + [None]:
        j = m.start() if m else len(text)
        chunk = text[i:j]
        if i and chunk.startswith("- **"):
            end = re.search(r"(?m)^#{1,3} ", chunk)
            body = chunk[:end.start()] if end else chunk
            first = next((n for n in _TOOLNAME.findall(body) if n in known), None)   # the bullet's subject: the first tool it names
            if first and first not in offered:
                chunk = chunk[end.start():] if end else ""
        out.append(chunk)
        i = j
    return "".join(out)


__all__ = ["FAMILIES", "WORDS", "families", "select", "system_for"]
