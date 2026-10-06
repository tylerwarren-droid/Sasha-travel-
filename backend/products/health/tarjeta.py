"""CR 30 (3) · ESPAÑAME — YOUR HEALTH CARD (Tarjeta Sanitaria, Comunidad de Madrid), from your DNI or passport.

The official process, read 6 Oct 2026:
  · www.comunidad.madrid/servicios/salud/tarjeta-sanitaria — in person at your health centre, or online ONLY with a DNIe
    or digital certificate (the citizen's sign-in, never Sasha's); documents: DNI, padrón (or authorise the consultation),
    INSS right to care (or authorise it); no fee; collected in person.
  · sede.comunidad.madrid/prestacion-social/tarjeta-sanitaria (updated 18/05/2026) — the in-person route: the official form
    "Solicitud de la Tarjeta Sanitaria", impreso **1449F1**, filled, printed, SIGNED and presented in person (by cita).
  · The online form (gestiona.comunidad.madrid …impresoGForms.jsf?cdImpreso=1449F1) is behind "demuestra que no eres un
    robot" — a CAPTCHA on a real site: never through Kanoe's browser. So the hand-over is the official PDF, filled here.

Sasha reads the ID (photo: DNI front and back, or a passport), checks it (the DNI letter; the machine-readable lines' check
digits), reads every value back for ONE yes, asks only what is missing, and fills 1449F1 field by field — each value naming
its source. LEFT FOR THE CITIZEN, never filled or ticked: §6's "I object to the electronic consultation" boxes, §5 how to be
notified, the date and the SIGNATURE. Nothing is submitted. No health identifier is asked or kept (the Social Security
number is optional on the form — the Comunidad consults the INSS — and is never asked); the case keeps the ID details for
24 hours (VALUES_TTL), then they're dropped.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import pathlib
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from booking_signer import yes as YS

from .. import store as ST

log = logging.getLogger("products.health.tarjeta")
HERE = pathlib.Path(__file__).parent
PDF = HERE / "1449F1-official.pdf"
PDF_SHA256 = "654a7c814a7727bca290464478667441dceb67a474028f5a3a5b2f2894d261a3"
SOURCE = {"name": "Solicitud de la Tarjeta Sanitaria (impreso 1449F1, Comunidad de Madrid)",
          "pdf": "https://gestiona7.madrid.org/i012_impresos/run/j/VerImpreso.icm?CDIMPRESO=1449F1",
          "procedure": "https://sede.comunidad.madrid/prestacion-social/tarjeta-sanitaria",
          "page": "https://www.comunidad.madrid/servicios/salud/tarjeta-sanitaria",
          "centres": "http://centrossanitarios.sanidadmadrid.org/",
          "read_on": "6 Oct 2026", "updated": "18/05/2026"}
VALUES_TTL = timedelta(hours=24)
MODEL = "claude-opus-5-5"
DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
MOTIVES = {"NUEVA": "a new card (first issue)", "DOMICILIO": "a change of registered address", "MODIFICACION": "a change of personal details",
           "EXTRAVIO": "a lost, stolen or damaged card"}
MOTIVE_BUTTONS = [("New card", "hx:ts:m:NUEVA"), ("New address", "hx:ts:m:DOMICILIO"), ("Lost / damaged", "hx:ts:m:EXTRAVIO")]
SHIFTS = {"MANIANA": "mornings", "TARDE": "afternoons", "INDISTINTO": "either"}
STREET_TYPES = {"CALLE": r"C/?|CL|CALLE", "AVENIDA": r"AV|AVD|AVDA|AVENIDA", "PLAZA": r"PL|PZA|PLAZA", "PASEO": r"PS|PSO|PASEO",
                "CARRETERA": r"CTRA|CARRETERA", "CAMINO": r"CMNO|CAMINO", "RONDA": r"RDA|RONDA", "TRAVESIA": r"TRAV|TRAVESIA",
                "GLORIETA": r"GTA|GLORIETA", "COSTANILLA": r"CTLLA|COSTANILLA", "PASAJE": r"PJE|PASAJE", "URBANIZACION": r"URB|URBANIZACION"}
LEFT_FOR_YOU = ["§5 how you'd like to be notified (online or by certified post) — your choice",
                "§6 the boxes to tick ONLY if you object to the Comunidad consulting your DNI, padrón and INSS records — "
                "leave them blank to let it consult (then you needn't bring copies)",
                "the date, and your signature"]


# ── reading the ID ─────────────────────────────────────────────────────────────────────────────────────────────────

SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "doc_type": {"type": "string", "enum": ["dni_front", "dni_back", "passport", "other"]},
    "legible": {"type": "boolean"},
    "dni_number": {"type": "string"}, "passport_number": {"type": "string"}, "support_number": {"type": "string"},
    "surname_1": {"type": "string"}, "surname_2": {"type": "string"}, "given_names": {"type": "string"},
    "sex": {"type": "string"}, "nationality": {"type": "string"}, "birth_date": {"type": "string"}, "expiry_date": {"type": "string"},
    "birth_place": {"type": "string"}, "birth_province": {"type": "string"},
    "address_line": {"type": "string"}, "address_municipality": {"type": "string"}, "address_province": {"type": "string"},
    "mrz_lines": {"type": "array", "items": {"type": "string"}}},
    "required": ["doc_type", "legible", "dni_number", "passport_number", "support_number", "surname_1", "surname_2", "given_names",
                 "sex", "nationality", "birth_date", "expiry_date", "birth_place", "birth_province", "address_line",
                 "address_municipality", "address_province", "mrz_lines"]}
PROMPT = ("This is a photo of a Spanish identity document: the FRONT or BACK of a DNI, or a passport's photo page. Transcribe "
          "exactly what is printed — never guess or complete a value; use \"\" for anything not on THIS side or not legible. "
          "doc_type: dni_front, dni_back, passport or other. Dates as YYYY-MM-DD. sex as printed (M/F). dni_number with its "
          "letter (e.g. 12345678Z). On a DNI back: the address lines (DOMICILIO), its municipality and province, the place of "
          "birth (LUGAR DE NACIMIENTO) and its province, and the three machine-readable lines at the bottom exactly as printed, "
          "'<' included. On a passport: its two machine-readable lines.")


async def _model_read(data: bytes, media_type: str) -> Dict[str, Any]:
    import anthropic
    client = anthropic.AsyncAnthropic()
    r = await client.beta.messages.create(
        model=MODEL, max_tokens=3000, betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"},
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64.standard_b64encode(data).decode()}},
            {"type": "text", "text": PROMPT}]}])
    if r.stop_reason == "refusal":
        raise RuntimeError("the model declined to read this image")
    return json.loads(next(b.text for b in r.content if b.type == "text"))


READ = _model_read          # tests replace it (specimens only)


def dni_ok(dni: str) -> bool:
    m = re.fullmatch(r"(\d{8})([A-Z])", (dni or "").replace(" ", "").replace("-", "").upper())
    return bool(m) and DNI_LETTERS[int(m.group(1)) % 23] == m.group(2)


def _cd(s: str) -> str:
    w, t = (7, 3, 1), 0
    for i, c in enumerate(s):
        v = 0 if c == "<" else int(c) if c.isdigit() else ord(c) - 55
        t += v * w[i % 3]
    return str(t % 10)


def mrz_td1(lines: List[str]) -> Dict[str, Any]:
    """A DNI back's three lines (30 characters each): the check digits, and what they carry."""
    ls = [re.sub(r"\s", "", x).upper() for x in lines if x and x.strip()]
    if len(ls) != 3 or any(len(x) != 30 for x in ls) or not ls[0].startswith("ID"):
        return {"ok": False, "why": "the back's three machine-readable lines weren't read in full"}
    l1, l2 = ls[0], ls[1]
    doc, dob, exp = l1[5:14], l2[0:6], l2[8:14]
    ok_doc, ok_dob, ok_exp = _cd(doc) == l1[14], _cd(dob) == l2[6], _cd(exp) == l2[14]
    composite = l1[5:30] + l2[0:7] + l2[8:15] + l2[18:29]
    ok_all = _cd(composite) == l2[29]
    return {"ok": ok_doc and ok_dob and ok_exp and ok_all, "support": doc.replace("<", ""), "dni": l1[15:24].replace("<", ""),
            "birth": dob, "expiry": exp, "sex": l2[7], "nationality": l2[15:18],
            "why": "" if ok_doc and ok_dob and ok_exp and ok_all else "a check digit in the machine-readable lines doesn't match"}


