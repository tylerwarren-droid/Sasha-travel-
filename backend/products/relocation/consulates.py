"""CR 12 · the Spanish consulates beyond London — each one's OWN non-lucrative-visa page, read at source, dated.

Where it comes from: scripts/cr12_consulates_read.py reads exteriores.gob.es (robots.txt first: /Consulados/ allowed;
≥ 10 s between requests) starting at the ministry's own directory of embassies and consulates, then each consulate's
home page, its "Demarcación" page (the territory it covers, with that page's own date) and its services catalogue, and
opens "Visados Nacionales - Visado de residencia no lucrativa" through the catalogue's OWN parameters (the consulate
code its home page links carry; the category and service names its catalogue publishes) — never an address composed
from memory. Each page is kept with its sha256 in docs/products/reads/us/; what it says is in consulates_read.json.

What it is used for, and nothing more:
  · the checklist — the page's own numbered "Documentos necesarios", in its own order and its own (Spanish) words; the
    English line beside each is OUR short label for it, marked as such;
  · the appointment route — the page's own "Lugar de presentación", quoted; an email route is prepared as a draft the
    applicant sends (we never send it, never book);
  · the document pack — what the applicant says they've gathered, numbered and named in the consulate's order, with the
    page's own words on originals and copies.
A consulate whose page couldn't be read, or doesn't publish the list, gets NO checklist and NO link: we say so.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional

_DATA = json.loads((Path(__file__).with_name("consulates_read.json")).read_text())
READ: Dict[str, dict] = _DATA["consulates"]
NETWORK: dict = _DATA.get("network") or {}

# OUR English labels for the consulates' own item titles (matched on their Spanish words; unmatched items keep Spanish)
_LABELS = [
    ("visa_form", r"solicitud de visado nacional", "National visa application form"),
    ("ex01", r"\bEX.?-?\s?01\b|autorizaci[oó]n de residencia no lucrativa", "EX-01 (residence authorisation form)"),
    ("photo", r"fotograf", "Passport photo"),
    ("passport", r"pasaporte", "Passport"),
    ("means", r"medios econ[oó]micos", "Proof of economic means"),
    ("insurance", r"seguro", "Health insurance"),
    ("criminal_record", r"antecedentes penales", "Criminal record certificate"),
    ("medical", r"certificado m[eé]dico", "Medical certificate"),
    ("residence_proof", r"residencia en la demarcaci|demarcaci[oó]n consular", "Proof you live in the consulate's territory"),
    ("fee", r"\btasas?\b|790", "Fees (form 790-052)"),
]

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico",
}
# the Spanish (and other) spellings consulates use for state names, so their own territory sentence can be matched
_ES = {"Nueva York": "New York", "Nueva Jersey": "New Jersey", "Pensilvania": "Pennsylvania", "Carolina del Norte":
       "North Carolina", "Carolina del Sur": "South Carolina", "Dakota del Norte": "North Dakota", "Dakota del Sur":
       "South Dakota", "Virginia Occidental": "West Virginia", "Nuevo México": "New Mexico", "Nuevo Mexico": "New Mexico",
       "Nuevo Hampshire": "New Hampshire", "Misisipi": "Mississippi", "Misuri": "Missouri", "Luisiana": "Louisiana",
       "Hawái": "Hawaii", "Kansas": "Kansas", "Oregón": "Oregon", "Míchigan": "Michigan", "Tejas": "Texas",
       "West Virgina": "West Virginia",   # the network list's own spelling (Washington's line)
       "Distrito de Columbia": "District of Columbia", "Washington D.C.": "District of Columbia", "Washington DC":
       "District of Columbia", "Puerto Rico": "Puerto Rico"}

# the consulates' own cities' clocks (for an appointment the applicant booked there)
TZ = {"newyork": "America/New_York", "washington": "America/New_York", "boston": "America/New_York",
      "miami": "America/New_York", "chicago": "America/Chicago", "houston": "America/Chicago",
      "losangeles": "America/Los_Angeles", "sanfrancisco": "America/Los_Angeles"}

_US = re.compile(r"(?i)^\s*(the\s+)?(us|u\.s\.?|usa|u\.s\.a\.?|united states( of america)?|america|estados unidos|eeuu|ee\.\s?uu\.?)\s*\.?\s*$")


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower().strip()


def label_for(title: str, text: str) -> tuple:
    for key, rx, en in _LABELS:
        if re.search(rx, title or "", re.I):
            return key, en
    for key, rx, en in _LABELS:
        if re.search(rx, (text or "")[:160], re.I):
            return key, en
    return None, None


def territory(cid: str) -> dict:
    """Where the territory comes from: the consulate's OWN Demarcación page when it names states, else the US network
    list one consulate publishes on its Demarcación page (each office with its 'Jurisdicción:' line). Never inferred."""
    own = (READ.get(cid) or {}).get("territory") or {}
    if own.get("text") and _names(own["text"]):
        return {"text": own["text"], "dated": own.get("dated"), "url": own.get("url"), "from": "its own page"}
    net = (NETWORK.get("offices") or {}).get(cid)
    if net:
        return {"text": net["text"], "dated": None, "url": NETWORK["url"], "from": f"the US consular network list on the {NETWORK['from']}'s page"}
    return {}


def states_of(cid: str) -> List[str]:
    return _names(territory(cid).get("text") or "")


def _names(t: str) -> List[str]:
    """The US states a sentence names (English names), whatever language it's in."""
    for es, en in _ES.items():
        t = t.replace(es, en)
    names = sorted(set(US_STATES.values()), key=len, reverse=True)
    found, rest = [], t
    for n in names:   # longest first: "West Virginia" before "Virginia", "District of Columbia" before nothing else
        if re.search(r"\b" + re.escape(n) + r"\b", rest):
            found.append(n)
            rest = re.sub(r"\b" + re.escape(n) + r"\b", " ", rest)
    return sorted(found)


