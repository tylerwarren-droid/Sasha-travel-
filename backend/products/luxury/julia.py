"""Sasha 419 · JULIA, THE LUXURYOFFSEASON VOICE (DESIGN §5; KANOE B3 11:03 and "LUXURYOFFSEASON — Julia" 13:29).

  · Sasha's backend, Sasha's voice engine (Deepgram speech in, the model, text_to_speech out), Sasha's own AgAPI key. No avatar.
  · She is "Julia, an AI for LuxuryOffseason", said BEFORE anything else: her first reply of a conversation opens with HELLO, by code.
  · She answers from offseason.deltas only (reader.py). Phase 1: no booking, no live "check my dates".
  · Every reply passes THE POST-CHECK (postcheck.py, R8) before it is spoken: a %, amount or date the turn's observed items don't hold →
    the whole reply is NO_MEASUREMENT. A failed read is UNREAD (the site's sentence), never "nothing measured".
  · English and Spanish, following the person (the language Deepgram heard).
Her prompt holds no figure, threshold, ranking or clock rule: every one is the reader's (§3.1).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Mapping

from . import postcheck as PC
from . import reader as R

log = logging.getLogger("sasha.julia")

#: Sasha's engine, Julia's voice (KANOE 13:29): Deepgram's warm, friendly female voice that speaks English AND Spanish (one of its
#: codeswitching voices), so she is one person in both — clearly not Sasha's aura-asteria-en
VOICE = os.getenv("JULIA_VOICE", "aura-2-selena-es")
MODEL = os.getenv("JULIA_MODEL", "claude-sonnet-5-5")
MODEL_TIMEOUT_S = 40.0
MAX_STEPS = 4
LANGS = ("en", "es")

HELLO = {"en": "Hi, I'm Julia, an AI for Luxury Offseason. I can tell you how much less five-star hotels cost out of season, "
               "from prices we've measured. Where would you like to go?",
         "es": "Hola, soy Julia, una inteligencia artificial de Luxury Offseason. Te cuento cuánto menos cuestan los hoteles de cinco "
               "estrellas fuera de temporada, según precios que hemos medido. ¿Adónde te gustaría ir?"}
#: §3.1 (c) — the site's own unread sentence, said the same way
UNREAD = {"en": "I can't see the measurements right now.", "es": "Ahora mismo no puedo ver las mediciones."}
#: §5 — the post-check's replacement
NO_MEASUREMENT = {"en": "I don't have a measurement for that.", "es": "No tengo una medición de eso."}

TOOL = {"name": "offseason_deltas",
        "description": "Read LuxuryOffseason's measured season gaps. level=destination with no destination_key: the ranked list of "
                       "destinations, in order. level=destination with a destination_key: that one destination. level=hotel with a "
                       "destination_key: that destination's hotels (add hotel_id for one hotel). Keys and ids come only from earlier "
                       "results; never invent one.",
        "input_schema": R.tool_input_schema()}


def lang_of(detected: Any) -> str:
    return "es" if str(detected or "").lower().startswith("es") else "en"


def prompt(lang: str) -> str:
    speak = "Spanish" if lang == "es" else "English"
    return (
        "You are Julia, an AI for LuxuryOffseason. You speak with a visitor on the LuxuryOffseason website, by voice only. "
        "Your introduction is said for you at the start of the conversation; never introduce yourself again.\n"
        f"Reply in {speak}, the language the person is speaking. Speak plainly and briefly: two or three short sentences, no lists, no markdown.\n"
        "WHAT YOU KNOW: only what the offseason_deltas tool returns in this turn. Read it before saying anything about a place or a hotel. "
        "It returns items in order; that order is the ranking. Each item's kind says what it is: a gap, a closure, not measured "
        "recently, or not measured.\n"
        "WHAT YOU MAY SAY: a gap's percentage exactly as given, with what it compares (the low window against the high window), and ALWAYS "
        "the date it was measured. A destination's figure is a median of its hotels' starting prices: say so, and never give it as any one "
        "hotel's figure. A hotel's own figure exists only when the tool returns one for that hotel. A closure: that the hotel had no rooms "
        "for sale on the dates checked, with when it was checked. When an item says near decay, say how many days ago it was measured.\n"
        "Write every number in digits, exactly as the tool gives it. Write dates with the month's name.\n"
        "NEVER: a price or any amount of money; a figure the tool did not give in this turn; a date it did not give; anything about the "
        "future or what prices will do; 'guaranteed', 'best price', 'lowest price' or 'cheapest'; who supplies the prices, any booking "
        "site's name, commission or package prices; whether rooms are available now. If asked who you work for: LuxuryOffseason; "
        "Kanoe runs it, if they ask further.\n"
        "If the tool returns unread, or has nothing for what they asked, say you don't have a measurement for it. You can't book or check "
        "dates yet; say so if asked.")


def _history(history: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for m in (history or [])[-12:]:
        if isinstance(m, Mapping) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str) and m["content"].strip():
            out.append({"role": m["role"], "content": m["content"][:2000]})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def greeted(history: Any) -> bool:
    """She has introduced herself in this conversation: one of her replies opens with HELLO."""
    return any(isinstance(m, Mapping) and m.get("role") == "assistant" and str(m.get("content") or "").startswith(tuple(HELLO.values()))
               for m in (history or []))


def _blocks(content: Any) -> List[Dict[str, Any]]:
    out = []
    for b in content or []:
        if getattr(b, "type", None) == "text":
            out.append({"type": "text", "text": b.text})
        elif getattr(b, "type", None) == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out


async def answer(said: str, lang: str, history: Any) -> Dict[str, Any]:
    """One turn's words: the model with its one tool, then the post-check. → {"say", "rule"} (rule: ok | unread | the rule broken)."""
    import app.services.llm as LLM
    msgs: List[Dict[str, Any]] = _history(history) + [{"role": "user", "content": said}]
    outputs: List[Mapping[str, Any]] = []
    unread, text = False, ""
    for _ in range(MAX_STEPS):
        r = await asyncio.wait_for(LLM.client.messages.create(model=MODEL, max_tokens=400, system=prompt(lang), tools=[TOOL],
                                                              messages=msgs), MODEL_TIMEOUT_S)
        uses = [b for b in r.content if getattr(b, "type", None) == "tool_use"]
        if not uses:
            text = " ".join(b.text for b in r.content if getattr(b, "type", None) == "text").strip()
            break
        msgs.append({"role": "assistant", "content": _blocks(r.content)})
        results = []
        for u in uses:
            got = await R.deltas(u.input if isinstance(u.input, Mapping) else {})
            if got["ok"]:
                outputs.append(got["result"])
                results.append({"type": "tool_result", "tool_use_id": u.id, "content": json.dumps(got["result"], separators=(",", ":"))[:60000]})
            else:
                unread = True
                log.warning("[julia] reader not read: %s", got["why"])
                results.append({"type": "tool_result", "tool_use_id": u.id, "content": json.dumps({"unread": True})})
        msgs.append({"role": "user", "content": results})
    if unread:
        return {"say": UNREAD[lang], "rule": "unread"}
    ok, rule = PC.check(text, outputs)
    if not (ok and text):
        log.warning("[julia] reply replaced by the post-check: %s", rule if text else "empty")
        return {"say": NO_MEASUREMENT[lang], "rule": rule if text else "empty"}
    return {"say": text, "rule": "ok"}


async def turn(said: str, lang: str, history: Any) -> Dict[str, Any]:
    """What Julia says to one thing the person said: HELLO first if she hasn't introduced herself, then the checked answer."""
    lang = lang if lang in LANGS else "en"
    a = await answer(said, lang, history)
    say = a["say"] if greeted(history) else f"{HELLO[lang]} {a['say']}"
    return {"say": say, "lang": lang, "rule": a["rule"]}


async def speak(text: str, lang: str) -> bytes:
    """Her voice through Sasha's ONE speech engine (voice_conductor.text_to_speech)."""
    from app.api.voice_conductor import text_to_speech
    return await text_to_speech(text, "mp3", voice=VOICE, lang=lang)


__all__ = ["HELLO", "UNREAD", "NO_MEASUREMENT", "VOICE", "TOOL", "prompt", "turn", "answer", "speak", "greeted", "lang_of"]