def _yymmdd(iso: str) -> str:
    return iso[2:4] + iso[5:7] + iso[8:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso or "") else ""


def checks(facts: Dict[str, dict], mrz: Optional[dict], today: date) -> List[str]:
    """What the ID's own checks say — a list of plain lines, ✓ or ⚠."""
    out = []
    dni = (facts.get("dni") or {}).get("value", "")
    if dni:
        out.append(f"{'✓' if dni_ok(dni) else '⚠'} The DNI letter {'matches' if dni_ok(dni) else 'does NOT match'} its number.")
    if mrz:
        if not mrz.get("ok"):
            out.append(f"⚠ {mrz['why']}.")
        else:
            agree = [mrz["dni"] == dni if dni else True,
                     mrz["birth"] == _yymmdd((facts.get("birth_date") or {}).get("value", "")),
                     mrz["expiry"] == _yymmdd((facts.get("expiry") or {}).get("value", ""))]
            out.append("✓ The machine-readable lines' check digits are right, and they agree with the front." if all(agree)
                       else "⚠ The machine-readable lines don't agree with the front — check the photo.")
    exp = (facts.get("expiry") or {}).get("value", "")
    if exp and exp < today.isoformat():
        out.append("⚠ This document has expired — the form needs one in force.")
    return out


def _fact(v: str, source: str) -> dict:
    return {"value": v.strip(), "source": source}


