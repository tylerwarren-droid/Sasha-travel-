"""Sasha 333 · THE TRAVELLER VAULT — a group member's passport, frequent-flyer and hotel loyalty numbers (docs/sasha/S-333-traveller-vault.md).

THE ONE RECORD: each member's numbers live ONLY in the Keep (agapi/s2_keep.py + agapi/keep.py: keep_keys / keep_items, a per-person data
key wrapped by the vault's KMS, every value AES-256-GCM, never logged), under THEIR member id — a Keep of their own, never the organiser's.
Everything else holds a masked view or a reference ("keep:<item id>"): the master list (✓ / missing), the planner (has_passport), the
booking call (CR 163: open(member, reference) at booking time, the one place a value leaves the vault).

  invite(owner, member_ids|None)   a signed, single-person, expiring link (7 days) per member → emailed when the list has their email,
                                   else handed to the organiser to forward (the link carries no number — the numbers are never in chat)
  read_token(token)                → {member, owner, movement} or None (bad signature / expired)
  page(token) · save(token, …) · erase(token)   the member's own page: masks only, a save, a delete of everything
  has_passport(member) · vault_view(member)      what the master list and planner may know: ✓ / missing, masks
  delete_by_phone(number, words)  "delete my passport" from the member's own WhatsApp (the webhook's verified sender)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger("booking_signer.traveller_vault")
LIFE_S = 7 * 24 * 3600


def _key() -> bytes:
    k = os.getenv("SASHA_VAULT_INVITE_SECRET", "").strip() or os.getenv("SASHA_BOOKING_KEY", "").strip()
    if not k:
        raise RuntimeError("no signing secret for vault invites (SASHA_BOOKING_KEY)")
    return hashlib.sha256(("sasha-traveller-vault:" + k).encode()).digest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(member_id: str, owner: str, movement_id: str, now: Optional[float] = None) -> str:
    body = json.dumps({"m": member_id, "o": owner, "v": movement_id, "n": secrets.token_hex(6), "e": int((now or time.time()) + LIFE_S)},
                      separators=(",", ":")).encode()
    return _b64(body) + "." + _b64(hmac.new(_key(), body, hashlib.sha256).digest())


def read_token(token: str, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    try:
        b, s = (token or "").split(".")
        body, sig = _unb64(b), _unb64(s)
    except Exception:
        return None
    if not hmac.compare_digest(sig, hmac.new(_key(), body, hashlib.sha256).digest()):
        return None
    d = json.loads(body)
    if d.get("e", 0) < (now or time.time()):
        return None
    return {"member": d["m"], "owner": d["o"], "movement": d["v"], "expires": d["e"]}


def link(token: str) -> str:
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/") + "/vault/" + token


# ── what anyone but the member may know: ✓ / missing (the organiser), masks (the member's own page) ───────────────────────────

async def _items(member_id: str) -> List[dict]:
    from agapi import s2_keep as KEEP
    try:
        return await KEEP.list_(member_id)
    except Exception as e:   # the Keep closed / not reachable: nothing known — never "has it"
        log.warning("[vault] not read: %s", type(e).__name__)
        return []


def _owner(member: Dict[str, Any]) -> str:
    """Sasha 351 · the vault is the PERSON's (the roster): a trip's member is a link to them — one passport, every trip."""
    return str(member.get("person_id") or member["id"])


async def has_passport(member: Dict[str, Any]) -> bool:
    return any(i["type"] == "passport" for i in await _items(_owner(member)))


async def vault_view(member: Dict[str, Any]) -> Dict[str, Any]:
    """The organiser's view: ✓ / missing — never a number, never a mask with digits. References for the booking call (CR 163)."""
    items = await _items(_owner(member))
    loy = [i for i in items if i["type"] == "loyalty"]
    pp = next((i for i in items if i["type"] == "passport"), None)
    return {"passport": bool(pp), "loyalty": [i["masked"].split("•")[0].strip() for i in loy],   # "Iberia Plus" — its name, no digits
            "refs": {"passport": "keep:" + pp["item_id"] if pp else None, "loyalty": ["keep:" + i["item_id"] for i in loy]}}


