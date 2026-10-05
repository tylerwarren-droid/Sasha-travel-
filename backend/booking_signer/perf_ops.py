"""Sasha 149 · PERFORMANCE, MEASURED ON THE SERVER ITSELF (founder only): where the time goes, step by step, from the
place the code actually runs — not from a laptop in Madrid. Each step is run a few times; p50 / p95 / max in ms.

  · db       — `select 1` through the booking store's pool (the Supabase round trip from this region)
  · net      — an HTTPS request to each host the hot path uses: a NEW connection each time vs one REUSED connection
  · find     — "Find venues" (one Places Text Search) as the WhatsApp/web cards do
  · photos   — the venues' own share pictures for the three cards
  · conduct  — a deterministic web turn (no model) and a model turn (FAST_MODEL)
  · model    — a one-line FAST_MODEL completion (the model's own latency)
  · voice    — speech in → reply spoken: TTS a sentence, STT it back, conduct, TTS the reply (Deepgram + conduct)

Costs: a few Places searches, a few short model calls, a few seconds of Deepgram. Nothing is booked or sent.
"""
from __future__ import annotations

import asyncio
import os
import statistics
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import APIRouter, Request

router = APIRouter(prefix="/ops", tags=["booking-ops"])

HOSTS = {"supabase": None, "places": "https://places.googleapis.com/", "routes": "https://routes.googleapis.com/",
         "duffel": "https://api.duffel.com/", "anthropic": "https://api.anthropic.com/", "bland": "https://api.bland.ai/",
         "deepgram": None,   # Sasha 150 · the endpoint actually used (DEEPGRAM_API_BASE)
         "twilio": "https://api.twilio.com/"}


def stats(ms: List[float]) -> Dict[str, Any]:
    if not ms:
        return {"n": 0}
    s = sorted(ms)
    p95 = s[min(len(s) - 1, max(0, round(0.95 * (len(s) - 1))))]
    return {"n": len(s), "p50": round(statistics.median(s)), "p95": round(p95), "max": round(s[-1])}


async def timed(fn: Callable[[], Awaitable[Any]], n: int) -> tuple:
    out, last, err = [], None, None
    for _ in range(n):
        t = time.perf_counter()
        try:
            last = await fn()
        except Exception as e:   # a failing step is reported, never hidden as fast
            err = f"{type(e).__name__}: {str(e)[:160]}"
            continue
        out.append((time.perf_counter() - t) * 1000)
    return stats(out), last, err


def _deepgram_url() -> str:
    from app.services.deepgram_service import DEEPGRAM_API_BASE
    return DEEPGRAM_API_BASE + "/"


def _supabase_url() -> Optional[str]:
    u = os.getenv("SASHA_SUPABASE_URL", "").strip().rstrip("/")
    return f"{u}/auth/v1/health" if u else None