def from_read(read: Dict[str, Any], side: str) -> Dict[str, dict]:
    """Only what this side shows, each with its source."""
    src = {"dni_front": "your DNI (front), read from your photo", "dni_back": "your DNI (back), read from your photo",
           "passport": "your passport, read from your photo"}[side]
    f: Dict[str, dict] = {}
    keys = {"dni_number": "dni", "surname_1": "surname_1", "surname_2": "surname_2", "given_names": "given_names", "sex": "sex",
            "nationality": "nationality", "birth_date": "birth_date", "expiry_date": "expiry", "birth_place": "birth_place",
            "birth_province": "birth_province", "address_line": "address_line", "address_municipality": "municipality",
            "address_province": "province", "support_number": "support"}
    for k, ours in keys.items():
        v = str(read.get(k) or "").strip()
        if v:
            f[ours] = _fact(v.upper() if ours in ("dni", "support") else v, src)
    if side == "passport" and not f.get("dni"):
        m = next((x for x in read.get("mrz_lines") or [] if len(re.sub(r"\s", "", x)) == 44 and re.search(r"\d{6}", x)), "")
        pn = re.sub(r"\s", "", m)[28:42].replace("<", "") if m else ""
        if re.fullmatch(r"\d{8}[A-Z]", pn):
            f["dni"] = _fact(pn, "your passport's machine-readable line (personal number)")
    return f


LABELS = [("dni", "DNI"), ("surname_1", "First surname"), ("surname_2", "Second surname"), ("given_names", "Name"),
          ("sex", "Sex"), ("birth_date", "Date of birth"), ("nationality", "Nationality"), ("birth_place", "Place of birth"),
          ("birth_province", "Province of birth"), ("expiry", "Valid until"), ("address_line", "Address (on the DNI)"),
          ("municipality", "Town"), ("province", "Province")]


def read_back(facts: Dict[str, dict]) -> List[str]:
    return [f"• {lbl}: {facts[k]['value']}" for k, lbl in LABELS if facts.get(k, {}).get("value")]


# ── the address, the questions, the form ───────────────────────────────────────────────────────────────────────────

