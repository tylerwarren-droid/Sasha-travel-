"""CR 37 · RELOCATEME, THREE CONSULATES END TO END — London, New York, Washington DC. Every line below was READ LIVE on
6 Oct 2026 on the consulate's own page (or the Spanish Government's), quoted, with its URL. Nothing is composed: where a page
is silent, we say it's silent; where a page is the Ministry's template, we say so.

For each: the fees up front in local currency (by nationality where the table varies) and the Modelo 790 código 052; the
consulate's own booking route, ONE tap to its exact page, the applicant's details each as its own copyable message; the
790-052 pre-filled where the official form allows (card + PDF); ONE print-ready PDF pack in the consulate's own order, with
"Sign here" on every signature box. The applicant picks, presses, signs and pays. Kanoe never books, sends or signs.

The 790-052 used is the official AcroForm the Washington consulate posts with its own instructions (sha256 6fb5b45b…); the
Ministry's own generator (sede.administracionespublicas.gob.es/tasasPDF) has a CAPTCHA and requires a NIF/NIE — someone
with no NIE can't complete it, and we never touch it. London and New York ask for "two copies… signed" of the same form.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("products.relocation.three")
READ_ON = "6 Oct 2026"
F790 = Path(__file__).with_name("790-052-official.pdf")
F790_SOURCE = ("https://www.exteriores.gob.es/Consulados/washington/en/ServiciosConsulares/PublishingImages/Paginas/Consular/"
               "Visado-de-residencia-no-lucrativa/Form%20790-052.pdf")
F790_SHA256 = "6fb5b45bce93d4e5ee2b26fda6f30c89f39d45837d3ddcaa5a2f6b9f2d0d39fc"
TASA_052 = {"tariff": "2.1.1 Residencia temporal no lucrativa (titular principal y sus familiares)", "eur": "10,94",
            "order": "Orden PJC/617/2025, de 13 de junio (BOE-A-2025-12056)", "url": "https://www.boe.es/buscar/act.php?id=BOE-A-2025-12056",
            "generator": "https://sede.administracionespublicas.gob.es/pagina/index/directorio/tasa052",
            "generator_note": "the Ministry's online generator has a CAPTCHA and requires a NIF/NIE — without an NIE you can't "
                              "complete it; the consulate takes the fee itself, in local currency"}

# nationality → the fee table's group (from the passport's own words or code)
_NAT = [("us", r"\b(usa|u\.?s\.?a?\.?|united states|american|estadounidense|ee\.?\s?uu)\b"),
        ("uk", r"\b(gbr|british|brit[aá]nic|united kingdom|uk|reino unido)\b"),
        ("ca", r"\b(can|canad)"), ("au", r"\b(aus|australia)"), ("et", r"\b(eth|ethiopia|eti[oó]p)"), ("mr", r"\b(mrt|maurit)")]
_ES_NAT = {"us": "EE.UU.", "uk": "REINO UNIDO", "ca": "CANADÁ", "au": "AUSTRALIA", "et": "ETIOPÍA", "mr": "MAURITANIA"}


def nat_group(nationality: str) -> str:
    t = (nationality or "").lower()
    return next((g for g, rx in _NAT if re.search(rx, t)), "other")


CONSULATES: Dict[str, dict] = {
    "london": {
        "office": "Consulado General de España en Londres", "city": "London", "tz": "Europe/London", "currency": "£",
        "page": "https://www.exteriores.gob.es/Consulados/londres/en/ServiciosConsulares/Paginas/Consular/Visado-de-residencia-no-lucrativa.aspx",
        "page_dated": "July 6, 2026",
        "template": "the Ministry's standard text for this visa, with London's own additions (the S1 paragraph, ACRO, the UK "
                    "medical wording, BLS as the place of submission)",
        "fees_url": "https://www.exteriores.gob.es/Consulados/londres/es/Comunicacion/Noticias/PublishingImages/Paginas/Articulos/"
                    "Tasas-Consulares/Listado%20precios%2001-01-26.pdf",
        "fees_dated": "in force from 1 Jan 2026 (printed 16/12/2025)",
        "visa_fee": {"uk": ("516.00", "“Visado residencia no lucrativa 516,00” (British reciprocity)"),
                     "et": ("409.40", "“Visado residencia no lucrativa 409,40” (Ethiopia)"),
                     "ca": (None, "the list doesn't name this visa for Canadians — its nearest line is “CN-Vis LarDur Residencia "
                                  "Principal 589,10”: confirm with the consulate"),
                     "us": (None, "the list has no line for this visa for US nationals — “999-Costes Complementarios (Vis. "
                                  "Americanos) 104,55” may apply: the list doesn't say; confirm with the consulate"),
                     "other": ("79.00", "“14-Visado 79,00” (the national visa fee)")},
        "fee_790": ("9.60", "“Aut. Inicial residencia temporal 9,60”"),
        "extra": [("BLS service charge", "14.85", "“£14,85(inclusive of VAT) per visa application” (BLS)")],
        "pay": "in pounds, at the BLS centre when you hand in the application — “The Visa fees can be paid by cash, credit/debit "
               "card” (BLS's page); the 790-052 can also be paid online with its receipt attached (the consulate's page)",
        "copies_790": 2, "copies_790_words": "“complete all the fields of, and sign, two copies of form 790 code 052”",
        "booking": {"kind": "bls", "who": "BLS Spain Visa Application Centre, 20 St Andrew Street, London EC4A 3AG",
                    "url": "https://uk.blsspainglobal.com/Global/account/login",
                    "words": "“Place of submission: BLS. Spain Visa Application Centre … 20 St Andrew Street, London EC4A 3AG”",
                    "notes": ["BLS asks you to create an account and log in; its login has a CAPTCHA — yours.",
                              "One person per appointment — family members book their own (the consulate's 2022 sheet; the "
                              "current page doesn't repeat it)."],
                    "in_person": "“Visa applications must be submitted in person by the applicant”"},
        "checklist": [("visa_form", "National visa application form", "complete and sign", "“Each applicant must complete and sign a visa application”"),
                      ("ex01", "EX-01", "complete and sign", "“Each applicant must complete and sign a copy of the EX-01 form”"),
                      ("photo", "Photograph", "1", "“A recent, passport-size, colour photograph, taken against a light background…”"),
                      ("passport", "Passport", "original + photocopy of the biometric page(s)", "“minimum validity period of 1 year and contain two blank pages”"),
                      ("means", "Proof of financial means", "originals and a copy", "“400% of… IPREM” (+100% per family member)"),
                      ("insurance", "Health insurance", "original and a copy", "“must cover all the risks insured by Spain's public health system”"),
                      ("criminal", "Criminal record certificate (ACRO for the UK)", "original and a copy", "past 5 years; “cannot be older than 6 months”; apostille + sworn translation"),
                      ("medical", "Medical certificate", "original and a copy", "issued “within 3 months”; Hague Apostille; UK or Spanish only"),
                      ("residence", "Proof of residence in the consular district", "", "“Proof of residence in the consular district.”"),
                      ("fees", "Payment of the fees (visa fee + 790-052)", "", "two signed copies of the 790-052")],
        "photo": "Recent, passport-size, colour, light background, facing forward, no dark or reflective glasses, nothing hiding "
                 "the oval of the face (the consulate's page). BLS adds: white background, not more than 6 months old, on photo "
                 "paper, stuck onto the visa form. No size in mm is given.",
        "sign": "Each form says “complete and sign”; no page says “wet”, “original” or “handwritten” — you hand in paper in person, "
                "so sign each by hand.",
    },
    "newyork": {
        "office": "Consulado General de España en Nueva York", "city": "New York", "tz": "America/New_York", "currency": "$",
        "page": "https://www.exteriores.gob.es/Consulados/nuevayork/es/ServiciosConsulares/Paginas/index.aspx?scco=Estados+Unidos"
                "&scd=215&scca=Visados&scs=Visados+Nacionales+-+Visado+de+residencia+no+lucrativa",
        "page_dated": "no date on the page",
        "template": "the Ministry's standard structure with New York's own text (the FBI rule, the driver's-licence proof, its "
                    "email route); its /en/ page is the same Spanish text, and its “Formulario” link is broken (404)",
        "fees_url": "https://www.exteriores.gob.es/DocumentosAuxiliaresSC/Estados%20Unidos/NUEVA%20YORK%20(C)/1.2.1%20Tasas%20Consulares%20NY%2001.01.2026.pdf",
        "fees_dated": "“TASAS CONSULARES 2026 / 1 de enero 2026”",
        "visa_fee": {"us": ("140", "“Visado sin finalidad laboral: $140 + Tasa de autorización de residencia … ($13) = $153”"),
                     "other": ("106", "“Visados de larga duración para nacionales de otros países: $106 + Tasa de autorización de "
                                      "residencia … ($13)”")},
        "fee_790": ("13", "“Tasa de autorización de residencia para todas las nacionalidades ($13)”"),
        "extra": [],
        "pay": "only by USPS money order — “Las tasas consulares solo pueden abonarse con \"money order\" de USPS” — at your "
               "appointment; the 790-052 may instead be paid online with its receipt attached",
        "copies_790": 2, "copies_790_words": "“firmar dos ejemplares del modelo 790 código 052, epígrafe 2.1”",
        "booking": {"kind": "email", "who": "the consulate itself, by email", "email": "cog.nuevayork.visnac@maec.es",
                    "words": "“Deberá concertar una cita previa para este tipo de visado a través del correo electrónico "
                             "cog.nuevayork.visnac@maec.es”",
                    "asks": ["A) Nombre completo", "B) Dirección de correo electrónico y número de teléfono",
                             "C) Número de pasaporte y nacionalidad", "D) Tipo de visado solicitado",
                             "E) Copia escaneada, en formato PDF, del ID/Carnet de conducir",
                             "F) Copia escaneada, en formato PDF, de la página de identidad de su pasaporte"],
                    "notes": ["All applicants in ONE email (its page: “todo en un único email”).",
                              "Non-US citizens also attach their US residence visa or Green Card (item F).",
                              # CR 44 · EU 174: the 2023 form's own footer prints cog.nuevayork.vis@maec.es; the visa page (read
                              # 6 Oct 2026) names …visnac@ for booking — the page is the current word, so the draft uses it
                              "This draft goes to the address on the consulate's current visa page (cog.nuevayork.visnac@maec.es). "
                              "The application form's own footer prints an older one (cog.nuevayork.vis@maec.es) — use the page's."],
                    "in_person": "“La solicitud de visado se presentará personalmente por el interesado”"},
        "checklist": [("visa_form", "Formulario de solicitud de visado nacional", "complete and sign", "“Cada solicitante completará … y firmará” (its link is broken: 404)"),
                      ("ex01", "EX-01", "sign one copy", "“firmar un ejemplar del impreso EX - 01”"),
                      ("photo", "Fotografía", "1", "“tamaño carné, a color, con fondo claro, tomada de frente…”"),
                      ("passport", "Pasaporte", "original + photocopy", "“validez mínima de 1 año y dos páginas en blanco”"),
                      ("means", "Medios económicos", "original y copia", "“400% del IPREM … 100% … por cada familiar”"),
                      ("insurance", "Seguro de enfermedad", "original y una copia", "entidad autorizada en España; all public-system risks"),
                      ("criminal", "Antecedentes penales (FBI)", "original y una copia", "últimos 5 años; apostille + translation; FBI only — no local/state police"),
                      ("medical", "Certificado médico", "original y una copia", "“Reglamento Sanitario Internacional de 2005”"),
                      ("residence", "Prueba de residencia en la demarcación", "original y fotocopia", "ID/driver's licence (no provisional); non-US: Green Card or US visa"),
                      ("fees", "Abono de las tasas", "", "money order; two signed copies of the 790-052")],
        "photo": "“Una fotografía reciente, tamaño carné, a color, con fondo claro, tomada de frente, sin gafas oscuras, ni reflejos, "
                 "ni prendas que oculten el óvalo de la cara.” No size in mm is given.",
        "sign": "Its page says “firmará” (visa form), “firmar un ejemplar” (EX-01) and “firmar dos ejemplares” (790); it never says "
                "“wet” or “original” — you hand in paper in person, so sign each by hand.",
        "territory": "Connecticut, Delaware, New Jersey, New York and Pennsylvania (its Demarcación page, 23 March 2022)",
    },
    "washington": {
        "office": "Sección Consular de la Embajada de España en Washington", "city": "Washington, D.C.", "tz": "America/New_York",
        "currency": "$",
        "page": "https://www.exteriores.gob.es/Consulados/washington/en/ServiciosConsulares/Paginas/Consular/Visado-de-residencia-no-lucrativa.aspx",
        "page_dated": "no page date (“Fees from January 1, 2026”)",
        "template": "its own text (BLS address, 2026 dollar amounts, its own PDFs); NOTE: the ministry-pattern URL for this visa "
                    "(…scd=288…) serves New York's page — we never use it",
        "fees_url": "https://www.exteriores.gob.es/Consulados/washington/en/ServiciosConsulares/Paginas/Consular/Visado-de-residencia-no-lucrativa.aspx",
        "fees_dated": "“Fees from January 1, 2026” — “revised quarterly according to current exchange rates”",
        "visa_fee": {"us": ("140", "“U.S. citizens: $140”"), "au": ("313", "“Citizens of Australia: $313”"),
                     "ca": ("789", "“Citizens of Canada: $789”"), "et": ("548", "“Citizens of Ethiopia: $548”"),
                     "mr": ("282", "“Citizens of Mauritania: $282”"), "uk": ("691", "“Citizens of the UK: $691”"),
                     "other": ("106", "“All other nationalities: $106”")},
        "fee_790": ("13", "“Residency permit fee: $13”"),
        "extra": [("BLS service fee", "20", "“BLS Service Fee … All Nationals 20” (BLS)"),
                  ("SMS notifications (optional)", "5", "“Notifications (SMS) 5” (BLS)")],
        "pay": "to BLS — “Payment made to BLS. Non-refundable.”",
        "copies_790": 1, "copies_790_words": "“Each applicant must complete and sign this form, selecting point \"1. c) "
                                              "Autorización inicial de Residencia Temporal\"”",
        "booking": {"kind": "bls", "who": "BLS Spain Visa Application Center, 1660 L Street NW, Suite 216, Washington, D.C. 20036",
                    "url": "https://usa.blsspainglobal.com/Global/account/login",
                    "words": "“The application must be submitted in person by appointment only to the BLS Spain Visa Application "
                             "Center for Spain in Washington DC.”",
                    "notes": ["Choose the National (Long-Term) visa section — “there are different sections for Schengen … and for "
                              "National (Long-Term) visa appointments”.",
                              "Family members can be added to the same booking.", "BLS's login has a CAPTCHA — yours."],
                    "in_person": "“in person by appointment only”"},
        "checklist": [("visa_form", "National Visa Application form", "complete and sign", "“can be filled out electronically or handwritten in capital letters”"),
                      ("photo", "One photo", "glued or clipped onto the form", "within the last 6 months, passport-size, colour, white/light background"),
                      ("passport", "Passport", "original + photocopy", "1 year validity, two blank visa pages; not issued more than 10 years ago"),
                      ("us_status", "Proof of legal US residence (non-US citizens)", "original and copy", "Green card or valid US long-term visa"),
                      ("residence", "Proof of residence in the district", "original and copy", "US driver's license or state ID"),
                      ("ex01", "Form EX 01", "original and copy", "“Each applicant must complete and sign a copy of Form EX 01”"),
                      ("fees_790", "Form 790-052", "", "point 1.c; sign inside the box"),
                      ("affidavit", "Affidavit", "", "notarized letter, in Spanish or with a translation"),
                      ("means", "Financial means", "", "“In 2026 the required amount is $32.000 per year for one applicant, and $8.000… for each dependent”"),
                      ("termination", "Termination or sabbatical letter (advisable)", "", ""),
                      ("accommodation", "Proof of accommodation (advisable)", "", ""),
                      ("school", "School enrolment letter (advisable)", "", ""),
                      ("insurance", "Health insurance", "", "unlimited, no copayment, valid 1 year; no travel insurance; card not accepted"),
                      ("medical", "Medical certificate", "", "issued within 90 days; stamp, signature and licence number"),
                      ("criminal", "FBI background check", "original and a copy", "within 6 months; Hague Apostille; sworn translation"),
                      ("disclaimer", "Disclaimer form (BLS)", "", "“Lugar, fecha y firma / Place, date and signature”"),
                      ("fees", "Payment of fees", "", "to BLS")],
        "photo": "“Recent (taken within the last 6 months…), passport-size, color photograph… white, light, clear, uniform background, "
                 "facing forward, without dark or reflective glasses…” — glued or clipped onto the visa application form.",
        "sign": "Its page says “complete and sign” (visa form, EX 01, 790-052); the 790 instructions: “Write your signature inside "
                "the box”; no page says “wet” or “original” — you hand in paper in person, so sign each by hand.",
        "territory": "Washington, D.C., Maryland, Virginia, West Virginia and North Carolina (its page)",
    },
}


def fees(cid: str, nationality: str) -> Tuple[List[str], Optional[str]]:
    """→ (lines, total or None) in the consulate's own currency, from its own table, for this nationality."""
    c = CONSULATES[cid]
    cur, g = c["currency"], nat_group(nationality)
    amount, words = c["visa_fee"].get(g) or c["visa_fee"]["other"]
    lines = [f"Visa fee: {cur}{amount} — {words}" if amount else f"Visa fee: not stated — {words}"]
    a790, w790 = c["fee_790"]
    lines.append(f"Residence-permit fee (Modelo 790 código 052, tariff 2.1.1 — €{TASA_052['eur']} in Spain): {cur}{a790} — {w790}")
    for name, amt, w in c["extra"]:
        lines.append(f"{name}: {cur}{amt} — {w}")
    total = None
    if amount:
        total = sum(float(x) for x in [amount, a790] + [amt for name, amt, _ in c["extra"] if "optional" not in name])
    lines.append(f"How you pay: {c['pay']}.")
    return lines, (f"{cur}{total:,.2f}".replace(".00", "") if total is not None else None)


