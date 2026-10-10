"""CR 74 · the demo's fake issuer (test mode only): "Example Bank" is NOT a real bank — every page says so. Two cards, each a product page
linking to its Guide to Benefits as a PDF (built here, so the card_terms reader's PDF path is exercised end to end)."""
from __future__ import annotations

from html import escape
from typing import Dict, List

LABEL = "Example Bank is not a real bank: this is a test fixture of the AgAPI sandbox."

CARDS: Dict[str, dict] = {
    "example-bank-travel-visa": {
        "issuer": "Example Bank", "product": "Example Bank Travel Visa", "network": "visa", "country": "ES",
        "page": ["The Example Bank Travel Visa has no foreign transaction fees and earns points on travel.",
                 "Read the Guide to Benefits for the full terms of your travel insurance and car rental cover."],
        "guide": [
            "EXAMPLE BANK TRAVEL VISA - GUIDE TO BENEFITS (effective 1 September 2026)",
            LABEL,
            "1. Foreign transactions. A foreign transaction fee of 0% applies to purchases in a currency other than the euro.",
            "2. Rewards. You earn 2 points per EUR on travel purchases, including flights, hotels and car rentals.",
            "You earn 1 point per EUR on everything else.",
            "3. Car Rental Collision Damage Waiver. This benefit is primary coverage and covers damage to and theft of the rental vehicle.",
            "To be eligible you must decline the rental company's collision damage waiver (CDW/LDW) and pay for the entire rental with your card.",
            "Third-party liability is not covered by this benefit.",
            "Rental periods of up to 31 consecutive days are covered.",
            "Excluded countries: Ireland, Israel, Jamaica.",
            "Excluded vehicles: motorcycles, campervans, vehicles with a retail value over EUR 75,000.",
            "The maximum benefit is EUR 50,000 per rental, including any excess charged by the rental company.",
            "4. Baggage Delay. If your checked baggage is delayed for more than 6 hours, we reimburse essential purchases up to EUR 300 per trip.",
            "Lost checked baggage is covered up to EUR 1,500 per person.",
            "5. Trip Delay. If your trip is delayed by more than 12 hours, we reimburse reasonable expenses up to EUR 500 per trip.",
            "Travel insurance applies only if the fare was paid with your Example Bank Travel Visa.",
            "6. Claims. Claims are handled by Example Assistance (not a real company).",
            "You must notify Example Assistance within 60 days of the incident.",
            "Send all documents within 180 days of the incident.",
            "Claims line: +34 900 000 000. Email: claims@example-assistance.example",
        ]},
    "example-bank-everyday-mastercard": {
        "issuer": "Example Bank", "product": "Example Bank Everyday Mastercard", "network": "mastercard", "country": "ES",
        "page": ["The Example Bank Everyday Mastercard is a simple card for everyday spending.",
                 "See the Guide to Benefits for its fees and rewards."],
        "guide": [
            "EXAMPLE BANK EVERYDAY MASTERCARD - GUIDE TO BENEFITS (effective 1 September 2026)",
            LABEL,
            "1. Foreign transactions. A foreign transaction fee of 3% applies to purchases in a currency other than the euro.",
            "2. Rewards. You earn 1 point per EUR on all purchases.",
            "3. Purchase Protection. Items you buy with the card are protected against theft and accidental damage for 90 days, up to EUR 1,000 per claim.",
            "4. Claims. Claims are handled by Example Assistance (not a real company).",
            "You must notify Example Assistance within 30 days of the incident.",
            "Claims line: +34 900 000 001.",
        ]},
}


def product_page(slug: str) -> str:
    c = CARDS[slug]
    body = "".join(f"<p>{escape(x)}</p>" for x in c["page"])
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{escape(c['product'])} · Example Bank (test fixture)</title>"
            f"<meta name='robots' content='noindex'></head><body><header><b>Example Bank</b> — <i>{escape(LABEL)}</i></header>"
            f"<h1>{escape(c['product'])}</h1>{body}<p><a href='/fixtures/cards/{slug}/guide-to-benefits.pdf'>Guide to Benefits (PDF)</a></p>"
            f"<footer>{escape(LABEL)}</footer></body></html>")


def tiny_pdf(lines: List[str]) -> bytes:
    """A real one-page PDF (Helvetica, one line each) — no PDF library needed to write it."""
    def esc(s: str) -> str:
        return s.encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    ops = ["BT", "/F1 8 Tf", "10 TL", "36 800 Td"]
    for ln in lines:
        ops.append(f"({esc(ln)}) Tj T*")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1", "replace")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    return out


def guide_pdf(slug: str) -> bytes:
    return tiny_pdf(CARDS[slug]["guide"])
