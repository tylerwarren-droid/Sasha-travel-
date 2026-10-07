"""CR 4 · the health conversation on WhatsApp. See __init__.py for the line it keeps (S-77). The model is never called."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from booking_signer import yes as YS

from .. import store as ST
from . import sources as SRC

log = logging.getLogger("products.health")
MADRID = ZoneInfo("Europe/Madrid")
APPROVAL_WINDOW = timedelta(minutes=15)
VALUES_TTL = timedelta(hours=24)
TEST_CLINIC = "Kanoe Test Clinic"
VAULT_PROVIDER = "sanidadmadrid.org"          # the vault names a provider by its address
VAULT_LABEL = "Tarjeta sanitaria (Madrid)"

CONSENT = {"v1": ("Health details are sensitive. For this I use only what the appointment needs — never why you need a "
                  "doctor — and I keep it at most 30 days. I never sign in, book or press on a public health website for "
                  "you. Is that OK?")}
CONSENT_CURRENT = "v1"
CHOOSE = ("What would help?\n1. *A private clinic* — I call them and book for you.\n2. *The public health service "
          "(SERMAS)* — I prepare everything; you book on its own page.\n3. *Your health card* — new, renewed, replaced "
          "or updated: send your DNI or passport and I fill the Comunidad de Madrid's official form for you to sign "
          "and take in.")
# CR 30 · the new-arrivals checklist belongs to RelocateMe (EspañaMe scope, row 10): off this menu; its old button
# (hx:new) and "new in Madrid" in words still reach it until RelocateMe's "setting up your home" carries it
CHOOSE_BUTTONS = [("1. Private clinic", "hx:priv"), ("2. Public (SERMAS)", "hx:pub"), ("3. Health card", "hx:tsi")]
FICTIONAL = {"card": "EJEMPLO-0000-0000", "birth": "1985-03-14", "dni_nie": "X0000000T", "name": "Lucía Ejemplo (fictional)"}


# CR 15 · "españa" — EspañaMe: Spain's public services. Health is the working demo; the rest are CONCEPTS, labelled so.
# CR 17 · EspañaMe = access to Spain's PUBLIC processes: six areas, only Salud live (health/espana.py holds each card)
ES_MENU = ("EspañaMe 🇪🇸 — Spain's public processes, done with you.\n"      # CR 52 · three lines; numbers as before
           "1. *Salud* — your health card and family doctor (live)\n"
           "Concepts: 2. *Padrón* · 3. *Identity and access* · 4. *Social security and tax* · 5. *DGT* · 6. *Education*")
ES_BUTTONS = [("1. Salud (live)", "hx:es:salud"), ("2. Padrón", "hx:es:padron"), ("3. Identity & access", "hx:es:identity")]
ES_KEYS = {"1": "salud", "2": "padron", "3": "identity", "4": "social", "5": "dgt", "6": "education"}
_ES_WORDS = [("salud", r"salud|health|doctor|m[eé]dico|sermas|tarjeta"), ("padron", r"padr[oó]n|empadron"),
             ("identity", r"cl@?ve|certificad|digital certificate|identity|identidad"),
             ("social", r"social security|seguridad social|tax|hacienda|agencia tributaria|nie|nif"),
             ("dgt", r"dgt|driving|licen[cs]e|carn[eé]t|permiso de conduc"), ("education", r"school|colegio|educaci|escuela")]
MOVED = ("Phone, internet, electricity and a bank account are part of RelocateMe now — “setting up your home” (a concept "
         "there). Say “relocate”.")


def es_pick(t: str, payload: str) -> str:
    if payload.startswith("hx:es:"):
        return payload[6:]
    m = re.match(r"^\s*([1-6])\b", t)
    if m:
        return ES_KEYS[m.group(1)]
    for key, rx in _ES_WORDS:
        if re.search(rf"(?i)\b({rx})", t):
            return key
    return "moved" if re.search(r"(?i)\b(movistar|internet|phone|utilit|electric|bank)", t) else ""



def web() -> str:
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/")


def consent(version: str = CONSENT_CURRENT) -> dict:
    t = CONSENT[version]
    return {"version": version, "sha256": hashlib.sha256(t.encode()).hexdigest()}


def public_health(name: str = "", url: str = "") -> bool:
    """S-77 §6 · Sasha never calls, fills or emails a PUBLIC health centre."""
    t = f"{name} {url}".lower()
    return any(h in t for h in SRC.PUBLIC_HEALTH_HOSTS) or any(w in t for w in SRC.PUBLIC_HEALTH_WORDS)


# ── when ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

_DAYS = {d: i for i, d in enumerate(("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"))}
_DAYS.update({"lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5,
              "domingo": 6})


def parse_when(t: str, now: datetime) -> Optional[datetime]:
    """"Tuesday 10:00", "tomorrow at 9", "martes 10:30" → the next such moment, Madrid time; None if unclear."""
    s = (t or "").lower()
    m = re.search(r"\b(\d{1,2})(?::|\.|h)?(\d{2})?\s*(am|pm)?\b", re.sub(r"\b(20\d\d)\b", "", s))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if m.group(3) == "pm" and h < 12:
        h += 12
    if not (7 <= h <= 21 and mi < 60):
        return None
    local = now.astimezone(MADRID)
    day = None
    if re.search(r"\b(tomorrow|mañana|manana)\b", s):
        day = local.date() + timedelta(days=1)
    elif re.search(r"\b(today|hoy)\b", s):
        day = local.date()
    else:
        for name, wd in _DAYS.items():
            if re.search(rf"\b{name}\b", s):
                day = local.date() + timedelta(days=(wd - local.weekday()) % 7 or 7)
                break
    if day is None:
        return None
    at = datetime(day.year, day.month, day.day, h, mi, tzinfo=MADRID)
    return at if at > local + timedelta(minutes=30) else None


# ── the turn ─────────────────────────────────────────────────────────────────────────────────────────────────────────

async def turn(ctx: dict, body: str, payload: str, *, entering: bool) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    step = pend.get("step")
    t = (body or "").strip()
    if step not in ("ci_pick", "ci_street", "ts_ask") and not payload:    # CR 35 · "find my centre", again, any time
        from . import cita as CI
        if CI.AGAIN.search(t):
            if await CI.resume(ctx):
                return
            out.text("I don't have a health-card form from you in the last 24 hours, so there's no address to look up. "
                     "Choose 1 · Salud → 3 · Your health card: I fill the form from your DNI, then find your centre.")
            return
    from .. import steps as STP0
    if STP0.is_more(payload or "", "hx:"):                     # CR 52 · a step's details, by its own button
        STP0.show(pend, STP0.is_more(payload, "hx:"), out)
        return
    if payload == "hx:es:menu":
        pend["step"] = "es_menu"
        out.ask(ES_MENU, ES_BUTTONS)
        return
    if entering and not step and ctx.get("espana"):            # CR 15 · "españa": the menu first
        pend["step"] = "es_menu"
        out.ask(ES_MENU, ES_BUTTONS)
        return
    if step == "es_menu" or payload.startswith("hx:es:"):
        from . import espana as ES
        pick = es_pick(t, payload)
        cards = {a["key"]: a for a in ES.areas()}
        from .. import steps as STP                   # CR 52 · the area in a line; what you need + the official page behind a tap
        if pick == "salud":
            STP.stash(pend, "area", [ES.card(cards["salud"])])
            pend["step"] = "consent"                 # the live demo: consent first, as always (its words unchanged)
            out.ask("🟢 *Salud* — your health card and family doctor.\n" + CONSENT[CONSENT_CURRENT],
                    [("Yes, continue", "hx:consent:yes"), ("No", "hx:consent:no"), STP.more("hx:", "area", "What you need")])
        elif pick in cards:
            STP.stash(pend, "area", [ES.card(cards[pick])])
            out.ask(ES.short(cards[pick]) + "\nAnother area? Reply 1–6.",
                    [STP.more("hx:", "area", "What you need"), ("1. Salud (live)", "hx:es:salud"), ("Back to the list", "hx:es:menu")])
            pend["step"] = "es_menu"
        elif pick in ("moved", "movistar"):            # an old button, or the words: they live in RelocateMe now
            out.text(MOVED)
            out.ask(ES_MENU, ES_BUTTONS)
            pend["step"] = "es_menu"
        else:
            out.ask(ES_MENU, ES_BUTTONS)
        return
    if entering and not step:
        pend["step"] = "consent"
        out.ask(CONSENT[CONSENT_CURRENT], [("Yes, continue", "hx:consent:yes"), ("No", "hx:consent:no")])
        return
    if step == "consent":
        if payload == "hx:consent:yes" or (not payload and YS.is_yes(t)):
            c = consent()
            pend.update(step="choose", consent={**c, "at": ctx["now"].isoformat()})
            out.ask(CHOOSE, CHOOSE_BUTTONS)
        else:
            pend["step"] = None
            out.text("OK — nothing kept.")
        return
    if step == "choose" or payload in ("hx:priv", "hx:pub", "hx:new", "hx:tsi"):
        pick = payload or {"1": "hx:priv", "2": "hx:pub", "3": "hx:tsi", "4": "hx:tsi"}.get(t[:1], "")
        if not pick and re.search(r"(?i)health card|card form|tarjeta|\bdni\b|passport|pasaporte|1449", t):
            pick = "hx:tsi"
        if not pick and re.search(r"(?i)\bprivate|privad", t):
            pick = "hx:priv"
        if not pick and re.search(r"(?i)\bpublic|sermas|p[uú]blic", t):
            pick = "hx:pub"
        if not pick and re.search(r"(?i)new in madrid|just (arrived|moved)|reci[eé]n llegad", t):
            pick = "hx:new"
        if pick == "hx:priv":
            pend["step"] = "when"
            out.text("Which day and time suits you this week? (e.g. \"Tuesday 10:00\") — I'll ask the clinic for exactly "
                     "that, for one person.")
        elif pick == "hx:pub":
            await _public(ctx, t)
        elif pick == "hx:new":
            await _new(ctx)
        elif pick == "hx:tsi":
            from . import tarjeta as TS
            await TS.start(ctx)
        else:
            out.ask(CHOOSE, CHOOSE_BUTTONS)
        return
    if step in ("ci_offer", "ci_pick", "ci_street", "ci_route", "ci_when", "ci_call_when", "ci_call_confirm", "ci_booked"):
        from . import cita as CI                                   # CR 34 · form → cita; CR 35 · pick / type the street
        if step == "ci_offer":
            await CI.on_offer(ctx, t, payload)
        elif step == "ci_pick":
            await CI.on_pick(ctx, t, payload)
        elif step == "ci_street":
            await CI.on_street(ctx, t)
        elif step == "ci_route":
            await CI.on_route(ctx, t, payload)
        elif step == "ci_call_when":
            await CI.call_prepare(ctx, t)
        elif step == "ci_call_confirm":
            await CI.call_yes(ctx, t, payload)
        else:
            await CI.on_when(ctx, t)
        return
    if step in ("ts_doc", "ts_back", "ts_confirm", "ts_ask"):     # CR 30 · the health-card form (tarjeta.py)
        from . import tarjeta as TS
        if step in ("ts_doc", "ts_back"):
            if not await TS.on_doc(ctx, t, payload):
                ctx["out"].text("Send a photo of your DNI (front, then back) or your passport's photo page — or type DEMO.")
        elif step == "ts_confirm":
            await TS.on_confirm(ctx, t, payload)
        else:
            await TS.on_answer(ctx, t, payload)
        return
    if step == "when":
        at = parse_when(t, ctx["now"])
        if not at:
            out.text("A day and a time from now on, please — e.g. \"Tuesday 10:00\" or \"tomorrow at 9\".")
            return
        await _private_prepare(ctx, at)
        return
    if step == "call_confirm":
        await _private_yes(ctx, t, payload)
        return
    if step == "pub_vault_confirm":
        await _public_vault_yes(ctx, t, payload)
        return
    if step == "padron_date":
        await _new_reminders(ctx, t)
        return
    if step in ("pub_offer", "sermas_wait") and _BOOKED.search(t) and _when_booked(t, ctx):
        await _sermas_offer(ctx, t)
        return
    if step == "sermas_add":
        await _sermas_add(ctx, t, payload)
        return
    if re.fullmatch(r"(?i)demo", t) and step == "pub_offer":
        await _public_handover(ctx, dict(FICTIONAL), "a fictional demo patient (not a real person)", fictional=True)
        return
    return False   # CR 10 · not health's: Sasha answers it


# ── (a) a private clinic, by phone, through Sasha's own call path ──────────────────────────────────────────────────

def test_clinic_number() -> Optional[str]:
    n = os.getenv("SASHA_TEST_CALL_NUMBER", "").strip()
    return n or None


async def _clinic_read(account: str) -> Optional[str]:
    """The stand-in clinic as a venue read whose phone is the Sasha TEST LINE — the founder's own phone (calls.py)."""
    number = test_clinic_number()
    if not number:
        return None
    from booking_signer import ladder_routes as LR
    rid = str(uuid.uuid4())
    read = {"name": TEST_CLINIC, "country": "ES", "listing": {"name": TEST_CLINIC},
            "facts": [{"kind": "phone", "value": number, "source_kind": "site",
                       "source_label": "the Sasha test line (the founder's own phone), standing in for a private clinic"}]}
    await LR.LADDER_STORE.put_read({"read_id": rid, "account_id": account, "query": "CR 4 test clinic", "venue_name": TEST_CLINIC,
                                    "country": "ES", "read": read, "created_at": datetime.now(MADRID)})
    return rid