async def measure(steps: List[str], n: int = 5) -> Dict[str, Any]:
    import httpx
    from . import guest_whatsapp as GW, routes as R
    from .identity import founder_account
    A, res = founder_account(), {}
    if "db" in steps:
        res["db"], _, e = await timed(lambda: R.STORE._run(lambda c: c.fetchval("select 1")), n * 2)
        if e:
            res["db"]["error"] = e
    if "net" in steps:
        net = {}
        for name, url in HOSTS.items():
            url = url or (_supabase_url() if name == "supabase" else _deepgram_url())
            if not url:
                continue

            async def fresh():
                async with httpx.AsyncClient(timeout=10) as c:
                    await c.get(url)
            new, _, e1 = await timed(fresh, 3)
            async with httpx.AsyncClient(timeout=10) as c:
                await c.get(url)   # open it once
                reused, _, e2 = await timed(lambda: c.get(url), 3)
            net[name] = {"new_connection": new, "reused_connection": reused, **({"error": e1 or e2} if (e1 or e2) else {})}
        res["net"] = net
    cards: List[dict] = []
    if "find" in steps or "photos" in steps:
        async def find():
            s, j = await GW.api(A, "POST", "/api/booking/venues/find", {"what": "dinner", "where": "Madrid", "country": "ES"})
            return j
        res["find"], j, e = await timed(find, max(2, n // 2))
        if e:
            res["find"]["error"] = e
        cands = (j or {}).get("candidates") or []
        cards = [c for c in cands if c.get("place_id") != "sasha-test-venue"][:3]
    if "photos" in steps and cards:
        # the photo cache is NOT cleared: it holds the founder's pre-warm. "first" is whatever state the cache is in
        res["photos_first"], _, e = await timed(lambda: GW._photos(A, "dinner", cards), 1)
        res["photos_again"], _, _ = await timed(lambda: GW._photos(A, "dinner", cards), 3)
    if "conduct" in steps:
        from app.services import conductor as CD
        res["conduct_deterministic"], _, e = await timed(lambda: CD.conduct("dinner for 2 in Madrid tomorrow at 9pm", [], user_id=A, signed_in=True), 3)
        res["conduct_model"], _, e2 = await timed(lambda: CD.conduct("what's a nice area to walk around in Madrid in the evening?", [], user_id=A, signed_in=True), 3)
        if e or e2:
            res["conduct_error"] = e or e2
    if "model" in steps:
        from app.services.llm import client, FAST_MODEL
        res["model"], _, e = await timed(lambda: client.messages.create(model=FAST_MODEL, max_tokens=20,
                                                                        messages=[{"role": "user", "content": "Say OK."}]), 3)
        res["model"]["model"] = FAST_MODEL
        if e:
            res["model"]["error"] = e
    if "voice" in steps:
        res["voice"] = await _voice(A)
    return res


async def _voice(account: str) -> Dict[str, Any]:
    """Speech in → reply spoken, step by step: the sentence is first spoken by Deepgram (standing in for the guest), then
    the real pipeline: STT → conduct → TTS."""
    from app.api.voice_conductor import text_to_speech
    from app.services.deepgram_service import transcribe_audio
    from app.services import conductor as CD
    if not os.getenv("DEEPGRAM_API_KEY", "").strip():
        return {"skipped": "DEEPGRAM_API_KEY is not set"}
    audio = await text_to_speech("Find me dinner for two in Madrid tomorrow at nine.")
    if not audio:
        return {"error": "no audio from TTS to stand in for the guest"}
    runs = []
    for _ in range(3):
        t0 = time.perf_counter()
        tr = await transcribe_audio(audio, "audio/mpeg")
        t1 = time.perf_counter()
        out = await CD.conduct((tr or {}).get("transcript") or "", [], user_id=account, signed_in=True)
        t2 = time.perf_counter()
        await text_to_speech(out.get("response") or "OK")
        t3 = time.perf_counter()
        runs.append(((t1 - t0) * 1000, (t2 - t1) * 1000, (t3 - t2) * 1000, (t3 - t0) * 1000))
    return {"stt": stats([r[0] for r in runs]), "conduct": stats([r[1] for r in runs]), "tts": stats([r[2] for r in runs]),
            "total": stats([r[3] for r in runs]), "heard": (tr or {}).get("transcript")}


@router.post("/perf")
async def perf(request: Request):
    from .ops import founder_only
    no = founder_only(request)
    if no:
        return no
    try:
        body = await request.json()
    except Exception:
        body = {}
    steps = [s for s in (body or {}).get("steps") or ["db", "net", "find", "photos", "conduct", "model", "voice"]]
    t = time.perf_counter()
    out = await measure(steps, int((body or {}).get("n") or 5))
    return {"ok": True, "region": os.getenv("RAILWAY_REPLICA_REGION") or os.getenv("RAILWAY_REGION"), "steps": out,
            "took_ms": round((time.perf_counter() - t) * 1000)}


# ── the 1-minute keep-warm (the health ping, from inside) ────────────────────────────────────────────────────────────

WARM_EVERY_S = 60
#: hosts kept warm in the pooled client — their ROOT pages, which are not API calls and are not billed
WARM_URLS = ("https://places.googleapis.com/", "https://api.duffel.com/")
_warm_task = None
LAST_WARM: Dict[str, Any] = {}


async def warm_once() -> Dict[str, Any]:
    """One keep-warm pass: the database pool's connection, and the kept-alive connections to the hot path's hosts.
    Returns what each took (shown on /ops/perf/warm)."""
    from . import routes as R
    from .http_pool import request
    out: Dict[str, Any] = {}
    t = time.perf_counter()
    try:
        await R.STORE._run(lambda c: c.fetchval("select 1"))
        out["db_ms"] = round((time.perf_counter() - t) * 1000)
    except Exception as e:
        out["db"] = f"{type(e).__name__}: {str(e)[:120]}"
    for u in WARM_URLS:
        t = time.perf_counter()
        try:
            await request("GET", u, timeout=10.0)
            out[u] = round((time.perf_counter() - t) * 1000)
        except Exception as e:
            out[u] = f"{type(e).__name__}"
    LAST_WARM.update(out, at=time.time())
    return out


async def _warm_forever() -> None:
    import logging
    log = logging.getLogger("booking_signer.perf")
    while True:
        try:
            await warm_once()
        except Exception as e:   # never stops the server; said in the log
            log.warning("[keep-warm] %s: %s", type(e).__name__, e)
        await asyncio.sleep(WARM_EVERY_S)


def start_warm() -> None:
    """Sasha 149 · SASHA_KEEP_WARM=1 (on in production; off in tests): the database and the hot path's connections are
    never cold when a guest writes after a quiet spell. Railway's own sleep is already off (sleepApplication: false)."""
    global _warm_task
    if _warm_task is None and os.getenv("SASHA_KEEP_WARM", "1") == "1" and os.getenv("DATABASE_URL", "").strip():
        _warm_task = asyncio.create_task(_warm_forever())


@router.get("/perf/warm")
async def warm_status(request: Request):
    from .ops import founder_only
    no = founder_only(request)
    if no:
        return no
    return {"ok": True, "running": _warm_task is not None and not _warm_task.done(), "last": LAST_WARM}


__all__ = ["router", "stats", "measure", "warm_once", "start_warm"]
