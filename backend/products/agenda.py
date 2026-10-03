"""CR 13 · the products' DATED items for one account, for Sasha's "what do I need to do this week?" (her intent merges
them with her trip items) and for the trip plan's one itinerary. Read-only; no personal identifiers in any text.

  agenda(account, start, end) → [{"on": "YYYY-MM-DD", "time": "HH:MM"|None, "text", "product", "source", "kind"}]
    · relocation — the reminders the file set (apply-from, certificates, the TIE), each from the sheet or page it cites;
    · health     — the new-in-Madrid follow-ups (padrón → volante → health card);
    · campus     — each visit prepared or registered, at its time (kind "visit"; a registered visit is ALSO a trip item,
                   which Sasha de-duplicates by its provider_name "… campus visit — …").
Self-booked appointments (consulate, TIE, SERMAS) are trip items already (products/itinerary.py): not repeated here.
"""
from __future__ import annotations

from datetime import date
from typing import List

from . import store as ST


async def agenda(account: str, start: date, end: date) -> List[dict]:
    a, b = start.isoformat(), end.isoformat()
    out: List[dict] = []
    for c in await ST.STORE.of_account(account, "relocation"):
        st = c["state"]
        if st.get("kind") == "conversation" or st.get("showcase"):
            continue
        after = st.get("after") or {}
        office = (after.get("consulate") or {}).get("office")
        for r in after.get("reminders") or []:
            if a <= r["on"] <= b:
                out.append({"on": r["on"], "time": None, "text": r["text"], "product": "relocation", "kind": "deadline",
                            "source": (f"{office}'s own page" if office and (after.get("consulate") or {}).get("id")
                                       else "the London consulate's sheet (11 Feb 2022)")})
    for c in await ST.STORE.of_account(account, "health"):
        st = c["state"]
        if st.get("kind") == "conversation" or st.get("showcase"):
            continue
        for r in st.get("reminders") or []:
            if a <= r["on"] <= b:
                out.append({"on": r["on"], "time": None, "text": r["text"], "product": "health", "kind": "reminder",
                            "source": "the official pages on your health checklist (padrón, INSS)"})
    from .campus import schools as SC, visits as VS
    for c in await ST.STORE.of_account(account, "campus"):
        st = c["state"]
        x = st.get("session") or {}
        if st.get("kind") == "conversation" or st.get("showcase") or not x.get("day") or not (a <= x["day"] <= b):
            continue
        s = SC.SCHOOLS.get(st.get("school") or "")
        if not s:
            continue
        status = {"registered_on_your_word": "registered on your word", "confirmed_in_writing": "confirmed by the school",
                  "handed_over": "prepared — not registered yet"}.get(st.get("status"), st.get("status") or "")
        out.append({"on": x["day"], "time": x.get("start"), "text": f"{VS.name_of(s, x)} ({status})", "product": "campus",
                    "kind": "visit", "source": f"{s['name']}'s own visit calendar"})
    out.sort(key=lambda r: (r["on"], r["time"] or "99:99"))
    seen, uniq = set(), []
    for r in out:   # two files setting the same reminder (e.g. a first try and a redo) are one thing to do, said once
        k = (r["on"], r["time"], r["text"])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq
