"""Sasha 224 · ADD TO THE KEEP FROM A PHOTO (/s2). "Add my passport" → the photo picker on their screen (keep_add) → the photo is
read ONCE (Claude vision) and dropped: a passport by its MRZ, every check digit verified (an unchecked read is never saved — they
take another photo); a loyalty / frequent-flyer card from a photo or an Apple Wallet screenshot → a MASKED card to confirm → on
their Confirm, saved encrypted in the Keep (s2_keep.put). The image is never stored, logged or sent anywhere else; the values wait
in this process only until Confirm (10 minutes), then go to the Keep or are dropped. The chat model only ever sees masks.

    keep_add            the tool: the capture card on their screen (kind passport | loyalty)
    parse_td3(l1, l2)   an ICAO 9303 passport MRZ → {number, country (ISO-2), expires_on} with every check digit verified
    POST /keep/scan                  {kind, image (base64), media_type} → {token, masked, shown} — nothing saved yet
    POST /keep/scan/{token}/confirm  → saved in the Keep → {item: masked}
    POST /keep/scan/{token}/discard  → dropped
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

KINDS = ("passport", "loyalty")
PENDING_TTL = timedelta(minutes=10)
MAX_IMAGE_BYTES = 6_000_000
_PENDING: Dict[str, dict] = {}   # token → {account, kind, values, at} — this process only; never written anywhere
READ = None                       # tests replace it: (kind, image_bytes, media_type) → the model's JSON (a dict)

# ICAO 9303 issuing states → ISO 3166-1 alpha-2 (a passport's MRZ uses alpha-3; Germany is "D")
_ISO3 = dict(p.split(":") for p in (
    "AFG:AF ALA:AX ALB:AL DZA:DZ ASM:AS AND:AD AGO:AO AIA:AI ATG:AG ARG:AR ARM:AM ABW:AW AUS:AU AUT:AT AZE:AZ BHS:BS BHR:BH BGD:BD "
    "BRB:BB BLR:BY BEL:BE BLZ:BZ BEN:BJ BMU:BM BTN:BT BOL:BO BIH:BA BWA:BW BRA:BR BRN:BN BGR:BG BFA:BF BDI:BI CPV:CV KHM:KH CMR:CM "
    "CAN:CA CYM:KY CAF:CF TCD:TD CHL:CL CHN:CN COL:CO COM:KM COG:CG COD:CD CRI:CR CIV:CI HRV:HR CUB:CU CUW:CW CYP:CY CZE:CZ DNK:DK "
    "DJI:DJ DMA:DM DOM:DO ECU:EC EGY:EG SLV:SV GNQ:GQ ERI:ER EST:EE SWZ:SZ ETH:ET FJI:FJ FIN:FI FRA:FR GAB:GA GMB:GM GEO:GE D:DE "
    "DEU:DE GHA:GH GIB:GI GRC:GR GRD:GD GTM:GT GIN:GN GNB:GW GUY:GY HTI:HT HND:HN HKG:HK HUN:HU ISL:IS IND:IN IDN:ID IRN:IR IRQ:IQ "
    "IRL:IE ISR:IL ITA:IT JAM:JM JPN:JP JOR:JO KAZ:KZ KEN:KE KIR:KI PRK:KP KOR:KR KWT:KW KGZ:KG LAO:LA LVA:LV LBN:LB LSO:LS LBR:LR "
    "LBY:LY LIE:LI LTU:LT LUX:LU MAC:MO MDG:MG MWI:MW MYS:MY MDV:MV MLI:ML MLT:MT MHL:MH MRT:MR MUS:MU MEX:MX FSM:FM MDA:MD MCO:MC "
    "MNG:MN MNE:ME MAR:MA MOZ:MZ MMR:MM NAM:NA NRU:NR NPL:NP NLD:NL NZL:NZ NIC:NI NER:NE NGA:NG MKD:MK NOR:NO OMN:OM PAK:PK PLW:PW "
    "PSE:PS PAN:PA PNG:PG PRY:PY PER:PE PHL:PH POL:PL PRT:PT PRI:PR QAT:QA ROU:RO RUS:RU RWA:RW KNA:KN LCA:LC VCT:VC WSM:WS SMR:SM "
    "STP:ST SAU:SA SEN:SN SRB:RS SYC:SC SLE:SL SGP:SG SVK:SK SVN:SI SLB:SB SOM:SO ZAF:ZA SSD:SS ESP:ES LKA:LK SDN:SD SUR:SR SWE:SE "
    "CHE:CH SYR:SY TWN:TW TJK:TJ TZA:TZ THA:TH TLS:TL TGO:TG TON:TO TTO:TT TUN:TN TUR:TR TKM:TM TUV:TV UGA:UG UKR:UA ARE:AE GBR:GB "
    "USA:US URY:UY UZB:UZ VUT:VU VAT:VA VEN:VE VNM:VN YEM:YE ZMB:ZM ZWE:ZW RKS:XK").split())


class ScanRefused(Exception):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule, self.message = rule, message


# ── the MRZ, checked ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def check_digit(s: str) -> str:
    total = 0
    for i, ch in enumerate(s):
        v = int(ch) if ch.isdigit() else (ord(ch) - 55 if "A" <= ch <= "Z" else 0)   # '<' is 0
        total += v * (7, 3, 1)[i % 3]
    return str(total % 10)


def _clean(line: str) -> str:
    return re.sub(r"\s+", "", str(line or "")).upper().replace("«", "<")


def _refill(l1: str, l2: str) -> tuple:
    """A reader miscounts runs of '<'. Line 1's trailing fillers are re-padded to 44; line 2's ONLY free run (the optional
    personal number, positions 28-41) is re-padded to 14 — every check digit is still verified after, so a misread never passes."""
    if l1.startswith("P") and 30 <= len(l1) <= 60 and len(l1) != 44:
        l1 = (l1.rstrip("<") + "<" * 44)[:44]
    if len(l2) != 44 and 30 <= len(l2) <= 60 and re.fullmatch(r"[A-Z0-9<]+", l2):
        mid = l2[28:-2].rstrip("<")
        if len(mid) <= 14:
            l2 = l2[:28] + (mid + "<" * 14)[:14] + l2[-2:]
    return l1, l2


def parse_td3(line1: str, line2: str) -> Dict[str, str]:
    """A passport's two 44-character MRZ lines → {number, country, expires_on}. Every check digit (number, birth date, expiry,
    the composite) must hold, or it's refused — a misread is never saved."""
    l1, l2 = _refill(_clean(line1), _clean(line2))
    if len(l1) != 44 or len(l2) != 44 or not l1.startswith("P") or not re.fullmatch(r"[A-Z0-9<]{44}", l2):
        raise ScanRefused("mrz_unreadable", "I couldn't read the two lines at the bottom of the photo page clearly — take another "
                                            "photo, flat, in good light, with the whole page in the frame.")
    num, num_cd, dob, dob_cd, exp, exp_cd, comp = l2[0:9], l2[9], l2[13:19], l2[19], l2[21:27], l2[27], l2[43]
    ok = (check_digit(num) == num_cd and check_digit(dob) == dob_cd and check_digit(exp) == exp_cd
          and check_digit(l2[0:10] + l2[13:20] + l2[21:43]) == comp)
    if not ok:
        raise ScanRefused("mrz_check_failed", "The photo didn't read cleanly — one of the passport's check digits didn't match, so "
                                              "I haven't kept anything. Take another photo, flat and sharp.")
    state = l1[2:5].replace("<", "")
    country = _ISO3.get(state)
    if not country:
        raise ScanRefused("country_unknown", "I couldn't tell which country issued it — nothing was kept.")
    try:
        expires = date(2000 + int(exp[0:2]), int(exp[2:4]), int(exp[4:6]))
    except ValueError:
        raise ScanRefused("mrz_check_failed", "The expiry date didn't read cleanly — take another photo.") from None
    return {"number": num.replace("<", ""), "country": country, "expires_on": expires.isoformat()}