DIFFERENCES = ("Which consulate you use is decided by where you live, not your nationality. What changes:\n"
               "• Booking — London and Washington: an online appointment at the BLS visa centre (account + CAPTCHA, yours); "
               "New York: an email to the consulate itself, with scans attached.\n"
               "• Fees — London in pounds (£79 for most nationalities; £516 for British citizens), New York $106/$140 + $13 paid "
               "ONLY by USPS money order, Washington $106–$789 by nationality + $13 + BLS's $20, paid to BLS.\n"
               "• Documents — Washington asks for more (an affidavit, the BLS disclaimer, $32,000 a year of means, unlimited health "
               "insurance); London wants a UK ACRO certificate and a medical certificate from the UK or Spain; New York accepts only "
               "an FBI check, never local or state police.")


def details(f: dict) -> List[Tuple[str, str]]:
    """The applicant's details as the booking pages ask for them — each will be its own message."""
    a = f.get("applicant") or {}
    v = lambda k: ((a.get(k) or {}).get("value") or "").strip()
    name = " ".join(x for x in (v("given_names"), v("surname_1"), v("surname_2")) if x)
    out = [("Full name", name), ("Email", v("email")), ("Phone", v("mobile")), ("Passport number", v("passport_number")),
           ("Nationality", v("nationality")), ("Date of birth", v("birth_date"))]
    return [(k, x) for k, x in out if x]


