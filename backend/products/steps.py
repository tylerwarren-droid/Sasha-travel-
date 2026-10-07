"""CR 52 · THE THREE ME'S, CALM: one step per message — what this step is, what's needed, one button for the next — and
every detail (sources, full checklists, legal notes, values to copy) kept behind a tap ("More", "Sources", "Copy my
details"), never pushed by default. A product stashes a step's details in the conversation; its own button shows them.

    steps.stash(pend, "fees", [line, line, …])
    out.ask("Your fees: …", [("Book it →", "rx:go:book"), steps.more("rx:", "fees", "Sources")])
    # the product's turn, on payload "rx:more:fees":  steps.show(pend, "fees", out)
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

MAX_LINES = 4          # a step on WhatsApp: about four lines (CR 52 rule 3)


def stash(pend: dict, key: str, texts: Iterable[Optional[str]], media: Optional[List[Tuple[str, str, str]]] = None) -> None:
    """Keep a step's details for its button: texts (each its own message) and media (caption, card url, pdf url)."""
    pend.setdefault("more", {})[key] = {"texts": [t for t in texts if t], "media": list(media or [])}


def more(prefix: str, key: str, label: str = "More") -> Tuple[str, str]:
    return (label, f"{prefix}more:{key}")


def is_more(payload: str, prefix: str) -> Optional[str]:
    """The stashed key a "More" button asks for, or None."""
    p = f"{prefix}more:"
    return payload[len(p):] if payload.startswith(p) else None


def show(pend: dict, key: str, out) -> None:
    """The details behind a step's button, exactly as kept; nothing kept → said so (never an empty reply)."""
    from . import formcard as FC
    got = (pend.get("more") or {}).get(key)
    if not got or not (got["texts"] or got["media"]):
        out.text("That's everything for this step.")
        return
    for caption, card, pdf in got["media"]:
        FC.show(out, caption, card, pdf)
    for t in got["texts"]:
        out.text(t)
