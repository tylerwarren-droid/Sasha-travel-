from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from app.services.deepgram_service import transcribe_audio, transcribe_url

router = APIRouter(prefix="/voice", tags=["voice"])

class TranscribeURLRequest(BaseModel):
    url: str

@router.post("/transcribe")
async def transcribe_endpoint(audio: UploadFile = File(...)):
    """
    Receive audio file from browser and return transcript.
    Frontend sends audio/webm from MediaRecorder API.
    """
    try:
        audio_data = await audio.read()
        if not audio_data:
            raise HTTPException(status_code=400, detail="No audio data received")

        result = await transcribe_audio(
            audio_data=audio_data,
            mime_type=audio.content_type or "audio/webm"
        )

        if not result["transcript"]:
            return {
                "transcript": "",
                "confidence": 0.0,
                "message": "No speech detected"
            }

        return {
            "transcript": result["transcript"],
            "confidence": result["confidence"],
            "words": result.get("words", [])
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transcribe-url")
async def transcribe_url_endpoint(request: TranscribeURLRequest):
    """Transcribe audio from a URL — useful for testing"""
    try:
        result = await transcribe_url(request.url)
        return {
            "transcript": result["transcript"],
            "confidence": result["confidence"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