async def _private_prepare(ctx: dict, at: datetime) -> None:
    from booking_signer import guest_whatsapp as GW
    pend, out, account = ctx["st"]["pending"], ctx["out"], ctx["account"]
    if public_health(TEST_CLINIC):
        out.text("That's a public health centre — I never call one for a patient. Option 2 prepares it for you to book.")
        return
    status, contact = await GW.api(account, "GET", "/api/booking/contact")
    c = (contact or {}).get("contact") or {}
    if not c.get("name") or not c.get("mobile_e164"):
        out.text(GW.NO_CONTACT.format(web=GW.web_url()))
        return
    read_id = await _clinic_read(account)
    if not read_id:
        out.text("The demo's stand-in clinic has no phone number set on this server (SASHA_TEST_CALL_NUMBER), so there is "
                 "nothing to call. Nothing was dialled.")
        return
    reservation = {"schema": "reservation/1", "flow": "book",
                   "who": {"name": c["name"], "contact": {"mobile_e164": c["mobile_e164"]}},
                   "what": {"category": "appointment", "activity": "a GP appointment",
                            "activity_venue_lang": "una cita con el médico general"},
                   "where": {}, "when": {"mode": "at", "at": at.strftime("%Y-%m-%dT%H:%M")},
                   "how_many": {"count": 1, "unit": "people"}}
    status, j = await GW.api(account, "POST", "/api/booking/calls", {"reservation": reservation, "read_id": read_id})
    if status != 200:
        out.text(f"Not prepared — {GW.refusal_words(j, status)}. Nothing was dialled.")
        pend["step"] = "when"
        return
    lines, sha = j["read_back"]["lines"], j["read_back"]["sha256"]
    out.text("Exactly what I'll say:\n" + "\n".join("• " + ln for ln in lines))
    out.ask(f"Call {TEST_CLINIC} now?", [("Yes, call them", f"hxyes:{sha[:16]}"), ("No", f"hxno:{sha[:16]}")])
    pend.update(step="call_confirm", call_id=j["call_id"], sha=sha, asked_at=ctx["now"].isoformat(),
                summary=f"GP appointment, {at.strftime('%A %-d %B at %H:%M')}")


