"""Sasha 332 · the group movement's S2 page: the master list (read live) and the organiser's list upload. /api/booking/group/*"""
from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, HTTPException, Request

from .account import account_for
from . import groups as G

log = logging.getLogger("booking_signer.group_routes")
router = APIRouter(prefix="/group", tags=["group"])
MAX_BYTES = 5 * 1024 * 1024


@router.get("/list")
async def master_list(request: Request):
    """THE MASTER LIST: one row per worker, computed from each worker's trip now (never stored)."""
    return await G.view(account_for(request), request.query_params.get("movement") or None)


@router.post("/upload")
async def upload(request: Request):
    """The organiser's list: {text} pasted / typed, or {name, media_type, content_base64} — a csv, an xlsx or a photo of one."""
    from . import group_outcome as GO
    account = account_for(request)
    body = await request.json()
    if not body.get("text") and not body.get("content_base64"):   # Sasha 346 · nothing given → said, by the field's name
        return await GO.run(account, "add", {"rows": None})
    if body.get("text"):
        rows = G.read_text(str(body["text"])[:200_000])
    else:
        try:
            data = base64.b64decode(str(body.get("content_base64") or ""), validate=True)
        except Exception:
            raise HTTPException(400, {"ok": False, "rule": "not_a_file", "message": "that file couldn't be read"})
        if not data or len(data) > MAX_BYTES:
            raise HTTPException(400, {"ok": False, "rule": "file_size", "message": "send a list up to 5 MB"})
        name, mt = str(body.get("name") or "").lower(), str(body.get("media_type") or "").lower()
        if name.endswith(".xlsx") or "spreadsheetml" in mt:
            rows = G.read_xlsx(data)
        elif name.endswith((".csv", ".txt")) or mt in ("text/csv", "text/plain"):
            rows = G.read_csv(data)
        elif mt in ("image/jpeg", "image/png", "image/webp", "image/heic"):
            rows = await G.read_photo(data, mt)
        else:
            raise HTTPException(400, {"ok": False, "rule": "file_type", "message": "send a .csv or .xlsx file, a photo of the list, or paste it"})
    return await GO.run(account, "add", {"rows": rows, "movement": body.get("movement") or None,
                                         "on_trip": body.get("on_trip") is not False, "company": body.get("company")})   # Sasha 358


# ── Sasha 351 · THE ROSTER: the company's people (each once — their profile and their own vault); a trip chooses from it ─────────

@router.get("/people")
async def people(request: Request):
    """The company's roster: each person once, with ✓ / missing for their passport (never a number)."""
    return await G.roster(account_for(request))


@router.post("/people")
async def people_add(request: Request):
    """{rows: [{name, grade, home_airport, home_city, email, phone}]} or {text} (a pasted list) → onto the roster (the ONE outcome)."""
    from . import group_outcome as GO
    body = await request.json()
    rows = body.get("rows") if isinstance(body.get("rows"), list) else (G.read_text(str(body.get("text"))[:200_000]) if body.get("text") else None)
    return await GO.run(account_for(request), "person_add", {"rows": rows or None, "company": body.get("company"),
                                                             "on_trip": bool(body.get("on_trip")), "trip": body.get("trip")})   # Sasha 358


@router.post("/people/{person_id}")
async def people_edit(person_id: str, request: Request):
    from . import group_outcome as GO
    body = await request.json()
    return await GO.run(account_for(request), "person_edit", {"person_id": person_id, "fields": body if isinstance(body, dict) else {}})


@router.post("/people/{person_id}/documents")
async def people_documents(person_id: str, request: Request):
    """Their own vault page (passport and loyalty numbers, saved once for every trip) — opened here or forwarded to them."""
    from . import group_outcome as GO
    return await GO.run(account_for(request), "documents", {"person_id": person_id})


@router.post("/choose")
async def choose(request: Request):
    """{who: [person ids or names]} → those roster people on this trip (a link each), then each planned from their home airport."""
    from . import group_outcome as GO
    body = await request.json()
    who = body.get("who") if isinstance(body.get("who"), list) else None
    return await GO.run(account_for(request), "choose", {"who": who or None, "movement": body.get("movement")})