def booking_messages(cid: str, f: dict) -> List[str]:
    """The ONE tap first, then each detail on its own (a long-press copies just it)."""
    c = CONSULATES[cid]
    b = c["booking"]
    if b["kind"] == "email":
        import urllib.parse
        a = dict(details(f))
        body = ("Buenos días:\n\nSolicito cita para un visado de residencia no lucrativa. Datos del solicitante:\n"
                f"A) Nombre completo: {a.get('Full name', '')}\nB) Correo electrónico y teléfono: {a.get('Email', '')} / {a.get('Phone', '')}\n"
                "C) Número de pasaporte y nacionalidad: \nD) Tipo de visado solicitado: Visado de residencia no lucrativa\n"
                "E) Adjunto copia escaneada en PDF del ID/carnet de conducir.\nF) Adjunto copia escaneada en PDF de la página de "
                "identidad del pasaporte.\n\nUn saludo.")
        mail = f"mailto:{b['email']}?" + urllib.parse.urlencode({"subject": "Cita visado de residencia no lucrativa", "body": body},
                                                               quote_via=urllib.parse.quote)
        head = (f"📧 {c['office']} books this visa by EMAIL — its page: {b['words']}\nOne tap opens it drafted in your own mail app "
                f"(you add C — your passport number and nationality — attach the two PDF scans, E and F, and press Send; I never "
                f"send it):\n{mail}")
    else:
        head = (f"📅 {c['office']}: you apply at {b['who']} — its page: {b['words']}\nOne tap to book (you pick the slot and press):\n"
                f"{b['url']}")
    msgs = [head] + [f"• {n}" for n in b.get("notes", [])]
    msgs += [x for _, x in details(f)]
    return msgs