async def _private_yes(ctx: dict, t: str, payload: str) -> None:
    from booking_signer import guest_whatsapp as GW
    pend, out, account = ctx["st"]["pending"], ctx["out"], ctx["account"]
    sha = pend.get("sha") or ""
    if payload == f"hxno:{sha[:16]}" or (not payload and re.match(r"(?i)^\s*no\b", t)):
        pend["step"] = "when"
        out.text("OK — not called. Another day or time?")
        return
    yes = payload == f"hxyes:{sha[:16]}" or (not payload and YS.is_yes(t))
    if not yes:
        out.text("Yes or no?" if not payload else "That button belonged to an earlier question — nothing was dialled.")
        return
    if ctx["now"] - datetime.fromisoformat(pend["asked_at"]) > APPROVAL_WINDOW:
        pend["step"] = "when"
        out.text("That yes came more than 15 minutes later — nothing was dialled. Which day and time?")
        return
    how = {"how": "whatsapp_button" if payload else "whatsapp_text", "said": t or "Yes, call them"}
    status, j = await GW.api(account, "POST", f"/api/booking/calls/{pend['call_id']}/place",
                             {"read_back_sha256": sha, "approval": how}, timeout=120)
    if status != 200:
        out.text(f"Not called — {GW.refusal_words(j, status)}. Nothing was dialled.")
        pend["step"] = "done"
        return
    if j.get("status") == "placed":
        out.text(f"📞 {j.get('say') or 'Calling ' + TEST_CLINIC + ' now.'} I'll tell you what they say.")
        GW._spawn(GW.watch_call(ctx["ch"], ctx["frm"], account, pend["call_id"], TEST_CLINIC, "book", pend.get("summary", "")))
    elif j.get("status") == "scheduled":
        out.text(f"They're closed now — I'll call at {j.get('scheduled_for')}, covered by your yes.")
    else:
        out.text(f"⚠ {j.get('say') or 'The call did not go through'} — nothing is booked.")
    pend["step"] = "done"


