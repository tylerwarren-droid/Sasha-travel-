import os
import httpx
from dotenv import load_dotenv

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
#: Sasha 150 · DEEPGRAM_API_BASE: the server moved to the EU (europe-west4), and Deepgram's EU endpoint
#: (https://api.eu.deepgram.com) is the near one; unset = the US endpoint, as before
DEEPGRAM_API_BASE = (os.getenv("DEEPGRAM_API_BASE", "").strip() or "https://api.deepgram.com").rstrip("/")
DEEPGRAM_URL = f"{DEEPGRAM_API_BASE}/v1/listen"

async def transcribe_audio(audio_data: bytes, mime_type: str = "audio/webm") -> dict:
    """
    Transcribe audio bytes using Deepgram Nova-3.
    Returns transcript text and confidence score.
    """
    params = {
        "model": "nova-3",
        "language": "en-US",
        "smart_format": "true",
        "punctuate": "true",
    }

    clean_mime = mime_type.split(";")[0].strip() if mime_type else "audio/mp4"
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": clean_mime,
    }

    from booking_signer.http_pool import request   # Sasha 150 · pooled, kept alive (no new TLS handshake per utterance)
    response = await request("POST", DEEPGRAM_URL, timeout=30.0, content=audio_data, headers=headers, params=params)
    response.raise_for_status()
    result = response.json()

    # Extract transcript
    channels = result.get("results", {}).get("channels", [])
    if not channels:
        return {"transcript": "", "confidence": 0.0}

    alternatives = channels[0].get("alternatives", [])
    if not alternatives:
        return {"transcript": "", "confidence": 0.0}

    best = alternatives[0]
    return {
        "transcript": best.get("transcript", "").strip(),
        "confidence": best.get("confidence", 0.0),
        "words": best.get("words", [])
    }


async def transcribe_url(audio_url: str) -> dict:
    """Transcribe audio from a URL"""
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "url": audio_url
    }
    params = {
        "model": "nova-3",
        "language": "en-GB",
        "smart_format": "true",
        "punctuate": "true",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            DEEPGRAM_URL,
            json=payload,
            headers=headers,
            params=params
        )
        response.raise_for_status()
        result = response.json()

    channels = result.get("results", {}).get("channels", [])
    if not channels:
        return {"transcript": "", "confidence": 0.0}

    alternatives = channels[0].get("alternatives", [])
    if not alternatives:
        return {"transcript": "", "confidence": 0.0}

    best = alternatives[0]
    return {
        "transcript": best.get("transcript", "").strip(),
        "confidence": best.get("confidence", 0.0),
    }
