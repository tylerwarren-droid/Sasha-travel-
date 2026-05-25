from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.golf_agent import run_golf_agent

router = APIRouter()

class GolfRequest(BaseModel):
    message: str
    conversation_history: list = []

class GolfResponse(BaseModel):
    response: str
    tools_used: list
    conversation_history: list

@router.post("/golf", response_model=GolfResponse)
async def golf_agent_endpoint(request: GolfRequest):
    try:
        result = run_golf_agent(
            user_message=request.message,
            conversation_history=request.conversation_history
        )
        return GolfResponse(
            response=result["response"],
            tools_used=result["tools_used"],
            conversation_history=result["messages"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
