"""CR 44 · A1 — the NATIONAL VISA APPLICATION (Solicitud de visado nacional), filled where the official form allows.

The form is FLAT (5 pages, 0 fillable fields — EU 174, docs/relocateme/forms-map.md row 1), so each value is drawn onto the
official page beside its own printed label: the label is FOUND on the page (PDFium's text, never a fixed coordinate), and the
value goes just under it. A form re-issued with the labels moved still fills; one whose label is gone refuses loudly.

Which PDF:
  · New York — its own "Application for a National Visa" (English, 2023), exteriores.gob.es/Consulados/nuevayork/…
    (sha256 ed72cd1a…, read 6 Oct 2026);
  · London and Washington — the Ministry's bilingual "Solicitud de visado nacional / Application for long-term visa"
    (2021, exteriores.gob.es/en/EmbajadasConsulados/Documents/Consular/…, sha256 b5e0f85d…): London's own page links no form
    of its own today (6 Oct 2026: only BLS), and Washington's link was empty (3 Oct read). Washington: "fill electronically
    or by hand in capitals" — every value here is in capitals.

⛔ Never written: place and date (27/30), the SIGNATURE (28/31), the photo, residence permit details abroad (18), anything about
someone else (10, 24–26). SIGN HERE marks the signature box in the pack.
"""
from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).parent
FORMS = {"ny": {"pdf": HERE / "visa-nacional-NY-EN-2023.pdf", "sha": "ed72cd1a", "name": "New York's own Application for a National Visa (2023)",
                "url": "https://www.exteriores.gob.es/Consulados/nuevayork/en/ServiciosConsulares/Documents/SOLICITUD-Visado-Nacional-INGLES-2023.pdf"},
         "generic": {"pdf": HERE / "visa-nacional-ES-EN-2021.pdf", "sha": "b5e0f85d",
                     "name": "the Ministry's bilingual Solicitud de visado nacional (2021)",
                     "url": "https://www.exteriores.gob.es/en/EmbajadasConsulados/Documents/Consular/20210611-Formulario%20nacional%20espa%C3%B1ol-ingl%C3%A9s.pdf"}}
FORM_FOR = {"newyork": "ny", "london": "generic", "washington": "generic"}

