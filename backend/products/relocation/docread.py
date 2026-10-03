"""CR 1 · reading a document the applicant sends (a passport's photo page) — M3. Until then it says so, plainly."""
from __future__ import annotations


async def on_media(ctx: dict, facts: dict) -> bool:
    ctx["out"].text("I can't read photos of documents here yet — please type the answer to the question above.")
    return True


async def on_confirm(ctx: dict, facts: dict, body: str, payload: str) -> None:
    ctx["st"]["pending"]["step"] = "facts"