# ── (b) the public service (SERMAS): a hand-over; the person presses ──────────────────────────────────────────────

async def _vault_card(account: str) -> Optional[dict]:
    try:
        from booking_signer.vault import crypto as VC
        rows = await VC.STORE.list(account)
    except Exception:
        return None
    return next((r for r in rows if not r.get("revoked_at") and r.get("kind") == "identifier"
                 and str(r.get("provider") or "").lower() == VAULT_PROVIDER and r.get("special_category")), None)


async def _public(ctx: dict, t: str) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    if re.search(r"(?i)\bdemo\b", t):
        await _public_handover(ctx, dict(FICTIONAL), "a fictional demo patient (not a real person)", fictional=True)
        return
    item = await _vault_card(ctx["account"])
    if item:
        from booking_signer.vault.crypto import access_line
        lines = [access_line(VAULT_PROVIDER, item["label"], "identifier"),
                 "I'll put your card code, date of birth and DNI/NIE on a private page, ready to copy, for 24 hours.",
                 f"You book on SERMAS's own page ({SRC.SERMAS['primary_care_url']}) and press yourself; I don't.",
                 "Ref HX-" + hashlib.sha256(f"{ctx['account']}|{ctx['now'].isoformat()}".encode()).hexdigest()[:6].upper() + "."]
        sha = hashlib.sha256("\n".join(lines).encode()).hexdigest()
        out.text("Exactly what I'll do:\n" + "\n".join("• " + ln for ln in lines))
        out.ask("Open it once from your vault?", [("Yes", f"hxv:{sha[:16]}"), ("No", f"hxvno:{sha[:16]}")])
        pend.update(step="pub_vault_confirm", lines=lines, sha=sha, item=str(item["id"]), asked_at=ctx["now"].isoformat())
        return
    from booking_signer.vault import api as VA
    if not VA.dpia_ref():
        out.text("I don't keep health card details yet — that needs Kanoe's data-protection assessment first — so I won't "
                 "ask for them. Your page lists exactly what to have ready. (Type DEMO to see it with a fictional patient.)")
    else:
        out.text("To have your card details ready to copy, add them in You → My accounts (health items need your explicit "
                 "consent there), then ask me again. For now your page lists what to have ready.")
    await _public_handover(ctx, None, None, fictional=False)
    if ctx["st"]["pending"].get("step") == "sermas_wait":
        ctx["st"]["pending"]["step"] = "pub_offer"                 # DEMO still answers after the page