def is_us(text: str) -> bool:
    return bool(_US.match(text or ""))


def state_from(text: str) -> Optional[str]:
    t = (text or "").strip().strip(".")
    if t.upper() in US_STATES:
        return US_STATES[t.upper()]
    ft = fold(t)
    for es, en in _ES.items():
        if fold(es) == ft:
            return en
    for n in US_STATES.values():
        if fold(n) == ft or re.search(r"\b" + re.escape(fold(n)) + r"\b", ft):
            return n
    return None


def for_state(state: str) -> Optional[str]:
    """The consulate whose territory (as published) names this state, or None (then we say so — never a guess). A state
    two consulates split (California) returns None here: see split_counties()."""
    hits = [cid for cid in READ if state in states_of(cid)]
    return hits[0] if len(hits) == 1 else None


def split(state: str) -> Optional[dict]:
    """A state the network list divides by county — California: one consulate names its counties ('condados de …'), the
    other takes 'the rest'. → {"named": cid, "counties": [...], "rest": cid}, or None."""
    hits = [cid for cid in READ if state in states_of(cid)]
    if len(hits) != 2:
        return None
    for named, rest in (hits, hits[::-1]):
        texts = [territory(named).get("text") or "", ((NETWORK.get("offices") or {}).get(named) or {}).get("text") or ""]
        m = next((x for x in (re.search(re.escape(state) + r"\s*\(condados de ([^)]*)\)", t) or
                              re.search(r"(?i)Sur de " + re.escape(state) + r"\s*:\s*Condados de ([^.]*)\.", t) for t in texts) if x), None)
        if m:
            counties = [c.strip() for c in re.split(r",\s*|\s+y\s+", m.group(1)) if c.strip()]
            return {"named": named, "counties": counties, "rest": rest}
    return None


def county_in(text: str, counties: List[str]) -> Optional[str]:
    ft = fold(re.sub(r"(?i)\bcounty\b", "", text or ""))
    for c in counties:
        if fold(c) == ft.strip() or re.search(r"\b" + re.escape(fold(c)) + r"\b", ft):
            return c
    return None


# the ministry template's own unfilled fields, left on some consulates' pages ("Campo para informar sobre …")
_PLACEHOLDER = re.compile(r"Campo (?:libre )?para (?:informar|añadir)[^.]*\.(?:\s*\([^)]*\))?")


def localised(cid: str) -> bool:
    """Whether a consulate's page adds anything of its own to the ministry's shared text: an appointment route, or an
    item worded differently from what most of the others publish. False = the template as it stands."""
    r = READ.get(cid) or {}
    if (r.get("route") or {}).get("text"):
        return True
    from collections import Counter
    for it in r.get("items") or []:
        norm = lambda x: re.sub(r"\W+", " ", _PLACEHOLDER.sub("", x)).strip().lower()   # spacing, punctuation, placeholders
        same_n = Counter(norm(x["text"]) for v in READ.values() for x in (v.get("items") or []) if x["n"] == it["n"])
        if same_n and len(norm(it["text"])) > len(same_n.most_common(1)[0][0]) + 40:   # it ADDS words of its own
            return True
    return False


def usable(cid: str) -> bool:
    r = READ.get(cid) or {}
    return bool(r.get("items")) and not r.get("error")


def consulate(cid: str) -> Optional[dict]:
    """The shape after.py and the file page use for a consulate: office, the route in its own words, the source."""
    r = READ.get(cid)
    if not r or not usable(cid):
        return None
    route = r.get("route") or {}
    email = next((urllib.parse.unquote(u.split(":", 1)[1]).strip() for _, u in route.get("links", []) if u.lower().startswith("mailto:")), None)
    web = next((u for t, u in route.get("links", []) if u.startswith("http")), None)
    return {
        "id": cid, "office": r["office"], "country": "united states",
        "appointment_words": route.get("text") or "", "appointment_email": email, "appointment_url": web,
        "appointment_asks": _asks(cid),
        "one_per_person": "the page asks for every applicant's details in the request",
        "territory": {**territory(cid), "states": states_of(cid)},
        "general": r.get("general"), "localised": localised(cid),
        "source": {"name": f"{r['office']} — Visado de residencia no lucrativa (its own page)",
                   "url": r["visa_page"]["url"], "dated": r.get("dated") or "the page shows no date",
                   "read": r["read"], "sha256": r["visa_page"]["sha256"]},
    }