# ── the member's own page (/vault/<token>) ────────────────────────────────────────────────────────────────────────────────

class VaultRefused(Exception):
    def __init__(self, rule: str, message: str):
        super().__init__(message)
        self.rule, self.message = rule, message


def _who(token: str) -> Dict[str, Any]:
    t = read_token(token)
    if not t:
        raise VaultRefused("link_expired", "This link has expired or isn't valid — ask the organiser for a new one.")
    return t


async def _member(t: Dict[str, Any]) -> Dict[str, Any]:
    from . import groups as G
    st = G.store()
    mv = await st.movement(t["owner"], t["movement"]) if t.get("movement") else None
    # Sasha 351 · the link names the PERSON (their vault is theirs, every trip); a link made before 351 named the trip's row
    m = next((x for x in (await st.members(mv["id"]) if mv else []) if t["member"] in (x.get("person_id"), x["id"])), None)
    company = (mv or {}).get("company")
    if not m:   # on the company's roster (a profile with no trip yet, or no longer on this one): their own vault, all the same
        grp = (mv or {}).get("group_id") or ((await st.company(t["owner"])) or {}).get("id")
        p = next((x for x in (await st.people(grp) if grp else []) if x["id"] == t["member"]), None)
        m = {**p, "person_id": p["id"]} if p else None
        company = company or ((await st.company(t["owner"])) or {}).get("name")
    if not m:
        raise VaultRefused("not_on_list", "You're no longer on this company's list — nothing to fill in.")
    return {**m, "company": company, "destination": (mv or {}).get("destination")}


async def page(token: str) -> Dict[str, Any]:
    """What the member's page shows: who it's for and the MASKS of what's saved (never a value)."""
    t = _who(token)
    m = await _member(t)
    return {"name": m["name"], "company": m.get("company"), "destination": m.get("destination"),
            "saved": [{"type": i["type"], "masked": i["masked"], "item_id": i["item_id"]} for i in await _items(_owner(m))]}


REQUIRED_PASSPORT = ("number", "country", "expires_on", "name", "born_on")   # what an airline needs (the Keep keeps the last two optional)


async def save(token: str, passport: Optional[dict] = None, loyalty: Optional[List[dict]] = None) -> Dict[str, Any]:
    """The member's numbers → THEIR Keep (encrypted, never logged, never to the model) → masks back. Nothing else is written."""
    from agapi import s2_keep as KEEP
    t = _who(token)
    m = await _member(t)
    saved = []
    try:
        if passport:
            missing = [f for f in REQUIRED_PASSPORT if not str(passport.get(f) or "").strip()]
            if missing:
                raise VaultRefused("required", "The airline needs: " + ", ".join(f.replace("_", " ").replace("born on", "date of birth")
                                                                                  .replace("name", "name as on the passport") for f in missing) + ".")
            saved.append(await KEEP.put(_owner(m), "passport", {k: str(passport[k]) for k in REQUIRED_PASSPORT}))
        for l in loyalty or []:
            if str(l.get("number") or "").strip():
                saved.append(await KEEP.put(_owner(m), "loyalty", {"program": str(l.get("program") or ""), "number": str(l["number"])}))
    except KEEP.KeepError as e:
        raise VaultRefused(e.rule if hasattr(e, "rule") else "refused", getattr(e, "message", str(e))) from None
    passport = loyalty = None   # the values are not kept past this line
    log.info("[vault] %d saved for a member", len(saved))   # a count only — never a value, never a mask
    return {"saved": [{"type": s["type"], "masked": s["masked"]} for s in saved]}