# ── Sasha 358 · THE GROUP ENGINE's doors: the one view, [Go], and one person's switch ───────────────────────────────────────────

@router.get("/state")
async def state(request: Request):
    """THE view (groups.state): the roster with each person's switch (the record itself), the open trip and its list, the trips."""
    return await G.state(account_for(request), request.query_params.get("trip") or None)


@router.post("/create")
async def create(request: Request):
    """[Go]: {destination, starts_on, ends_on, hotel_area, who: [person ids], company?} → the trip made, who's going on it, each planned."""
    from . import group_outcome as GO
    body = await request.json()
    who = body.get("who") if isinstance(body.get("who"), list) else None
    return await GO.run(account_for(request), "create", {k: body.get(k) for k in ("destination", "starts_on", "ends_on", "hotel_area", "company")}
                        | {"who": who})


@router.post("/switch")
async def switch(request: Request):
    """{person, on, trip?} → that person on the trip or off it (the engine's set_on_trip): said; booked → Cancel offered."""
    from . import group_outcome as GO
    body = await request.json()
    return await GO.run(account_for(request), "switch", {"person": body.get("person"), "on": body.get("on") is not False, "trip": body.get("trip")})


@router.get("/trips")
async def trips(request: Request):
    """Sasha 351 · the organiser's trips, the OPEN one first (each a selection from the one roster)."""
    return await G.trips(account_for(request))


@router.post("/open")
async def open_trip(request: Request):
    """{trip: id or destination} → that trip is the open one: the list, booking and the invoice are about it."""
    from . import group_outcome as GO
    body = await request.json()
    return await GO.run(account_for(request), "open", {"trip": body.get("trip")})


# ── Sasha 333 · the traveller vault ──────────────────────────────────────────────────────────────────────────────────────

@router.post("/invite")
async def invite_vault(request: Request):
    """The organiser's "Invite to vault": one member, several, or all ({who: null}). Emailed where the list has their email; the rest
    come back as links to forward. The links carry no number."""
    from . import group_outcome as GO   # Sasha 346 · the ONE outcome: who was invited, or exactly why nobody
    body = await request.json()
    who = body.get("who")
    return await GO.run(account_for(request), "invite", {"who": [str(x) for x in who] if isinstance(who, list) else None})


# the member's own page: NO account — the signed, single-person, 7-day token IS the key (gate.py lets /api/booking/vault/ through)
vault = APIRouter(prefix="/vault", tags=["vault"])


def _refused(e):
    from fastapi.responses import JSONResponse
    return JSONResponse({"ok": False, "rule": e.rule, "message": e.message}, status_code=403 if e.rule == "link_expired" else 400,
                        headers={"Cache-Control": "no-store"})


@vault.get("/{token}")
async def vault_page(token: str):
    from . import traveller_vault as TV
    try:
        return await TV.page(token)
    except TV.VaultRefused as e:
        return _refused(e)


@vault.post("/{token}")
async def vault_save(token: str, request: Request):
    from . import traveller_vault as TV
    body = await request.json()
    try:
        return await TV.save(token, body.get("passport") if isinstance(body.get("passport"), dict) else None,
                             [x for x in body.get("loyalty") or [] if isinstance(x, dict)][:10])
    except TV.VaultRefused as e:
        return _refused(e)


@vault.delete("/{token}")
async def vault_delete(token: str, request: Request):
    from . import traveller_vault as TV
    try:
        return await TV.erase(token, request.query_params.get("item") or None)
    except TV.VaultRefused as e:
        return _refused(e)


# ── Sasha 334 · the master list's actions, the invoice, and the Keep resolver ─────────────────────────────────────────────