async def _public_vault_yes(ctx: dict, t: str, payload: str) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    sha = pend.get("sha") or ""
    yes = payload == f"hxv:{sha[:16]}" or (not payload and YS.is_yes(t))
    if not yes or ctx["now"] - datetime.fromisoformat(pend["asked_at"]) > APPROVAL_WINDOW:
        pend["step"] = "pub_offer"
        out.text("OK — not opened. Your page lists what to have ready, without values.")
        await _public_handover(ctx, None, None, fictional=False)
        return
    from booking_signer.vault import crypto as VC
    approval = {"read_back_sha256": sha, "at": ctx["now"].isoformat()}
    try:
        async with VC.use(ctx["account"], pend["item"], approval=approval, approved_lines=pend["lines"],
                          action_kind="health_handover", action_ref=f"health-{sha[:12]}") as secret:
            raw = secret.get("value") or ""
            values = json.loads(raw) if raw.strip().startswith("{") else {"card": raw.strip()}   # saved in "You": the code alone
    except Exception as e:
        out.text(f"❌ Your saved card details couldn't be opened ({e}). Nothing was shown.")
        return
    await _public_handover(ctx, values, "your vault (opened once, under your yes)", fictional=False)


async def _public_handover(ctx: dict, values: Optional[dict], source: Optional[str], *, fictional: bool) -> None:
    pend, out, now = ctx["st"]["pending"], ctx["out"], ctx["now"]
    keep = {k: values.get(k) for k in ("card", "birth", "dni_nie") if values and values.get(k)} if values else None
    state = {"kind": "sermas", "appointment_type": "Atención Primaria — medicina de familia (your family doctor)",
             "values": keep, "values_source": source, "values_expire_at": (now + VALUES_TTL).isoformat() if keep else None,
             "fictional": fictional, "consent": pend.get("consent"), "status": "handed_over"}
    try:
        cid = await ST.STORE.put("health", ctx["account"], ctx["ch"]["wa_id_sha256"], state)
    except Exception as e:   # 029 not applied: the product_cases check doesn't know "health" yet
        log.error("[health] case not kept: %s", type(e).__name__)
        out.text("Health isn't switched on on this server yet (its storage isn't ready). Nothing was kept.")
        return
    pend.update(step="sermas_wait", case_id=cid)
    link = f"{web()}/health-handover/{cid}"
    out.text(f"Your SERMAS appointment, prepared — the official page, what it asks for{' (ready to copy)' if keep else ''}, "
             f"and the appointment type:\n{link}")
    if ctx["frm"] == "web":                    # CR 34 · from the laptop, the page goes to the phone: the citizen books there
        from . import cita as CI
        sent = await CI._to_phone(ctx, f"📲 Your SERMAS appointment, ready — open SERMAS's own page from here and book it "
                                       f"yourself:\n{link}")
        out.text("I've sent it to your phone too." if sent else "(Your phone isn't linked, so open it from here.)")
    out.text("You open SERMAS's own page and press. I never sign in, book or press on a public health website — and I "
             "never look for free slots for you. Once you've booked, tell me the day and time if you'd like it in your itinerary.")


