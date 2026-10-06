"""CR 44 · AFTER ARRIVAL — every form from EU 174's map (docs/relocateme/forms-map.md rows 6–9), from the same Keep facts.

  · B6 EX-17 (the TIE application): the official PDF is on inclusion.gob.es, which we may not fetch (robots 403). Once the
    founder drops it at products/relocation/ex17-official.pdf (and its field map, ex17_map.json, is made from it), it fills from
    the EX-01's values; until then it is said plainly: "waiting for the official EX-17 PDF".
  · B7 Modelo 790-012 (the TIE fee): the police's own web form, sede.policia.gob.es/Tasa790_012/ImpresoRellenar — read 6 Oct
    2026: it carries a security-code CAPTCHA ("codSeguridadForm"), so it is NEVER filled in Kanoe's browser; each value is
    prepared to copy, and the person fills, solves, downloads, prints and pays. The fee row, read at source: "TIE que documenta
    la primera concesión de la autorización de residencia temporal…" — 16.08 € (option tasa5).
  · C9 TA.1 (Social Security number): the TGSS's own AcroForm (TA.1 V.6, 07-2024, sha256 7b017684…), filled; "acepto
    comunicaciones", place, date, signature and the NSS are never written.
  · C8 Padrón (Madrid): the official hoja padronal PDF was not located on madrid.es (EU 174), so its values are prepared to
    copy, with the cita route (servpub PAD, or 010 / 914 800 010) and what is in person — said plainly.
"""
from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).parent
EX17_PDF, EX17_MAP = HERE / "ex17-official.pdf", HERE / "ex17_map.json"
EX17_URL = "https://www.inclusion.gob.es/documents/410169/2156469/17-Formulario_TIE.pdf"
TA1_PDF = HERE / "TA_1-V6-official.pdf"
TA1_SOURCE = "the TGSS's TA.1 (V.6, 07-2024) from seg-social.es, read 6 Oct 2026 (EU 174; sha256 7b017684…)"
P790_012 = "https://sede.policia.gob.es/Tasa790_012/ImpresoRellenar"
P790_012_ROW = "TIE que documenta la primera concesión de la autorización de residencia temporal, de estancia o para trabajadores transfronterizos"
P790_012_FEE = "16.08 €"
PADRON_CITA = "https://servpub.madrid.es/GNSIS_WBCIUDADANO/tramitePorCodigoWeb.do?codTramite=PAD"
PADRON_PAGE = "https://www.madrid.es/portales/munimadrid/es/Inicio/El-Ayuntamiento/Estadistica/Tramites-de-Padron-y-censo-electoral-con-cita-previa"
READ_ON = "6 Oct 2026"


def _v(f: dict, k: str) -> str:
    return (((f.get("applicant") or {}).get(k) or {}).get("value") or "").strip()


def address(f: dict) -> Dict[str, str]:
    """The Spanish address in the parts the forms use (CALLE · DE EJEMPLO · 12 · 3 · B)."""
    from ..health import address as AD
    line = f"{_v(f, 'address_street')} {_v(f, 'address_number')}" + (f", {_v(f, 'address_floor')}" if _v(f, "address_floor") else "")
    p = AD.parse(line) if _v(f, "address_street") else {k: "" for k in ("type", "name", "number", "floor", "door", "portal", "stair", "block")}
    return {**p, "postcode": _v(f, "address_postcode"), "town": _v(f, "address_town"), "province": _v(f, "address_province")}


# ── C9 · TA.1 ──────────────────────────────────────────────────────────────────────────────────────────────────────
# Its field names say nothing ("Texto1"…), so each is mapped by the label printed above its box (page 1, read 6 Oct 2026).
TA1_NEVER = {"Texto9", "Si", "Texto67", "Texto68", "Texto69", "Texto70"}   # NSS, "acepto comunicaciones", place/date (both)