def split_address(line: str) -> Dict[str, str]:
    """'C. PADRE DAMIAN 41 P05 B' → type CALLE, name PADRE DAMIAN, number 41, floor 05, letter B (best effort; read back)."""
    t = re.sub(r"\s+", " ", (line or "").upper().replace(",", " ")).strip()
    out = {"type": "", "name": "", "number": "", "floor": "", "letter": ""}
    for typ, rx in STREET_TYPES.items():
        m = re.match(rf"^({rx})\.?\s+", t)
        if m:
            out["type"], t = typ, t[m.end():]
            break
    m = re.search(r"\s(\d+[A-Z]?)\b(.*)$", " " + t)
    if m:
        out["name"] = t[:m.start()].strip()
        out["number"] = m.group(1)
        rest = m.group(2)
        fl = re.search(r"\bP(?:ISO)?\.?\s*(\d+|BJ|BAJO)\b", rest) or re.search(r"\b(\d+)[ºª]", rest)
        if fl:
            out["floor"] = fl.group(1)
        le = re.search(r"\b([A-Z])\s*$", rest)
        if le:
            out["letter"] = le.group(1)
    else:
        out["name"] = t
    return out


QUESTIONS = [
    ("motive", "What is the card for?", None),
    ("address_ok", None, None),
    ("postcode", "Your postcode? (five digits, as on your padrón)", r"^\s*(\d{5})\s*$"),
    ("phone", "A mobile number for the health centre? (e.g. 600 000 000)", r"^\s*(\+?[\d\s]{9,15})\s*$"),
    ("email", "And an email? (the form asks it only to reach you about your care) — or say SKIP", None),
    ("shift", "Your family doctor: mornings, afternoons, or either?", None),
    ("centre", f"Do you know your health centre's name? It's on {SOURCE['centres']} — or say SKIP and they'll assign it from your address.", None),
]


def next_question(f: Dict[str, dict]) -> Optional[str]:
    for k, _, _ in QUESTIONS:
        if k == "address_ok":
            if f.get("address_line") and "address_ok" not in f:
                return k
            if not f.get("address_line") and "street" not in f:
                return "street"
            continue
        if k not in f:
            return k
    return None


def ask(out, k: str, f: Dict[str, dict]) -> None:
    if k == "motive":
        out.ask("What is the card for?\n" + "\n".join(f"• {v}" for v in MOTIVES.values()) + "\n(or type \"changed details\")", MOTIVE_BUTTONS)
    elif k == "address_ok":
        out.ask(f"Your DNI says: *{f['address_line']['value']}*{', ' + f['municipality']['value'] if f.get('municipality') else ''}. "
                "Is that still where you're registered (your padrón)?", [("Yes, still there", "hx:ts:addr:yes"), ("No, it's changed", "hx:ts:addr:no")])
    elif k == "street":
        out.text("Your current address, as on your padrón? (street and number, floor and door — e.g. \"Calle Padre Damián 41, 5º B\")")
    elif k == "shift":
        out.ask("Your family doctor: mornings, afternoons, or either?", [("Mornings", "hx:ts:s:MANIANA"), ("Afternoons", "hx:ts:s:TARDE"),
                                                                           ("Either", "hx:ts:s:INDISTINTO")])
    else:
        out.text(dict((q, w) for q, w, _ in QUESTIONS)[k])


