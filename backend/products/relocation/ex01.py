"""CR 1 · the official EX-01 PDF (AcroForm, 96 widgets), kept in the repo byte for byte.

Source: the founder's download from inclusion.gob.es's models page (AD P807jr:8–20; the host refuses our egresses, so it
is never fetched by code), 23 Sep 2026. The field map beside it is AD's measurement, copied unedited (`ac4229c`).
"""
from __future__ import annotations

import hashlib
import pathlib

HERE = pathlib.Path(__file__).parent
PDF = HERE / "ex01-official.pdf"
PDF_SHA256 = "3fd926b60822f1d9708616f225c586dd200f2226facd38dbee26dce438486c6f"
FIELD_MAP = HERE / "ex01-field-map-2026-09-23.json"


def pdf_status() -> dict:
    if not PDF.exists():
        return {"present": False}
    sha = hashlib.sha256(PDF.read_bytes()).hexdigest()
    return {"present": True, "sha256_ok": sha == PDF_SHA256}