def ta1_rows(f: dict) -> List[dict]:
    a = address(f)
    bd = _v(f, "birth_date")
    nie = _v(f, "nie")
    rows: List[Tuple[str, str, str]] = [
        ("Texto1", _v(f, "surname_1").upper(), "1.1 primer apellido — your passport"),
        ("Texto2", _v(f, "surname_2").upper(), "segundo apellido — your passport"),
        ("Texto3", _v(f, "given_names").upper(), "nombre — your passport"),
        ("Texto4", {"H": "H", "M": "M"}.get(_v(f, "sex"), ""), "1.2 sexo — your passport"),
        ("Casilla de verificación6", "/Yes" if nie else "", "1.3 tarjeta de extranjero — your NIE"),
        ("Texto8", nie.upper(), "1.4 nº de documento — your NIE"),
        ("Texto10", bd[8:10] if len(bd) == 10 else "", "fecha de nacimiento: día"),
        ("Texto11", bd[5:7] if len(bd) == 10 else "", "mes"), ("Texto12", bd[:4] if len(bd) == 10 else "", "año"),
        ("Texto13", _v(f, "father_name").upper(), "A-progenitor/a — your answers"),
        ("Texto14", _v(f, "mother_name").upper(), "B-progenitor/a — your answers"),
        ("Texto15", _v(f, "birth_place").upper(), "lugar de nacimiento — your passport"),
        ("Texto17", _v(f, "birth_country").upper(), "país de nacimiento — your answers"),
        ("Texto19", _v(f, "nationality").upper(), "nacionalidad — your passport"),
        ("Texto21", a["type"], "1.8 tipo de vía — your address in Spain"), ("Texto22", a["name"], "nombre de la vía"),
        ("Texto24", a["number"], "núm."), ("Texto27", a["floor"], "piso"), ("Texto28", a["door"], "puerta"),
        ("Texto29", a["postcode"], "c. postal"), ("Texto30", a["town"].upper(), "municipio"),
        ("Texto31", a["province"].upper(), "provincia"),
        ("Texto32", _v(f, "email"), "1.9 correo electrónico — your Keep"), ("Texto35", _v(f, "mobile"), "teléfono móvil — your Keep"),
        ("A", "/1", "2 · asignación número de Seguridad Social — what you're asking for"),
        ("Texto71", f"DIRECCIÓN PROVINCIAL DE LA TGSS DE {a['province'].upper()}" if a["province"] else "",
         "órgano: the TGSS office of your province"),
    ]
    if ((f.get("choices") or {}).get("notices_to_own_address") or {}).get("value") == "yes":
        rows.append(("d", "/0", "3 · notificación: the address above (as you chose on the EX-01)"))
    return [{"field": k, "value": v, "source": s} for k, v, s in rows if v]


def fill_ta1(rows: List[dict]) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject
    for r in rows:
        if r["field"] in TA1_NEVER:
            raise ValueError(f"{r['field']} is the applicant's (NSS, consent to communications, place/date/signature)")
    values = {r["field"]: r["value"] for r in rows if not r["value"].startswith("/")}
    states = {r["field"]: r["value"] for r in rows if r["value"].startswith("/")}
    w = PdfWriter(clone_from=PdfReader(str(TA1_PDF)))
    w.set_need_appearances_writer(True)
    for page in w.pages:
        if not page.get("/Annots"):
            continue
        w.update_page_form_field_values(page, values, auto_regenerate=False)
        for an in page.get("/Annots") or []:
            an = an.get_object()
            parent = an.get("/Parent").get_object() if an.get("/Parent") else None
            t = an.get("/T") or (parent.get("/T") if parent else None)
            if t not in states:
                continue
            want = states[t]
            have = list((an.get("/AP") or {}).get("/N", {}).keys())
            on = want if want in have else None              # a radio's kid carries its own state (/0, /1 …); a box /Yes
            an[NameObject("/AS")] = NameObject(on or "/Off")
            if on:
                (parent or an)[NameObject("/V")] = NameObject(on)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


# ── B7 · 790-012 (the police's web form: a CAPTCHA → prepared, never filled by us) ──────────────────────────────────