# ── the 790-052, pre-filled where the official form allows ─────────────────────────────────────────────────────────

INSTR_790 = "the 790's official instructions, as the Washington consulate publishes them"   # CR 41 · read by a New York or
# London applicant too: "Washington's instructions" alone read as the wrong consulate's
LEFT_790 = [f"your NIE (leave it blank if you have none — {INSTR_790}, item 2)",
            "your current address abroad (the same instructions, items 5–9; we hold only your Spanish address)",
            "the place and date, and your signature inside the box (item 12)", "how it's paid (the consulate takes it)"]


def rows_790(f: dict, today: date) -> List[dict]:
    a = f.get("applicant") or {}
    v = lambda k: ((a.get(k) or {}).get("value") or "").strip()
    src = lambda k: (a.get(k) or {}).get("source") or "your answers"
    rs = []
    y = str(today.year)
    for i, ch in enumerate(y):
        rs.append({"field": f"Ejercicio_{i}", "value": ch, "source": f"the current year ({INSTR_790}, item 1)"})
    surnames = " ".join(x for x in (v("surname_1"), v("surname_2")) if x)
    if surnames or v("given_names"):
        rs.append({"field": "Nombre_Completo", "value": f"{surnames} {v('given_names')}".strip().upper(),
                   "source": "your passport — surnames, then names (item 3)"})
    nat = v("nationality")
    if nat:
        g = nat_group(nat)
        rs.append({"field": "Nacionalidad", "value": _ES_NAT.get(g, nat.upper()), "source": "your passport, in Spanish (item 4)"})
    if v("mobile"):
        rs.append({"field": "Telefono_Domicilio", "value": v("mobile"), "source": "your phone (item 6)"})
    rs.append({"field": "PRINCIPAL", "value": "/Yes", "source": f"{INSTR_790}, item 10"})
    rs.append({"field": "Activado1_3", "value": "/Yes", "source": "1.c Autorización inicial de residencia temporal (item 11)"})
    return rs


