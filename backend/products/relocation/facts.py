"""CR 1 · the applicant's facts — each one {value, source, read_on}, the shape AD's P807lu §3.1 proposed, so every value
on the form names where it came from.

A fact comes from what the person SAID on WhatsApp ("said on WhatsApp, 3 Oct 2026"), from a DOCUMENT they sent and
confirmed ("passport photo page, read 3 Oct 2026, confirmed by you"), or from a CHOICE they made ("your choice: notices
to your own address"). Two sources for one fact are both kept: the checker compares them (P807jy: an application comes
back over one fact that disagrees across documents).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Callable, Dict, List, Optional, Tuple

NIE_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"


def nie_ok(letter: str, number: str, control: str) -> bool:
    """The NIE's control letter: X/Y/Z → 0/1/2 prefixed to the 7 digits, mod 23 (the same table as the DNI's)."""
    if letter.upper() not in "XYZ" or not re.fullmatch(r"\d{7}", number or "") or len(control or "") != 1:
        return False
    n = int(str("XYZ".index(letter.upper())) + number)
    return NIE_LETTERS[n % 23] == control.upper()


# Spain's 52 provinces by the first two digits of a postcode (INE province codes) — for the checker's cross-check
PROVINCES = {
    "01": "Álava", "02": "Albacete", "03": "Alicante", "04": "Almería", "05": "Ávila", "06": "Badajoz", "07": "Baleares",
    "08": "Barcelona", "09": "Burgos", "10": "Cáceres", "11": "Cádiz", "12": "Castellón", "13": "Ciudad Real", "14": "Córdoba",
    "15": "A Coruña", "16": "Cuenca", "17": "Girona", "18": "Granada", "19": "Guadalajara", "20": "Gipuzkoa", "21": "Huelva",
    "22": "Huesca", "23": "Jaén", "24": "León", "25": "Lleida", "26": "La Rioja", "27": "Lugo", "28": "Madrid", "29": "Málaga",
    "30": "Murcia", "31": "Navarra", "32": "Ourense", "33": "Asturias", "34": "Palencia", "35": "Las Palmas", "36": "Pontevedra",
    "37": "Salamanca", "38": "Santa Cruz de Tenerife", "39": "Cantabria", "40": "Segovia", "41": "Sevilla", "42": "Soria",
    "43": "Tarragona", "44": "Teruel", "45": "Toledo", "46": "Valencia", "47": "Valladolid", "48": "Bizkaia", "49": "Zamora",
    "50": "Zaragoza", "51": "Ceuta", "52": "Melilla",
}
_PROV_ALIASES = {"alava": "01", "araba": "01", "alicante": "03", "alacant": "03", "baleares": "07", "illes balears": "07",
                 "islas baleares": "07", "castellon": "12", "castello": "12", "a coruna": "15", "la coruna": "15", "coruna": "15",
                 "gipuzkoa": "20", "guipuzcoa": "20", "girona": "17", "gerona": "17", "lleida": "25", "lerida": "25",
                 "ourense": "32", "orense": "32", "bizkaia": "48", "vizcaya": "48", "valencia": "46", "valència": "46"}


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower().strip()


def province_code(name: str) -> Optional[str]:
    f = fold(name)
    if f in _PROV_ALIASES:
        return _PROV_ALIASES[f]
    for code, p in PROVINCES.items():
        if fold(p) == f:
            return code
    return None


# ── parsing what a person typed ──────────────────────────────────────────────────────────────────────────────────────

_NONE = re.compile(r"^\s*(none|no|n/?a|not yet|i don'?t have (?:one|it)|no tengo|ninguno|-)\s*\.?\s*$", re.I)


def is_none(t: str) -> bool:
    return bool(_NONE.match(t or ""))


def parse_date(t: str) -> Optional[str]:
    t = re.sub(r"\s+", " ", (t or "").strip())
    for fmt in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%B %d, %Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            continue
    return None


SEX = {"m": "H", "male": "H", "man": "H", "h": "H", "hombre": "H", "f": "M", "female": "M", "woman": "M", "mujer": "M",
       "x": "X", "unspecified": "X", "non-binary": "X", "nonbinary": "X"}
MARITAL = {"single": "S", "soltero": "S", "soltera": "S", "s": "S", "married": "C", "casado": "C", "casada": "C", "c": "C",
           "widowed": "V", "widow": "V", "widower": "V", "viudo": "V", "viuda": "V", "v": "V", "divorced": "D",
           "divorciado": "D", "divorciada": "D", "d": "D", "separated": "Sp", "separado": "Sp", "separada": "Sp", "sp": "Sp"}
SEX_WORDS = {"H": "male (H)", "M": "female (M)", "X": "X"}
MARITAL_WORDS = {"S": "single (S)", "C": "married (C)", "V": "widowed (V)", "D": "divorced (D)", "Sp": "separated (Sp)"}


#: CR 30 · not an answer, said in any of the ways people say it — never stored as a value
NOT_AN_ANSWER = re.compile(r"(?i)^\s*(hmm+|umm*|err*|\?+|idk|not sure|unsure|no idea|i don'?t know|dunno|don'?t remember|"
                           r"no s[eé]|ni idea|no lo s[eé]|wait|one sec(ond)?|hang on)\b")


def _text(min_len: int = 1) -> Callable[[str], Tuple[Optional[str], Optional[str]]]:
    def p(t: str):
        t = re.sub(r"\s+", " ", (t or "").strip())
        if NOT_AN_ANSWER.match(t):
            return None, "No problem — type it when you have it, or say “later” and I'll keep everything."
        return (t, None) if len(t) >= min_len else (None, "Please type it out.")
    return p


def _passport(t: str):
    """The number, from however it's said: "AB1234567", "ab 123 4567", "my passport number is AB1234567" (CR 30: a whole
    sentence used to be squashed into one long string and refused — every time). It has 5–12 letters and digits and at
    least one digit ("HMMNOTSURE" isn't a number)."""
    if NOT_AN_ANSWER.match(t or ""):
        return None, "No problem — send a photo of the passport's photo page and I'll read it, or type the number when you have it."
    whole = re.sub(r"[\s-]", "", t or "").upper()
    if re.fullmatch(r"(?=.*\d)[A-Z0-9]{5,12}", whole):
        return whole, None
    tokens = [x for x in re.findall(r"[A-Z0-9]+", (t or "").upper()) if re.fullmatch(r"(?=.*\d)[A-Z0-9]{5,12}", x)]
    if len(tokens) == 1:
        return tokens[0], None
    return None, "A passport number is letters and digits, e.g. 567812345 — or send a photo of the photo page and I'll read it."


def _nie(t: str):
    if is_none(t):
        return "", None
    v = re.sub(r"[\s.-]", "", t or "").upper()
    m = re.fullmatch(r"([XYZ])(\d{7})([A-Z])", v)
    if not m:
        return None, "An NIE looks like X1234567L — or say NONE if you don't have one yet."
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", None


def _date_past(t: str):
    d = parse_date(t)
    if not d:
        return None, "Please write the date like 14 March 1985 or 14/03/1985 (day first)."
    if d >= date.today().isoformat():
        return None, "That date isn't in the past — could you check it?"
    return d, None


def _date_any(t: str):
    d = parse_date(t)
    return (d, None) if d else (None, "Please write the date like 14 March 2031 or 14/03/2031 (day first).")


def _choice(table: Dict[str, str], ask: str):
    def p(t: str):
        v = table.get(fold(t).strip(" ."))
        return (v, None) if v else (None, ask)
    return p


def _yesno(t: str):
    f = fold(t)
    if re.match(r"^(yes|y|si|sí)\b", f):
        return "yes", None
    if re.match(r"^(no|n)\b", f):
        return "no", None
    return None, "Yes or no?"


def _email(t: str):
    v = (t or "").strip()
    return (v, None) if re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", v) else (None, "That doesn't look like an email address.")


def _mobile(t: str):
    v = re.sub(r"[\s().-]", "", t or "")
    return (v, None) if re.fullmatch(r"\+?\d{8,15}", v) else (None, "A mobile number with its country code, e.g. +34 600 000 000.")


def _postcode(t: str):
    v = re.sub(r"\s", "", t or "")
    return (v, None) if re.fullmatch(r"\d{5}", v) and v[:2] in PROVINCES else (None, "A Spanish postcode is five digits, e.g. 28010.")


def _optional_text(t: str):
    return ("", None) if is_none(t) else _text()(t)


# key, the question, the parser — the ORDER is the conversation's (applicant first, as the form reads)
APPLICANT: List[Tuple[str, str, Callable]] = [
    ("passport_number", "Your passport number?", _passport),
    ("surname_1", "Your first surname, exactly as on your passport?", _text()),
    ("surname_2", "Your second surname? (Say NONE if your passport shows only one.)", _optional_text),
    ("given_names", "Your given name(s), as on your passport?", _text()),
    ("sex", "Sex as shown on your passport: M, F or X?", _choice(SEX, "M, F or X, as your passport shows it.")),
    ("birth_date", "Your date of birth? (day first, e.g. 14/03/1985)", _date_past),
    ("birth_place", "Your place of birth (town or city)?", _text()),
    ("birth_country", "Your country of birth?", _text(2)),
    ("nationality", "Your nationality?", _text(2)),
    ("passport_expiry", "When does your passport expire? (It isn't on the form, but the checker uses it.)", _date_any),
    ("marital_status", "Marital status: single, married, widowed, divorced or separated?",
     _choice(MARITAL, "Single, married, widowed, divorced or separated?")),
    ("father_name", "Your father's name? (Say NONE to leave it blank.)", _optional_text),
    ("mother_name", "Your mother's name? (Say NONE to leave it blank.)", _optional_text),
    ("nie", "Do you already have an NIE? Type it (e.g. X1234567L), or NONE.", _nie),
    ("address_street", "Your address in Spain — street name only? (Say NONE if you don't have one yet.)", _optional_text),
    ("address_number", "The street number?", _text()),
    ("address_floor", "Floor and door (e.g. 3º B)? Say NONE if it's a house.", _optional_text),
    ("address_town", "Town or city?", _text(2)),
    ("address_postcode", "Postcode?", _postcode),
    ("address_province", "Province?", _text(2)),
    ("mobile", "Your mobile number, with the country code?", _mobile),
    ("email", "Your email address?", _email),
    # CR 44 · the Keep: asked once, here, because the national visa form, the EX-17, the padrón and the TA.1 need them too
    ("home_address_abroad", "Your home address now, where you live (street, city, state or region, postcode, country)?", _text(8)),
    ("occupation", "Your current occupation?", _text(2)),
    ("passport_issued", "Your passport's date of issue? (on its photo page, e.g. 30/06/2021)", _date_past),
    ("passport_issuer", "Issued by — the authority printed on your passport (e.g. United States Department of State)?", _text(3)),
    ("school_age_children_in_spain", "Do you have children of school age who will be in your care in Spain? Yes or no.", _yesno),
]
ADDRESS_KEYS = ("address_number", "address_floor", "address_town", "address_postcode", "address_province")


def questions_for(facts: Dict[str, dict]) -> List[Tuple[str, str, Callable]]:
    """What is still to ask. No Spanish street → the rest of the address isn't asked."""
    no_street = "address_street" in facts and facts["address_street"]["value"] == ""
    return [q for q in APPLICANT if q[0] not in facts and not (no_street and q[0] in ADDRESS_KEYS)]


def fact(value: str, source: str, read_on: str) -> dict:
    return {"value": value, "source": source, "read_on": read_on}