# ── CR 10 · the SERMAS appointment the person booked, into their itinerary — only on an explicit yes ─────────────────

_BOOKED = re.compile(r"(?i)\b(booked|reserv|cita|appointment|tengo)\b")


def _when_booked(t: str, ctx: dict):
    from .. import itinerary as IT
    return IT.parse_day_time(t, ctx["now"].astimezone(MADRID).date())


async def _sermas_offer(ctx: dict, t: str) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    on, at = _when_booked(t, ctx)
    pend.update(step="sermas_add", sermas_on=on.isoformat(), sermas_at=at)
    out.ask(f"Add “doctor's appointment (SERMAS), {on.strftime('%A %-d %B')} at {at}” to your itinerary? It's then kept "
            "with your bookings like any other — not just 30 days — and I'll remind you the day before. Only the day and "
            "time: never why.", [("Yes, add it", "hx:sermas:yes"), ("No", "hx:sermas:no")])


async def _sermas_add(ctx: dict, t: str, payload: str) -> None:
    from .. import itinerary as IT
    pend, out = ctx["st"]["pending"], ctx["out"]
    if payload == "hx:sermas:yes" or (not payload and YS.is_yes(t)):
        item = await IT.guest_booked(ctx["account"], type_="doctor", provider_name=IT.SERMAS,
                                     on=date.fromisoformat(pend["sermas_on"]), at=pend["sermas_at"], tz="Europe/Madrid")
        on = date.fromisoformat(pend["sermas_on"])
        from . import cita as CI                 # CR 34 · and the calendar: only the day and time, never why
        link = CI.gcal("Cita médica (SERMAS)", on, pend["sermas_at"], "", "Booked by you on SERMAS's own page.")
        out.text(("Added to your itinerary — booked by you. I'll remind you the day before." if item else
                  "I couldn't add it to your itinerary just now — nothing was kept.") + f"\n📅 Add it to your calendar: {link}")
    else:
        out.text("OK — not added. Nothing was kept.")
    for k in ("sermas_on", "sermas_at"):
        pend.pop(k, None)
    pend["step"] = "done"


# ── (c) new in Madrid: the sourced checklist, then reminders ──────────────────────────────────────────────────────