def fill_790(rs: List[dict]) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject
    never = re.compile(r"^(NIF|Ciudad_Solicitud|Fecha_Actual|EN EFECTIVO|ADEUDO EN CUENTA|Importe_|Entidad_|Oficina_|Numero_Cuenta)")
    for r in rs:
        if never.match(r["field"]):
            raise ValueError(f"{r['field']} is the applicant's (NIE, place/date/signature, payment)")
    ticks = {r["field"] for r in rs if r["value"] == "/Yes"}
    values = {r["field"]: r["value"] for r in rs if r["value"] != "/Yes"}
    w = PdfWriter(clone_from=PdfReader(str(F790)))
    w.set_need_appearances_writer(True)
    for page in w.pages:
        if not page.get("/Annots"):
            continue
        w.update_page_form_field_values(page, values, auto_regenerate=False)
        for an in page.get("/Annots") or []:
            an = an.get_object()
            t = an.get("/T") or (an.get("/Parent").get_object().get("/T") if an.get("/Parent") else None)
            if t in ticks:                                   # a field on both copies keeps its value on its parent
                an[NameObject("/AS")] = NameObject("/Yes")
                (an.get("/Parent").get_object() if an.get("/Parent") else an)[NameObject("/V")] = NameObject("/Yes")
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


# ── the one print-ready pack ─────────────────────────────────────────────────────────────────────────────────────
# Every page is drawn at print resolution (150 dpi, A4): the filled forms as PDFium draws them (the same rendering as the
# chat's cards — so the pack can never show something the form doesn't hold), the checklist and photo pages with a real
# font (Bitstream Vera, shipped inside reportlab) so accents print; "SIGN HERE" is drawn beside every signature box.