def answer(k: str, t: str, payload: str, f: Dict[str, dict]) -> Optional[str]:
    """Stores the answer → None, or says what's wrong (the question is asked again with that line)."""
    said = "you, in this chat"
    if k == "motive":
        v = payload[8:] if payload.startswith("hx:ts:m:") else next(
            (m for m, rx in (("NUEVA", r"new|nueva|first|primera"), ("DOMICILIO", r"address|domicilio|moved|mudad"),
                             ("EXTRAVIO", r"lost|stolen|damag|perd|robo|rota|extrav"), ("MODIFICACION", r"detail|dato|name|nombre|change"))
             if re.search(rf"(?i)\b({rx})", t)), "")
        if v not in MOTIVES:
            return "New card, new address, changed details, or lost/damaged?"
        f["motive"] = _fact(v, said)
    elif k == "address_ok":
        yes = payload == "hx:ts:addr:yes" or (not payload and YS.is_yes(t))
        no = payload == "hx:ts:addr:no" or bool(re.match(r"(?i)^\s*(no|nope|changed|it'?s changed)\b", t))
        if not (yes or no):
            return "Is the DNI's address still the one on your padrón — yes or no?"
        f["address_ok"] = _fact("yes" if yes else "no", said)
        if no:
            f.pop("address_line", None)
            f.pop("municipality", None)
            if f.get("motive", {}).get("value") == "NUEVA":
                pass
    elif k == "street":
        if len(t.strip()) < 6 or not re.search(r"\d", t):
            return "The street and its number, please — e.g. \"Calle Padre Damián 41, 5º B\"."
        f["street"] = _fact(t.strip(), said)
    elif k == "postcode":
        m = re.match(r"^\s*(\d{5})\s*$", t)
        if not m or not m.group(1).startswith("28"):
            return "A Madrid postcode is five digits starting 28, e.g. 28036."
        f["postcode"] = _fact(m.group(1), said)
    elif k == "phone":
        d = re.sub(r"\D", "", t)
        d = d[2:] if d.startswith("34") and len(d) == 11 else d
        if not re.fullmatch(r"[6-9]\d{8}", d):
            return "A Spanish number is nine digits, e.g. 600 000 000."
        f["phone"] = _fact(d, said)
    elif k == "email":
        if re.fullmatch(r"(?i)\s*skip\s*", t):
            f["email"] = _fact("", said)
        elif re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", t.strip()):
            f["email"] = _fact(t.strip(), said)
        else:
            return "That doesn't look like an email — or say SKIP."
    elif k == "shift":
        v = payload[8:] if payload.startswith("hx:ts:s:") else ("MANIANA" if re.search(r"(?i)morn|mañana|manana", t) else
                                                            "TARDE" if re.search(r"(?i)after|tarde", t) else
                                                            "INDISTINTO" if re.search(r"(?i)either|any|indist|igual", t) else "")
        if not v:
            return "Mornings, afternoons, or either?"
        f["shift"] = _fact(v, said)
    elif k == "centre":
        f["centre"] = _fact("" if re.fullmatch(r"(?i)\s*(skip|no|don'?t know|not sure)\s*", t) else t.strip(), said)
    return None


