"""
Chat history API — read back the stored conversations for the current (hardcoded) user.

Persistence itself happens transparently inside the conductor endpoint on every turn; these
endpoints just expose what was stored so the data is verifiable and usable by a future UI.
"""

from fastapi import APIRouter, HTTPException, Request

from app.services import chat_store
from app.services.chat_account import chat_account

router = APIRouter(prefix="/api/chats", tags=["chats"])


@router.get("")
async def list_chats(request: Request):
    """List the caller's own chat sessions (newest first) — a signed-in guest's, or the public demo's (S-62 step 7)."""
    account = await chat_account(request)
    sessions = await chat_store.list_sessions(account)
    # Sasha 249 · no fixed person for the demo (it was "Jon Peters"): the demo is nobody, and says no name
    return {"user": {"id": account, "email": None, "display_name": None}, "sessions": sessions}


@router.get("/{session_id}")
async def get_chat(session_id: str, request: Request):
    """Every stored message for one session — only the caller's own. Someone else's answers as one that does not exist."""
    account = await chat_account(request)
    if await chat_store.session_owner(session_id) != account:
        raise HTTPException(status_code=404, detail="chat session not found")
    messages = await chat_store.get_messages(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="chat session not found")
    return {"session_id": session_id, "messages": messages}