# ── the photo, read once ─────────────────────────────────────────────────────────────────────────────────────────────────────

_ASK = {
    "passport": ("This is a photo the account holder took of the photo page of their own passport, to save it in their private, "
                 "encrypted Keep. Transcribe ONLY the machine-readable zone: the two lines of 44 characters at the bottom, exactly, "
                 "character for character, with '<' fillers. Reply with JSON only: {\"mrz\": [\"line 1\", \"line 2\"]} — or "
                 "{\"mrz\": null} if the two lines aren't fully visible and sharp. Never guess a character."),
    "loyalty": ("This is a photo of the account holder's own loyalty / frequent-flyer card, or a screenshot of it in Apple Wallet, to "
                "save in their private Keep. Reply with JSON only: {\"program\": \"the programme's name, e.g. Iberia Plus\", "
                "\"number\": \"the membership number exactly as printed, no spaces\"} — or {\"number\": null} if it isn't legible. "
                "Never guess a character."),
}


async def _read(kind: str, image: bytes, media_type: str) -> dict:
    if READ is not None:
        return await READ(kind, image, media_type)
    import app.services.llm as LLM
    r = await LLM.client.messages.create(
        model=os.getenv("SASHA_KEEP_SCAN_MODEL", "claude-opus-5-5"), max_tokens=2500,   # it thinks first (~700 tokens for an MRZ)
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(image).decode()}},
            {"type": "text", "text": _ASK[kind]}]}])
    text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}