def rows(f: Dict[str, dict], today: date) -> List[dict]:
    """Every value the form will hold → {field, label, value, source} — and what's left for the citizen."""
    v = lambda k: (f.get(k) or {}).get("value", "")
    src = lambda k: (f.get(k) or {}).get("source", "")
    addr = split_address(v("street") or v("address_line"))
    a_src = src("street") or src("address_line")
    out = []

    def put(field, label, value, source):
        if value:
            out.append({"field": field, "label": label, "value": value, "source": source})
    put("ITMOTIVO_SOLIC", "Reason", v("motive"), src("motive"))
    put("ITTURNO_SOLI", "Preferred shift", v("shift"), src("shift"))
    put("TLNOMBRECENTRO_SOLI", "Health centre", v("centre"), src("centre"))
    put("TLAPELLIDO1_INTER", "First surname", v("surname_1").upper(), src("surname_1"))
    put("TLAPELLIDO2_INTER", "Second surname", v("surname_2").upper(), src("surname_2"))
    put("TLNOMBRE_INTER", "Name", v("given_names").upper(), src("given_names"))
    sx = {"F": "M", "M": "H"}.get(v("sex").upper()[:1], "")      # the DNI prints F/M; the form wants Mujer/Hombre
    put("DSSEXO_INTER", "Sex", sx, src("sex"))
    put("TLPROVNAC_INTER", "Province of birth", v("birth_province").upper(), src("birth_province"))
    put("TLPAISNAC_INTER", "Country of birth", "ESPAÑA" if v("birth_province") else "", src("birth_province") + " (a Spanish province)" if v("birth_province") else "")
    put("TLNACIONALIDAD_INTER", "Nationality", "ESPAÑOLA" if v("nationality").upper()[:3] in ("ESP", "ESPAÑOLA"[:3]) else v("nationality").upper(), src("nationality"))
    bd = v("birth_date")
    put("TLFECHANAC_INTER", "Date of birth", f"{bd[8:10]}/{bd[5:7]}/{bd[0:4]}" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", bd) else "", src("birth_date"))
    put("CDDOCIDENT_INTER", "NIF", v("dni"), src("dni"))
    put("TLTELF_MOVIL_INTER", "Mobile", v("phone"), src("phone"))
    put("TLEMAIL_INTER", "Email", v("email"), src("email"))
    put("TLTIPOVIAL_INTER", "Street type", addr["type"], a_src)
    put("TLNOMVIAL_INTER", "Street", addr["name"], a_src)
    put("NMNUMVIAL_INTER", "Number", addr["number"], a_src)
    put("TLPISO_INTER", "Floor", addr["floor"], a_src)
    put("TLPUERTA_INTER", "Door", addr["letter"], a_src)
    put("CDPOSTAL_INTER", "Postcode", v("postcode"), src("postcode"))
    put("DSMUNI_INTER", "Town", (v("municipality") or "MADRID").upper(), src("municipality") or "your Madrid postcode")
    put("DSPROV_INTER", "Province", (v("province") or "MADRID").upper(), src("province") or "your Madrid postcode")
    put("DSPAIS_INTER", "Country", "ESPAÑA", "your address in Madrid")
    put("TLLOCFIRMA_PIE", "Place of signing", (v("municipality") or "MADRID").upper(), "your town")
    return out


RADIOS = ("ITMOTIVO_SOLIC", "ITTURNO_SOLI")
NEVER = re.compile(r"^(ITICDA_|ITTIPONOTIFICA|DDFECHA|MMFECHA|AAFECHA|TLNUMAFILSS|BOT_)")   # objections, notification, date, NUSS, buttons


def fill(rs: List[dict]) -> bytes:
    """The official 1449F1 with exactly these values; ⛔ a value for a box that is the citizen's raises."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, TextStringObject
    for r in rs:
        if NEVER.match(r["field"]):
            raise ValueError(f"{r['field']} is the citizen's to decide (an objection, the notification, the date or the signature)")
        if not r.get("source"):
            raise ValueError(f"{r['field']}: a value with no source")
    values = {r["field"]: r["value"] for r in rs if r["field"] not in RADIOS}
    radios = {r["field"]: r["value"] for r in rs if r["field"] in RADIOS}
    w = PdfWriter(clone_from=PdfReader(str(PDF)))
    w.set_need_appearances_writer(True)
    for page in w.pages:
        if not page.get("/Annots"):
            continue
        w.update_page_form_field_values(page, values, auto_regenerate=False)
        for a in page.get("/Annots") or []:
            a = a.get_object()
            par = a.get("/Parent").get_object() if a.get("/Parent") else None
            t = a.get("/T") or (par.get("/T") if par else None)
            if t in radios:
                states = [k for k in (a.get("/AP") or {}).get("/N", {}).keys() if k != "/Off"]
                on = f"/{radios[t]}"
                a[NameObject("/AS")] = NameObject(on if on in states else "/Off")
                (par or a)[NameObject("/V")] = NameObject(on)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def expired(st: dict, now: datetime) -> bool:
    """The form's values live VALUES_TTL; compared as instants (the case may be written in Madrid time, read in UTC)."""
    try:
        return datetime.fromisoformat(st["values_expire_at"]) <= now
    except (KeyError, TypeError, ValueError):
        return True


def read_pdf(pdf: bytes) -> Dict[str, str]:
    from pypdf import PdfReader
    return {k: str(v.get("/V")) for k, v in (PdfReader(io.BytesIO(pdf)).get_fields() or {}).items()
            if v.get("/V") not in (None, "", "/Off")}


# ── the conversation (called from health.turn) ────────────────────────────────────────────────────────────────────

IMAGE_TYPES = ("image/jpeg", "image/png")


def web() -> str:
    from .turn import web as w
    return w()


async def start(ctx: dict) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    pend.update(step="ts_doc", ts={"facts": {}, "mrz": None, "sides": []})
    out.text("Your health card — I'll fill the Comunidad de Madrid's own form (1449F1) for you. I read your ID once to fill "
             "it; I don't ask for your Social Security number or anything about your health, and I keep the details 24 hours.")
    out.text("Send a photo of the FRONT of your DNI (then the back), or your passport's photo page. "
             "(Type DEMO for a fictional specimen.)")


async def on_doc(ctx: dict, t: str) -> bool:
    """A photo (or DEMO) at ts_doc / ts_back. True when this turn was handled."""
    pend, out = ctx["st"]["pending"], ctx["out"]
    ts = pend["ts"]
    if re.fullmatch(r"(?i)\s*demo\s*", t):
        ts["facts"] = {k: _fact(v, "a fictional specimen (not a real person)") for k, v in SPECIMEN.items()}
        ts["mrz"], ts["sides"], ts["fictional"] = mrz_td1(SPECIMEN_MRZ), ["dni_front", "dni_back"], True
        _confirm(ctx)
        return True
    imgs = [m for m in ctx.get("media") or [] if m.get("type") in IMAGE_TYPES]
    if not imgs:
        if ctx.get("media") and all((m.get("type") or "").startswith("audio/") for m in ctx["media"]):
            out.text("I couldn't make out that voice note. For the form I need a photo of your DNI (front, then back) or "
                     "your passport's photo page — or type DEMO.")
            return True
        if ctx.get("media"):
            out.text("I can read a photo (JPEG or PNG) of your DNI or passport — not that kind of file.")
            return True
        return False
    await ctx["early"]("Reading your document… It goes to Anthropic's AI model to be read, once; I don't keep the photo.")
    from ..relocation import docread as DR
    for m in imgs[:2]:
        try:
            data, mt = (m["bytes"], m["type"]) if m.get("bytes") else await DR.FETCH(m["url"])
            read = await READ(data, mt if mt in IMAGE_TYPES else m["type"])
        except Exception as e:
            log.error("[tarjeta] not read: %s", type(e).__name__)
            out.text(f"I couldn't read that photo ({type(e).__name__}). Nothing was kept — try a sharper one.")
            return True
        side = read.get("doc_type")
        if side not in ("dni_front", "dni_back", "passport") or not read.get("legible"):
            out.text("That doesn't look like a legible DNI side or passport photo page — try again in good light.")
            return True
        for k, v in from_read(read, side).items():
            ts["facts"].setdefault(k, v)
        if side == "dni_back" and read.get("mrz_lines"):
            ts["mrz"] = mrz_td1(read["mrz_lines"])
        ts["sides"] = sorted(set(ts["sides"]) | {side})
    if "dni_front" in ts["sides"] and "dni_back" not in ts["sides"] and "passport" not in ts["sides"]:
        pend["step"] = "ts_back"
        out.text("Got the front. Now the BACK of your DNI, please — it has your address and where you were born.")
        return True
    _confirm(ctx)
    return True


def _confirm(ctx: dict) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    ts = pend["ts"]
    lines = read_back(ts["facts"]) + [""] + checks(ts["facts"], ts.get("mrz"), ctx["now"].date())
    sha = hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]
    pend.update(step="ts_confirm", ts_sha=sha)
    out.text("What I read:\n" + "\n".join(lines))
    out.ask("Is every line right?", [("Yes, all right", f"hx:ts:ok:{sha}"), ("Something's wrong", f"hx:ts:bad:{sha}")])


