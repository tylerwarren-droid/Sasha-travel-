"""Sasha 419 · Julia's door: /api/booking/products/julia/* — called ONLY by the LuxuryOffseason site's server, which embeds her (KANOE
13:29), with JULIA_SITE_SECRET (X-Julia-Key). Nothing is stored: the conversation lives in the person's page; transcripts are logged only
through the S-78 guard's for_log."""
from __future__ import annotations

import base64
import hmac
import json
import os

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from . import julia as J

router = APIRouter(prefix="/julia", tags=["luxury"])


def _authorized(request: Request) -> None:
    secret = os.getenv("JULIA_SITE_SECRET", "")
    got = request.headers.get("x-julia-key", "")
    if not secret:
        raise HTTPException(status_code=503, detail="julia is not configured")
    if not hmac.compare_digest(secret.encode(), got.encode()):
        raise HTTPException(status_code=401, detail="not the LuxuryOffseason site")


async def _voiced(say: str, lang: str) -> str:
    audio = await J.speak(say, lang)
    return base64.b64encode(audio).decode() if audio else ""


@router.post("/hello")
async def hello(request: Request):
    """Her introduction, before anything else (the page plays it when the person first opens her)."""
    _authorized(request)
    return {"say": J.HELLO["en"], "lang": "en", "audio": await _voiced(J.HELLO["en"], "en")}


@router.post("/turn")
async def turn(request: Request, audio: UploadFile = File(...), history: str = Form(default="[]")):
    _authorized(request)
    from app.services.deepgram_service import transcribe_audio
    from booking_signer.vault.guard import for_log, looks_like_secret
    raw = await audio.read()
    if not raw or len(raw) > 8_000_000:
        raise HTTPException(status_code=400, detail="no audio")
    heard = await transcribe_audio(raw, audio.content_type or "audio/webm", language="detect")
    said = (heard.get("transcript") or "").strip()
    lang = J.lang_of(heard.get("language"))
    if not said:
        return {"heard": False, "lang": lang}
    if looks_like_secret(said):   # S-78: a password, code or card number spoken never reaches the model
        said = "(something private, not repeated)"
    print(f"[Julia] heard ({lang}): {for_log(said)}")
    try:
        hist = json.loads(history or "[]")
    except Exception:
        hist = []
    out = await J.turn(said, lang, hist)
    return {"heard": True, "said": said, "say": out["say"], "lang": out["lang"], "audio": await _voiced(out["say"], out["lang"])}
