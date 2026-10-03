"""Sasha 88 · WHAT SASHA SAYS ALOUD, IN THE VENUE'S LANGUAGE: a name spelled the way that country spells on the phone,
a phone number as its digits in words, and her own booking reference.

1 Oct 2026, call a1c85ca6 (Botavara Chamberí): she spelled "W A R R E N" letter by letter and the venue wrote "David";
the guest's number was in the task as "+ 3 4 6 0 8 …", which is not how anyone in Madrid says a number. Here every
one of those is a sentence a person at that venue would say back. Deterministic: no model, nothing invented.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Optional

#: the telephone spelling alphabets each country actually uses
_SPELL = {
    "es": ("de", dict(A="Alicante", B="Barcelona", C="Cáceres", D="Dinamarca", E="España", F="Francia", G="Gerona",
                      H="Huelva", I="Italia", J="Jaén", K="Kilo", L="Lérida", M="Madrid", N="Navarra", Ñ="Ñandú",
                      O="Oviedo", P="Pamplona", Q="Queso", R="Roma", S="Sevilla", T="Toledo", U="Úbeda", V="Valencia",
                      W="Washington", X="Xilófono", Y="Yegua", Z="Zaragoza")),
    "en": ("as in", dict(A="Alpha", B="Bravo", C="Charlie", D="Delta", E="Echo", F="Foxtrot", G="Golf", H="Hotel",
                         I="India", J="Juliett", K="Kilo", L="Lima", M="Mike", N="November", O="Oscar", P="Papa",
                         Q="Quebec", R="Romeo", S="Sierra", T="Tango", U="Uniform", V="Victor", W="Whiskey", X="X-ray",
                         Y="Yankee", Z="Zulu")),
    "fr": ("comme", dict(A="Anatole", B="Berthe", C="Célestin", D="Désiré", E="Eugène", F="François", G="Gaston",
                         H="Henri", I="Irma", J="Joseph", K="Kléber", L="Louis", M="Marcel", N="Nicolas", O="Oscar",
                         P="Pierre", Q="Quintal", R="Raoul", S="Suzanne", T="Thérèse", U="Ursule", V="Victor",
                         W="William", X="Xavier", Y="Yvonne", Z="Zoé")),
    "it": ("come", dict(A="Ancona", B="Bologna", C="Como", D="Domodossola", E="Empoli", F="Firenze", G="Genova",
                        H="Hotel", I="Imola", J="Jolly", K="Kappa", L="Livorno", M="Milano", N="Napoli", O="Otranto",
                        P="Palermo", Q="Quarto", R="Roma", S="Savona", T="Torino", U="Udine", V="Venezia",
                        W="Washington", X="Xeres", Y="Yacht", Z="Zara")),
    "pt": ("de", dict(A="Aveiro", B="Braga", C="Coimbra", D="Dafundo", E="Évora", F="Faro", G="Guarda", H="Horta",
                      I="Itália", J="José", K="Kodak", L="Lisboa", M="Maria", N="Nazaré", O="Ovar", P="Porto",
                      Q="Queluz", R="Rossio", S="Setúbal", T="Tavira", U="Unidade", V="Vidago", W="Waldemar",
                      X="Xavier", Y="York", Z="Zulmira")),
    "de": ("wie", dict(A="Anton", B="Berta", C="Cäsar", D="Dora", E="Emil", F="Friedrich", G="Gustav", H="Heinrich",
                       I="Ida", J="Julius", K="Kaufmann", L="Ludwig", M="Martha", N="Nordpol", O="Otto", P="Paula",
                       Q="Quelle", R="Richard", S="Samuel", T="Theodor", U="Ulrich", V="Viktor", W="Wilhelm",
                       X="Xanthippe", Y="Ypsilon", Z="Zacharias")),
}
_DIGITS = {
    "es": ("cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"),
    "en": ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"),
    "fr": ("zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf"),
    "it": ("zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove"),
    "pt": ("zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove"),
    "de": ("null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun"),
}
_PLUS = {"es": "más", "en": "plus", "fr": "plus", "it": "più", "pt": "mais", "de": "plus"}
#: the calling code a venue speaking that language dials without (its own country's numbers are said nationally)
_HOME = {"es": "34", "pt": "351", "fr": "33", "it": "39", "de": "49"}
ASK_REFERENCE = {
    "es": "¿Me da un número de reserva o localizador?",
    "en": "Could you give me a booking reference, please?",
    "fr": "Pourriez-vous me donner un numéro de réservation ?",
    "it": "Mi può dare un numero di prenotazione?",
    "pt": "Pode dar-me um número de reserva?",
    "de": "Können Sie mir eine Reservierungsnummer geben?",
}
#: Sasha 118 · after the recap's "ok"/"vale" (Botavara, 1 Oct: "Ok." — then "Correcto." while she was already talking)
RECAP_AGAIN = {"es": "¿Es correcto, sí?", "en": "Is that right, yes?", "fr": "C'est bien ça, oui ?", "it": "È corretto, sì?",
               "pt": "Está correto, sim?", "de": "Ist das richtig, ja?"}
_OWN_REFERENCE = {
    "es": "Por nuestra parte, la referencia es {ref}.",
    "en": "Our own reference for it is {ref}.",
    "fr": "De notre côté, la référence est {ref}.",
    "it": "Da parte nostra, il riferimento è {ref}.",
    "pt": "Da nossa parte, a referência é {ref}.",
    "de": "Unsere eigene Referenz dafür ist {ref}.",
}
#: Sasha's own references: no 0/O, 1/I, 5/S, 8/B — said on a phone line, nothing can be heard as something else
REF_ALPHABET = "ACDEFHJKLMNPRTUVWXY234679"
REF_RX = re.compile(rf"^K-[{REF_ALPHABET}]{{4}}$")


def code(lang_code: str) -> str:
    c = (lang_code or "en").split("-")[0].lower()
    return c if c in _SPELL else "en"


def spell(name: str, lang_code: str) -> str:
    """"Warren" in Spanish → "W de Washington, A de Alicante, R de Roma, R de Roma, E de España, N de Navarra"."""
    link, words = _SPELL[code(lang_code)]
    out = []
    for ch in name.strip():
        if ch.isspace() or ch in "-'’.":
            continue
        up = ch.upper()
        base = up if up in words else unicodedata.normalize("NFD", up)[0]
        out.append(f"{up} {link} {words[base]}" if base in words else up)
    return ", ".join(out)


def digits(number: str, lang_code: str) -> str:
    """"+34608445715" for a Spanish venue → "seis cero ocho, cuatro cuatro cinco, siete uno cinco" (grouped in threes,
    said nationally); a number from another country keeps its code: "más cuatro cuatro, …"."""
    c = code(lang_code)
    d = re.sub(r"\D", "", number or "")
    home = _HOME.get(c)
    lead = ""
    if (number or "").strip().startswith("+") or len(d) > 10:
        if home and d.startswith(home):
            d = d[len(home):]
        else:
            cc = next((d[:n] for n in (3, 2, 1) if d[:n] in ("351", "34", "33", "39", "49", "44", "1", "353", "41", "31", "32")), d[:2])
            lead = f"{_PLUS[c]} {' '.join(_DIGITS[c][int(x)] for x in cc)}, "
            d = d[len(cc):]
    groups = [d[i:i + 3] for i in range(0, len(d), 3)]
    if len(groups) > 1 and len(groups[-1]) == 1:   # never a lone last digit: 3-3-2-2 rather than 3-3-3-1
        groups[-2:] = [groups[-2][:2], groups[-2][2:] + groups[-1]]
    return lead + ", ".join(" ".join(_DIGITS[c][int(x)] for x in g) for g in groups)


def own_reference(*parts: object) -> str:
    """Sasha's own booking reference, "K-7F3A": derived from the booking itself (venue, day, time, party, name, the
    moment it was prepared), so the same booking built twice is the same reference and two bookings are not."""
    h = int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest(), 16)
    out = []
    for _ in range(4):
        h, r = divmod(h, len(REF_ALPHABET))
        out.append(REF_ALPHABET[r])
    return "K-" + "".join(out)


def say_reference(ref: str, lang_code: str) -> str:
    """"K-7F3A" in Spanish → "K de Kilo, siete, F de Francia, tres, A de Alicante"."""
    c = code(lang_code)
    link, words = _SPELL[c]
    return ", ".join(_DIGITS[c][int(ch)] if ch.isdigit() else f"{ch} {link} {words[ch]}" for ch in ref.replace("-", ""))


def own_reference_line(ref: str, lang_code: str) -> str:
    return _OWN_REFERENCE[code(lang_code)].format(ref=say_reference(ref, lang_code))


def ask_reference(lang_code: str) -> str:
    return ASK_REFERENCE[code(lang_code)]


__all__ = ["spell", "digits", "own_reference", "say_reference", "own_reference_line", "ask_reference", "REF_RX", "code",
           "RECAP_AGAIN"]
