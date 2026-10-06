"""CR 34 · ESPAÑAME — FROM THE FORM TO THE CITA. The founder's rule: Sasha assists ONE citizen to book THEIR OWN appointment; she
is not a bot, never slot-hunts, never resells. The citizen presses.

After the 1449F1 is prepared, "Book the appointment to hand it in?":
  1. the citizen's centro de salud, from their address, on SERMAS's own finder — READ LIVE (three requests: the page, the
     address search, the centre's page; robots.txt answers 404 there, i.e. nothing is disallowed; an honest User-Agent);
  2. its routes, as the official pages give them (read 6 Oct 2026):
     · GO: "Puede solicitar la tarjeta sanitaria en el centro de salud que tenga asignado en horario de atención al público
       (8.30 a 20.30h)" (comunidad.madrid) — the citizen picks a day and time;
     · CALL (phone): the centre's own "Teléfono cita previa" from the finder — on the citizen's yes Sasha calls through her
       call path (AI disclosure in Spanish, first), asks only for a time to hand the form in, agrees to nothing else, reports
       their exact words. ⚖ This crosses S-77 §6's "the phone rung refuses a health centre": the founder's CR 34 decision,
       held to the FOUNDER's own account until counsel signs the change (H-1);
     · ONLINE: the Comunidad's registry-office cita (gestiona.comunidad.madrid/ctac_cita/OFIREG) — sent to the citizen's
       phone with their details ready to copy; it ends with a reCAPTCHA and "Enviar": both the citizen's, in their browser.
       SERMAS's own online cita (citaprevia) needs the card's CIPA — not for a first card.
  3. the result → the itinerary + a calendar link, with what to bring (read from the 1449F1 itself, §6).
Never: a login, Cl@ve, a press, a slot search, a second appointment. Nothing health-related is kept: the address is used for
the one lookup and dropped with the rest after VALUES_TTL.
"""
from __future__ import annotations

import asyncio
import html as H
import logging
import re
import time
import unicodedata
import urllib.parse
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("products.health.cita")

READ_ON = "6 Oct 2026"
FINDER = {"name": "Búsqueda de centros por dirección — Portal de Salud de la Comunidad de Madrid",
          "url": "https://centrossanitarios.sanidadmadrid.org/CentrosDireccion/misCentroPorDireccion.aspx",
          "detail": "https://centrossanitarios.sanidadmadrid.org/RedAsistencial/DetalleAsistenciales.aspx?ID={id}"}
HAND_IN = {"page": "https://www.comunidad.madrid/servicios/salud/tarjeta-sanitaria",
           "words": "Puede solicitar la tarjeta sanitaria en el centro de salud que tenga asignado en horario de atención al "
                    "público (8.30 a 20.30h)."}
OFIREG = {"name": "Cita previa — Oficinas de Registro y Atención al Ciudadano (Comunidad de Madrid)",
          "url": "https://gestiona.comunidad.madrid/ctac_cita/OFIREG",
          "info": "https://www.comunidad.madrid/servicios/informacion-atencion-ciudadano/cita-previa-oficinas-registro-atencion-ciudadano",
          "words": "En la Red de Oficinas se atiende con cita y sin cita según disponibilidad."}
SERMAS_ONLINE_NEEDS_CIPA = "SERMAS's own online cita asks for your card's code (CIPA) — not possible before your first card."
UA = "KanoeEspanaMe/0.1 (+https://project.kanoe.ai; one citizen's own lookup, read-only; tyler@kanoe.ai)"
PACE = 2.0
CACHE_S = 24 * 3600                       # a centre's page (its phone, hours) — re-read after a day


def bring(motive: str) -> List[str]:
    """What to take, read from the 1449F1's own §6 (the Comunidad consults DNI/TIE, padrón and INSS electronically unless
    the citizen objects there)."""
    out = ["the 1449F1, printed and SIGNED by you", "your DNI or TIE, in force (to show)"]
    obj = "only if you ticked an objection box in §6: the documents you objected to its consulting"
    if motive == "NUEVA":
        out.append(obj + " (DNI/TIE copy, volante de empadronamiento under 90 days, the INSS document)")
    elif motive == "DOMICILIO":
        out.append(obj + " (the volante de empadronamiento, issued under 90 days ago)")
    else:
        out.append(obj)
    return out


