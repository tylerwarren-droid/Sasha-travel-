from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.conductor import conduct

router = APIRouter()

class ConductorRequest(BaseModel):
    message: str
    conversation_history: list = []

class ConductorResponse(BaseModel):
    response: str
    intents: list
    photos: list
    tools_used: list
    conversation_history: list

@router.post("/conductor")
async def conductor_endpoint(request: ConductorRequest):
    try:
        result = await conduct(
            user_message=request.message,
            conversation_history=request.conversation_history
        )
        return ConductorResponse(
            response=result["response"],
            intents=result["intents"],
            photos=result["photos"],
            tools_used=result["tools_used"],
            conversation_history=result["messages"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
