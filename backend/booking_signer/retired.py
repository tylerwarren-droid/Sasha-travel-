"""Sasha 319 · ONE SENDER TO VENUES: AgAPI's acts (venue.submit_booking / change_booking / cancel_booking, and its call act).

booking_signer's own sends to a venue — the ladder's email and form, its call, the reservation route's cancel (link / email / text /
call) and its change and running-late notices — were a SECOND copy of that sender: no sandbox, no window rules, no never-twice, and
the address read off the venue's own website. They are gone. Their endpoints remain only to say so, and send nothing; a booking
made on this route long ago is handed to Tyler. Sasha's own messages to the GUEST (receipts) are not venue sends and stay."""
from __future__ import annotations

from fastapi.responses import JSONResponse

TO_TYLER = "I'll hand this to Tyler — nothing was sent to them."
RULE = "venue_send_retired"


def refusal(what: str) -> JSONResponse:
    """410: this endpoint used to contact a venue directly; nothing is sent now (AgAPI's acts are the one sender)."""
    return JSONResponse({"error": TO_TYLER, "rule": RULE, "say": TO_TYLER, "what": what, "sent": False}, status_code=410)