DPI = 150
A4 = (1240, 1754)


def _font(size: int, bold: bool = False):
    import os
    from PIL import ImageFont
    try:
        import reportlab
    except ImportError:                                  # an environment without it: the pack still builds (accents may not print)
        log.warning("[three] reportlab missing: Pillow's own font for the pack")
        return ImageFont.load_default(size=size)
    return ImageFont.truetype(os.path.join(os.path.dirname(reportlab.__file__), "fonts", "VeraBd.ttf" if bold else "Vera.ttf"), size)


def _text_page(title: str, lines: List[str]):
    from PIL import Image, ImageDraw
    W, H = A4
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 110], fill=(17, 94, 89))
    d.text((60, 55), title, fill="white", font=_font(34, True), anchor="lm")
    small = _font(20)
    y = 145
    for ln in lines:
        cur = ""
        for wd in ln.split(" "):                        # wrap at the page width
            if cur and d.textlength(cur + " " + wd, font=small) > W - 140:
                d.text((70, y), cur, fill=(20, 20, 20), font=small)
                y, cur = y + 28, "    " + wd
            else:
                cur = f"{cur} {wd}" if cur else wd
        d.text((70, y), cur, fill=(20, 20, 20), font=small)
        y += 38
        if y > H - 60:
            break
    return im


