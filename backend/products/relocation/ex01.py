"""CR 1 · the official EX-01 PDF (AcroForm, 96 widgets), kept in the repo byte for byte, and filled from the file's facts.

Source: the founder's download from inclusion.gob.es's models page (AD P807jr:8–20; the host refuses our egresses, so it
is never fetched by code), 23 Sep 2026. The field map beside it is AD's measurement, copied unedited (`ac4229c`); which
widget takes which fact is ex01_map.json, classified by a person from the rendered form.

The rule ported from AD's prepareField (lib/agapi/relocation/visa-form.ts:187–216), unweakened:
  · an IRREDUCIBLE widget (a consent, an intent, the signature) is never given a value — `fill` raises
    DeclarationRefused if one is ever passed, whatever the caller meant;
  · a value with no source is refused (every filled value names the document or the words it came from);
  · a widget nobody placed is left blank, and the screen says so.
Nothing here sends the form anywhere. It returns bytes for the applicant to download, sign by hand, and lodge themselves.
"""
from __future__ import annotations

import hashlib
import io
import json
import pathlib
import re
from typing import Dict, List, Optional

HERE = pathlib.Path(__file__).parent
PDF = HERE / "ex01-official.pdf"
PDF_SHA256 = "3fd926b60822f1d9708616f225c586dd200f2226facd38dbee26dce438486c6f"
FIELD_MAP = HERE / "ex01-field-map-2026-09-23.json"
MAP = HERE / "ex01_map.json"

# the five states P807lu §2.1 draws, plus the two its §2.4/P807lu-4 asked for
FILLED, PREPARED, NO_DATA, NO_MAPPING, UNPLACED = "filled", "prepared_not_adopted", "blank_no_data", "blank_no_mapping", "blank_unplaced"
NOT_APPLICABLE, SIBLING = "not_applicable", "answered_by_sibling"
STATES = (FILLED, SIBLING, PREPARED, NO_DATA, NO_MAPPING, UNPLACED, NOT_APPLICABLE)


class DeclarationRefused(Exception):
    def __init__(self, field: str, why: str) -> None:
        super().__init__(f'refusing to fill "{field}": {why}')
        self.field, self.why = field, why


def pdf_status() -> dict:
    if not PDF.exists():
        return {"present": False}
    return {"present": True, "sha256_ok": hashlib.sha256(PDF.read_bytes()).hexdigest() == PDF_SHA256}


def _maps():
    return json.loads(FIELD_MAP.read_text()), json.loads(MAP.read_text())


def _parts(f: Dict[str, dict], key: str) -> Optional[dict]:
    """A fact by its dotted key, e.g. "applicant.birth_date"."""
    role, _, name = key.partition(".")
    return (f.get(role) or {}).get(name)


def _value_for(spec: dict, fct: dict) -> str:
    v = fct["value"]
    part = spec.get("part")
    if part:                                   # a date split over three boxes
        y, m, d = v.split("-")
        return {"dd": d, "mm": m, "yyyy": y}[part]
    return v


def _derive(facts: Dict[str, Dict[str, dict]]) -> Dict[str, Dict[str, dict]]:
    """Facts the form wants in its own shape: the NIE in three boxes; section 4 from the applicant's choice."""
    f = {r: dict(v) for r, v in facts.items()}
    a = f.setdefault("applicant", {})
    nie = a.get("nie")
    if nie and nie["value"]:
        l, n, c = nie["value"].split("-")
        a["nie_letter"], a["nie_number"], a["nie_control"] = ({**nie, "value": l}, {**nie, "value": n}, {**nie, "value": c})
    choice = (f.get("choices") or {}).get("notices_to_own_address")
    if choice and choice["value"] == "yes" and a.get("address_street", {}).get("value"):
        src = f"{choice['source']} — copied from section 1"
        name = " ".join(x["value"] for x in (a.get("given_names"), a.get("surname_1"), a.get("surname_2")) if x and x["value"])
        n = f.setdefault("notifications", {})
        n["name"] = {"value": name, "source": src, "read_on": choice["read_on"]}
        for k in ("address_street", "address_number", "address_floor", "address_town", "address_postcode", "address_province",
                  "mobile", "email"):
            if a.get(k) and a[k]["value"]:
                n[k] = {**a[k], "source": src}
        idf = a.get("nie") if a.get("nie") and a["nie"]["value"] else a.get("passport_number")
        if idf:
            n["id_number"] = {**idf, "value": idf["value"].replace("-", ""), "source": src}
    return f


