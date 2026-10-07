"""CR 17 · EspañaMe = access to Spain's PUBLIC processes (the founder's design, 4 Oct 2026). Six areas, each said the same
way — what you need · the official route · what Sasha prepares · you press — and each labelled: only Salud is LIVE; the
rest are CONCEPTS (designed, not built). Every "need" and every route comes from an official page READ at source, with
its date; an area whose page couldn't be read says so and gives no route. Nothing is composed from memory.

  Salud — sources.py (CR 4: SERMAS, the tarjeta sanitaria, the INSS) · Padrón — sources.py (madrid.es, CR 4)
  Identity and access · Social security and tax · DGT · Education — espana_sources.json (read 4 Oct 2026)

Phone, internet, electricity and a bank account are NOT here: they are RelocateMe's "setting up your home" (CR 17).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from . import sources as SRC

_READ = json.loads(Path(__file__).with_name("espana_sources.json").read_text()) \
    if Path(__file__).with_name("espana_sources.json").exists() else {"read_on": None, "topics": {}}

# what Sasha would PREPARE and what YOU press — the product's own design (the same line as S-77: we prepare, you press)
PREPARE = {
    "padron": ("the list of what to bring, in order, and its own appointment page", "booking the appointment and going in person"),
    "identity": ("what each route asks of you and the official page to start from", "registering and signing in yourself — I never hold your Cl@ve or your certificate"),
    "social": ("what to bring and the official page for your number, and the tax basics in order", "the request, signed in or in person"),
    "dgt": ("whether your licence can be exchanged, what to bring, and the official route", "the appointment and the exchange"),
    "education": ("the official calendar and what the application asks for", "the application itself"),
}
SALUD_PREPARE = ("everything for your appointment — the official page, the details to copy — and, for a private clinic, the "
                 "call itself after your one yes; new in Madrid, the steps in order with reminders",
                 "signing in and pressing on the public service's own page; I never sign in or book there for you")


def _topic(key: str) -> Optional[dict]:
    return (_READ.get("topics") or {}).get(key)


def areas() -> List[Dict]:
    """The six areas, each with its label and its four parts — the WhatsApp/web cards and the tab read this."""
    out = [{
        "key": "salud", "name": "Salud — health card, family doctor, SERMAS", "live": True,
        "need": SRC.TARJETA["bring"],
        "route": f"your health card at your health centre or online; appointments on SERMAS's own page",
        "route_url": SRC.TARJETA["page"],
        "prepare": SALUD_PREPARE[0], "press": SALUD_PREPARE[1],
        "source": f"{SRC.TARJETA['name']}; {SRC.SERMAS['name']}; {SRC.INSS['name']} — read {SRC.READ_ON}",
        "read": True,
    }, {
        "key": "padron", "name": "Padrón — registering at the town hall", "live": False,
        "need": SRC.PADRON["bring"], "route": "an appointment at the town hall, booked on its own page",
        "route_url": SRC.PADRON["appointment_url"], "prepare": PREPARE["padron"][0], "press": PREPARE["padron"][1],
        "source": f"{SRC.PADRON['name']} — read {SRC.READ_ON}", "read": True,
    }]
    for key, name, topics in (("identity", "Identity and access — Cl@ve, your digital certificate", ("B", "C")),
                              ("social", "Social security and tax — your social-security number, Agencia Tributaria basics", ("D", "E")),
                              ("dgt", "DGT — exchanging a foreign driving licence", ("F",)),
                              ("education", "Education — a school place", ("G",))):
        parts = [t for t in (_topic(k) for k in topics) if t]
        read = [t for t in parts if t.get("read")]
        out.append({
            "key": key, "name": name, "live": False,
            "need": [n for t in read for n in (t.get("need") or [])][:6],
            "route": " · ".join(f"{t.get('name')}: {t.get('route')}" for t in read if t.get("route")) or None,
            "route_url": next((t.get("route_url") or t.get("page") for t in read), None),
            "links": [{"name": t.get("name"), "url": t.get("route_url") or t.get("page")} for t in read],
            "prepare": PREPARE[key][0], "press": PREPARE[key][1],
            "source": "; ".join(f"{t.get('name')} ({t.get('host')}) — read {_READ.get('read_on')}" for t in read) or None,
            "unread": [f"{t.get('name')}: {t.get('why_not') or 'not read'}" for t in parts if not t.get("read")],
            "read": bool(read),
        })
    return out


def short(a: Dict) -> str:
    """CR 52 · an area in two lines: what it is and whether it's live; the rest (what you need, the route, the source) is
    its card, behind "What you need"."""
    head = f"{'🟢' if a['live'] else '○'} *{a['name']}* — {'LIVE' if a['live'] else 'CONCEPT, not built yet'}"
    if not a.get("read"):
        return f"{head}\nIts official page hasn't been read yet, so nothing here from memory."
    return f"{head}\n*I {'prepare' if a['live'] else 'would prepare'}:* {a['prepare']}; *you press:* {a['press']}."


def card(a: Dict) -> str:
    """One area as a WhatsApp/web message. A concept says so first; an unread page gives no route and says why."""
    head = f"{'🟢' if a['live'] else '○'} *{a['name']}* — {'LIVE' if a['live'] else 'CONCEPT, not built yet'}"
    if not a.get("read"):
        why = "; ".join(a.get("unread") or []) or "its official page hasn't been read yet"
        return f"{head}\nI haven't read its official page yet ({why}), so no list and no route here — nothing from memory."
    lines = [head]
    if a.get("need"):
        lines.append("*What you need* (from the official page" + ("s" if len(a.get("links") or []) > 1 else "") + "): " + "; ".join(a["need"]))
    if a.get("route"):
        lines.append(f"*The official route:* {a['route']}" + (f"\n{a['route_url']}" if a.get("route_url") else ""))
    lines.append(f"*What I {'prepare' if a['live'] else 'would prepare'}:* {a['prepare']}.")
    lines.append(f"*You press:* {a['press']}.")
    if a.get("unread"):
        lines.append("Not read yet: " + "; ".join(a["unread"]) + ".")
    lines.append(f"Source: {a['source']}.")
    return "\n".join(lines)
