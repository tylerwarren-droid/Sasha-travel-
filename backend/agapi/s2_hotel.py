"""Sasha 235 · UPGRADE MY ROOM (/s2 only): a request to the hotel they're booked at — drafted to the address the hotel publishes on
its OWN site (the ladder's venue read), read back, sent only on their yes in a later turn (send_email's own read-back, yes and
capture: live only for the allow-listed accounts), and the hotel's reply said in THEIR words.

A TEST stay (every stay booked through Sasha today: a TEST- reference, no hotel contacted) was never made at the real hotel, so
its requests go to OUR test hotel (Kanoe Test Hotel, form_rung.test_hotel_desk) — captured, never sent anywhere — and the test
hotel answers with a scripted reply that says it's a test. Never a real hotel in a test.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("agapi.s2_hotel")
TEST_HOTEL = "Kanoe Test Hotel"
REPLIES: Dict[str, dict] = {}   # account → the hotel's latest reply (their words), for "did they answer?"

# our test hotel's scripted answer — its words, in its language, saying it's a test
TEST_REPLY = {
    "upgrade": ("Buenos días: gracias por su mensaje. Para su estancia podemos ofrecerle una habitación superior con vistas por "
                "25 € más por noche, o sin coste si a su llegada queda alguna libre. Díganos cuál prefiere. Un saludo, Recepción · "
                "Kanoe Test Hotel (hotel de pruebas de Kanoe: no es un hotel real)."),
    "other": ("Buenos días: gracias por su mensaje. Tomamos nota de su petición y se la confirmamos a su llegada. Un saludo, "
              "Recepción · Kanoe Test Hotel (hotel de pruebas de Kanoe: no es un hotel real)."),
}
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def is_test_stay(stay: dict) -> bool:
    from booking_signer import hotel_test as HT
    return str(stay.get("reference") or "").startswith("TEST-") or HT.MARK in str(stay.get("title") or "")


def plain_hotel(title: str) -> str:
    from booking_signer import hotel_test as HT
    return str(title or "").replace(HT.MARK, "").strip() or "your hotel"


def draft(stay: dict, ask: str, name: str, spanish: bool) -> Dict[str, str]:
    """The message: their reservation, the request, their name. Deterministic (the read-back's hash must match on the yes)."""
    hotel, ref, nights = plain_hotel(stay.get("title")), stay.get("reference") or "", int(stay.get("nights") or 1)
    try:
        d = date.fromisoformat(str(stay.get("when") or "")[:10])
    except ValueError:
        d = None
    upgrade = ask == "upgrade"
    if spanish:
        cuando = f"el {d.day} de {_MESES[d.month - 1]} de {d.year}" if d else "en la fecha de mi reserva"
        want = ("¿Sería posible una mejora de habitación? Si tiene un coste, ¿me pueden decir cuánto?" if upgrade else f"Quería pedirles: {ask}.")
        body = (f"Hola:\n\nTengo una reserva en {hotel}" + (f" (localizador {ref})" if ref else "") + f", con llegada {cuando}, "
                f"{nights} noche{'s' if nights > 1 else ''}, a nombre de {name}.\n\n{want}\n\nGracias,\n{name}")
        subject = ("Petición de mejora de habitación" if upgrade else "Petición para mi estancia") + (f" — reserva {ref}" if ref else "")
    else:
        when = d.strftime("%-d %B %Y") if d else "on my reservation's date"
        want = ("Would a room upgrade be possible? If there's a charge, could you tell me how much?" if upgrade else f"I'd like to ask: {ask}.")
        body = (f"Hello,\n\nI have a reservation at {hotel}" + (f" (reference {ref})" if ref else "") + f", arriving {when}, "
                f"{nights} night{'s' if nights > 1 else ''}, under the name {name}.\n\n{want}\n\nThank you,\n{name}")
        subject = ("Room upgrade request" if upgrade else "A request for my stay") + (f" — reservation {ref}" if ref else "")
    return {"subject": subject, "body": body}


async def _desk(ctx, stay: dict) -> Optional[dict]:
    """The hotel's address, READ from its own site through the ladder ({address, name, source}). A TEST stay → our test hotel."""
    from agapi import venues as VN
    from booking_signer import form_rung as FR
    GW = VN._API()
    if is_test_stay(stay):
        body = {"name": TEST_HOTEL, "city": stay.get("where") or "Madrid", "country": "ES", "website": FR.test_venue_url("hotel")}
        label = TEST_HOTEL
    else:
        if not stay.get("website"):
            return None
        body = {"name": plain_hotel(stay.get("title")), "city": stay.get("where") or "", "website": stay["website"]}
        label = body["name"]
    status, rd = await GW.api(ctx.account, "POST", "/api/booking/venues/read", body)
    if status != 200:
        log.info("[s2_hotel] the hotel's site wasn't read: %s", status)
        return None
    for f in (rd or {}).get("facts") or []:
        if f.get("kind") == "email" and "@" in str(f.get("value") or ""):
            return {"address": f["value"], "name": label, "source": f.get("source_url") or body["website"],
                    "test": label == TEST_HOTEL}
    return None


async def hotel_request(ctx, a: dict) -> dict:
    from agapi.v0 import ToolError
    from agapi import s2_manage as M, s2_tools as S2T
    if a.get("check_reply"):
        r = REPLIES.get(ctx.account)
        if not r:
            return {"status": "no_reply_yet", "say": "Say plainly there's no reply from the hotel yet."}
        return {"status": "replied", "their_reply": r, "how": "Say who replied and quote their words exactly; then, if it's not English, a short translation."}
    stays = [p for p in await M.plans_of(ctx.account) if p.get("kind") == "hotel" and p.get("status") == "booked"]
    if a.get("hotel"):
        want = str(a["hotel"]).lower()
        stays = [s for s in stays if want in plain_hotel(s.get("title")).lower()] or stays
    stays.sort(key=lambda s: str(s.get("when") or ""))
    today = datetime.now(timezone.utc).date().isoformat()
    stay = next((s for s in stays if str(s.get("when") or "") >= today), stays[-1] if stays else None)
    if not stay:
        raise ToolError("no_stay", "there's no booked hotel stay on their account to ask about")
    desk = await _desk(ctx, stay)
    if not desk:
        raise ToolError("no_contact", f"{plain_hotel(stay.get('title'))}'s own site doesn't list an email I can write to")
    from agapi import venues as VN
    _s, cj = await VN._API().api(ctx.account, "GET", "/api/booking/contact")
    name = ((cj or {}).get("contact") or {}).get("name") or "Guest"
    ask = "upgrade" if str(a.get("ask") or "upgrade").strip().lower() in ("upgrade", "room upgrade", "upgrade my room") else str(a["ask"])[:200]
    msg = draft(stay, ask, name, spanish=desk["test"] or str(desk["address"]).endswith(".es"))
    out = await S2T.send_email(ctx, {"to": {"address": desk["address"], "name": desk["name"]}, **msg,
                                     "approval": {"said": ((a.get("approval") or {}).get("said")) or ctx.user_said or ""}})
    via = f"{desk['name']}'s own website lists {desk['address']} for guests' requests." + (
        " This stay is a TEST booking, so it goes to our test hotel — captured, it never leaves Kanoe." if desk["test"] else "")
    if out.get("status") == "awaiting_yes":
        return {**out, "read_back": [via, *out.get("read_back", [])],
                "say": "Read it back exactly (the first line too), then ask: shall I send it?"}
    reply = None
    if desk["test"]:   # our test hotel answers — its own words, scripted, and it says it's a test
        reply = {"from": f"Recepción · {TEST_HOTEL}", "text": TEST_REPLY["upgrade" if ask == "upgrade" else "other"], "test": True,
                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        REPLIES[ctx.account] = reply
    return {**out, **({"their_reply": reply} if reply else {}),
            "how": ((out.get("say") or "") + (" Then their reply, in their words, quoted exactly — then a short translation."
                                               if reply else " Their reply comes back here when it arrives."))}


def tools() -> List[dict]:
    from agapi.v0 import _t
    appr = {"approval": {"type": "object", "properties": {"said": {"type": "string"}}}}
    return [
        _t("hotel_request", "Austen", hotel_request, "A request to the hotel they're booked at — 'Upgrade my room' → ask='upgrade' (or "
           "their words: a late check-out, a quiet room…). Written to the address the hotel publishes on its own website. FIRST call: "
           "the read-back — read it exactly and ask; after their yes in a LATER turn, call again (same ask) to send. When the hotel "
           "replies, say their words exactly. check_reply=true: has the hotel answered?",
           {"ask": {"type": "string"}, "hotel": {"type": "string"}, "check_reply": {"type": "boolean"}, **appr}, [],
           {"type": "object", "properties": {"status": {"type": "string"}}},
           ["no_stay", "no_contact", "no_explicit_yes", "invalid_input"], austen=True),
    ]