def checklist() -> List[dict]:
    return [
        {"step": "1. Register on the padrón (empadronamiento)", "do": "Ask for an appointment in the city's own system; bring "
         + "; ".join(SRC.PADRON["bring"]) + ". " + "; ".join(SRC.PADRON["rules"]).capitalize() + ".",
         "link": SRC.PADRON["appointment_url"], "source": SRC.PADRON["name"], "how": SRC.PADRON["how"],
         "note": "Then ask for the volante de empadronamiento — the card needs one issued in the last 90 days."},
        {"step": "2. Your right to public healthcare (INSS)", "do": f"Entitled: {SRC.INSS['who']}. Ask the INSS for "
         f"{SRC.INSS['document']}.", "link": SRC.INSS["request_url"], "link_words": SRC.INSS["request_words"],
         "source": SRC.INSS["name"], "how": SRC.INSS["how"]},
        {"step": "3. Your tarjeta sanitaria", "do": f"Ask {SRC.TARJETA['where']}, bringing: " + "; ".join(SRC.TARJETA["bring"])
         + ". " + SRC.TARJETA["delivery"].capitalize() + ".", "link": SRC.TARJETA["online_url"], "source": SRC.TARJETA["name"],
         "how": SRC.TARJETA["how"]},
        {"step": "4. Your family doctor", "do": "Your doctor is at the health centre where you collect your card. To book, "
         "SERMAS asks for " + ", ".join(SRC.SERMAS["needs"]) + " — then option 2 here prepares it for you.",
         "link": SRC.SERMAS["page"], "source": SRC.SERMAS["name"], "how": SRC.SERMAS["how"]},
    ]


async def _new(ctx: dict) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    state = {"kind": "new_in_madrid", "checklist": checklist(), "consent": pend.get("consent"), "status": "checklist"}
    try:
        cid = await ST.STORE.put("health", ctx["account"], ctx["ch"]["wa_id_sha256"], state)
    except Exception as e:
        log.error("[health] case not kept: %s", type(e).__name__)
        out.text("Health isn't switched on on this server yet (its storage isn't ready). Nothing was kept.")
        return
    out.text("New in Madrid — four steps, in order, each from the official page:\n"
             "1. Padrón (town hall) → 2. INSS: your right to healthcare → 3. Tarjeta sanitaria → 4. Your family doctor.\n"
             f"Every step, with what to bring and the official link:\n{web()}/health-handover/{cid}\n"
             "I never hunt for padrón appointments — they're scarce, and automated searching takes them from other people.")
    out.text("When did you register on the padrón — or when is your appointment? (a date, e.g. 20 October 2026 — or SKIP)")
    pend.update(step="padron_date", case_id=cid)


async def _new_reminders(ctx: dict, t: str) -> None:
    from ..relocation import facts as F
    pend, out, now = ctx["st"]["pending"], ctx["out"], ctx["now"]
    if re.match(r"(?i)^\s*skip\b", t):
        pend["step"] = "done"
        out.text("OK — no reminders. Everything is on your page.")
        return
    d = F.parse_date(t)
    if not d:
        out.text("A date please, like 20 October 2026 — or SKIP.")
        return
    p = date.fromisoformat(d)
    rs = [(p + timedelta(days=1), "Padrón done? Ask for your volante de empadronamiento, then request your INSS document "
                                  "(the DAD) — the link is on your page."),
          (p + timedelta(days=60), "Your volante de empadronamiento must be under 90 days old when you ask for your health "
                                   f"card — ask before {(p + timedelta(days=90)).strftime('%-d %B')}.")]
    reminders = [{"on": x.isoformat(), "text": s, "sent": False} for x, s in sorted(rs) if x >= now.date()]
    case = await ST.STORE.get(pend.get("case_id") or "")
    if case:
        st = case["state"]
        st.update(padron_date=d, reminders=reminders, wa=ctx["ch"]["wa_id_sha256"], number_from=ctx["frm"])
        await ST.STORE.update(case["id"], st)
    pend["step"] = "done"
    lines = "\n".join(f"• {date.fromisoformat(r['on']).strftime('%-d %b %Y')}: {r['text'].split(' — ')[0]}" for r in reminders)
    out.text(f"I'll remind you here:\n{lines or '(both dates have passed — everything is on your page)'}\n(WhatsApp lets me "
             "write first only within 24 hours of your last message; otherwise it waits for your next one.)")