async def on_confirm(ctx: dict, t: str, payload: str) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    sha = pend.get("ts_sha", "")
    if payload == f"hx:ts:ok:{sha}" or (not payload and YS.is_yes(t)):
        pend["step"] = "ts_ask"
        k = next_question(pend["ts"]["facts"])
        pend["ts_q"] = k
        ask(out, k, pend["ts"]["facts"])
        return
    pend.update(step="ts_doc", ts={"facts": {}, "mrz": None, "sides": []})
    out.text("OK — nothing kept. Send the photo again (in good light, the whole card in frame), or type DEMO.")


async def on_answer(ctx: dict, t: str, payload: str) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    f = pend["ts"]["facts"]
    k = pend.get("ts_q") or next_question(f)
    wrong = answer(k, t, payload, f)
    if wrong:
        out.text(wrong)
        ask(out, k, f)
        return
    k = next_question(f)
    if k:
        pend["ts_q"] = k
        ask(out, k, f)
        return
    await _prepare(ctx)


async def _prepare(ctx: dict) -> None:
    pend, out, now = ctx["st"]["pending"], ctx["out"], ctx["now"]
    f = pend["ts"]["facts"]
    rs = rows(f, now.date())
    fill(rs)                                       # the guard runs before anything is kept
    state = {"kind": "tarjeta", "form": "1449F1", "rows": rs, "left_for_you": LEFT_FOR_YOU, "source": SOURCE,
             "fictional": bool(pend["ts"].get("fictional")), "values_expire_at": (now + VALUES_TTL).isoformat(),
             "status": "ready_for_you", "prepared_at": now.isoformat(), "consent": pend.get("consent")}
    try:
        cid = await ST.STORE.put("health", ctx["account"], ctx["ch"]["wa_id_sha256"], state)
    except Exception as e:
        log.error("[tarjeta] case not kept: %s", type(e).__name__)
        out.text("Health isn't switched on on this server yet (its storage isn't ready). Nothing was kept.")
        return
    pend.update(step="done", case_id=cid)
    pend.pop("ts", None)
    out.text(f"✅ Your health-card form is ready: {len(rs)} boxes of the official 1449F1 filled from your ID and your answers, "
             "each naming its source. Nothing has been submitted.")
    from .. import formcard as FC                     # CR 33 · page 1 as a card, the filled boxes highlighted
    FC.show(out, "Your health-card form (1449F1), page 1 — highlighted: what I filled. Not signed, not submitted.",
            f"{web()}/api/products/health/{cid}/1449F1-card.jpg", f"{web()}/api/products/health/{cid}/1449F1-prepared.pdf")
    out.text("Left for you:\n" + "\n".join(f"• {x}" for x in LEFT_FOR_YOU) +
             f"\n\nThen: print it, sign it, and take it to your health centre (with a cita) — the card is collected there in "
             f"person. Source: {SOURCE['procedure']} (updated {SOURCE['updated']}), read {SOURCE['read_on']}. "
             f"The link works for 24 hours; then the details are dropped.")


# a fictional specimen (Spain's own DNI specimen style) — tests and DEMO only, never a real person
SPECIMEN = {"dni": "99999999R", "surname_1": "ESPAÑOLA", "surname_2": "ESPAÑOLA", "given_names": "CARMEN", "sex": "F",
            "nationality": "ESP", "birth_date": "1980-01-01", "expiry": "2031-06-30", "birth_place": "MADRID",
            "birth_province": "MADRID", "address_line": "C. EJEMPLO 1 P02 A", "municipality": "MADRID", "province": "MADRID"}


def _specimen_mrz() -> List[str]:
    sup, dni = "BAA000000", "99999999R"
    l1 = "IDESP" + sup + _cd(sup) + dni + "<" * 6
    l1 = l1[:30]
    dob, exp = "800101", "310630"
    body = dob + _cd(dob) + "F" + exp + _cd(exp) + "ESP" + "<" * 11
    composite = l1[5:30] + body[0:7] + body[8:15] + body[18:29]
    l2 = body + _cd(composite)
    l3 = ("ESPANOLA<ESPANOLA<<CARMEN" + "<" * 30)[:30]
    return [l1, l2, l3]


SPECIMEN_MRZ = _specimen_mrz()
