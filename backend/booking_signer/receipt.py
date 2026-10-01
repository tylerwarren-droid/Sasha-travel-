"""Sasha 88 · THE BOOKING RECEIPT — every booking leaves an artefact of the conversation that made it (founder's rule).

    GET /api/booking/reservations/{trip_item_id}/receipt

One reservation, as it can be shown and proved:
  · the venue by its NAME — the listing's, re-read now and never stored (Sasha 64), or its own site's — never the words
    the guest searched with;
  · what, when, for whom; BOTH references — the venue's, verbatim and only if they said it, and Sasha's own (K-XXXX),
    which she said to them;
  · their words, and the whole two-sided transcript of the call;
  · the recording: NOT kept — transcript only, until the disclosure line says the call is recorded and counsel clears it;
  · anything the venue WROTE about it (an SMS, a WhatsApp, a voicemail, a reply to Sasha's email), verbatim;
  · the proof: the read-back the guest approved (its hash), how and when they said yes, the brief's and the object's hashes.
Nothing here is new information: every field is read from what was stored when it happened.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .account import account_for
from .store import StorageUnavailable

router = APIRouter(prefix="/reservations", tags=["booking-receipt"])

RECORDING_NOT_KEPT = ("Not kept — transcript only. A recording is kept only once Sasha's opening says the call is recorded "
                      "and counsel has cleared it.")
_SPEAKER = {"assistant": "Sasha", "user": "Venue"}


def transcript(details: Optional[Mapping[str, Any]]) -> List[dict]:
    """Bland's turns, both sides, in order — who said it, their exact words, when. Its own actions are left out."""
    out = []
    for t in (details or {}).get("transcripts") or []:
        who = _SPEAKER.get(str(t.get("user")))
        text = str(t.get("text") or "").strip()
        if who and text:
            out.append({"who": who, "text": text, "at": t.get("created_at")})
    return out


def build(call: Mapping[str, Any], item: Mapping[str, Any], written: List[Mapping[str, Any]], venue: Mapping[str, Any],
          shown_lines: Optional[List[str]] = None) -> Dict[str, Any]:
    """The receipt, from the stored rows. `venue` is {name, source}: who the guest chose, as shown now."""
    from .routes import status_words, what_of   # the list's own wording, so the card and the list never disagree
    brief = call.get("brief") or {}
    reading = call.get("reading") or {}
    request = item.get("request") or {}
    approval = call.get("approval") or {}
    who = (request.get("who") or {}).get("name") or brief.get("name") or call.get("guest_name")
    return {
        "trip_item_id": str(item.get("id") or call.get("trip_item_id")), "call_id": str(call["call_id"]),
        "venue": dict(venue),
        **what_of(request or None, item.get("party_size") or brief.get("party")),
        "date": brief.get("date"), "time": brief.get("time"), "timezone": brief.get("timezone"),
        "for_whom": who, "phone_given_if_asked": brief.get("phone"),
        "status": item.get("status"), "status_words": status_words(item.get("status") or "", request or None),
        "references": {
            # the VENUE's, only as they said it (calls.read_call keeps it only if a venue line quotes it)
            "venue": reading.get("reference") or item.get("booking_reference"),
            # Sasha's own — in the brief the guest's yes bound, and said to the venue
            "sasha": brief.get("own_reference"),
        },
        "their_words": call.get("venue_words"),
        "reading": {k: reading.get(k) for k in ("outcome", "why", "quote", "read_by") if reading.get(k) is not None},
        "transcript": transcript(call.get("bland_details")),
        "recording": {"kept": False, "why": RECORDING_NOT_KEPT},
        "written": [{"channel": w.get("channel"), "from": w.get("from_addr"), "subject": w.get("subject"),
                     "text": w.get("body_text"), "recording_url": w.get("recording_url"),
                     "received_at": w["received_at"].isoformat() if hasattr(w.get("received_at"), "isoformat") else w.get("received_at")}
                    for w in written],
        "proof": {
            "read_back": shown_lines if shown_lines is not None else list(call.get("read_back_lines") or []),
            "read_back_sha256": call.get("read_back_sha256"),
            "approved": {"how": approval.get("how"), "said": approval.get("said"),
                         "at": approval.get("at") or (call["approved_at"].isoformat() if hasattr(call.get("approved_at"), "isoformat") else call.get("approved_at"))},
            "brief_sha256": call.get("brief_sha256"), "request_sha256": item.get("request_sha256") or call.get("request_sha256"),
            "placed_at": call["placed_at"].isoformat() if hasattr(call.get("placed_at"), "isoformat") else call.get("placed_at"),
        },
    }


@router.get("/{trip_item_id}/receipt")
async def receipt(trip_item_id: str, request: Request):
    from . import call_routes as CRT
    account = account_for(request)
    try:
        rows = await CRT.CALL_STORE.receipt_rows(account, trip_item_id)
    except StorageUnavailable as e:
        return JSONResponse({"ok": False, "rule": e.rule, "message": e.detail}, status_code=503)
    if rows is None:
        return JSONResponse({"ok": False, "rule": "receipt_unknown", "message": "no booking call of yours made that reservation"},
                            status_code=404)
    call = rows["call"]
    stored = call.get("brief", {}).get("venue_name") or rows["item"].get("provider_name") or "the venue"
    try:
        read = await CRT._read_of(account, call.get("brief") or {})
    except StorageUnavailable:
        read = None
    listed = (((read or {}).get("listing") or {}).get("name") or "").strip()
    venue = ({"name": listed, "source": "its Google Maps listing, read now (never stored)"} if listed
             else {"name": stored, "source": "their own website" if read else "as booked"})
    # the read-back exactly as the guest saw it: the stored marker is where the listing's name was shown
    lines = [ln.replace(CRT.LISTING_NAME_STORED, listed) for ln in call.get("read_back_lines") or []] if listed else None
    return build(call, rows["item"], rows["written"], venue, lines)


__all__ = ["router", "build", "transcript", "RECORDING_NOT_KEPT"]