# key → (label regex on the page, kind). text: the value under the label; tick: an X in the □ just before the option's words.
# "after" (a regex) starts the search there — "Single" the marital status, never "Single entry".
ANCHORS: Dict[str, Dict[str, Tuple]] = {
    "ny": {
        "surnames": (r"1\. Surname \(Family name\)", "text"), "given_names": (r"3\. First name\(s\)", "text"),
        "birth_date": (r"4\. Date of birth", "text"), "birth_place": (r"5\. Place of birth", "text"),
        "birth_country": (r"6\. Country of birth", "text"), "nationality": (r"7\.\s*Current nationality", "text"),
        "sex_H": (r"Male", "tick", r"8\. Sex"), "sex_M": (r"Female", "tick", r"8\. Sex"),
        "marital_S": (r"Single", "tick", r"9\. Marital"), "marital_C": (r"Married", "tick", r"9\. Marital"),
        "marital_Sp": (r"Separated", "tick", r"9\. Marital"), "marital_D": (r"Divorced", "tick", r"9\. Marital"),
        "marital_V": (r"Widow", "tick", r"9\. Marital"),
        "passport_ordinary": (r"Ordinary passport", "tick"),
        "passport_number": (r"13\. Number of travel document", "text"), "passport_issued": (r"14\. Date of issue", "text"),
        "passport_expiry": (r"15\. Valid until", "text"), "passport_issuer": (r"16\. Issued by", "text"),
        "home": (r"17\. Applicant's home address and e-mail address", "text"), "phone": (r"Telephone number\(s\)", "text"),
        "abroad_no": (r"No", "tick", r"18\. Residence"), "abroad_yes": (r"Yes\. Residence permit", "tick", r"18\. Residence"),
        "occupation": (r"19\. Current occupation", "text"),
        "purpose": (r"Residence without work permit", "tick"),
        "arrival": (r"21\. Intended date of arrival in Spain", "text"), "single_entry": (r"Single entry", "tick"),
        "spain_address": (r"23\. Applicant.s address in Spain", "text"),
        "signature": (r"28\. Signature", "sign"), "place_date": (r"27\. Place and date", "leave"),
    },
    "generic": {
        "surnames": (r"1\. Apellido\(s\)/Surname\(s\)", "text"), "given_names": (r"3\. Nombre\(s\)/ Given name\(s\)", "text"),
        "birth_date": (r"4\. Fecha de nacimiento\s*\(día-mes-año\)/ Date of birth \(day.\s*month-year\):", "text"),   # its hyphen is U+FFFE
        "birth_place": (r"5\. Lugar de nacimiento/Place of\s*birth:", "text"),
        "birth_country": (r"6\. País de nacimiento/Country of\s*birth:", "text"),
        "nationality": (r"7\. Nacionalidad actual/Current\s*nationality:", "text"),
        "sex_H": (r"Varón/Male", "tick"), "sex_M": (r"Mujer/Female", "tick"),
        "marital_S": (r"Soltero.{0,3}a/Single", "tick"), "marital_C": (r"Casado.{0,3}a/Married", "tick"),
        "marital_Sp": (r"Separado.{0,3}a/Separated", "tick"), "marital_D": (r"Divorciado.{0,3}a/Divorced", "tick"),
        "marital_V": (r"Viudo.{0,3}a/Widow", "tick"),
        "passport_ordinary": (r"Pasaporte ordinario/Ordinary", "tick"),
        "passport_number": (r"13\. Número del documento de viaje/\s*Number of travel document:", "text"),
        "passport_issued": (r"14\. Fecha de expedición/\s*Date of issue:", "text"),
        "passport_expiry": (r"15\. Válido hasta/Valid until\s*:", "text"),
        "passport_issuer": (r"16\s*\.\s*Expedido por \(país\)/Issued by\s*\(country\):", "text"),
        "home": (r"17\. Domicilio postal y dirección de correo electrónico del solicitante/ Applicant's home address and\s*e-mail address:", "text"),
        "phone": (r"Número\(s\) de teléfono/Telephone\s*number\(s\):", "text"),
        "abroad_no": (r"No/No", "tick"), "abroad_yes": (r"Si/Yes Permiso de residencia", "tick"),
        "occupation": (r"19\. Profesión actual/ Current occupation:", "text"),
        "purpose": (r"Residencia sin finalidad laboral", "tick"),
        "arrival": (r"21\. Fecha prevista de entrada en España/ Intended date of entry into\s*Spain:", "text"),
        "single_entry": (r"Una/One entry", "tick"),
        "spain_address": (r"23\. Domicilio postal del solicitante en España/ Applicant's address in Spain:", "text"),
        "nie": (r"24\. Número de Identificación de Extranjero/Foreign National\s*Identification Number \(NIE\)", "text"),
        "signature": (r"31\. Firma del solicitante", "sign"), "place_date": (r"30\. Lugar y fecha/Place and date", "leave"),
    },
}
# the widest a value may run (PDF points) before it wraps: its own box, never the next column (read off the rendered pages)
WIDTH = {"ny": {"birth_date": 125, "birth_place": 125, "birth_country": 125, "nationality": 170, "passport_number": 115,
                "passport_issued": 75, "passport_expiry": 75, "passport_issuer": 125, "home": 255, "phone": 120},
         "generic": {"birth_date": 120, "birth_place": 125, "birth_country": 125, "nationality": 165, "passport_number": 150,
                     "passport_issued": 100, "passport_expiry": 100, "passport_issuer": 115, "home": 360, "phone": 120,
                     "arrival": 240, "nie": 240}}
LEFT = ["the place and date (27 — on the bilingual form, 30)", "your signature (28 — on the bilingual form, 31)",
        "the photo, glued in its box", "residence-permit details if you live outside your nationality's country (18)"]
FONT = 8.5


class FormChanged(Exception):
    """A label the fill relies on is not on the page: nothing is drawn by guesswork."""


def _fact(f: dict, k: str) -> str:
    return (((f.get("applicant") or {}).get(k) or {}).get("value") or "").strip()


def _dmy(iso: str) -> str:
    return f"{iso[8:10]}-{iso[5:7]}-{iso[:4]}" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso or "") else (iso or "")


