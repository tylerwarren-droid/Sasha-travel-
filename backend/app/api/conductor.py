from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from app.services.conductor import conduct

router = APIRouter()


class ConductorRequest(BaseModel):
    message: str
    conversation_history: list = []
    trip_id: str = ""
    user_id: str = ""


class ConductorResponse(BaseModel):
    response: str
    intents: list
    photos: list
    tools_used: list
    conversation_history: list


@router.post("/conductor")
async def conductor_endpoint(body: ConductorRequest, request: Request):
    try:
        client_config = getattr(request.state, "client", None)
        result = await conduct(
            user_message=body.message,
            conversation_history=body.conversation_history,
            client_config=client_config,
            trip_id=body.trip_id or "",
            user_id=body.user_id or "",
        )
        return ConductorResponse(
            response=result["response"],
            intents=result["intents"],
            photos=result["photos"],
            tools_used=result["tools_used"],
            conversation_history=result["messages"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
