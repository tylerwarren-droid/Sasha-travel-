"""
Chat history API — read back the stored conversations for the current (hardcoded) user.

Persistence itself happens transparently inside the conductor endpoint on every turn; these
endpoints just expose what was stored so the data is verifiable and usable by a future UI.
"""

from fastapi import APIRouter, HTTPException

from app.services import chat_store

router = APIRouter(prefix="/api/chats", tags=["chats"])


@router.get("")
async def list_chats():
    """List the current user's chat sessions (newest first) with message counts."""
    sessions = await chat_store.list_sessions(chat_store.DEMO_USER_ID)
    return {
        "user": {
            "id": chat_store.DEMO_USER_ID,
            "email": chat_store.DEMO_USER_EMAIL,
            "display_name": chat_store.DEMO_USER_NAME,
        },
        "sessions": sessions,
    }


@router.get("/{session_id}")
async def get_chat(session_id: str):
    """Return every stored message for one session."""
    messages = await chat_store.get_messages(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="chat session not found")
    return {"session_id": session_id, "messages": messages}