def _values(kind: str, got: dict) -> Dict[str, str]:
    from agapi import keep as K
    if kind == "passport":
        mrz = got.get("mrz") if isinstance(got, dict) else None
        if not (isinstance(mrz, list) and len(mrz) == 2):
            raise ScanRefused("mrz_unreadable", "I couldn't see the two lines at the bottom of the photo page — take another photo "
                                                "with the whole page in the frame.")
        v = parse_td3(mrz[0], mrz[1])
    else:
        num = re.sub(r"\s+", "", str((got or {}).get("number") or ""))
        if not num:
            raise ScanRefused("unreadable", "I couldn't read the membership number — take another photo or screenshot.")
        v = {"program": str((got or {}).get("program") or "Loyalty").strip()[:60], "number": num}
    try:
        return K.normalise(kind, v)
    except K.Refused as e:
        raise ScanRefused(e.rule, e.message) from None


def _sweep() -> None:
    now = datetime.now(timezone.utc)
    for t in [t for t, p in _PENDING.items() if now - p["at"] > PENDING_TTL]:
        _PENDING.pop(t, None)


async def scan(account: str, kind: str, image: bytes, media_type: str) -> dict:
    """Read the photo once → a masked card to confirm (nothing saved). The image bytes are not kept past this call."""
    from agapi import keep as K
    kind = (kind or "").strip().lower()
    if kind not in KINDS:
        raise ScanRefused("kind_unknown", "I can add a passport or a loyalty card from a photo.")
    if not image or len(image) > MAX_IMAGE_BYTES or media_type not in ("image/jpeg", "image/png", "image/webp", "image/heic"):
        raise ScanRefused("image_invalid", "That photo couldn't be read — try a JPEG or PNG under 6 MB.")
    try:
        got = await _read(kind, image, "image/jpeg" if media_type == "image/heic" else media_type)
    finally:
        image = b""   # dropped: never stored, never logged
    values = _values(kind, got)
    _sweep()
    token = secrets.token_urlsafe(18)
    _PENDING[token] = {"account": account, "kind": kind, "values": values, "at": datetime.now(timezone.utc)}
    masked = K.mask(kind, values)
    shown = [masked] + ([f"Expires {values['expires_on'][:7]}"] if kind == "passport" else [])
    return {"token": token, "kind": kind, "masked": masked, "shown": shown,
            "say": "Check it's yours, then Confirm — it's saved encrypted in your Keep. The photo isn't kept."}


