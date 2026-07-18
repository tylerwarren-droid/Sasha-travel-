from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from app.services.deepgram_service import transcribe_audio
from app.services.conductor import conduct
import httpx
import os
import json

router = APIRouter()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
DEEPGRAM_PROJECT_ID = os.getenv("DEEPGRAM_PROJECT_ID", "")
DEEPGRAM_KEY_TTL = int(os.getenv("DEEPGRAM_KEY_TTL", "3600"))  # seconds; covers a session
DEEPGRAM_TTS_URL = "https://api.deepgram.com/v1/speak"


@router.post("/voice/deepgram-key")
async def deepgram_ephemeral_key():
    """Mint a short-lived, scoped Deepgram key for browser STT.

    Production fix for the exposed `NEXT_PUBLIC_DEEPGRAM_API_KEY`: instead of shipping a
    long-lived key to every browser (where it can be lifted and abused), the client asks
    the backend for a temporary `usage:write`-only key that expires on its own. The master
    key never leaves the server.

    Returns 501 when the proxy isn't configured (no master key / project id) so the client
    can transparently fall back to the public env key for local development.
    """
    if not DEEPGRAM_API_KEY or not DEEPGRAM_PROJECT_ID:
        raise HTTPException(status_code=501, detail="deepgram key proxy not configured")
    try:
        async with httpx.AsyncClient(timeout=8.0) as http:
            r = await http.post(
                f"https://api.deepgram.com/v1/projects/{DEEPGRAM_PROJECT_ID}/keys",
                headers={
                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "comment": "sasha-ephemeral-stt",
                    "scopes": ["usage:write"],
                    "time_to_live_in_seconds": DEEPGRAM_KEY_TTL,
                },
            )
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail="could not mint deepgram key")
        data = r.json()
        return {"key": data.get("key"), "expires_in": DEEPGRAM_KEY_TTL}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"deepgram key error: {e}")

async def text_to_speech(text: str) -> bytes:
    """Convert text to speech using Deepgram TTS."""
    # Strip markdown for voice
    clean = text.replace("**", "").replace("*", "").replace("#", "").replace("→", "to").replace("—", "-")
    # Keep it concise for voice
    if len(clean) > 500:
        clean = clean[:500] + "..."

    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "text": clean
    }
    params = {
        "model": "aura-asteria-en",
        "encoding": "mp3"
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            DEEPGRAM_TTS_URL,
            json=payload,
            headers=headers,
            params=params
        )
        if response.status_code == 200:
            return response.content
        return b""


@router.post("/voice/conductor")
async def voice_conductor(
    audio: UploadFile = File(...),
    conversation_history: str = Form(default="[]"),
    session_id: str = Form(default="")
):
    """
    Full voice pipeline:
    Audio → Deepgram STT → The Conductor → Deepgram TTS → Audio response
    Returns JSON with transcript, response text, and base64 audio.
    """
    try:
        # Step 1 — Transcribe audio
        audio_bytes = await audio.read()
        mime_type = audio.content_type or "audio/webm"
        
        transcription = await transcribe_audio(audio_bytes, mime_type)
        transcript = transcription.get("transcript", "").strip()
        
        if not transcript:
            return JSONResponse({
                "transcript": "",
                "response": "I didn't catch that — could you try again?",
                "audio": None,
                "intents": [],
                "photos": []
            })

        print(f"[Voice Conductor] Transcript: {transcript}")

        # Step 2 — Route through The Conductor
        try:
            history = json.loads(conversation_history)
        except:
            history = []

        result = await conduct(transcript, history)
        response_text = result["response"]
        intents = result.get("intents", [])
        photos = result.get("photos", [])

        print(f"[Voice Conductor] Response: {response_text[:100]}...")

        # Step 3 — Convert response to speech
        audio_data = await text_to_speech(response_text)
        
        import base64
        audio_b64 = base64.b64encode(audio_data).decode() if audio_data else None

        return JSONResponse({
            "transcript": transcript,
            "response": response_text,
            "audio": audio_b64,
            "audio_format": "mp3",
            "intents": intents,
            "photos": photos,
            "conversation_history": result.get("messages", [])
        })

    except Exception as e:
        print(f"[Voice Conductor] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/voice/tts")
async def tts_only(request: dict):
    """Text to speech only — for when you have text and just need audio."""
    text = request.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")
    
    audio_data = await text_to_speech(text)
    if not audio_data:
        raise HTTPException(status_code=500, detail="TTS failed")
    
    return StreamingResponse(
        iter([audio_data]),
        media_type="audio/mpeg",
        headers={"Content-Disposition": "attachment; filename=response.mp3"}
    )
