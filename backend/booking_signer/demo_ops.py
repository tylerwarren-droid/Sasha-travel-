"""Sasha 121 · the INVESTOR DEMO's controls — founder only, every one honest about what it is.

  POST /api/booking/ops/demo/leave-now    E · the "time to leave" for his next confirmed booking, on WhatsApp NOW: the real
                                          route time (Routes API, from his saved starting point), labelled "sent early for
                                          the demo" — never a "time to leave" that isn't.
  POST /api/booking/ops/demo/gmail-seed   G · OUR test venue emails a booking confirmation to the Gmail he connected
                                          (it says it's Kanoe's test restaurant); then Sasha's Gmail check runs and the
                                          find is offered on WhatsApp — the real path from there on.
  POST /api/booking/ops/demo/reset        every demo booking at our test venue cancelled (the calendar loop then removes
                                          its events), their Gmail finds and reminder ledger cleared, his open WhatsApp
                                          question closed, the demo shop's orders cleared. Real bookings are untouched.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .store import StorageUnavailable

log = logging.getLogger("booking_signer.demo_ops")
router = APIRouter(prefix="/ops/demo", tags=["booking-ops"])
TEST_VENUE = "Sasha Test Venue"
NOW = lambda: datetime.now(timezone.utc)


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


async def _tell(account: str, text: str) -> str:
    from . import guest_whatsapp as GW
    ch = await GW.STORE.channel_of_account(account) if GW.STORE else None
    if not ch or not GW.guest_numbers():
        return "not sent: no WhatsApp linked"
    st = await GW.STORE.get_state(ch["wa_id_sha256"])
    return ", ".join(await GW.deliver(ch, sorted(GW.guest_numbers())[0], GW.Out().text(text), st.get("last_inbound_at")))


@router.post("/leave-now")
async def leave_now(request: Request):
    from .ops import founder_only
    from . import guest_whatsapp as GW, proactive as PR
    no = founder_only(request)
    if no:
        return no
    from .account import account_for
    account = account_for(request)
    rows = [r for r in await GW._upcoming(account) if r.get("status") in PR.CONFIRMED and PR.starts_at(r)]
    if not rows:
        return _refuse(422, "no_confirmed_booking", "you have no confirmed booking ahead to leave for")
    b = min(rows, key=PR.starts_at)
    place = await PR.STORE.default_place(account)
    if not place:
        return _refuse(422, "no_starting_point", "save a starting point in You first — Sasha never guesses a travel time")
    mode = os.getenv("SASHA_PROACTIVE_MODE", "TRANSIT")
    secs = await PR.travel(place["address"], f"{b.get('venue')}, {b.get('address') or 'Madrid'}", PR.starts_at(b), mode)
    if not secs:
        return _refuse(502, "no_route", "the Routes API gave no route, so no time to leave is sent")
    text = PR.render("leave_now", b, {"minutes": round(secs / 60), "mode_words": PR.MODE_WORDS.get(mode, ""), "label": place["label"]}, NOW())
    said = f"(Demo — sent early.) When it's time, this is what arrives: {text}"
    return {"ok": True, "text": said, "whatsapp": await _tell(account, said)}


async def _gmail_address(account: str) -> Optional[str]:
    from . import mailbox as MB
    from .vault import crypto as VC
    link = await MB.STORE.get_link(account)
    if not link:
        return None
    token = await VC.use_connection(account, link["vault_item_id"], purpose="gmail_read")
    s, j = await MB.GMAIL_HTTP("GET", f"{MB.GMAIL}/profile", token)
    return j.get("emailAddress") if s == 200 else None


@router.post("/gmail-seed")
async def gmail_seed(request: Request):
    from .ops import founder_only
    from . import emailing as E, ladder_routes as LR, mailbox as MB
    no = founder_only(request)
    if no:
        return no
    from .account import account_for
    account = account_for(request)
    to = await _gmail_address(account)
    if not to:
        return _refuse(422, "gmail_not_connected", "connect Gmail in You first")
    day = (NOW().astimezone(ZoneInfo("Europe/Madrid")) + timedelta(days=6)).date()
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    ref = "TV-" + uuid.uuid4().hex[:6].upper()
    domain = os.getenv("SASHA_INBOUND_DOMAIN", "booking.kanoe.ai").strip()
    sent = await E.send(LR.HTTP, {"from": f"{TEST_VENUE} <reservas-prueba@{domain}>", "to": to,
                                  "subject": f"Reserva confirmada en {TEST_VENUE}",
                                  "text": f"Hola,\n\nTu reserva está confirmada: {dias[day.weekday()]} {day.day} de {meses[day.month - 1]} a las 21:00, "
                                          f"2 personas. Localizador: {ref}.\n\n¡Te esperamos!\n\n{TEST_VENUE} — el restaurante de pruebas de "
                                          f"Kanoe (no es un restaurante real)."})
    if not sent.sent:
        return _refuse(502, "seed_not_sent", f"the test venue's email was not sent: {sent.why}")
    for _ in range(6):   # Gmail takes a moment to file it
        await asyncio.sleep(5)
        found = await MB.sync(account)
        hit = next((f for f in found if (f.get("facts") or {}).get("reference") == ref), None)
        if hit:
            return {"ok": True, "to": to, "reference": ref, "offered": hit.get("offered_sentence")}
    return {"ok": True, "to": to, "reference": ref, "offered": None,
            "say": "sent; Gmail hadn't filed it within 30 seconds — press 'Check my email now' in You"}


@router.post("/reset")
async def reset(request: Request):
    from .ops import founder_only
    from . import demo_shop as DS, guest_whatsapp as GW, ladder_routes as LR
    no = founder_only(request)
    if no:
        return no
    from .account import account_for
    account = account_for(request)
    a = uuid.UUID(account)

    async def go(c):
        async with c.transaction():
            items = [r["id"] for r in await c.fetch(
                "select ti.id from trip_items ti join trips t on t.id = ti.trip_id where t.owner_id = $1 and ti.provider_name = $2 "
                "and ti.status <> 'cancelled'", a, TEST_VENUE)]
            n_items = await c.execute("update trip_items set status = 'cancelled', updated_at = now() where id = any($1)", items)
            n_finds = await c.execute("delete from mailbox_finds where account_id = $1 and facts->>'venue' = $2", a, TEST_VENUE)
            n_sent = await c.execute("delete from proactive_sent where account_id = $1 and trip_item_id in (select ti.id from trip_items ti "
                                     "join trips t on t.id = ti.trip_id where t.owner_id = $1 and ti.provider_name = $2)", a, TEST_VENUE)
            return {"test_venue_bookings_cancelled": int(n_items.split()[-1]), "gmail_finds_cleared": int(n_finds.split()[-1]),
                    "reminder_ledger_cleared": int(n_sent.split()[-1])}
    try:
        out = await LR.LADDER_STORE._run(go)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    ch = await GW.STORE.channel_of_account(account) if GW.STORE else None
    if ch:
        st = await GW.STORE.get_state(ch["wa_id_sha256"])
        st["pending"] = None
        await GW.STORE.put_state(ch["wa_id_sha256"], st)
    out["demo_shop_orders_cleared"] = len(DS.ORDERS)
    DS.ORDERS.clear()
    return {"ok": True, **out, "say": "Demo reset: test-venue bookings cancelled (their calendar events go within a minute); real bookings untouched."}


__all__ = ["router"]
