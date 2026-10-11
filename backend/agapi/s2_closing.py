"""Sasha 231 · "THANK YOU" → DORMANT on /s2: a message that is ONLY a thanks / that's all / bye (any language she speaks) gets one
spoken line — "OK! Just tap me if you need me — I'm right here." (in their language) — and /s2 fades her to the background and stops
listening until they tap. A tap brings her back with no re-introduction. Never the model: the words are fixed, and nothing is done.

A thanks with anything else in it ("thanks — and book the spa too") is NOT a closing: it goes to her as always.
    closing(message) → the language ("en", "es", …) or None · LINES[lang] → her one line
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

LINES = {
    "en": "OK! Just tap me if you need me — I'm right here.",
    "es": "¡Vale! Tócame si me necesitas, aquí estoy.",
    "ca": "D'acord! Toca'm si em necessites, sóc aquí.",
    "fr": "D'accord ! Touchez-moi si vous avez besoin de moi, je suis là.",
    "de": "Okay! Tipp mich einfach an, wenn du mich brauchst — ich bin da.",
    "it": "Ok! Toccami se hai bisogno di me, sono qui.",
    "pt": "Ok! É só tocar em mim se precisar, estou aqui.",
    "nl": "Oké! Tik me maar aan als je me nodig hebt, ik ben hier.",
}

# the whole message, once punctuation, emoji and filler ("ok", "great", "sasha", "so much") are taken away, is one of these
_PHRASES = {
    "en": ["thanks", "thank you", "thankyou", "thx", "ty", "cheers", "that's all", "thats all", "that is all", "that's it", "thats it",
           "that's everything", "nothing else", "no that's all", "bye", "goodbye", "bye bye", "see you", "see ya", "later", "good night",
           "goodnight", "all good", "i'm good", "im good", "i'm done", "im done", "all done", "we're done", "that'll be all", "perfect thanks"],
    "es": ["gracias", "muchas gracias", "mil gracias", "eso es todo", "es todo", "nada mas", "nada más", "adios", "adiós", "hasta luego",
           "chao", "chau", "buenas noches", "ya esta", "ya está", "listo", "vale gracias"],
    "ca": ["gracies", "gràcies", "moltes gracies", "moltes gràcies", "aixo es tot", "això és tot", "adeu", "adéu", "fins després", "bona nit"],
    "fr": ["merci", "merci beaucoup", "c'est tout", "cest tout", "rien d'autre", "au revoir", "bonne nuit", "a plus", "à plus", "bonne soirée"],
    "de": ["danke", "danke schön", "danke schon", "dankeschön", "vielen dank", "das war's", "das wars", "das ist alles", "tschüss", "tschuss",
           "tschüs", "auf wiedersehen", "bis später", "gute nacht"],
    "it": ["grazie", "grazie mille", "ciao", "è tutto", "e tutto", "nient'altro", "arrivederci", "ciao ciao", "a dopo", "buonanotte"],
    "pt": ["obrigado", "obrigada", "muito obrigado", "muito obrigada", "é tudo", "e tudo", "só isso", "so isso", "tchau", "adeus",
           "até logo", "ate logo", "boa noite"],
    "nl": ["dank je", "dankjewel", "dank je wel", "bedankt", "dank u", "dat was het", "dat is alles", "doei", "dag", "tot ziens", "welterusten"],
}
_FILLER = r"(?:ok(?:ay)?|okey|oké|great|perfect|perfecto|parfait|perfekt|perfetto|perfeito|super|lovely|awesome|cool|sasha|so much|a lot|" \
          r"again|very much|for now|for that|for everything|you|vale|genial|vielen|bien|muy bien|top|nice|amazing|brilliant|no)"


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFC", (t or "").lower())
    t = re.sub(r"[’`´]", "'", t)
    t = re.sub(r"[^\w\s']", " ", t)   # punctuation and emoji
    return re.sub(r"\s+", " ", t).strip()


_BY: dict = {}
for _lang, _ps in _PHRASES.items():
    for _p in _ps:
        _BY.setdefault(_norm(_p), _lang)
_ALT = "|".join(sorted((re.escape(p) for p in _BY), key=len, reverse=True))
_WHOLE = re.compile(rf"^(?:(?:{_FILLER}|{_ALT})\s*)+$")
_ANY = re.compile(rf"(?:^|\s)({_ALT})(?=\s|$)")


def closing(message: str) -> Optional[str]:
    """The language of a pure closing ("Thanks!", "That's all, bye", "Gracias, eso es todo"), else None."""
    t = _norm(message)
    if not t or len(t.split()) > 8 or not _WHOLE.match(t):
        return None
    found = [m.group(1) for m in _ANY.finditer(t)]
    if not found:
        return None   # only filler ("ok", "great") is not a goodbye
    return _BY[found[0]]


def line(lang: Optional[str]) -> str:
    return LINES.get(lang or "en", LINES["en"])


__all__ = ["closing", "line", "LINES"]