def p790_012(f: dict) -> List[Tuple[str, str]]:
    a = address(f)
    name = " ".join(x for x in (_v(f, "surname_1"), _v(f, "surname_2")) if x) + (", " + _v(f, "given_names") if _v(f, "given_names") else "")
    vals = [("NIF / NIE", _v(f, "nie").upper()), ("Apellidos y nombre", name.upper()),
            ("Tipo de vía (calle)", a["type"]), ("Nombre de la vía", a["name"]), ("Número", a["number"]),
            ("Escalera", a["stair"]), ("Piso", a["floor"]), ("Puerta", a["door"]), ("Teléfono", _v(f, "mobile")),
            ("Municipio", a["town"].upper()), ("Provincia", a["province"].upper()), ("Código postal", a["postcode"]),
            ("Trámite", f"{P790_012_ROW} — {P790_012_FEE}")]
    return [(k, v) for k, v in vals if v]


# ── C8 · padrón (the official hoja padronal not located: its values, prepared) ─────────────────────────────────────

def padron(f: dict) -> List[Tuple[str, str]]:
    a = address(f)
    street = " ".join(x for x in (a["type"], a["name"], a["number"]) if x) + (f", {a['floor']}º {a['door']}".rstrip() if a["floor"] else "")
    bd = _v(f, "birth_date")
    vals = [("Nombre", _v(f, "given_names").upper()),
            ("Apellidos", " ".join(x for x in (_v(f, "surname_1"), _v(f, "surname_2")) if x).upper()),
            ("Fecha de nacimiento", f"{bd[8:10]}/{bd[5:7]}/{bd[:4]}" if len(bd) == 10 else bd),
            ("Lugar y país de nacimiento", ", ".join(x for x in (_v(f, "birth_place"), _v(f, "birth_country")) if x).upper()),
            ("Nacionalidad", _v(f, "nationality").upper()),
            ("Documento", f"NIE {_v(f, 'nie').upper()}" if _v(f, "nie") else f"Pasaporte {_v(f, 'passport_number').upper()}"),
            ("Domicilio", ", ".join(x for x in (street, a["postcode"], a["town"].upper()) if x))]
    return [(k, v) for k, v in vals if v]


PADRON_IN_PERSON = ("📍 Padrón — in person, at a Línea Madrid office, with a cita: book it at "
                    f"{PADRON_CITA} (or call 010 / 914 800 010). Online needs Cl@ve — not something I can do for you. "
                    "Bring your ID in force (passport or TIE) and proof you use the home: a rental contract in your name signed "
                    "by both sides, or the owner's authorisation. The hoja padronal is signed by hand there by every adult on it. "
                    f"(Madrid's own page, read {READ_ON}: {PADRON_PAGE})")


# ── B6 · EX-17 ─────────────────────────────────────────────────────────────────────────────────────────────────────

def ex17_ready() -> bool:
    return EX17_PDF.exists() and EX17_MAP.exists()


EX17_WAITING = ("🪪 EX-17 (your TIE application): waiting for the official PDF — Kanoe may not download it from inclusion.gob.es "
                "(its robots file refuses), so the founder brings it in. Once it's here, it fills from your EX-01 answers like "
                "the others; you sign it at your fingerprint appointment.")


def ex17_rows(f: dict) -> List[dict]:
    """The EX-17 from the EX-01's values, by the map made from the founder's copy (ex17_map.json: field → fact key)."""
    import json
    m = json.loads(EX17_MAP.read_text())
    out = []
    for field, spec in m["fields"].items():
        v = _v(f, spec["fact"])
        if spec.get("upper"):
            v = v.upper()
        if v:
            out.append({"field": field, "value": v, "source": spec.get("source", spec["fact"])})
    return out


def fill_ex17(rows: List[dict]) -> bytes:
    """The founder's copy of the official EX-17, filled; the map's "never" fields (signature, place/date, the person's own
    choices) are refused by code, as the EX-01's are."""
    import json
    from pypdf import PdfReader, PdfWriter
    never = set(json.loads(EX17_MAP.read_text()).get("never", []))
    for r in rows:
        if r["field"] in never:
            raise ValueError(f"{r['field']} is the applicant's to write")
    w = PdfWriter(clone_from=PdfReader(str(EX17_PDF)))
    w.set_need_appearances_writer(True)
    vals = {r["field"]: r["value"] for r in rows}
    for page in w.pages:
        if page.get("/Annots"):
            w.update_page_form_field_values(page, vals, auto_regenerate=False)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