async def due(now: Optional[datetime] = None) -> int:
    """Daily, with the other products' jobs: send each health reminder whose day has come (in-session only)."""
    from booking_signer import guest_whatsapp as GW
    now = now or datetime.now(MADRID)
    sent = 0
    for c in await ST.STORE.of_product("health"):
        st = c["state"]
        changed = False
        if st.get("values") and st.get("values_expire_at") and st["values_expire_at"] <= now.isoformat():
            st["values"], changed = None, True                        # the identifiers go after VALUES_TTL
        if st.get("kind") == "tarjeta" and st.get("rows"):
            from . import tarjeta as TS
            if TS.expired(st, now):
                st["rows"], changed = None, True                      # CR 30 · the form's ID details go after 24 hours
        for r in st.get("reminders") or []:
            if r["sent"] or r["on"] > now.date().isoformat():
                continue
            from .. import whatsapp as PW
            ch, wkey, frm = await PW.reach(st.get("wa", ""), st.get("number_from"), c.get("account_id"))   # CR 20
            gst = await GW.STORE.get_state(wkey) if ch else {}
            res = await GW.deliver(ch, frm, GW.Out().text("🩺 " + r["text"]), gst.get("last_inbound_at")) \
                if ch else ["no channel"]
            if res and all(x == "sent" for x in res):
                r["sent"], changed = True, True
                sent += 1
        if changed:
            await ST.STORE.update(c["id"], st)
    return sent


# ── CR 10 · one Sasha: is this message an answer to health's own question? And what context goes to Sasha ──────────

def claims(pend: dict, body: str, payload: str, media: list) -> bool:
    step, t = pend.get("step"), (body or "").strip()
    if payload.startswith(("hx:", "hxyes:", "hxno:", "hxv:", "hxvno:")):   # incl. hx:sermas:…
        return True
    from . import cita as CI
    if CI.AGAIN.search(t):                                    # CR 35 · "find my centre" is health's, from any step
        return True
    if step in ("ci_offer", "ci_call_confirm"):
        return YS.is_yes(t) or bool(re.match(r"(?i)^\s*(no|not now|later)\b", t))
    if step == "ci_pick":
        return bool(re.match(r"(?i)^\s*([1-3]\b|none\b|no\b)", t))
    if step == "ci_street":
        return bool(re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3}.*\d", t))
    if step == "ci_route":
        return bool(re.search(r"(?i)\bcall|llam|online|web|internet|\bgo\b|myself|walk", t))
    if step in ("ci_when", "ci_booked"):
        from . import cita as CI
        return CI.when(t, datetime.now(MADRID)) is not None
    if step == "ci_call_when":
        return parse_when(t, datetime.now(MADRID)) is not None
    if step in ("ts_doc", "ts_back"):
        return bool(media) or bool(re.fullmatch(r"(?i)\s*demo\s*", t)) or payload.startswith("hx:ts:rx:")
    if step == "ts_confirm":
        return YS.is_yes(t) or bool(re.match(r"(?i)^\s*(no|wrong)\b", t))
    if step == "ts_ask":                     # CR 35 · only an answer to ITS question (a shared account's other product may be asking)
        from . import tarjeta as TS
        import copy
        ts = pend.get("ts") or {}
        k = pend.get("ts_q") or TS.next_question(ts.get("facts") or {})
        return bool(t or payload) and bool(k) and TS.answer(k, t, payload, copy.deepcopy(ts.get("facts") or {})) is None
    if step in ("consent", "call_confirm", "pub_vault_confirm"):
        return YS.is_yes(t) or bool(re.match(r"(?i)^\s*no\b", t))
    if step == "es_menu":
        return bool(es_pick(t, ""))
    if step == "choose":
        return bool(re.match(r"^\s*[1234]\b", t) or re.search(r"(?i)\bprivate|privad|public|sermas|p[uú]blic|new|nuev|tarjeta|health card|\bdni\b|passport", t))
    if step == "when":
        return parse_when(t, datetime.now(MADRID)) is not None
    if step in ("pub_offer", "sermas_wait"):
        from .. import itinerary as IT
        return (step == "pub_offer" and bool(re.fullmatch(r"(?i)demo", t))) or \
            (bool(_BOOKED.search(t)) and IT.parse_day_time(t, datetime.now(MADRID).date()) is not None)
    if step == "sermas_add":
        return YS.is_yes(t) or bool(re.match(r"(?i)^\s*no\b", t))
    if step == "padron_date":
        from ..relocation import facts as F
        return bool(F.parse_date(t)) or bool(re.match(r"(?i)^\s*skip\b", t))
    return False


def context(pend: dict) -> dict:
    """Health hands Sasha only the city — never a reason, a card code or an appointment's purpose."""
    return {"product": "health", "city": "Madrid", "country": "Spain", "dates": [], "name": None,
            "line": "[Health: in Madrid, Spain]"}
