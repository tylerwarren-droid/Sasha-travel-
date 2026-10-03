"""CR 1 · reading the passport photo page the applicant SENDS on WhatsApp — the only place a product calls the model.

  1. The photo is fetched from Twilio (Basic auth), kept in memory for this one call, never stored or logged.
  2. Claude reads it into a strict schema (structured outputs): the visible fields AND the two machine-readable lines.
  3. ⚠ The reading is CHECKED, not trusted: the passport's own ICAO 9303 check digits (7-3-1) over the document
     number, the birth date and the expiry are recomputed from the MRZ the model read. A value whose check digit
     fails, or that disagrees with the MRZ, is shown as such — never silently kept.
  4. Every value is read back to the person; it becomes a fact only on THEIR "yes" (source: "passport photo page,
     read by Kanoe's AI and confirmed by you"). A value they had already typed differently is kept as a second
     source, and the reviewer shows the disagreement.
The person is told before anything is sent that the photo goes to Anthropic's model to be read and is not kept.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from booking_signer import yes as YS

from . import facts as F

log = logging.getLogger("products.relocation.docread")
MODEL = "claude-opus-5-5"
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
MAX_BYTES = 8 * 1024 * 1024

SCHEMA = {
    "type": "object",
    "properties": {
        "is_passport_photo_page": {"type": "boolean"},
        "legible": {"type": "boolean"},
        "issuing_country": {"type": "string"},
        "passport_number": {"type": "string"},
        "surnames": {"type": "string"},
        "given_names": {"type": "string"},
        "nationality": {"type": "string"},
        "sex": {"type": "string", "enum": ["M", "F", "X", ""]},
        "birth_date": {"type": "string", "description": "YYYY-MM-DD, or empty"},
        "birth_place": {"type": "string"},
        "expiry_date": {"type": "string", "description": "YYYY-MM-DD, or empty"},
        "mrz_line_1": {"type": "string"},
        "mrz_line_2": {"type": "string"},
    },
    "required": ["is_passport_photo_page", "legible", "issuing_country", "passport_number", "surnames", "given_names",
                 "nationality", "sex", "birth_date", "birth_place", "expiry_date", "mrz_line_1", "mrz_line_2"],
    "additionalProperties": False,
}
PROMPT = ("This is a photo a person sent of their own passport, to fill in their Spanish residence application. Transcribe "
          "exactly what is printed on the photo page. Copy each field character for character as printed; do not "
          "correct, translate or complete anything. Leave a field empty when it is not visible or not legible — an "
          "empty field is always better than a guess. Copy the two machine-readable lines at the bottom exactly, "
          "including every '<'. If this is not a passport's photo page, set is_passport_photo_page to false.")

# ── ICAO 9303 check digits ─────────────────────────────────────────────────────────────────────────────────────────────


def _cd(s: str) -> str:
    w, total = (7, 3, 1), 0
    for i, ch in enumerate(s):
        v = int(ch) if ch.isdigit() else (ord(ch) - 55 if ch.isalpha() else 0)
        total += v * w[i % 3]
    return str(total % 10)


def mrz_check(line2: str) -> Dict[str, Any]:
    """TD3 line 2: number(9)+cd, nationality(3), birth YYMMDD+cd, sex, expiry YYMMDD+cd, …"""
    l2 = re.sub(r"\s", "", line2 or "").upper()
    if len(l2) < 28:
        return {"readable": False}
    num, ncd, birth, bcd, sex, exp, ecd = l2[0:9], l2[9], l2[13:19], l2[19], l2[20], l2[21:27], l2[27]
    return {"readable": True, "number": num.replace("<", ""), "number_ok": _cd(num) == ncd, "birth": birth,
            "birth_ok": _cd(birth) == bcd, "sex": sex.replace("<", "X"), "expiry": exp, "expiry_ok": _cd(exp) == ecd}


def _yymmdd(iso: str) -> str:
    return iso[2:4] + iso[5:7] + iso[8:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso or "") else ""


def verify(read: Dict[str, Any]) -> Dict[str, str]:
    """Per field: "ok" (agrees with the MRZ and its check digit holds) · a sentence saying what doesn't."""
    m = mrz_check(read.get("mrz_line_2", ""))
    if not m["readable"]:
        return {"_mrz": "the machine-readable lines couldn't be read, so nothing could be cross-checked"}
    out = {}
    pn = (read.get("passport_number") or "").replace(" ", "").upper()
    out["passport_number"] = ("ok" if m["number_ok"] and pn == m["number"] else
                              f"the passport's check digit fails for the number read ({m['number']})" if not m["number_ok"]
                              else f"the printed number ({pn}) and the machine-readable one ({m['number']}) differ")
    out["birth_date"] = ("ok" if m["birth_ok"] and _yymmdd(read.get("birth_date", "")) == m["birth"] else
                         "the birth date's check digit fails" if not m["birth_ok"] else
                         "the printed birth date and the machine-readable one differ")
    out["passport_expiry"] = ("ok" if m["expiry_ok"] and _yymmdd(read.get("expiry_date", "")) == m["expiry"] else
                              "the expiry's check digit fails" if not m["expiry_ok"] else
                              "the printed expiry and the machine-readable one differ")
    out["sex"] = "ok" if (read.get("sex") or "X") == m["sex"] else "the printed sex and the machine-readable one differ"
    # line 1 carries the surname the passport itself treats as the surname (no check digit — compared, not "verified")
    l1 = re.sub(r"\s", "", read.get("mrz_line_1", "") or "").upper()
    if l1.startswith("P") and "<<" in l1[5:]:
        mrz_sur = l1[5:].split("<<", 1)[0].replace("<", " ").strip()
        printed = re.sub(r"[^A-Z ]", " ", F.fold(read.get("surnames", "")).upper()).split()
        if mrz_sur and " ".join(printed) != mrz_sur:
            out["surname_1"] = (f"the machine-readable zone gives the surname as {mrz_sur}; the printed field reads "
                                f"“{read.get('surnames')}” — tell me which belongs on the form")
    return out


