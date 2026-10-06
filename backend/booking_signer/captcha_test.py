"""Sasha 159 (5) · "send me the captcha test" — the founder's own proof, on demand: a FRESH live hand-over of OUR test venue's
CAPTCHA page (Google's documented reCAPTCHA v2 TEST key, a fictional guest, no reservation anywhere), and ONE WhatsApp tap
to his phone (guest_whatsapp.tap_to_finish). Founder only. The session lasts handover.SESSION_SECONDS (10 minutes).
"""
from __future__ import annotations

import re
from typing import Optional

ASK = re.compile(r"\b(?:send|give|open)\s+(?:me\s+)?(?:the\s+|a\s+)?captcha\s+test\b", re.I)


def asked(message: str) -> bool:
    return bool(ASK.search(message or ""))


async def send(account: Optional[str]) -> str:
    """The sentence to say back. Never raises."""
    from . import form_rung as FR, guest_whatsapp as GW, handover as H
    from .guest_accounts import founder
    if not founder(account):
        return "The CAPTCHA test is the founder's — nothing was sent."
    url = FR.test_venue_url("captcha")
    m = FR.form_map(url)
    vals = {**H.FICTIONAL, "date": "2026-12-15", "time": "21:00"}
    step1 = [{"name": n, "value": vals[r], "label": lbl} for n, (r, lbl) in m["fields"].items() if r in vals]
    o = {"what": {"activity": "table", "activity_venue_lang": "mesa", "category": "restaurant"},
         "when": {"mode": "at", "at": "2026-12-15T21:00"}, "how_many": {"count": 2, "unit": "people"},
         "who": {"name": H.FICTIONAL["person_name"]}}
    try:
        rec = await H.open_handover(page_url=url, m=m, step1=step1, step2=[], venue="Sasha Test Venue (CAPTCHA test)", account=account,
                                    form_id=None, read_only=False, request=o, fictional=True)
    except H.Refused as e:
        return f"I couldn't open the CAPTCHA test — {e.say}."
    except Exception as e:   # never a stopped chat
        return f"I couldn't open the CAPTCHA test ({type(e).__name__})."
    out = await GW.tap_to_finish(account, "Sasha Test Venue (CAPTCHA test)", H.view_url(rec),
                                 "a fictional guest; tick “I'm not a robot”, then Reservar")
    mins = H.SESSION_SECONDS // 60
    if out.startswith("not"):
        return f"The CAPTCHA test is ready, but the WhatsApp tap wasn't sent ({out[5:]}). Open it here: {H.view_url(rec)} — live for {mins} minutes."
    return f"Sent — tap it on your phone: tick “I'm not a robot”, then Reservar. It's live for {mins} minutes."


__all__ = ["asked", "send", "ASK"]