def values(f: dict, after: Optional[dict], residence: Optional[str]) -> Dict[str, Tuple[str, str]]:
    """key → (value, its source). Ticks carry "X". Only what the applicant gave us, the passport, or the route fixes."""
    from .three import nat_group
    v: Dict[str, Tuple[str, str]] = {}
    put = lambda k, val, src: v.__setitem__(k, (val.upper() if k not in ("home",) else val, src)) if val else None
    surn = " ".join(x for x in (_fact(f, "surname_1"), _fact(f, "surname_2")) if x)
    put("surnames", surn, "your passport (fields 1–3 as in the travel document)")
    put("given_names", _fact(f, "given_names"), "your passport")
    put("birth_date", _dmy(_fact(f, "birth_date")), "your passport")
    put("birth_place", _fact(f, "birth_place"), "your passport")
    put("birth_country", _fact(f, "birth_country"), "your answers")
    put("nationality", _fact(f, "nationality"), "your passport")
    sex = {"H": "sex_H", "M": "sex_M"}.get(_fact(f, "sex"))
    if sex:
        v[sex] = ("X", "your passport")
    mar = {"S": "marital_S", "C": "marital_C", "Sp": "marital_Sp", "D": "marital_D", "V": "marital_V"}.get(_fact(f, "marital_status"))
    if mar:
        v[mar] = ("X", "your answers")
    v["passport_ordinary"] = ("X", "an ordinary passport — the one you gave me")
    put("passport_number", _fact(f, "passport_number"), "your passport")
    put("passport_issued", _dmy(_fact(f, "passport_issued")), "your passport (your answers)")
    put("passport_expiry", _dmy(_fact(f, "passport_expiry")), "your passport")
    put("passport_issuer", _fact(f, "passport_issuer"), "your passport (your answers)")
    home = "\n".join(x for x in (_fact(f, "home_address_abroad").upper(), _fact(f, "email")) if x)   # the email on its own line
    put("home", home, "your answers: home address abroad and email")
    put("phone", _fact(f, "mobile"), "your answers: mobile")
    if residence and _fact(f, "nationality"):
        same = {"us": "united states", "uk": "united kingdom"}.get(nat_group(_fact(f, "nationality"))) == residence
        v["abroad_no" if same else "abroad_yes"] = ("X", f"you live in {residence.title()}; nationality {_fact(f, 'nationality')}")
    put("occupation", _fact(f, "occupation"), "your answers: occupation")
    v["purpose"] = ("X", "the non-lucrative residence visa — residence without work")
    if (after or {}).get("entry_date"):
        put("arrival", _dmy(after["entry_date"]), "the entry date you gave me")
    v["single_entry"] = ("X", "one entry: the TIE follows in Spain")
    street = " ".join(x for x in (_fact(f, "address_street"), _fact(f, "address_number"), _fact(f, "address_floor")) if x)
    town = " ".join(x for x in (_fact(f, "address_postcode"), _fact(f, "address_town")) if x)
    prov = _fact(f, "address_province")
    put("spain_address", ", ".join(x for x in (street, town, prov if prov and prov.lower() != _fact(f, "address_town").lower() else "") if x),
        "your address in Spain — the same as on the EX-01")
    put("nie", _fact(f, "nie"), "your NIE")
    return v


def _locate(doc, pattern: str, after: Optional[str] = None):
    """→ (page index, [(l, b, r, t) per matched char]) of the pattern's first match (after `after`, if given), else None."""
    for i in range(len(doc)):
        tp = doc[i].get_textpage()
        text = tp.get_text_range()
        start = 0
        if after:
            a = re.search(after, text, re.S)
            if not a:
                continue
            start = a.end()
        m = re.compile(pattern, re.S).search(text, start)
        if not m:
            continue
        boxes = [tp.get_charbox(j) for j in range(m.start(), m.end()) if not text[j].isspace()]
        tick = None
        k = m.start() - 1
        while k >= 0 and m.start() - k <= 4:              # the □ just before the option's words
            if text[k] == "□":
                tick = tp.get_charbox(k)
                break
            k -= 1
        return i, boxes, tick
    return None