# ── the two outside calls (tests replace both) ──────────────────────────────────────────────────────────────────────


async def _twilio_media(url: str) -> Tuple[bytes, str]:
    import httpx
    sid, tok = os.getenv("TWILIO_ACCOUNT_SID", ""), os.getenv("TWILIO_AUTH_TOKEN", "")
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=True) as c:
        r = await c.get(url, auth=(sid, tok) if sid and tok else None)
    r.raise_for_status()
    return r.content, r.headers.get("content-type", "").split(";")[0]


async def _model_read(data: bytes, media_type: str) -> Dict[str, Any]:
    import anthropic
    client = anthropic.AsyncAnthropic()
    r = await client.beta.messages.create(
        model=MODEL, max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        extra_body={"fallbacks": "default"},            # a policy decline re-runs on Anthropic's chosen fallback model
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                         "data": base64.standard_b64encode(data).decode()}},
            {"type": "text", "text": PROMPT}]}])
    if r.stop_reason == "refusal":
        raise RuntimeError("the model declined to read this image")
    return json.loads(next(b.text for b in r.content if b.type == "text"))


FETCH = _twilio_media
READ = _model_read


# ── the conversation ────────────────────────────────────────────────────────────────────────────────────────────────

LABELS = [("passport_number", "Passport number"), ("surname_1", "First surname"), ("surname_2", "Second surname"),
          ("given_names", "Given names"), ("sex", "Sex"), ("birth_date", "Date of birth"), ("birth_place", "Place of birth"),
          ("nationality", "Nationality"), ("passport_expiry", "Expires")]


def to_facts(read: Dict[str, Any]) -> Dict[str, str]:
    # the surname field as printed, whole: splitting "VAN DER BERG" on spaces would invent two wrong surnames. Someone
    # with two Spanish-style surnames corrects it in the confirmation ("No") and types them.
    sex = {"F": "M", "M": "H", "X": "X"}.get(read.get("sex") or "", "")
    out = {"passport_number": (read.get("passport_number") or "").replace(" ", "").upper(),
           "surname_1": (read.get("surnames") or "").strip(),
           "given_names": (read.get("given_names") or "").strip(), "sex": sex,
           "birth_date": read.get("birth_date") or "", "birth_place": (read.get("birth_place") or "").strip(),
           "nationality": read.get("nationality") or "", "passport_expiry": read.get("expiry_date") or ""}
    return {k: v for k, v in out.items() if v}


