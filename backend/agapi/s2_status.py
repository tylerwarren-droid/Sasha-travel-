"""Sasha 249 · ONE STATUS (EU 245 §1.12 / T8). What is booked on an account is decided HERE and nowhere else, from three records:

  the basket       trip_basket_items' states (booked / pending_payment / failed / cancelled) — Pacioli's status_line for each
  reservations     the account's reservations (venues, and anything else Pacioli recorded), via agapi.venues.venue_bookings
  the ledger       the outcomes ledger's still-open attempts for this account (agapi.s2_outcomes._OPEN)
  a read-back      a trip read back by hold_booking and not yet said yes to (agapi.v0._HELD)
  prepared pages   Sasha 254 · a venue's own page prefilled for them, their tap pending (agapi.venues.prepared_pages) — said as
                   prepared and not booked, never "nothing"

    status_of(account, trip_id=None, sweep=True) → get_status's dict (unchanged keys) + {"state", "line", "refs", "ledger_open"}

Every surface reads it: the get_status tool (chat), the /s2 "Booked" card (its line arrives on the `booked` live event —
booking_signer/live_events.on_settled), the Trip banner (/api/booking/plan → trip_status) and the WhatsApp line after a payment
(booking_signer/paid_watch._tell). Before this, /s2 made a "Booked" card from a regex on her reply and the Trip banner said
"✓ Paid … · not booked yet" from a client prop.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# the words for each state — the ONE place they are written (hold_booking's read-back status uses HELD as it always said it)
HELD = "not booked — waiting for the yes"
WORDS = {"nothing": "Nothing is booked yet.",
         "held": "Not booked — read back and waiting for your yes.",
         "awaiting_payment": "Waiting for your payment — nothing is booked until it's paid.",
         "requested": "Requested — not confirmed yet",
         "booked": "Booked",
         "partly_booked": "Partly booked",
         "failed": "Not booked",
         "prepared": "Prepared, not booked — their page is filled in, waiting for you to book it there",
         # Sasha 256 · CR 94: the venue's own answer to a request — another time offered is NOT a booking; the person decides
         "proposed": "Not booked — they offered another time; tell me if it suits",
         "declined": "Not booked — the venue said no",
         # Sasha 259 · S2 item 12: the trip's CHOSEN items (its flights picked, not paid) are on the one status too — the Trip tab says
         # "not booked yet" for them, so the chat's "what's coming up" says the same, beside the booked tables
         "chosen": "Chosen, not booked yet"}
ON_IT = ("booked", "partly_booked", "awaiting_payment")   # a Trip banner shows; the Book button goes


def _venue_line(b: dict) -> str:
    return f"{b['venue']} — {b.get('date') or ''} {b.get('time') or ''}".strip(" —") + (f" · ref {b['reference']}" if b.get("reference") else "")


def decide(st: Dict[str, Any], held: bool = False, ledger_open: int = 0) -> Dict[str, str]:
    """The state and its line from get_status's own lists — pure (tests drive it directly)."""
    booked: List[str] = list(st.get("booked") or [])
    refs_seen = " ".join(booked)
    venues = [b for b in st.get("venues") or [] if b.get("status") != "cancelled"]
    conf = [_venue_line(b) for b in venues if b.get("status") in ("confirmed", "guest_booked")
            and not (b.get("reference") and f"ref {b['reference']}" in refs_seen)]   # a basket row already listed is not said twice
    asked = [_venue_line(b) for b in venues if b.get("status") not in ("confirmed", "guest_booked", "declined", "failed", "proposed")]
    proposed = [_venue_line(b) for b in venues if b.get("status") == "proposed"]   # Sasha 256 · the venue's own answer
    declined = [_venue_line(b) for b in venues if b.get("status") == "declined"]
    done, failed = booked + conf, list(st.get("failed") or [])
    if st.get("awaiting_payment"):
        state, line = "awaiting_payment", WORDS["awaiting_payment"]
    elif done and failed:
        state, line = "partly_booked", f"{WORDS['partly_booked']}: " + "; ".join(done) + f". {WORDS['failed']}: " + "; ".join(failed) + "."
    elif done:
        state, line = "booked", f"{WORDS['booked']}: " + "; ".join(done) + "."
    elif failed:
        state, line = "failed", f"{WORDS['failed']}: " + "; ".join(failed) + "."
    elif asked or ledger_open:
        state, line = "requested", f"{WORDS['requested']}" + (": " + "; ".join(asked) if asked else "") + "."
    elif held:
        state, line = "held", WORDS["held"]
    else:
        state, line = "nothing", WORDS["nothing"]
    chosen = [str(x).replace(" · chosen", "") for x in st.get("chosen") or []]
    for key, rows in (("proposed", proposed), ("declined", declined), ("chosen", chosen)):   # Sasha 256/259 · said beside the rest, never as "booked"
        if rows:
            said = f"{WORDS[key]}: " + "; ".join(rows) + "."
            state, line = (key, said) if state == "nothing" else (state, f"{line} {said}")
    prepared = list(st.get("prepared") or [])   # Sasha 254 · ONE TRUTH: a page prepared for them is never "nothing"
    if prepared:
        said = f"{WORDS['prepared']}: " + "; ".join(prepared) + "."
        state, line = ("prepared", said) if state == "nothing" else (state, f"{line} {said}")
    return {"state": state, "line": " ".join(line.split())}