# ── the order, and the conversation ────────────────────────────────────────────────────────────────────────────────

def forms_table(f: dict) -> List[dict]:
    """form · filled · why not — the readout's table, from this file."""
    return [
        {"form": "National visa application", "filled": True, "why_not": "place/date, signature, photo are yours"},
        {"form": "EX-01", "filled": True, "why_not": "section 5, Dehú consent, place/date, signature are yours"},
        {"form": "790-052", "filled": True, "why_not": "NIE, address abroad, place/date, signature, payment are yours"},
        {"form": "EX-17", "filled": ex17_ready(), "why_not": None if ex17_ready() else "waiting for the official PDF (inclusion.gob.es: robots 403)"},
        {"form": "790-012", "filled": False, "why_not": "the police's web form has a CAPTCHA — every value prepared to copy"},
        {"form": "Padrón", "filled": False, "why_not": "the official hoja padronal PDF not located — values prepared; in person, signed by hand"},
        {"form": "TA.1", "filled": True, "why_not": "the NSS, consent to communications, place/date, signature are yours"},
        {"form": "Tarjeta sanitaria 1449F1", "filled": True, "why_not": "EspañaMe fills it (CR 30); §5, §6, date, NSS are yours"},
    ]


async def present(ctx: dict, web: str) -> None:
    """After arrival: each form in process order — padrón → fingerprints (EX-17 + 790-012) → TA.1. Nothing is sent."""
    from .. import formcard as FC
    pend, out = ctx["st"]["pending"], ctx["out"]
    f = pend.get("facts") or {}
    cid = pend.get("case_id")
    out.text("After you arrive — in this order (each is on your “Move to Madrid” trip):\n1. Padrón (book first — the fingerprint "
             "appointment often asks for it).\n2. Fingerprints for your TIE, within a month of entry: the EX-17 and the 790-012 fee.\n"
             "3. Your Social Security number: the TA.1.\n4. Your health card: say “españa” (EspañaMe fills the 1449F1).")
    out.text(PADRON_IN_PERSON)
    out.text("Padrón — your details, each ready to copy onto the hoja padronal:")
    for k, v in padron(f):
        out.text(f"{k}: {v}")
    if ex17_ready():
        FC.show(out, "Your EX-17 (TIE application), filled from your EX-01 answers. Not signed — you sign it at the appointment.",
                f"{web}/api/products/relocation/{cid}/EX-17-card.jpg", f"{web}/api/products/relocation/{cid}/EX-17.pdf")
    else:
        out.text(EX17_WAITING)
    out.text(f"💶 790-012 (the TIE fee, {P790_012_FEE}): the police's own form — {P790_012}\nIt has a security code (a CAPTCHA), so "
             "you fill it: every value is below, ready to copy. Then download it, print it, and pay at a bank or online — yours.")
    for k, v in p790_012(f):
        out.text(f"{k}: {v}")
    if not _v(f, "nie"):
        out.text("Your NIE isn't on file yet — it's printed on your visa. Tell me “my NIE is X1234567L” and the 790-012, the TA.1 and "
                 "the EX-17 fill it in.")
    FC.show(out, "Your TA.1 (Social Security number), filled from your Keep. Not signed — the NSS, consent to communications, "
                 "place, date and signature are yours. In person at the TGSS.",
            f"{web}/api/products/relocation/{cid}/TA-1-card.jpg", f"{web}/api/products/relocation/{cid}/TA-1.pdf")


NIE_SAID = re.compile(r"(?i)\bmy\s+nie\s+is\s+([XYZ]\s*-?\s*\d{7}\s*-?\s*[A-Z])\b")
ARRIVAL = re.compile(r"(?i)\b(after arrival|arrived|i'?ve arrived|when i arrive|padr[oó]n|ta\.?\s?1|social security|seguridad social|"
                     r"ex-?17|790-?012|tie (?:form|fee|application))\b")
