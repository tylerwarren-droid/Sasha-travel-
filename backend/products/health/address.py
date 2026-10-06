"""CR 35 · a Spanish address as the DNI prints it → its parts, the way the Comunidad's forms and SERMAS's finder use them.

  "VEREDA DE PALACIO, Nº 1, PORTAL 8, 11-B"  → name VEREDA DE PALACIO · number 1 · portal 8 · floor 11 · door B
  "C. PADRE DAMIAN 41 P05 B"                 → type CALLE · name PADRE DAMIAN · number 41 · floor 05 · door B
  "AVDA. DE AMERICA 12, 3º B"                → type AVENIDA · name DE AMERICA · number 12 · floor 3 · door B
The type words are the Comunidad's own (the 1449F1's street-type list, read 6 Oct 2026), only those that are street types
and never the start of a name ("PALACIO", "PUERTA", "CASA" are on that list too — as types of building, not of street).
A word that is a type in one address can be the name in another: SERMAS lists Alcobendas's "CALLE DE LA VEREDA DE PALACIO",
so matching tries the name with and without a leading type word (key()).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Set

# the 1449F1's TLTIPOVIAL_INTER options that name a kind of street
TYPES = ("ALAMEDA", "AUTOVIA", "AVENIDA", "BAJADA", "BARRIO", "BULEVAR", "CALLE", "CALLEJA", "CALLEJON", "CAMINO", "CAÑADA",
         "CARRERA", "CARRETERA", "CARRIL", "COLONIA", "COSTANILLA", "CUESTA", "GLORIETA", "PASAJE", "PASEO", "PLAZA",
         "PLAZUELA", "POLIGONO", "PROLONGACION", "RAMBLA", "RONDA", "ROTONDA", "SENDA", "SUBIDA", "TRAVESIA", "URBANIZACION",
         "VEREDA", "VIA")
# the DNI's and SERMAS's abbreviations (SERMAS's finder writes "CRA DE SAN JERONIMO", "PSAJE DE …")
ABBR = {"C": "CALLE", "CL": "CALLE", "CALL": "CALLE", "AV": "AVENIDA", "AVD": "AVENIDA", "AVDA": "AVENIDA", "PZA": "PLAZA",
        "PL": "PLAZA", "PLZA": "PLAZA", "PS": "PASEO", "PSO": "PASEO", "PJE": "PASAJE", "PSAJE": "PASAJE", "CTRA": "CARRETERA",
        "CRA": "CARRERA", "CMNO": "CAMINO", "CM": "CAMINO", "RDA": "RONDA", "TRAV": "TRAVESIA", "TRVA": "TRAVESIA",
        "GTA": "GLORIETA", "URB": "URBANIZACION", "CTLLA": "COSTANILLA", "CJON": "CALLEJON", "VDA": "VEREDA", "BULV": "BULEVAR",
        "BULEV": "BULEVAR", "COL": "COLONIA", "CUSTA": "CUESTA", "CSTA": "CUESTA", "PRAZ": "PLAZUELA", "SDA": "SENDA"}
ARTICLES = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "Y"}


def plain(s: str) -> str:
    """Upper case, accents off (Ñ kept), punctuation to spaces."""
    s = (s or "").upper().replace("Ñ", "\0")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().replace("\0", "Ñ")
    return re.sub(r"\s+", " ", re.sub(r"[^A-ZÑ0-9/º ]", " ", s.replace("º", "º "))).strip()


def _type_of(word: str) -> str:
    w = word.rstrip(".").rstrip("/")
    return w if w in TYPES else ABBR.get(w, "")


_UNIT = re.compile(r"\b(?:(PORTAL|PTAL)|(ESCALERA|ESC)|(PISO|PLANTA|PLTA|PL|P(?=\d))|(PUERTA|PTA|PRTA)|(BLOQUE|BLQ))\s*\.?\s*"
                   r"(BAJO|BJ|IZQ|DCHA|[0-9]+[A-Z]?|[A-Z]{1,2}\b)", re.I)


def parse(line: str) -> Dict[str, str]:
    """→ {type, name, number, portal, stair, floor, door, block}; "" where the address doesn't say."""
    out = {k: "" for k in ("type", "name", "number", "portal", "stair", "floor", "door", "block")}
    t = (line or "").upper().replace("Nº", " ").replace("N°", " ")
    t = re.sub(r"\bN(?:UM(?:ERO)?)?\s*\.\s*(?=\d)", " ", t)
    t = re.sub(r"[,;]", " , ", t)
    words = plain(t.replace("/", "/ ")).split()
    if words and _type_of(words[0]) and len(words) > 1:
        out["type"] = _type_of(words[0])
        words = words[1:]
    t = " ".join(words)
    m = re.search(r"^(.*?[A-ZÑ])\s*,?\s+(\d+[A-Z]?)\b(.*)$", t)
    if not m:
        out["name"] = t.strip(" ,")
        return out
    out["name"], out["number"], rest = m.group(1).strip(" ,"), m.group(2), m.group(3)
    for u in _UNIT.finditer(rest):
        key = ("portal", "stair", "floor", "door", "block")[next(i for i in range(5) if u.group(i + 1))]
        out[key] = out[key] or u.group(6)
    rest = _UNIT.sub(" ", rest)
    left = [x for x in re.split(r"[\s,]+", rest) if x]
    for x in left:                                   # what's left, in the DNI's order: "11-B" / "3º B" / "05 B"
        fl = re.fullmatch(r"(\d+|BJ|BAJO)º?(?:-([A-Z0-9]{1,3}))?", x)
        if fl and not out["floor"]:
            out["floor"] = fl.group(1)
            out["door"] = out["door"] or (fl.group(2) or "")
        elif re.fullmatch(r"[A-Z]{1,2}|IZQ|DCHA|\d{1,2}", x) and not out["door"] and out["floor"]:
            out["door"] = x
    if re.fullmatch(r"P\d+", out["name"].split()[-1] if out["name"] else ""):
        out["name"] = " ".join(out["name"].split()[:-1])
    return out