def _pages(pdf: bytes, signs: Dict[int, Tuple[float, float, float, float]]):
    """Each page of a filled form as PDFium draws it; "SIGN HERE" drawn at each (page → PDF-point rect)."""
    import pypdfium2 as pdfium
    from PIL import ImageDraw
    doc = pdfium.PdfDocument(pdf)
    doc.init_forms()
    out = []
    try:
        for i in range(len(doc)):
            pg = doc[i]
            w, h = pg.get_size()
            scale = A4[0] / w
            im = pg.render(scale=scale, may_draw_forms=True).to_pil().convert("RGB")
            if i in signs:
                x0, y0, x1, y1 = signs[i]
                d = ImageDraw.Draw(im)
                box = [x0 * scale, (h - y1) * scale, x1 * scale, (h - y0) * scale]
                d.rectangle(box, fill=(255, 242, 168), outline=(192, 0, 0), width=3)
                d.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), "SIGN HERE >", fill=(192, 0, 0), font=_font(22, True), anchor="mm")
            out.append(im)
    finally:
        doc.close()
    return out


def ex01_signature(pdf: bytes) -> Optional[Tuple[int, Tuple[float, float, float, float]]]:
    """Where the EX-01's own signature box (FIRMA, field Texto68) is: (page index, a strip just above it)."""
    from pypdf import PdfReader
    for i, pg in enumerate(PdfReader(io.BytesIO(pdf)).pages):
        for an in pg.get("/Annots") or []:
            an = an.get_object()
            t = an.get("/T") or (an.get("/Parent").get_object().get("/T") if an.get("/Parent") else None)
            if t == "Texto68":
                x0, y0, x1, y1 = (float(v) for v in an["/Rect"])
                mid = (y0 + y1) / 2                        # beside the box, on its left: its own label stays readable
                return i, (max(8, min(x0, x1) - 150), mid - 11, min(x0, x1) - 6, mid + 11)
    return None


SIGN_790 = (60, 150, 290, 170)            # under the "En … a …" line: the box item 12 of the instructions names


def pack(cid: str, ex01_pdf: bytes, rs790: List[dict], applicant: str, visa: Optional[tuple] = None) -> bytes:
    """ONE PDF: the consulate's checklist (its order) → each document we prepared, at its place in that order (the EX-01, the
    790-052 × the copies it asks for, the photo spec) — SIGN HERE beside every signature box. Nothing signed, nothing sent."""
    c = CONSULATES[cid]
    lines = [f"For: {applicant} — prepared by Kanoe from {c['office']}'s own page, read {READ_ON}:", c["page"],
             f"Signatures: {c['sign']}", ""]
    for i, (key, name, copies, words) in enumerate(c["checklist"], 1):
        mark = {"ex01": "[IN THIS PACK]", "fees_790": "[IN THIS PACK]", "photo": "[spec IN THIS PACK]",
                "visa_form": "[IN THIS PACK]" if visa else "[yours to gather]"}.get(
            key, "[the 790-052 IN THIS PACK]" if key == "fees" and cid != "washington" else "[yours to gather]")
        lines.append(f"{i}. {name}{' — ' + copies if copies else ''} {mark} {words}")
    pages = [_text_page(f"{c['city']}: your visa pack, in the consulate's order", lines)]
    for key, name, copies, words in c["checklist"]:
        if key == "visa_form" and visa:                  # CR 44 · the national visa form, filled, its signature box marked
            vpdf, sign = visa
            pages += _pages(vpdf, {sign[0]: sign[1]} if sign else {})
        elif key == "ex01":
            at = ex01_signature(ex01_pdf)
            pages += _pages(ex01_pdf, {at[0]: at[1]} if at else {})
        elif key == "fees_790" or (key == "fees" and cid != "washington"):
            pages += _pages(fill_790(rs790), {0: SIGN_790, 1: SIGN_790})   # its two pages ARE its two copies (Interesado,
                                                                            # Administración): sign both
        elif key == "photo":
            pages.append(_text_page("Photograph: the consulate's own words", [c["photo"]]))
    buf = io.BytesIO()
    pages[0].save(buf, "PDF", resolution=DPI, save_all=True, append_images=pages[1:])
    return buf.getvalue()


# ── the conversation (called from after.py once the consulate is known) ──────────────────────────────────────────