def fill(form: str, vals: Dict[str, Tuple[str, str]]) -> Tuple[bytes, List[dict], Optional[Tuple[int, Tuple[float, float, float, float]]]]:
    """→ (the filled PDF, what was put where [{key, value, source, page, rect}], the signature's (page, rect))."""
    import pypdfium2 as pdfium
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os
    import reportlab
    try:
        pdfmetrics.getFont("KanoeVera")
    except KeyError:
        pdfmetrics.registerFont(TTFont("KanoeVera", os.path.join(os.path.dirname(reportlab.__file__), "fonts", "Vera.ttf")))
    src = FORMS[form]["pdf"].read_bytes()
    doc = pdfium.PdfDocument(src)
    placed, draw, sign = [], {}, None
    try:
        sizes = [doc[i].get_size() for i in range(len(doc))]
        for key, spec in ANCHORS[form].items():
            pattern, kind = spec[0], spec[1]
            if kind in ("text", "tick") and key not in vals:
                continue
            hit = _locate(doc, pattern, spec[2] if len(spec) > 2 else None)
            if hit is None:
                raise FormChanged(f"{FORMS[form]['name']}: the label for “{key}” isn't on the page any more — nothing filled")
            page, boxes, tick = hit
            x0 = min(b[0] for b in boxes)
            low = min(b[1] for b in boxes)                # get_charbox → (left, bottom, right, top)
            if kind == "sign":
                sign = (page, (x0, low - 34, x0 + 210, low - 10))
                continue
            if kind == "leave":
                continue
            value, source = vals[key]
            if kind == "tick":
                if tick is None:
                    raise FormChanged(f"{FORMS[form]['name']}: no box beside “{key}” — nothing filled")
                l, b, r, t = tick
                draw.setdefault(page, []).append(("X", (l + r) / 2, b + 0.4, True))
                rect = (l - 1, b - 1, r + 1, t + 1)
            else:
                width = WIDTH[form].get(key, sizes[page][0] - x0 - 60)
                lines = [ln for part in value.split("\n") for ln in _wrap(part, width)]
                for n, ln in enumerate(lines):
                    draw.setdefault(page, []).append((ln, x0 + 1, low - 10 - n * 10, False))
                rect = (x0, low - 12 - 10 * (len(lines) - 1), x0 + max(_w(ln) for ln in lines) + 2, low - 1)
            placed.append({"key": key, "value": value, "source": source, "page": page, "rect": rect})
    finally:
        doc.close()
    reader = PdfReader(io.BytesIO(src))
    w = PdfWriter()
    for i, pg in enumerate(reader.pages):
        if i in draw:
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=sizes[i])
            for text, x, y, centre in draw[i]:
                c.setFont("KanoeVera", 9 if centre else FONT)
                (c.drawCentredString if centre else c.drawString)(x, y, text)
            c.save()
            pg.merge_page(PdfReader(io.BytesIO(buf.getvalue())).pages[0])
        w.add_page(pg)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue(), placed, sign


def _w(s: str) -> float:
    from reportlab.pdfbase.pdfmetrics import stringWidth
    return stringWidth(s, "KanoeVera", FONT)


def _wrap(s: str, width: float) -> List[str]:
    out, cur = [], ""
    for wd in s.split(" "):
        if cur and _w(cur + " " + wd) > width:
            out.append(cur)
            cur = wd
        else:
            cur = f"{cur} {wd}" if cur else wd
    return out + [cur] if cur else out


def card(pdf: bytes, placed: List[dict], strip: str, page: int = 0) -> bytes:
    """Page 1 as a picture, every value we drew highlighted (the same PDF the applicant downloads)."""
    from .. import formcard as FC
    return FC.card_rects(pdf, [p["rect"] for p in placed if p["page"] == page], strip, page)


def build(case: dict, consulate: str) -> Tuple[bytes, List[dict], Optional[tuple], str]:
    """The case's national visa form for its consulate → (pdf, placed, signature, which form)."""
    st = case["state"] if "state" in case else case
    f, after = st.get("facts") or {}, st.get("after") or {}
    residence = ((f.get("choices") or {}).get("residence") or {}).get("value")
    form = FORM_FOR.get(consulate, "generic")
    pdf, placed, sign = fill(form, values(f, after, residence))
    return pdf, placed, sign, form


__all__ = ["FORMS", "FORM_FOR", "values", "fill", "card", "build", "LEFT", "FormChanged"]