async def confirm(account: str, token: str) -> dict:
    from agapi import s2_keep as KEEP
    _sweep()
    p = _PENDING.get(token)
    if not p or p["account"] != account:
        raise ScanRefused("scan_expired", "That photo's reading has expired — add it again.")
    _PENDING.pop(token, None)
    try:
        out = await KEEP.put(account, p["kind"], p["values"])
    finally:
        p["values"] = None
    try:   # Sasha 228 · the account's open pages hear it (a /next waiting on "Add from your phone" carries on) — the mask only
        from agapi.keep_handoff import added_line
        from booking_signer import live_events as LE
        LE.publish(account, {"type": "keep_added", "kind": out.get("type"), "masked": out.get("masked"), "text": added_line(out.get("masked") or "")})
    except Exception as e:
        log.info("[keep] keep_added not published: %s", type(e).__name__)
    return {"item": out.get("masked"), "created": out.get("created"), "type": out.get("type")}


def discard(account: str, token: str) -> None:
    p = _PENDING.get(token)
    if p and p["account"] == account:
        _PENDING.pop(token, None)


# ── the tool: the capture card on their screen ───────────────────────────────────────────────────────────────────────────────

async def keep_add(ctx, a: dict) -> dict:
    kind = str(a.get("kind") or "").strip().lower()
    kind = "loyalty" if kind in ("loyalty", "frequent_flyer", "frequent flyer", "airline", "hotel") else kind
    if kind not in KINDS:
        from agapi.v0 import ToolError
        raise ToolError("kind_unknown", "keep_add takes a passport or a loyalty / frequent-flyer card")
    return {"status": "capture_on_screen", "kind": kind,
            "say": ("The photo picker is on their screen: they take or choose a photo of the passport's photo page"
                    if kind == "passport" else "The photo picker is on their screen: they take a photo of the card or choose an Apple "
                                               "Wallet screenshot") + ". You never see the number — only a mask, once they confirm."}


def tools() -> List[dict]:
    from agapi.v0 import _t
    return [_t("keep_add", "Pacioli", keep_add, "Add a passport or a loyalty / frequent-flyer card to the person's Keep FROM A PHOTO: "
               "puts the camera / photo picker on their screen. They confirm a masked card; you never see the number. Never ask "
               "them to type a document number.", {"kind": {"type": "string", "description": "passport or loyalty"}}, ["kind"],
               {"type": "object", "properties": {"status": {"type": "string"}}}, ["kind_unknown"])]


# ── routes (mounted under the agent router → /api/agent/keep/scan…) ─────────────────────────────────────────────────────────

from fastapi import APIRouter, Request                       # noqa: E402
from fastapi.responses import JSONResponse                   # noqa: E402

router = APIRouter()


async def _who(request: Request) -> Optional[str]:
    from app.services.chat_account import chat_account, signed_in
    account = await chat_account(request)
    return account if signed_in(account) else None


def _no(e) -> JSONResponse:
    code = 503 if e.rule in ("keep_closed", "keep_unreachable") else 422
    return JSONResponse({"ok": False, "rule": e.rule, "message": e.message}, status_code=code)


@router.post("/keep/scan")
async def scan_route(request: Request):
    who = await _who(request)
    if not who:
        return JSONResponse({"ok": False, "rule": "sign_in"}, status_code=403)
    try:
        body = await request.json()
        image = base64.b64decode(str(body.get("image") or ""), validate=False)
    except Exception:
        return JSONResponse({"ok": False, "rule": "image_invalid", "message": "That photo couldn't be read."}, status_code=400)
    try:
        out = await scan(who, str(body.get("kind") or ""), image, str(body.get("media_type") or "image/jpeg"))
    except ScanRefused as e:
        return _no(e)
    finally:
        image, body = b"", None
    return {"ok": True, **out}


@router.post("/keep/scan/{token}/confirm")
async def confirm_route(token: str, request: Request):
    from agapi.s2_keep import KeepError
    who = await _who(request)
    if not who:
        return JSONResponse({"ok": False, "rule": "sign_in"}, status_code=403)
    try:
        return {"ok": True, **(await confirm(who, token))}
    except (ScanRefused, KeepError) as e:
        return _no(e)


@router.post("/keep/scan/{token}/discard")
async def discard_route(token: str, request: Request):
    who = await _who(request)
    if who:
        discard(who, token)
    return {"ok": True}


__all__ = ["keep_add", "tools", "router", "scan", "confirm", "discard", "parse_td3", "check_digit", "ScanRefused"]