def items(cid: str, f: Optional[dict] = None, today: Optional[date] = None) -> List[dict]:
    """The consulate's own list in the shape the document pack uses (after._pack / consulates.pack); the passport checked
    against the year all three pages ask for ("minimum validity period of 1 year")."""
    from datetime import timedelta
    exp = (((f or {}).get("applicant") or {}).get("passport_expiry") or {}).get("value")
    out = []
    for i, (key, name, copies, words) in enumerate(CONSULATES[cid]["checklist"], 1):
        it = {"n": i, "key": key, "label": name, "words": words, "copies": copies or None,
              "status": "prepared" if key == "ex01" else "yours", "why": None}
        if key == "passport" and exp and today:
            ok = exp >= (today + timedelta(days=365)).isoformat()
            it.update(status="ok" if ok else "problem", why=f"your passport is valid until {exp}: " +
                      ("at least a year from today" if ok else "LESS than a year from today — the consulate asks for at least one year"))
        out.append(it)
    return out


def which(residence: str, state: Optional[str], us_cid: Optional[str]) -> Optional[str]:
    if residence == "united kingdom":
        return "london"
    return us_cid if us_cid in ("newyork", "washington") else None


async def present(ctx: dict, cid: str, base: dict, web: str, save) -> None:
    """Everything for this consulate, in the order the applicant needs it: who and why, the differences, the fees, the
    booking (one tap + each detail its own message), the 790-052 (card + PDF), the one print-ready pack."""
    from .. import formcard as FC
    pend, out = ctx["st"]["pending"], ctx["out"]
    c = CONSULATES[cid]
    f = pend.get("facts") or {}
    case = pend.get("case_id")
    nat = ((f.get("applicant") or {}).get("nationality") or {}).get("value", "")
    out.text(f"Your consulate: *{c['office']}*" + (f" — it covers {c['territory']}" if c.get("territory") else "") +
             f". Everything below is from its own page, read {READ_ON}: {c['page']} ({c['page_dated']}). The page is {c['template']}.")
    out.text(DIFFERENCES)
    lines, total = fees(cid, nat)
    out.text(f"💷 Fees at {c['office']}{' for ' + nat if nat else ''} — its own table ({c['fees_dated']}):\n" +
             "\n".join("• " + x for x in lines) + (f"\nTotal: {total}." if total else ""))
    for m in booking_messages(cid, f):
        out.text(m)
    out.text("When it's booked, tell me the day and time (e.g. \"consulate booked 12 November 10:00\") and it goes on your "
             "“Move to Madrid” trip with what to bring.")
    from . import visa_form as VF                     # CR 44 · A1: the national visa form, filled, first in every consulate's list
    vf = VF.FORMS[VF.FORM_FOR.get(cid, "generic")]
    FC.show(out, f"Your national visa application ({vf['name']}), filled from your answers and your Keep. Not signed — the "
                 "place, date, signature and photo are yours.",
            f"{web}/api/products/relocation/{case}/visa-form-card.jpg", f"{web}/api/products/relocation/{case}/visa-form.pdf")
    FC.show(out, f"Your Modelo 790 código 052, filled where the official form allows — {c['copies_790_words']}. Not signed, not paid.",
            f"{web}/api/products/relocation/{case}/790-card.jpg", f"{web}/api/products/relocation/{case}/790-052.pdf")
    out.text("Left for you on the 790: " + "; ".join(LEFT_790) + ".")
    out.text(f"🖨 Your whole pack as ONE print-ready PDF, in {c['office']}'s own order — its checklist, the national visa form, the EX-01, the 790-052 "
             f"(both copies), the photo spec — with SIGN HERE beside every signature box:\n{web}/api/products/relocation/{case}/pack.pdf\n"
             f"Signatures: {c['sign']}")
    out.text("After you arrive, say “after arrival”: your padrón, your TIE (EX-17 + the 790-012 fee) and your Social Security "
             "number (TA.1) — each prepared from the same answers, in the order you need them.")      # CR 44
    pend["consulate_office"] = c["office"]
    its = items(cid, f, ctx["now"].date())
    flag = next((i for i in its if i["status"] == "problem"), None)
    if flag:
        out.text(f"⚠ {flag['why']}.")
    await save(ctx, {"after": {**base, "consulate": {"office": c["office"], "three": cid, **({"id": cid} if cid != "london" else {})},
                               "checklist": its}})
