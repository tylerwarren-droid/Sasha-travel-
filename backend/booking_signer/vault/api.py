"""S-78 §3, §7, §8, step 4 · THE VAULT'S ROUTES — the caller's own items only, metadata only, never a secret back.

  GET    /api/booking/vault                 → {items: [metadata + its uses], kinds (strongest first), consent, open}
  POST   /api/booking/vault                 {provider, label, kind, fields, special_category?, consent_version?, consent_sha256?}
  PUT    /api/booking/vault/{id}            {fields} → resealed with a NEW data key
  DELETE /api/booking/vault/{id}            → revoked: its keys and ciphertext deleted (crypto-shred), pending uses cancelled
  POST   /api/booking/vault/revoke-all      → every item revoked

  · R8 · a card number (13–19 digits passing Luhn) in ANY field is refused — payments go through Stripe.
  · V-2 · no standing permission: every use needs that booking's yes (crypto.use); nothing here grants one.
  · V-3 · no plaintext export and no "reveal" here: nothing in this module decrypts.
  · V-4 · a health (special-category) item is refused until a DPIA is recorded (SASHA_VAULT_HEALTH_DPIA_REF), and then
    only with the explicit Art. 9 consent below, its version and hash proving the words shown.
  · An `oauth` item is refused: no site is connected by sign-in yet, so offering it would promise what can't be done.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..account import account_for
from ..store import StorageUnavailable
from . import crypto, kms
from .guard import has_card_number

log = logging.getLogger("booking_signer.vault")
router = APIRouter(prefix="/vault", tags=["booking-vault"])
NOW = lambda: datetime.now(timezone.utc)

#: R7 · strongest first, with what each honestly is
KINDS = [
    {"kind": "oauth", "offered": False, "words": "Sign in with the site (revocable there) — no site is connected this way yet."},
    {"kind": "app_password", "offered": True, "words": "An app password the site issued for Sasha — revocable at the site without changing your password."},
    {"kind": "passkey", "offered": True, "words": "A passkey stays on your device, so Sasha can't use it: she prepares, and you sign in and press."},
    {"kind": "password", "offered": True, "words": "Your password — the last resort. If the site offers an app password or \"sign in with Google\", use that instead: it can be revoked without changing your password."},
    {"kind": "identifier", "offered": True, "words": "A number that identifies you (a loyalty or membership number) — not a password, still kept encrypted."},
]
FIELDS = {"app_password": ("username", "password"), "password": ("username", "password"), "identifier": ("value",), "passkey": ()}
HEALTH_CONSENT = {"v1": ("I explicitly consent to Sasha by Kanoe keeping this health-related access, encrypted, and using it only for "
                         "a booking I approve, one at a time. I can delete it at any time.")}
HEALTH_CURRENT = "v1"


def health_consent(version: str = HEALTH_CURRENT) -> dict:
    t = HEALTH_CONSENT[version]
    return {"version": version, "text": t, "sha256": hashlib.sha256(t.encode()).hexdigest()}


def dpia_ref() -> Optional[str]:
    return os.getenv("SASHA_VAULT_HEALTH_DPIA_REF", "").strip() or None


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _view(m: dict, uses=()) -> dict:
    return {**{k: _iso(v) for k, v in m.items()},
            "uses": [{"action_kind": u["action_kind"], "action_ref": u["action_ref"], "status": u["status"],
                      "started_at": _iso(u["started_at"]), "ended_at": _iso(u.get("ended_at"))} for u in uses]}


_PROVIDER = re.compile(r"^(?=.{3,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")


def _clean(body: dict) -> Any:
    """→ (provider, label, kind, fields) or a refusal."""
    provider = str(body.get("provider") or "").strip().lower()
    provider = re.sub(r"^https?://", "", provider).split("/")[0].removeprefix("www.")
    if not _PROVIDER.match(provider):
        return _refuse(422, "vault_provider_invalid", "name the site by its address, e.g. mercadona.es")
    label = re.sub(r"\s+", " ", str(body.get("label") or "")).strip()
    if not 1 <= len(label) <= 80:
        return _refuse(422, "vault_label_invalid", "give it a short name you'll recognise, e.g. \"Mercadona login\"")
    kind = body.get("kind")
    if kind == "oauth":
        return _refuse(422, "vault_oauth_unavailable", "no site is connected by sign-in yet; an app password is the next best")
    if kind not in FIELDS:
        return _refuse(422, "vault_kind_invalid", "choose an app password, a password, a passkey or a number")
    raw = body.get("fields") if isinstance(body.get("fields"), dict) else {}
    fields = {k: str(raw.get(k) or "") for k in FIELDS[kind]}
    if any(not v.strip() for v in fields.values()):
        return _refuse(422, "vault_fields_missing", f"fill in: {', '.join(k for k, v in fields.items() if not v.strip())}")
    if any(len(v) > 512 for v in fields.values()):
        return _refuse(422, "vault_field_too_long", "a field is longer than 512 characters")
    # R8 · in EVERY field — the site and the label too
    if any(has_card_number(v) for v in (provider, label, *fields.values())):
        log.info("[vault] a card number was refused (nothing stored)")
        return _refuse(422, "vault_card_refused", "Card numbers can't be saved here. Payments go through Stripe, which never shows us your card.")
    return provider, label, kind, fields


@router.get("")
async def vault_list(request: Request):
    account = account_for(request)
    try:
        items = await crypto.STORE.list(account)
        uses = await crypto.STORE.uses_of(account)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"items": [_view(m, [u for u in uses if u["item_id"] == m["id"]]) for m in items], "kinds": KINDS,
            "open": kms.status(), "health": {"allowed": bool(dpia_ref()), "consent": health_consent()}}


@router.post("")
async def vault_create(request: Request):
    account = account_for(request)
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        return _refuse(400, "vault_malformed", "send {provider, label, kind, fields}")
    c = _clean(body)
    if isinstance(c, JSONResponse):
        return c
    provider, label, kind, fields = c
    special = bool(body.get("special_category"))
    consent: Dict[str, Any] = {}
    if special:
        if not dpia_ref():
            log.warning("[vault] a health item was refused: no DPIA is recorded (V-4)")
            return _refuse(422, "vault_health_needs_dpia", "health-related accesses can't be saved yet — that needs a data-protection "
                                                            "assessment first, and it hasn't been done")
        hc = health_consent()
        if body.get("consent_version") != hc["version"] or body.get("consent_sha256") != hc["sha256"]:
            return _refuse(422, "vault_health_consent", "tick the consent sentence shown — it must be the current one")
        consent = {"consent_at": NOW(), "consent_wording_version": hc["version"], "consent_text_sha256": hc["sha256"]}
    item_id, now = str(uuid.uuid4()), NOW()
    try:
        sealed = await crypto.seal(account, item_id, kind, json.dumps(fields).encode()) if kind != "passkey" else {}
    except kms.VaultClosed as e:
        return _refuse(503, e.rule, str(e))
    try:
        await crypto.STORE.create({"id": item_id, "account_id": account, "provider": provider, "label": label, "kind": kind,
                                   **sealed, "special_category": special, **consent, "created_at": now, "updated_at": now})
        await crypto.STORE.event(account, item_id, "created", {"kind": kind, "provider": provider, "special_category": special}, now)
        m = await crypto.STORE.get(account, item_id)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"item": _view(m), "say": next(k["words"] for k in KINDS if k["kind"] == kind)}


@router.put("/{item_id}")
async def vault_update(item_id: str, request: Request):
    account = account_for(request)
    try:
        body = await request.json()
        m = await crypto.STORE.get(account, item_id) if _uuid(item_id) else None
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    except Exception:
        body, m = None, None
    if m is None or m.get("revoked_at"):
        return _refuse(404, "vault_item_unknown", "no saved access of yours with that id")
    if m["kind"] == "passkey":
        return _refuse(422, "vault_passkey", "a passkey has nothing to change here — it stays on your device")
    c = _clean({**(body or {}), "provider": m["provider"], "label": m["label"], "kind": m["kind"]})
    if isinstance(c, JSONResponse):
        return c
    try:
        sealed = await crypto.seal(account, item_id, m["kind"], json.dumps(c[3]).encode())
        ok = await crypto.STORE.reseal(account, item_id, sealed, NOW())
        if ok:
            await crypto.STORE.event(account, item_id, "updated", {}, NOW())
    except kms.VaultClosed as e:
        return _refuse(503, e.rule, str(e))
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"updated": ok}


def _uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except ValueError:
        return False


def _revoked_words(m: dict) -> str:
    if m["kind"] in ("password", "app_password"):
        return (f"Sasha has deleted her copy. To be sure nobody can use it, change the password at {m['provider']}"
                + (" (or revoke the app password there)." if m["kind"] == "app_password" else "."))
    return "Sasha has deleted her copy."


@router.delete("/{item_id}")
async def vault_revoke(item_id: str, request: Request):
    account = account_for(request)
    if not _uuid(item_id):
        return _refuse(404, "vault_item_unknown", "no saved access of yours with that id")
    try:
        m = await crypto.STORE.revoke(account, item_id, NOW())
        if m:
            await crypto.STORE.event(account, item_id, "revoked", {}, NOW())
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if m is None:
        return _refuse(404, "vault_item_unknown", "no saved access of yours with that id (or it was already revoked)")
    return {"revoked": True, "say": _revoked_words(m)}


@router.post("/revoke-all")
async def vault_revoke_all(request: Request):
    account = account_for(request)
    try:
        items = [m for m in await crypto.STORE.list(account) if not m.get("revoked_at")]
        done = []
        for m in items:
            r = await crypto.STORE.revoke(account, m["id"], NOW())
            if r:
                await crypto.STORE.event(account, m["id"], "revoked", {"all": True}, NOW())
                done.append(r)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    try:   # S-79 · a calendar connection's token is among them: its link goes too
        from .. import calendar_sync as CS
        if CS.STORE is not None and any(m["kind"] == "oauth" for m in done):
            await CS.STORE.delete_link(account)
    except StorageUnavailable as e:
        log.warning("[vault] the calendar link was not removed: %s", e.detail)
    return {"revoked": len(done), "say": [f"{m['label']}: {_revoked_words(m)}" for m in done]}


__all__ = ["router", "KINDS", "health_consent", "dpia_ref"]
