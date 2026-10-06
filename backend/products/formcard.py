"""CR 33 · a filled official form, shown as a card in the chat (web and WhatsApp): its first page as an image, every field
Sasha filled highlighted, a strip on top saying what it is — filled, NOT signed, NOT submitted — and the full PDF one tap
away. Rendered from the same filled PDF the guest downloads (PDFium draws the form's own fields), so the card can never
show something the PDF doesn't hold.
"""
from __future__ import annotations

import io
import re
from typing import Iterable, Optional, Tuple

HIGHLIGHT = (255, 214, 0, 80)
OUTLINE = (214, 120, 0, 255)
STRIP = (17, 94, 89)                     # Kanoe teal
SCALE = 1.5                              # ~900 px wide for an A4 page: sharp on a phone, ~250 KB as JPEG


def _names(a) -> set:
    """A widget's own name and its parent's (radios and some text fields keep /T on the parent)."""
    out = set()
    while a is not None:
        if a.get("/T"):
            out.add(str(a["/T"]))
        a = a.get("/Parent").get_object() if a.get("/Parent") else None
    return out


def card(pdf: bytes, filled: Iterable[str], strip: str, page: int = 0) -> bytes:
    """JPEG of `page` with the widgets named in `filled` highlighted (a radio or a tick only where it is on)."""
    import pypdfium2 as pdfium
    from PIL import Image, ImageDraw, ImageFont
    from pypdf import PdfReader
    filled = set(filled)
    doc = pdfium.PdfDocument(pdf)
    doc.init_forms()
    try:
        pg = doc[page]
        width, height = pg.get_size()
        img = pg.render(scale=SCALE, may_draw_forms=True).to_pil().convert("RGBA")
    finally:
        doc.close()
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    for a in PdfReader(io.BytesIO(pdf)).pages[page].get("/Annots") or []:
        a = a.get_object()
        if a.get("/Subtype") != "/Widget" or not (_names(a) & filled):
            continue
        if a.get("/AS") is not None and str(a.get("/AS")) == "/Off":
            continue                                   # the radio's other choices, an unticked box
        x0, y0, x1, y1 = (float(v) for v in a["/Rect"])
        x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1))
        d.rectangle([x0 * SCALE - 1, (height - y1) * SCALE - 1, x1 * SCALE + 1, (height - y0) * SCALE + 1],
                    fill=HIGHLIGHT, outline=OUTLINE, width=2)
    img = Image.alpha_composite(img, over).convert("RGB")
    bar = max(54, img.width // 16)
    out = Image.new("RGB", (img.width, img.height + bar), "white")
    out.paste(img, (0, bar))
    d = ImageDraw.Draw(out)
    d.rectangle([0, 0, img.width, bar], fill=STRIP)
    try:
        font = ImageFont.load_default(size=int(bar * 0.36))
    except TypeError:                                   # Pillow < 10.1: the small bitmap font
        font = ImageFont.load_default()
    d.text((bar // 3, bar // 2), strip, fill="white", font=font, anchor="lm")
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=82, optimize=True)
    return buf.getvalue()


def card_rects(pdf: bytes, rects, strip: str, page: int = 0) -> bytes:
    """CR 44 · the same card for a FLAT form (no fields): the rectangles (PDF points) where Sasha drew a value, highlighted."""
    import pypdfium2 as pdfium
    from PIL import Image, ImageDraw, ImageFont
    doc = pdfium.PdfDocument(pdf)
    try:
        pg = doc[page]
        width, height = pg.get_size()
        img = pg.render(scale=SCALE).to_pil().convert("RGBA")
    finally:
        doc.close()
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    for x0, y0, x1, y1 in rects:
        d.rectangle([x0 * SCALE - 1, (height - y1) * SCALE - 1, x1 * SCALE + 1, (height - y0) * SCALE + 1],
                    fill=HIGHLIGHT, outline=OUTLINE, width=2)
    img = Image.alpha_composite(img, over).convert("RGB")
    bar = max(54, img.width // 16)
    out = Image.new("RGB", (img.width, img.height + bar), "white")
    out.paste(img, (0, bar))
    d = ImageDraw.Draw(out)
    d.rectangle([0, 0, img.width, bar], fill=STRIP)
    try:
        font = ImageFont.load_default(size=int(bar * 0.36))
    except TypeError:
        font = ImageFont.load_default()
    d.text((bar // 3, bar // 2), strip, fill="white", font=font, anchor="lm")
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=82, optimize=True)
    return buf.getvalue()


PDF_LINE = "📄 Open the full PDF: "
_PDF_LINE = re.compile(r"\n?" + re.escape(PDF_LINE) + r"(\S+)\s*$")


def show(out, caption: str, card_url: str, pdf_url: str) -> None:
    """The card as the chat's picture (WhatsApp: an image message), its caption ending with the full PDF's link."""
    out.media(f"{caption}\n{PDF_LINE}{pdf_url}", card_url)


def split(caption: str) -> Tuple[str, Optional[str]]:
    """For the web chat: (the caption without the link line, the PDF's link) — the card itself opens the PDF."""
    m = _PDF_LINE.search(caption or "")
    return ((caption[:m.start()], m.group(1)) if m else (caption, None))