def _show(k: str, v: str) -> str:
    if k == "sex":   # the Spanish form's letters differ from the passport's: F on a passport is M (mujer) on the EX-01
        return {"M": "female — M (mujer) on the Spanish form", "H": "male — H (hombre) on the Spanish form",
                "X": "X"}.get(v, v)
    if k in ("birth_date", "passport_expiry") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v or ""):
        from datetime import date
        return date.fromisoformat(v).strftime("%-d %B %Y")
    return v


async def on_media(ctx: dict, facts: dict) -> bool:
    pend, out = ctx["st"]["pending"], ctx["out"]
    m = next((x for x in ctx["media"] if x["type"] in IMAGE_TYPES), None)
    if not m:
        out.text("I can read a photo (JPEG or PNG) of your passport's photo page — not that kind of file. Or type the "
                 "answer to the question above.")
        return True
    await ctx["early"]("Reading your passport photo page… It goes to Anthropic's AI model to be read, once; I don't keep the "
                       "photo.")
    try:
        data, mt = await FETCH(m["url"])
        if len(data) > MAX_BYTES:
            raise ValueError("the photo is larger than 8 MB")
        read = await READ(data, mt if mt in IMAGE_TYPES else m["type"])
    except Exception as e:
        log.error("[docread] not read: %s", type(e).__name__)
        out.text(f"I couldn't read that photo ({type(e).__name__}). Nothing was kept. Try a sharper photo, or type the answer.")
        return True
    finally:
        data = b""
    if not read.get("is_passport_photo_page") or not read.get("legible"):
        out.text("That doesn't look like a legible passport photo page — nothing was kept. Try again with the whole page in "
                 "frame, flat and in good light, or type the answer.")
        return True
    vals, checks = to_facts(read), verify(read)
    lines = []
    for k, label in LABELS:
        if k in vals:
            c = checks.get(k)
            mark = " ✓ (the passport's own check digit agrees)" if c == "ok" else (f" ⚠ {c}" if c else "")
            lines.append(f"• {label}: {_show(k, vals[k])}{mark}")
    if checks.get("_mrz"):
        lines.append(f"⚠ {checks['_mrz']}.")
    out.text("I read:\n" + "\n".join(lines))
    out.ask("Is every line right?", [("Yes, all right", "rx:doc:yes"), ("No", "rx:doc:no")])
    pend.update(doc_read=vals, doc_checks=checks, step_before_doc=pend.get("step"), step="doc_confirm")
    return True


async def on_confirm(ctx: dict, facts: dict, body: str, payload: str) -> None:
    from . import turn as RT
    pend, out = ctx["st"]["pending"], ctx["out"]
    vals = pend.pop("doc_read", {}) or {}
    checks = pend.pop("doc_checks", {}) or {}
    pend["step"] = pend.pop("step_before_doc", None) or "facts"
    if payload == "rx:doc:yes" or (not payload and YS.is_yes(body)):
        src, on = "passport photo page, read by Kanoe's AI and confirmed by you", ctx["now"].strftime("%-d %b %Y")
        a, docs = facts.setdefault("applicant", {}), facts.setdefault("documents", {})
        for k, v in vals.items():
            if checks.get(k) not in (None, "ok"):
                continue          # a value its own passport contradicts is never kept: they type it instead
            prior = a.get(k)
            if prior and F.fold(str(prior["value"])) != F.fold(v):
                docs.setdefault(f"applicant.{k}", []).append(prior)    # what they typed stays, as a second source
            a[k] = F.fact(v, src, on)
        kept = [k for k in vals if checks.get(k) in (None, "ok")]
        out.text(f"Kept {len(kept)} value{'s' if len(kept) != 1 else ''} from your passport, each marked as read from it.")
    else:
        out.text("OK — nothing from the photo was kept. Let's type them instead.")
    if pend["step"] in ("facts", "route", "resources", "presenter"):
        if pend["step"] != "facts":
            out.text("(Your passport details are kept; let's finish the questions above first.)")
            return
        RT._next_question(pend, out)
        if pend["step"] == "notices_done":
            await RT._prepare(ctx)
