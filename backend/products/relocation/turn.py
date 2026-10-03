"""CR 1 · relocation on WhatsApp — M2 (intake → EX-01 fill → reviewer screen). Until then it says so, plainly."""
from __future__ import annotations


async def turn(ctx: dict, body: str, payload: str, *, entering: bool) -> None:
    ctx["out"].text("Relocation isn't open on this number yet. Say EXIT to go back to Sasha, or CAMPUS for CampusMe.")