async def status_of(account: str, trip_id: Optional[str] = None, sweep: bool = True) -> Dict[str, Any]:
    """THE status of an account (its latest trip, or `trip_id`). Raises v0's store_unreachable when the records don't answer —
    never "nothing booked" for an outage."""
    from booking_signer import basket as BK, paid_watch as PW, plan_store as PS
    from agapi import venues as VN, v0 as API, s2_outcomes as OC
    if trip_id:
        p = await PS.by_id(account, trip_id)
    else:
        p = await API._latest(API.Ctx(account=account))
    if p and sweep:
        await PW.sweep(account)   # a payment waiting is settled first (Pacioli writes the outcome)
    vb_all = await VN.venue_bookings(account, include_cancelled=True)
    vb = [b for b in vb_all if b.get("status") != "cancelled"]
    vc = [f"{b['venue']} — {b.get('date')} {b.get('time') or ''}".strip() + " · cancelled" for b in vb_all if b.get("status") == "cancelled"]
    if not p:   # Sasha 211 · no trip: the venue bookings still have their status
        st: Dict[str, Any] = {"venues": vb, "anything_booked": any(b["status"] == "confirmed" for b in vb), "booked": [], "failed": [],
                              "cancelled": vc, "awaiting_payment": 0}   # Sasha 226 · a cancelled table is on the record too
        rows: List[dict] = []
    else:
        rows = await BK.items(account, p["trip_id"], ("pending_payment", "booked", "failed", "cancelled"))
        st = {"venues": vb, "anything_booked": any(r["state"] == "booked" for r in rows) or any(b["status"] == "confirmed" for b in vb),
              "booked": [r["status_line"] for r in rows if r["state"] == "booked"],
              "failed": [r["status_line"] for r in rows if r["state"] == "failed"],
              "cancelled": [r["status_line"] for r in rows if r["state"] == "cancelled"] + vc,
              "awaiting_payment": sum(1 for r in rows if r["state"] == "pending_payment")}
        try:   # Sasha 259 · the trip's chosen-not-booked items (S2 item 12: one truth with the Trip tab's "not booked yet")
            st["chosen"] = [r.get("status_line") or BK.status_line(r) for r in await BK.items(account, p["trip_id"], ("chosen",))]
        except Exception as e:
            import logging
            logging.getLogger("agapi.s2_status").warning("[status] chosen items not read: %s", type(e).__name__)
    # Sasha 254 · ONE TRUTH: the pages hold_venue prepared (its "It's in your bookings"), unless that booking is already on the record
    on_record = {(VN._base(b.get("venue") or ""), str(b.get("date") or "")) for b in vb}
    prep = [f"{x['venue']} — {x.get('date') or ''} {x.get('time') or ''}".strip() for x in await VN.prepared_pages(account)
            if (VN._base(x.get("venue") or ""), str(x.get("date") or "")) not in on_record]
    if prep:
        st["prepared"] = prep
    open_n = len(OC._OPEN.get(account) or ())
    d = decide(st, held=account in API._HELD, ledger_open=open_n)
    # Sasha 258 · the TRIP's own state (its basket rows only): the Trip tab's banner reads it — a table booked elsewhere on the
    # account never makes an unbooked trip say "Trip total" (found by the scoreboard once in-app bookings really confirmed)
    trip_state = decide({"booked": st.get("booked") or [], "failed": st.get("failed") or [],
                         "awaiting_payment": st.get("awaiting_payment") or 0})["state"] if p else d["state"]
    refs = [r["booking_reference"] for r in rows if r["state"] == "booked" and r.get("booking_reference")] + \
           [b["reference"] for b in vb if b.get("status") in ("confirmed", "guest_booked") and b.get("reference")]
    from agapi import booking_decide as BD   # Sasha 254 · R12 — an automatic stop is said here too, never only logged
    stops = BD.stops_of(account)
    return {**st, **d, "trip_state": trip_state, "refs": list(dict.fromkeys(refs)), "ledger_open": open_n, **({"stopped": stops} if stops else {})}


def public(st: Dict[str, Any]) -> Dict[str, Any]:
    """What a page may show (the Trip banner, the /s2 card): the state, its line and the references — nothing else."""
    return {"state": st.get("state"), "line": st.get("line"), "refs": list(st.get("refs") or []),
            "trip_state": st.get("trip_state") or st.get("state")}   # Sasha 258 · the trip's own (the Trip tab's banner)


__all__ = ["status_of", "decide", "public", "WORDS", "HELD", "ON_IT"]