def words(s: str) -> List[str]:
    return [w for w in plain(s).split() if w not in ARTICLES and w != "º"]


def keys(name: str) -> Set[str]:
    """The name with and without a leading street type ("CALLE DE LA VEREDA DE PALACIO" ↔ "VEREDA DE PALACIO")."""
    w = [ABBR.get(x, x) for x in words(name)]
    out = {" ".join(w)}
    if len(w) > 1 and w[0] in TYPES:
        out.add(" ".join(w[1:]))
    return {k for k in out if k}


def full(p: Dict[str, str]) -> str:
    return f"{p['type']} {p['name']}".strip()


def queries(p: Dict[str, str]) -> List[str]:
    """What to type into SERMAS's finder, most precise first: the type and name as written ("VEREDA DE PALACIO" — it may be
    the name), the name alone, without articles, then each distinctive word, longest first (the finder matches the typed
    text inside its street names, so a single word lists every street that has it)."""
    name = plain(p["name"])
    qs = [plain(full(p)) if p["type"] else "", name, " ".join(words(name))]
    qs += sorted({w for w in words(name) if len(w) >= 4 and w not in TYPES}, key=len, reverse=True)
    return [q for i, q in enumerate(qs) if q and q not in qs[:i]][:4]


def same(p: Dict[str, str], theirs: str) -> bool:
    """The same street: one side's whole name is the other's, with or without its leading type word — so
    "VEREDA DE PALACIO" is SERMAS's "CALLE DE LA VEREDA DE PALACIO", but never its "PLAZA DEL PALACIO"."""
    ours_full, their_full = " ".join(ABBR.get(w, w) for w in words(full(p))), " ".join(ABBR.get(w, w) for w in words(theirs))
    return ours_full in keys(theirs) or their_full in keys(full(p))


def closeness(ours: str, theirs: str) -> float:
    a, b = {ABBR.get(w, w) for w in words(ours)}, {ABBR.get(w, w) for w in words(theirs)}
    return len(a & b) / len(a | b) if a | b else 0.0