_COPIES = [(r"dos ejemplares", "two signed copies"), (r"original y (una )?(foto)?copia", "the original and one copy"),
           (r"original y fotocopia", "the original and one copy"), (r"un ejemplar", "one copy, signed")]


def copies(text: str) -> Optional[str]:
    for rx, en in _COPIES:
        if re.search(rx, text or "", re.I):
            return en
    return None


def checklist(cid: str) -> List[dict]:
    """The consulate's own numbered list. words = the page's words (Spanish); label = ours (English), marked as ours."""
    r = READ[cid]
    out = []
    for it in r["items"]:
        key, en = label_for(it.get("title") or "", it["text"])
        ph = _PLACEHOLDER.search(it["text"])
        out.append({"key": key or f"item_{it['n']}", "n": it["n"], "label": en, "label_is_ours": True,
                    "placeholder": ph.group(0) if ph else None,   # shown as the page's unfilled template field, not a rule
                    "words": it["text"], "copies": copies(it["text"]),
                    "links": [{"text": t, "url": u} for t, u in it.get("links", []) if u.startswith("http")],
                    "source": f"{r['office']}, its own page (read {r['read']})"})
    return out


def _slug(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()).strip("-")
    return s[:60].rstrip("-") or "document"


def pack(items: List[dict], have: set) -> List[dict]:
    """The document pack: each item in the consulate's own order, named so the files sort in that order, with what the
    page says about originals and copies. 'prepared' = the EX-01 Kanoe prepared (signed by the applicant)."""
    out = []
    for it in items:
        status = "prepared" if it["key"] == "ex01" else ("gathered" if it["n"] in have else "missing")
        title = it["label"] or (it["words"].split(".")[0])
        out.append({"n": it["n"], "name": f"{it['n']:02d}_{_slug(title)}", "title": title, "status": status,
                    "copies": it["copies"], "words": it["words"]})
    return out


def numbers_in(text: str, top: int) -> Optional[set]:
    """'1 3 4-6' / 'all' → the item numbers; None when it isn't a list of numbers."""
    t = (text or "").strip().lower()
    if re.fullmatch(r"(all|todos?|everything)", t):
        return set(range(1, top + 1))
    if not re.fullmatch(r"[\d\s,;\-–and&y]+", t) or not re.search(r"\d", t):
        return None
    got = set()
    for m in re.finditer(r"(\d+)\s*[-–]\s*(\d+)|(\d+)", t):
        lo, hi = (int(m.group(1)), int(m.group(2))) if m.group(1) else (int(m.group(3)), int(m.group(3)))
        got |= {n for n in range(lo, hi + 1) if 1 <= n <= top}
    return got


def _asks(cid: str) -> List[dict]:
    """The page's own lettered list of what the appointment email must carry: each kept in its words; whether it's a line
    of the email or a file to attach; which of our fields can fill it (never a passport number — theirs to type)."""
    out = []
    for letter, words in (READ.get(cid) or {}).get("route_asks_raw") or []:
        w = words.strip().rstrip(" .")
        attach = bool(re.search(r"(?i)copia escaneada|adjunt|pdf", w))
        fill = ("name" if re.search(r"(?i)nombre", w) else "contact" if re.search(r"(?i)correo|tel[eé]fono", w)
                else "visa" if re.search(r"(?i)tipo de visado", w) else None)
        out.append({"letter": letter, "words": w, "attach": attach, "fill": None if attach else fill})
    return out


def email_draft(c: dict, applicant: dict) -> Optional[dict]:
    """The appointment request the page asks for, as a DRAFT the applicant sends from their own address: each lettered
    line the page lists, filled where we know it and left as [to fill] where we don't; the files to attach named, not
    attached. We never send it."""
    if not c.get("appointment_email"):
        return None
    asks = c.get("appointment_asks") or []
    lines = [f"{x['letter']}) {x['words']}: {applicant.get(x['fill']) or '[to fill]'}" for x in asks if not x["attach"]]
    files = [f"{x['letter']}) {x['words']}" for x in asks if x["attach"]]
    body = ("Buenos días:\n\nSolicito cita previa para presentar una solicitud de visado de residencia no lucrativa.\n\n"
            + "\n".join(lines) + ("\n\nAdjunto:\n" + "\n".join(files) if files else "") + "\n\nUn saludo.")
    subject = "Solicitud de cita — visado de residencia no lucrativa"
    return {"to": c["appointment_email"], "subject": subject, "body": body, "attach": files,
            "mailto": f"mailto:{c['appointment_email']}?" + urllib.parse.urlencode({"subject": subject, "body": body},
                                                                                     quote_via=urllib.parse.quote)}


def unread_offices() -> List[str]:
    return [r.get("office") or cid for cid, r in READ.items() if not usable(cid)]


def summary() -> Dict[str, dict]:
    """For the readout and the health route: each consulate, read or not, and why."""
    return {cid: {"office": r.get("office"), "items": len(r.get("items") or []), "route": bool(r.get("route")),
                  "states": states_of(cid), "error": r.get("error")} for cid, r in READ.items()}