@router.post("/act")
async def group_act(request: Request):
    """{action: book|swap|cancel, who: [names] | null, to: name (swap), over_ok} → AgAPI's read-backs as ONE card (its Yes / No).
    Sasha 339 · BOOK runs as ONE background job (group_book.start): this answers at once with its progress; GET /group/job follows it."""
    from . import group_outcome as GO
    body = await request.json()
    account, action = account_for(request), str(body.get("action") or "")
    # Sasha 346 · EVERY action answers from the record (group_outcome — the ONE place): what was done, or exactly why not and what's
    # missing. book → its background job (Sasha 339) only when someone can be booked; swap/cancel → AgAPI's card, or the list's own swap
    out = await GO.run(account, action if action in ("book", "swap", "cancel") else "?" + action,
                       {"who": body.get("who") or None, "to": body.get("to"), "to_city": body.get("to_city"), "to_grade": body.get("to_grade"),
                        "over_ok": bool(body.get("over_ok"))})
    return _with_buttons(out)


def _with_buttons(out: dict) -> dict:
    from app.agent.sasha import yes_buttons
    if out.get("status") == "awaiting_yes":
        out = {**out, **(yes_buttons(f"group_{out['action']}", out) or {})}   # Sasha 330 · the ONE place a read-back gets its Yes / No
    if out.get("reasked"):   # Sasha 340 · each moved fare's own card — the same one place
        out = {**out, "reasked": [{**x, **(yes_buttons(f"group_{x['action']}", x) or {})} for x in out["reasked"]]}
    return out


@router.get("/waiting")
async def group_waiting(request: Request):
    """Sasha 340 · the moved-fare cards still waiting for a yes (each its own Yes / No) — the page asks on load."""
    from . import group_book as GB
    return {"reasked": _with_buttons({"reasked": GB.waiting_cards(account_for(request))})["reasked"]
            if GB.waiting_cards(account_for(request)) else []}


@router.get("/job")
async def group_job(request: Request):
    """Sasha 339 · the book job's progress ("Preparing 18… 12 ready"), then its ONE card (with its Yes / No) or what held each worker."""
    from . import group_book as GB
    v = GB.job_view(account_for(request))
    if v.get("result"):
        v = {**v, "result": _with_buttons(v["result"])}
    return v


@router.post("/confirm")
async def group_confirm(request: Request):
    """{card, choice} — once per card (card_tap's claim rule: the durable key card_tap:<account>:<card>:<choice>)."""
    from . import group_book as GB
    from agapi import v0 as API
    account = account_for(request)
    body = await request.json()
    card, choice = str(body.get("card") or "")[:80], str(body.get("choice") or "")
    ctx = API.Ctx(account=account, mode="test", user_said=str(body.get("said") or ""))
    ctx.idem = f"card_tap:{account}:{card}:{choice}"
    try:
        await API.claim(ctx)
    except API.ToolError:
        return {"status": "nothing_waiting", "say": "That card's already answered."}
    return _with_buttons(await GB.answer(account, card, choice, str(body.get("said") or ("Yes, go ahead." if choice == "group_yes" else ""))))   # Sasha 339 · a job when several


@router.get("/invoice")
async def group_invoice(request: Request):
    from . import group_outcome as GO   # Sasha 346 · nothing booked → said; else the link (the page shows it — never a blocked pop-up)
    return await GO.run(account_for(request), "invoice", {})


invoice_public = APIRouter(prefix="/group-invoice", tags=["group"])


@invoice_public.get("/{token}")
async def invoice_by_link(token: str):
    """The invoice's own link (sent on WhatsApp): signed, that organiser's movement only, 30 days — no sign-in."""
    from fastapi.responses import JSONResponse
    from . import group_book as GB
    t = GB.read_invoice_token(token)
    if not t:
        return JSONResponse({"ok": False, "rule": "link_expired", "message": "This invoice link has expired — ask Sasha for a new one."}, status_code=403)
    return await GB.invoice(t["owner"])


resolver = APIRouter(prefix="/keep", tags=["keep"])


@resolver.post("/resolve")
async def keep_resolve(request: Request):
    """CR 163's ask: AgAPI opens a keep:<id> reference at booking time — HMAC-signed, fresh, and only for the worker Sasha is booking now."""
    from fastapi.responses import JSONResponse
    from . import keep_resolver as KR
    body = await request.body()
    try:
        return JSONResponse(await KR.resolve(body, request.headers.get("x-agapi-signature")), headers={"Cache-Control": "no-store"})
    except KR.Refused as e:
        return JSONResponse({"ok": False, "rule": e.rule}, status_code=e.status)
