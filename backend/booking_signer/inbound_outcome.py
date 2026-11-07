"""Sasha 357 · THE INBOUND HANDLER'S ONE OUTCOME (the server side of 348's lib/outcome): every inbound message ends in exactly one of

  handled   its reply (the turn's own words)
  refused   a reason the person reads (not linked, AD's closed beta, the model's daily cap, the credit gone — each says why)
  failed    "I couldn't take that just now — please send it again", in their language

Found (Sasha 355): a database error failed CLOSED — the step wasn't recorded, so nothing was handed to AgAPI — logged, and the person heard
nothing. 348's rule: nothing silent. A failure point never writes its own line (a try/except with a message in one place is a patch):
it raises its cause (Failed, or the error itself) to one of the two boundaries — the webhook (inbound_phone.sms, the reply in its TwiML)
and the background turn (guest_whatsapp._turn, sent through deliver, which records it on the conversation record, Sasha 349) — and the
words come from HERE (words_for). The cause is named in the log once, here.

A failure AFTER something was done this turn (a table asked for, a payment opened) never says "send it again" (resending could repeat it):
it says what was already done (sasha.what_happened).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Optional

log = logging.getLogger("booking_signer.inbound_outcome")

HANDLED, REFUSED, FAILED_KIND = "handled", "refused", "failed"

FAILED = {
    "en": "I couldn't take that just now — please send it again.",
    "es": "No he podido recibir eso ahora mismo — por favor, envíamelo otra vez.",
    "fr": "Je n'ai pas pu prendre ça pour l'instant — renvoyez-le, s'il vous plaît.",
    "it": "Non sono riuscita a prenderlo adesso — per favore, rimandamelo.",
    "pt": "Não consegui receber isso agora — por favor, envie de novo.",
    "de": "Das konnte ich gerade nicht annehmen — bitte schick es noch einmal.",
}
CAPPED = {   # refused: the model's daily cap (model_gateway.ModelBudgetExceeded) — sending it again today won't help, so it never says so
    "en": "I've reached today's limit on my side, so I can't take that now — nothing was booked or sent. Please try again tomorrow.",
    "es": "Hoy he llegado a mi límite, así que no puedo atender eso ahora — no se ha reservado ni enviado nada. Inténtalo de nuevo mañana.",
    "fr": "J'ai atteint ma limite pour aujourd'hui, je ne peux pas traiter ça maintenant — rien n'a été réservé ni envoyé. Réessayez demain.",
    "it": "Oggi ho raggiunto il mio limite, quindi non posso occuparmene ora — non è stato prenotato né inviato nulla. Riprova domani.",
    "pt": "Cheguei ao meu limite de hoje, por isso não posso tratar disso agora — nada foi reservado nem enviado. Tente novamente amanhã.",
    "de": "Ich habe mein heutiges Limit erreicht und kann das gerade nicht annehmen — nichts wurde gebucht oder gesendet. Bitte versuch es morgen.",
}
UNFINISHED = {   # failed AFTER an act: what was done follows (sasha.what_happened) — never "send it again"
    "en": "Sorry — I couldn't finish that on my side.",
    "es": "Perdona — no he podido terminarlo por mi parte.",
    "fr": "Désolée — je n'ai pas pu terminer ça de mon côté.",
    "it": "Scusa — non sono riuscita a finirlo da parte mia.",
    "pt": "Desculpe — não consegui terminar isso do meu lado.",
    "de": "Entschuldige — ich konnte das auf meiner Seite nicht abschließen.",
}

_WORDS = {
    "es": r"hola|quiero|quisiera|puedes|podr[ií]as|gracias|reserva\w*|mesa|por favor|para|una|el|los|las|del|que|est[aá]|c[oó]mo|"
          r"d[oó]nde|cu[aá]ndo|vuelo|esta|noche|ma[ñn]ana|buscas|necesito|hay|y",
    "fr": r"bonjour|merci|je|vous|pour|une|est|s'il|pouvez|r[ée]server|ce|soir|vol|avec|nous|plait|pla[iî]t",
    "it": r"ciao|grazie|vorrei|per favore|sono|questa|sera|volo|prenotare|tavolo|puoi|mi|un|della",
    "pt": r"ol[aá]|obrigad[oa]|voc[eê]|n[aã]o|uma|reservar|mesa|esta|noite|voo|pode|quero|preciso",
    "de": r"hallo|danke|ich|bitte|f[üu]r|eine|einen|nicht|heute|abend|flug|tisch|kannst|k[öo]nnen|und|mir",
}
_RX = {k: re.compile(rf"(?<![\w'])(?:{v})(?![\w'])", re.I) for k, v in _WORDS.items()}


def lang_of(text: Optional[str]) -> str:
    """The language their message is in (Sasha's languages), by its own words; English when it can't tell."""
    t = (text or "").strip()
    if not t:
        return "en"
    score = {k: len(rx.findall(t)) for k, rx in _RX.items()}
    if re.search(r"[¿¡ñ]", t):
        score["es"] += 3
    if re.search(r"[ãõç]", t):
        score["pt"] += 2
    if re.search(r"[ßäöü]", t):
        score["de"] += 2
    best = max(score, key=score.get)
    n_en = len(re.findall(r"(?<![\w'])(?:the|a|an|to|for|me|my|i|you|can|please|is|and|of|in|on|book|find|what|flight|table)(?![\w'])", t, re.I))
    return best if score[best] > n_en else "en"


_REPLIES: dict = {}   # a person's key → replies that left (guest_whatsapp.deliver) — the outcome's own knowledge, never the dots


def replied(key: str) -> None:
    """A REPLY to this person left (words, or another's answer — never an acknowledgement, never nothing)."""
    if key:
        _REPLIES[key] = _REPLIES.get(key, 0) + 1


def replies(key: str) -> int:
    return _REPLIES.get(key, 0)


class Failed(Exception):
    """A failure point's cause, raised to the boundary (never a line of its own): "the message's step agapi_in wasn't recorded (…)"."""

    def __init__(self, cause: str) -> None:
        super().__init__(cause)
        self.cause = cause


def _capped(e: BaseException) -> bool:
    try:
        from .model_gateway import ModelBudgetExceeded
        return isinstance(e, ModelBudgetExceeded)
    except Exception:
        return False


def cause_of(e: BaseException) -> str:
    return e.cause if isinstance(e, Failed) else f"{type(e).__name__}: {str(e)[:240]}"


def words_for(e: Optional[BaseException], text: Optional[str] = None, *, where: str = "", calls: Iterable[dict] = ()) -> str:
    """THE words a person reads when their message failed — and the cause named in the log, once. `calls`: what this turn already
    did (the brain's tool calls): after an act, what was done, never "send it again"."""
    lang = lang_of(text)
    log.error("[outcome] FAILED %s— %s", f"({where}) " if where else "", cause_of(e) if e is not None else "no reply")
    if e is not None and _capped(e):
        return CAPPED[lang]
    calls = [c for c in calls or [] if isinstance(c, dict)]
    if calls:
        from app.agent import sasha as AG
        said = AG.what_happened(calls, "")
        if said.strip() != "Nothing was booked or sent.":   # something was done (or may have been): said — never resent
            return f"{UNFINISHED[lang]}{said}"
    return FAILED[lang]


async def record(account: Optional[str], line: str) -> None:
    """A webhook's own reply (its TwiML — not sent through deliver) on the conversation record (349)."""
    if not account:
        return
    try:
        from agapi import s2_memory as MEM
        await MEM.record(account, MEM.message("out", "wa", line, "outcome"))
    except Exception as e:
        log.error("[outcome] the failure's line was not recorded on the conversation: %s", type(e).__name__)


__all__ = ["replied", "replies", "Failed", "words_for", "lang_of", "record", "cause_of", "FAILED", "CAPPED", "UNFINISHED", "HANDLED", "REFUSED", "FAILED_KIND"]