async def erase(token: str, item_id: Optional[str] = None) -> Dict[str, Any]:
    """Delete one item, or the member's whole vault (their key destroyed: every value shredded)."""
    from agapi import s2_keep as KEEP
    m = await _member(_who(token))
    return await KEEP.delete(_owner(m), item_id)


# ── the organiser's invite ────────────────────────────────────────────────────────────────────────────────────────────────

SEND = None   # tests replace it: (msg) → {"sent": bool}


async def person_link(owner: str, person_id: str) -> Optional[str]:
    """Sasha 351 · a roster person's own vault page (People → their documents) — their link, with no trip needed."""
    from . import groups as G
    grp = await G.store().company(owner)
    if not grp or not any(p["id"] == person_id for p in await G.store().people(grp["id"])):
        return None
    return link(make_token(person_id, owner, ""))


async def invite(owner: str, who: Optional[List[str]] = None, movement_id: Optional[str] = None) -> Dict[str, Any]:
    """A signed, single-person, expiring link per member (one, several by id or name, or all) → emailed where the list has their email;
    the rest handed to the organiser to forward. The link carries no number, and nothing is ever collected in chat."""
    from . import groups as G
    mv = await G.store().movement(owner, movement_id)
    if not mv:
        return {"why": "there's no group movement yet"}
    members = await G.store().members(mv["id"])
    if who:
        want = {w.strip().lower() for w in who}
        members = [m for m in members if m["id"] in who or m.get("person_id") in who or m["name"].lower() in want]
    emailed, forward = [], []
    for m in members:
        url = link(make_token(_owner(m), owner, mv["id"]))   # Sasha 351 · the PERSON's page (one vault, every trip)
        if m.get("email"):
            msg = {"from": os.getenv("SASHA_EMAIL_FROM", "").strip(), "to": m["email"],
                   "subject": f"{mv.get('company')}: add your passport for the trip to {mv.get('destination')}",
                   "text": f"Hi {m['name'].split()[0]},\n\n{mv.get('company')} is booking your travel to {mv.get('destination')}. The airline "
                           f"needs your passport details. Add them on your own secure page (only you can open it; the link expires in 7 days):\n\n"
                           f"{url}\n\nYour numbers are encrypted and never shown to anyone — the organiser only sees that they're there. "
                           f"You can delete them from the same page at any time.\n\n— Sasha"}
            try:
                if SEND is not None:
                    r = await SEND(msg)
                else:
                    from . import live_events as LE
                    r = await LE.send_email(msg)
            except Exception as e:
                r = {"sent": False, "why": type(e).__name__}
            (emailed if r.get("sent") else forward).append({"name": m["name"], **({} if r.get("sent") else {"link": url})})
        else:
            forward.append({"name": m["name"], "link": url})
    return {"emailed": [e["name"] for e in emailed], "forward": forward, "movement_id": mv["id"]}


DELETE_WORDS = re.compile(r"\b(?:delete|remove|erase|forget|borra|elimina)\b.{0,30}\b(?:passport|pasaporte|vault|numbers|data|datos)\b", re.I)


async def delete_by_phone(number_e164: str, text: str) -> Optional[str]:
    """ "delete my passport" from a member's own WhatsApp (the webhook's verified sender) → their whole vault deleted → one line. None when
    the words aren't that, or the number is no member's."""
    if not DELETE_WORDS.search(text or ""):
        return None
    from . import groups as G
    from agapi import s2_keep as KEEP
    ms = await G.store().members_by_phone(number_e164)
    if not ms:
        return None
    n = 0
    for m in ms:
        n += (await KEEP.delete(_owner(m))).get("deleted", 0)
    return "Done — your passport and travel numbers are deleted. Nothing of them is kept." if n else \
        "There's nothing saved for you — nothing to delete."


__all__ = ["make_token", "read_token", "link", "invite", "page", "save", "erase", "has_passport", "vault_view", "delete_by_phone",
           "VaultRefused", "LIFE_S"]