def rows(facts: Dict[str, Dict[str, dict]], applies: Dict[str, bool]) -> List[dict]:
    """One row per widget, in the form's reading order (page, then top to bottom, then left to right).
    `applies`: {"2": False, "3": False, "legal_rep": False} — the "en su caso" sections that don't apply to this file."""
    fmap, m = _maps()
    f = _derive(facts)
    out = []
    for w in sorted(fmap["fields"], key=lambda w: (w["page"], -round(w["rect"][1] / 6), w["rect"][0])):
        name = w["name"]
        spec, irr = m["fields"].get(name), m["irreducible"].get(name)
        sec = (spec or {}).get("section") or next((k for k, s in m["sections"].items() if w["section"].startswith(k + ")")), "?")
        row = {"name": name, "page": w["page"], "type": w["type"], "section": m["sections"].get(sec, {}).get("title", w["section"]),
               "label": _clean((spec or {}).get("basis")) or (irr or {}).get("what") or w["label"] or "(no printed text within reach)",
               "basis": (spec or {}).get("basis"),
               "measured_label": w["label"], "state": None, "value": None, "provenance": None, "why": None}
        if irr:
            row.update(state=PREPARED, kind=irr["class"], label=irr["what"], the_person_must=irr["the_person_must"])
        elif spec is None:
            row.update(state=UNPLACED, why="Nothing places this field; a person classifies it first — "
                                           + (f"label found: “{w['label']}”" if w["label"] else "no printed text within reach"))
        elif spec.get("office"):
            row.update(state=NO_MAPPING, why=f"Nothing we hold answers this field: {spec['office']}, from the consulate's own page")
        elif spec.get("at_signing"):
            row.update(state=NO_DATA, why=f"{spec['at_signing'][:1].upper()}{spec['at_signing'][1:]} — written when you sign, by you")
        elif (sec in ("2", "3") and not applies.get(sec, False)) or (spec.get("en_su_caso") and not applies.get("legal_rep", False)):
            row.update(state=NOT_APPLICABLE, why=(m["sections"][sec].get("en_su_caso") if sec in ("2", "3") else spec["en_su_caso"])
                       + " — not your case, so left blank")
        else:
            fct = _parts(f, spec["fact"])
            if fct is None:
                row.update(state=NO_DATA, why="We know what belongs here and hold nothing.", fact=spec["fact"])
            elif fct["value"] == "":
                row.update(state=NO_DATA, why=f"You told us there is none ({fct['source']}).", fact=spec["fact"])
            elif spec.get("tick_when"):
                ticked = fct["value"] == spec["tick_when"]
                row.update(state=FILLED if ticked else SIBLING, value="✓" if ticked else None, fact=spec["fact"],
                           provenance=f"{fct['source']}, {fct['read_on']}", answer=fct["value"],
                           why=None if ticked else f"your answer ({fct['value']}) is another box on this row")
            else:
                row.update(state=FILLED, value=_value_for(spec, fct), provenance=f"{fct['source']}, {fct['read_on']}", fact=spec["fact"])
        out.append(row)
    return out


def _clean(basis: Optional[str]) -> Optional[str]:
    """The form's own words for a box: "Sexo, box 'H' (hombre)" → "Sexo: H (hombre)"; the classifier's notes stay in basis."""
    if not basis:
        return None
    t = re.sub(r"\s*\((?:rendered|unlabelled)[^)]*\)", "", basis).split(" — ")[0]
    return re.sub(r", box '([^']+)'", r": \1", t).replace(" box", "").strip()


def counts(rs: List[dict]) -> Dict[str, int]:
    return {s: sum(1 for r in rs if r["state"] == s) for s in STATES}


def fill(rs: List[dict]) -> bytes:
    """The official PDF with the FILLED rows entered — and nothing else. ⛔ An irreducible widget raises."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject
    _, m = _maps()
    values, ticks = {}, []
    for r in rs:
        if r["state"] != FILLED:
            continue
        if r["name"] in m["irreducible"]:
            raise DeclarationRefused(r["name"], "it is a consent, an intent or the signature, and a value was supplied for it. "
                                                "We may prepare the words; we never make the applicant's assertion.")
        if not r.get("provenance"):
            raise DeclarationRefused(r["name"], "a value with no source — every filled value names where it came from")
        if r["type"] == "checkbox":
            ticks.append(r["name"])
        else:
            values[r["name"]] = r["value"]
    w = PdfWriter(clone_from=PdfReader(str(PDF)))
    w.set_need_appearances_writer(True)
    for page in w.pages:
        w.update_page_form_field_values(page, values, auto_regenerate=False)
        for a in page.get("/Annots") or []:
            a = a.get_object()
            t = a.get("/T") or (a.get("/Parent").get_object().get("/T") if a.get("/Parent") else None)
            if t in ticks:
                a[NameObject("/V")] = NameObject("/Yes")
                a[NameObject("/AS")] = NameObject("/Yes")
                if a.get("/Parent"):
                    a["/Parent"].get_object()[NameObject("/V")] = NameObject("/Yes")
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def read_back(pdf: bytes) -> Dict[str, str]:
    """What the PDF now holds, read with a fresh reader — the test of the fill, and of what was NOT filled."""
    from pypdf import PdfReader
    out = {}
    for k, v in (PdfReader(io.BytesIO(pdf)).get_fields() or {}).items():
        val = v.get("/V")
        if val not in (None, "", "/Off"):
            out[k] = str(val)
    return out
