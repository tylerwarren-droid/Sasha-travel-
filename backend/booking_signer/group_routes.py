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
    account = account_for(request)
    body = await request.json()
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
    return await G.upload(account, rows, body.get("movement") or None)


# ── Sasha 333 · the traveller vault ──────────────────────────────────────────────────────────────────────────────────────

@router.post("/invite")
async def invite_vault(request: Request):
    """The organiser's "Invite to vault": one member, several, or all ({who: null}). Emailed where the list has their email; the rest
    come back as links to forward. The links carry no number."""
    from . import traveller_vault as TV
    body = await request.json()
    who = body.get("who")
    return await TV.invite(account_for(request), [str(x) for x in who] if isinstance(who, list) else None, body.get("movement") or None)


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
    """{action: book|swap|cancel, who: [names] | null, to: name (swap), over_ok} → AgAPI's read-backs as ONE card (its Yes / No)."""
    from . import group_book as GB
    body = await request.json()
    out = await GB.prepare(account_for(request), str(body.get("action") or ""), body.get("who") or None, body.get("to"), bool(body.get("over_ok")))
    if out.get("status") == "awaiting_yes":
        from app.agent.sasha import yes_buttons
        out = {**out, **(yes_buttons(f"group_{out['action']}", out) or {})}   # Sasha 330 · the ONE place a read-back gets its Yes / No
    return out


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
    return await GB.confirm(account, card, choice, str(body.get("said") or ("Yes, go ahead." if choice == "group_yes" else "")))


@router.get("/invoice")
async def group_invoice(request: Request):
    from . import group_book as GB
    account = account_for(request)
    inv = await GB.invoice(account)
    if not inv.get("why"):
        from . import groups as G
        mv = await G.store().movement(account)
        inv["link"] = GB.invoice_link(account, mv["id"])
    return inv


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