# ── the finder (read live) ────────────────────────────────────────────────────────────────────────────────────────

class FinderRefused(Exception):
    pass


async def _http(method: str, url: str, data: Optional[dict] = None, cookies=None):
    """→ (status, text in the page's own charset, the cookie jar — kept whole: the site sets one name on two domains)."""
    import httpx
    async with httpx.AsyncClient(timeout=25.0, headers={"User-Agent": UA}, cookies=cookies, follow_redirects=True) as c:
        r = await (c.post(url, data=data) if method == "POST" else c.get(url))
        return r.status_code, r.text, httpx.Cookies(c.cookies)


HTTP = _http                              # tests replace it
_LAST: Dict[str, float] = {}
_CENTRES: Dict[str, Tuple[float, dict]] = {}


async def _paced(method: str, url: str, data: Optional[dict] = None, cookies=None):
    host = urllib.parse.urlsplit(url).netloc
    wait = PACE - (time.monotonic() - _LAST.get(host, 0))
    if wait > 0 and HTTP is _http:
        await asyncio.sleep(wait)
    _LAST[host] = time.monotonic()
    return await HTTP(method, url, data, cookies)


def _flat(h: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", t))).strip()


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    words = [w for w in s.split() if w not in ("DE", "DEL", "LA", "LAS", "LOS", "EL", "Y")]
    return " ".join(words)


_TYPES = ("CALLE", "AVENIDA", "PLAZA", "PASEO", "CARRETERA", "CRA", "CAMINO", "RONDA", "TRAVESIA", "GLORIETA", "COSTANILLA",
          "PASAJE", "PSAJE", "URBANIZACION", "CL", "AV", "PL", "PS")


def _street_key(s: str) -> str:
    w = _norm(s).split()
    return " ".join(w[1:] if w and w[0] in _TYPES else w)


def municipalities(page: str) -> Dict[str, str]:
    sel = re.search(r'cbxLocalidades".*?</select>', page, re.S)
    return {_norm(n): v for v, n in re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)</option>', sel.group(0))} if sel else {}


def candidates(page: str) -> List[dict]:
    return [{"id": i, "address": _flat(a), "municipality": _flat(m)} for i, a, m in
            re.findall(r"DetalleAsistenciales\.aspx\?ID=(\d+)'[^>]*>(.*?)</a>.*?<td[^>]*>(.*?)</td>", page, re.S)]


def pick(cands: List[dict], street: str, number: str) -> List[dict]:
    """The candidates that ARE this address: the same street name and number (never the nearest-sounding one)."""
    key, n = _street_key(street), (number or "").strip().upper()
    return [c for c in cands if _street_key(c["address"].rsplit(",", 1)[0]) == key
            and c["address"].rsplit(",", 1)[-1].strip().upper() == n]


_FIELDS = [("code", r"Código de centro:"), ("address", r"Dirección postal:"), ("municipality", r"Municipio:"),
           ("postcode", r"Código postal:"), ("hours", r"Horario del centro:"), ("phone_info", r"Teléfono de información:"),
           ("phone_cita", r"Teléfono cita previa:"), ("modes", r"Otras modalidades de gestión de cita:")]
_END = r"(?=Código de centro:|Dirección postal:|Municipio:|Código postal:|Horario del centro:|Teléfono de información:|" \
       r"Teléfono cita previa:|Otras modalidades de gestión de cita:|Ampliar el mapa|Recursos sanitarios|Página web del centro|Volver|$)"


def centre(page: str, cid: str) -> dict:
    t = _flat(page)
    m = re.search(r"Detalles del centro\s+(?:Detalles del centro\s+)?(.+?)\s+Código de centro:", t)
    out = {"name": m.group(1).strip() if m else "", "finder_id": cid, "source": FINDER["detail"].format(id=cid)}
    for k, lab in _FIELDS:
        mm = re.search(lab + r"\s*(.*?)\s*" + _END, t)
        out[k] = mm.group(1).strip() if mm else ""
    out["phone_e164"] = "+34" + re.sub(r"\D", "", out["phone_cita"] or out["phone_info"])[-9:] if (out["phone_cita"] or out["phone_info"]) else ""
    return out


async def find(street: str, number: str, municipality: str) -> dict:
    """SERMAS's own finder, read now → {centre…} or FinderRefused (say why; never a guess)."""
    st, page, ck = await _paced("GET", FINDER["url"])
    if st != 200:
        raise FinderRefused(f"SERMAS's finder answered HTTP {st}")
    munis = municipalities(page)
    code = munis.get(_norm(municipality))
    if not code:
        raise FinderRefused(f"SERMAS's finder has no municipality “{municipality}”")
    form = {k: H.unescape(v) for k, v in re.findall(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', page)}
    form.update({"ctl00$ContenedorContenidoSeccion$txtDireccion": _street_key(street) or street,
                 "ctl00$ContenedorContenidoSeccion$txtNumero": number or "S/N",
                 "ctl00$ContenedorContenidoSeccion$cbxLocalidades": code,
                 "ctl00$ContenedorContenidoSeccion$btnBuscar": "Buscar"})
    st, page, ck = await _paced("POST", FINDER["url"], form, ck)
    if st != 200:
        raise FinderRefused(f"SERMAS's finder answered HTTP {st}")
    hits = pick(candidates(page), street, number)
    if len(hits) != 1:
        raise FinderRefused("SERMAS's finder " + ("doesn't list that exact address" if not hits else
                            f"lists {len(hits)} addresses like it") + " — check the street and number")
    cid = hits[0]["id"]
    hit = _CENTRES.get(cid)
    if hit and time.monotonic() - hit[0] < CACHE_S:
        return dict(hit[1])
    st, page, _ = await _paced("GET", FINDER["detail"].format(id=cid), None, ck)
    if st != 200:
        raise FinderRefused(f"SERMAS's centre page answered HTTP {st}")
    c = centre(page, cid)
    if not c["name"] or not c["address"]:
        raise FinderRefused("SERMAS's centre page didn't name the centre — not guessed")
    c["read_at"] = datetime.now().isoformat(timespec="minutes")
    _CENTRES[cid] = (time.monotonic(), c)
    return c


def card(c: dict) -> str:
    return (f"Your centro de salud — from SERMAS's own finder, read just now:\n*{c['name']}*\n{c['address']}, {c['postcode']} "
            f"{c['municipality'].title()}\n{c['hours']}\nCita line: {c['phone_cita'] or c['phone_info']}\n"
            f"The Comunidad's page: “{HAND_IN['words']}”")


# ── the calendar ─────────────────────────────────────────────────────────────────────────────────────────────────

def gcal(title: str, on: date, at: str, location: str, details: str, minutes: int = 30) -> str:
    from zoneinfo import ZoneInfo
    a = datetime.combine(on, datetime.strptime(at, "%H:%M").time(), ZoneInfo("Europe/Madrid")).astimezone(ZoneInfo("UTC"))
    b = a + timedelta(minutes=minutes)
    q = {"action": "TEMPLATE", "text": title, "dates": f"{a:%Y%m%dT%H%M%SZ}/{b:%Y%m%dT%H%M%SZ}", "location": location,
         "details": details}
    return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(q)


# ── the conversation (called from health.turn) ───────────────────────────────────────────────────────────────────

ROUTE_BUTTONS = [("Call them for me", "hx:ci:call"), ("Book online", "hx:ci:web"), ("I'll just go", "hx:ci:go")]


def offer(out, pend: dict, keep: dict, expire_at: str) -> None:
    """Right after the 1449F1: the question, and only what the lookup and the copy lines need (dropped with the form)."""
    pend["ci"] = {**keep, "expire_at": expire_at}
    pend["step"] = "ci_offer"
    out.ask("Book the appointment to hand it in? I'll find your centro de salud from your address on SERMAS's own finder.",
            [("Yes, find my centre", "hx:ci:find"), ("Not now", "hx:ci:no")])


def _expired(ci: dict, now: datetime) -> bool:
    try:
        return datetime.fromisoformat(ci["expire_at"]) <= now
    except (KeyError, TypeError, ValueError):
        return True


async def on_offer(ctx: dict, t: str, payload: str) -> None:
    from booking_signer import yes as YS
    pend, out = ctx["st"]["pending"], ctx["out"]
    ci = pend.get("ci") or {}
    if payload == "hx:ci:no" or (not payload and re.match(r"(?i)^\s*(no|not now|later)\b", t)) or _expired(ci, ctx["now"]):
        pend.pop("ci", None)
        pend["step"] = "done"
        out.text("OK. Your form's link stays valid for 24 hours; the Comunidad's page says you can hand it in at your centro "
                 "de salud during public hours, 8:30–20:30.")
        return
    if not (payload == "hx:ci:find" or YS.is_yes(t)):
        out.ask("Shall I find your centro de salud?", [("Yes, find my centre", "hx:ci:find"), ("Not now", "hx:ci:no")])
        return
    await ctx["early"]("Reading SERMAS's centre finder for your address…")
    try:
        c = await find(ci["street"], ci["number"], ci["municipality"])
    except FinderRefused as e:
        out.text(f"I couldn't find it: {e}. You can look yourself on SERMAS's finder: {FINDER['url']}")
        pend["step"] = "done"
        pend.pop("ci", None)
        return
    except Exception as e:
        log.error("[cita] finder: %s", type(e).__name__)
        out.text(f"SERMAS's finder didn't answer just now ({type(e).__name__}). Its page: {FINDER['url']}")
        return
    ci["centre"] = c
    pend["step"] = "ci_route"
    out.text(card(c))
    out.ask("How would you like to do it?", ROUTE_BUTTONS)


async def on_route(ctx: dict, t: str, payload: str) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    ci = pend.get("ci") or {}
    pick_ = payload[6:] if payload.startswith("hx:ci:") else ("call" if re.search(r"(?i)\bcall|llam", t) else
                                                             "web" if re.search(r"(?i)online|web|internet", t) else
                                                             "go" if re.search(r"(?i)\bgo\b|myself|ir\b|walk", t) else "")
    c = ci.get("centre") or {}
    if pick_ == "go":
        pend.update(step="ci_when", ci_route="go")
        out.text(f"Which day and time will you go to {c.get('name')}? (e.g. \"Tuesday 10:00\") — I'll put it in your itinerary "
                 "with what to bring.")
    elif pick_ == "web":
        await _online(ctx, ci)
    elif pick_ == "call":
        from booking_signer import handover as HO
        if not HO.founder_override(ctx["account"]):
            out.text("Calling a public health centre for you isn't open yet (it waits for our lawyers' sign-off). Its cita "
                     f"line is {c.get('phone_cita')} — or book online, or just go.")
            out.ask("Which would you like?", ROUTE_BUTTONS[1:])
            return
        pend.update(step="ci_call_when", ci_route="call")
        out.text(f"Which day and time suits you to hand it in at {c.get('name')}? (e.g. \"Tuesday 10:00\") — I'll ask for that "
                 "time, and nothing else.")
    else:
        out.ask("Call them for you, book online, or just go?", ROUTE_BUTTONS)


async def _online(ctx: dict, ci: dict) -> None:
    """The registry offices' own cita page, to the citizen's phone; their details ready to copy; the CAPTCHA and Enviar theirs."""
    pend, out = ctx["st"]["pending"], ctx["out"]
    copy = ci.get("copy") or {}
    lines = [f"{k}: {v}" for k, v in (("Nombre", copy.get("nombre")), ("Apellidos", copy.get("apellidos")),
                                      ("DNI/NIE", copy.get("dni")), ("Móvil", copy.get("movil")), ("Correo", copy.get("correo"))) if v]
    msg = (f"📲 The Comunidad's own cita page for its registry offices (Oficinas de Registro y Atención al Ciudadano):\n"
           f"{OFIREG['url']}\nPick an office near you, the service, then a day and time. Your details, ready to copy:\n"
           + "\n".join("• " + x for x in lines) +
           "\nIt ends with a “No soy un robot” box and Enviar — both yours. Then tell me the day and time (and the code they give you).")
    pend.update(step="ci_booked", ci_route="online")
    if ctx["frm"] == "web":
        sent = await _to_phone(ctx, msg)
        out.text("I've sent the cita page to your phone — " + ("open it there." if sent else
                 f"(your phone isn't linked, so here it is): {OFIREG['url']}"))
    else:
        out.text(msg)
    out.text(f"(SERMAS's own online cita isn't the route here: {SERMAS_ONLINE_NEEDS_CIPA})")


async def _to_phone(ctx: dict, text: str) -> bool:
    from booking_signer import guest_whatsapp as GW
    from .. import whatsapp as PW
    ch, _, number = await PW.reach("", None, ctx["account"])
    if not ch:
        return False
    gst = await GW.STORE.get_state(ch["wa_id_sha256"])
    res = await GW.deliver(ch, number, GW.Out().text(text), gst.get("last_inbound_at"))
    return bool(res) and all(x == "sent" for x in res)


def when(t: str, now: datetime) -> Optional[Tuple[date, str]]:
    """"Tuesday 10:00" (the health turn's own reading) or "14 October 9:30" (the itinerary's) → (day, "HH:MM")."""
    from .. import itinerary as IT
    from .turn import MADRID, parse_when
    at = parse_when(t, now if now.tzinfo else now.replace(tzinfo=MADRID))
    if at:
        at = at.astimezone(MADRID)
        return at.date(), at.strftime("%H:%M")
    return IT.parse_day_time(t, now.astimezone(MADRID).date() if now.tzinfo else now.date())


async def on_when(ctx: dict, t: str) -> None:
    """The day the citizen will go, or the day they booked → the itinerary, the calendar, what to bring."""
    from .. import itinerary as IT
    pend, out = ctx["st"]["pending"], ctx["out"]
    got = when(t, ctx["now"])
    if not got:
        out.text("A day and a time, please — e.g. \"Tuesday 10:00\" or \"14 October 9:30\".")
        return
    await _record(ctx, *got, said=t)


async def _record(ctx: dict, on: date, at: str, said: str = "") -> None:
    from .. import itinerary as IT
    pend, out = ctx["st"]["pending"], ctx["out"]
    ci = pend.get("ci") or {}
    c = ci.get("centre") or {}
    route = pend.get("ci_route")
    place = c.get("name") if route != "online" else "Oficina de Registro (Comunidad de Madrid)"
    loc = f"{c.get('address')}, {c.get('postcode')} {c.get('municipality', '').title()}" if route != "online" else ""
    code = re.search(r"\b(?:code|c[oó]digo)\D{0,6}(\d{3,6})\b", said or "", re.I)
    items = bring(ci.get("motive", ""))
    item = await IT.guest_booked(ctx["account"], type_="doctor", provider_name=f"{place} — hand in your health-card form",
                                 on=on, at=at, tz="Europe/Madrid", location=loc or None)
    details = ("Hand in your Solicitud de Tarjeta Sanitaria (1449F1). Bring: " + "; ".join(items) +
               (f". Cita code: {code.group(1)}" if code else "") + f". Source: {HAND_IN['page']}")
    link = gcal(f"Tarjeta sanitaria — {place}", on, at, loc, details)
    out.text(("✅ In your itinerary" if item else "Noted (your itinerary couldn't be reached just now)") +
             f": {place}, {on.strftime('%A %-d %B')} at {at}{' (cita ' + code.group(1) + ')' if code else ''}.\n"
             "Bring:\n" + "\n".join("• " + x for x in items) + f"\n📅 Add it to your calendar: {link}")
    pend.pop("ci", None)
    pend.pop("ci_route", None)
    pend["step"] = "done"


async def call_prepare(ctx: dict, t: str) -> None:
    """The founder's CR 34 route: the centre's own cita line, from the finder; the read-back first; one yes."""
    from booking_signer import guest_whatsapp as GW
    from booking_signer import ladder_routes as LR
    from .turn import MADRID, parse_when
    import uuid
    pend, out, account = ctx["st"]["pending"], ctx["out"], ctx["account"]
    ci = pend.get("ci") or {}
    c = ci.get("centre") or {}
    at = parse_when(t, ctx["now"])
    if not at:
        out.text("A day and a time from now on, please — e.g. \"Tuesday 10:00\".")
        return
    if not c.get("phone_e164"):
        out.text("SERMAS's page gives no cita line for that centre — nothing to call.")
        return
    status, contact = await GW.api(account, "GET", "/api/booking/contact")
    who = (contact or {}).get("contact") or {}
    if not who.get("name") or not who.get("mobile_e164"):
        out.text(GW.NO_CONTACT.format(web=GW.web_url()))
        return
    rid = str(uuid.uuid4())
    read = {"name": c["name"], "country": "ES", "listing": {"name": c["name"]},
            "facts": [{"kind": "phone", "value": c["phone_e164"], "source_kind": "site",
                       "source_label": f"SERMAS's own centre finder (“Teléfono cita previa”), read {c.get('read_at', READ_ON)}"}]}
    await LR.LADDER_STORE.put_read({"read_id": rid, "account_id": account, "query": "CR 34 centro de salud", "venue_name": c["name"],
                                    "country": "ES", "read": read, "created_at": datetime.now(MADRID)})
    reservation = {"schema": "reservation/1", "flow": "book",
                   "who": {"name": who["name"], "contact": {"mobile_e164": who["mobile_e164"]}},
                   "what": {"category": "appointment", "activity": "a time to hand in a health-card application",
                            "activity_venue_lang": "una cita para entregar la solicitud de la tarjeta sanitaria"},
                   "where": {}, "when": {"mode": "at", "at": at.strftime("%Y-%m-%dT%H:%M")},
                   "how_many": {"count": 1, "unit": "people"}}
    status, j = await GW.api(account, "POST", "/api/booking/calls", {"reservation": reservation, "read_id": rid})
    if status != 200:
        out.text(f"Not prepared — {GW.refusal_words(j, status)}. Nothing was dialled.")
        return
    lines, sha = j["read_back"]["lines"], j["read_back"]["sha256"]
    out.text("Exactly what I'll say:\n" + "\n".join("• " + ln for ln in lines) +
             "\nI ask only for that time to hand in the form; I agree to nothing else, and I tell you their exact words.")
    out.ask(f"Call {c['name']} now?", [("Yes, call them", f"hxyes:{sha[:16]}"), ("No", f"hxno:{sha[:16]}")])
    pend.update(step="ci_call_confirm", call_id=j["call_id"], sha=sha, asked_at=ctx["now"].isoformat(),
                summary=f"a time to hand in the health-card form, {at.strftime('%A %-d %B at %H:%M')}")


async def call_yes(ctx: dict, t: str, payload: str) -> None:
    from booking_signer import guest_whatsapp as GW
    from booking_signer import yes as YS
    from .turn import APPROVAL_WINDOW
    pend, out, account = ctx["st"]["pending"], ctx["out"], ctx["account"]
    sha = pend.get("sha", "")
    c = (pend.get("ci") or {}).get("centre") or {}
    if payload == f"hxno:{sha[:16]}" or (not payload and re.match(r"(?i)^\s*no\b", t)):
        pend["step"] = "ci_route"
        out.ask("OK — not called. Another way?", ROUTE_BUTTONS)
        return
    if not (payload == f"hxyes:{sha[:16]}" or (not payload and YS.is_yes(t))):
        out.text("Yes or no?" if not payload else "That button belonged to an earlier question — nothing was dialled.")
        return
    if ctx["now"] - datetime.fromisoformat(pend["asked_at"]) > APPROVAL_WINDOW:
        pend["step"] = "ci_call_when"
        out.text("That yes came more than 15 minutes later — nothing was dialled. Which day and time?")
        return
    how = {"how": "whatsapp_button" if payload else "whatsapp_text", "said": t or "Yes, call them"}
    status, j = await GW.api(account, "POST", f"/api/booking/calls/{pend['call_id']}/place",
                             {"read_back_sha256": sha, "approval": how}, timeout=120)
    if status != 200:
        out.text(f"Not called — {GW.refusal_words(j, status)}. Nothing was dialled.")
        return
    if j.get("status") == "placed":
        out.text(f"📞 {j.get('say') or 'Calling ' + c.get('name', 'the centre') + ' now.'} I'll tell you their exact words. "
                 "When they've given you a time, tell me (e.g. \"booked Tuesday 10:00\") and it goes in your itinerary.")
        GW._spawn(GW.watch_call(ctx["ch"], ctx["frm"], account, pend["call_id"], c.get("name", "the centre"), "book",
                                pend.get("summary", "")))
    elif j.get("status") == "scheduled":
        out.text(f"They're closed now — I'll call at {j.get('scheduled_for')}, covered by your yes.")
    else:
        out.text(f"⚠ {j.get('say') or 'The call did not go through'} — nothing is booked.")
    pend["step"] = "ci_booked"
