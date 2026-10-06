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
# CR 37 · the office and service for handing in the 1449F1 by cita, read on the OFIREG page itself (6 Oct 2026): under
# "06 Consejería de Sanidad (OFICINA 360)", the office "SERMAS. Paseo de la Castellana, 280", service "01-REGISTRO DE
# DOCUMENTACIÓN" (id 3152); the page's own link ?servicio=3152 opens straight on "Solicitar cita" with both chosen.
# (CR 36 had preselected DAT Madrid Norte: an EDUCATION office — dropped.)
SERMAS_REGISTRY = {"servicio": "3152", "name": "SERMAS. Paseo de la Castellana, 280", "service": "01-REGISTRO DE DOCUMENTACIÓN",
                   "address": "Paseo de la Castellana, 280, Madrid", "url": "https://gestiona.comunidad.madrid/ctac_cita/OFIREG?servicio=3152"}
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


def municipalities(page: str) -> Dict[str, str]:
    sel = re.search(r'cbxLocalidades".*?</select>', page, re.S)
    return {_norm(n): v for v, n in re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)</option>', sel.group(0))} if sel else {}


def candidates(page: str) -> List[dict]:
    return [{"id": i, "address": _flat(a), "municipality": _flat(m)} for i, a, m in
            re.findall(r"DetalleAsistenciales\.aspx\?ID=(\d+)'[^>]*>(.*?)</a>.*?<td[^>]*>(.*?)</td>", page, re.S)]


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


class Choose(Exception):
    """No single exact address: the finder's own closest streets for the citizen to pick (empty: nothing like it at all)."""

    def __init__(self, cands: List[dict], said: str):
        super().__init__(said)
        self.cands, self.said = cands, said


def _form(page: str) -> dict:
    return {k: H.unescape(v) for k, v in re.findall(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', page)}


async def find(line: str, municipality: str) -> dict:
    """SERMAS's own finder, read now, for the citizen's address as written (DNI or padrón) → the centre, or Choose with the
    finder's closest streets, or FinderRefused (the finder itself didn't answer). Never a guess: a street is taken only when
    its name IS the citizen's (address.same), at their number."""
    from . import address as A
    p = A.parse(line)
    if not p["name"] or not p["number"]:
        raise Choose([], "I need the street and its number")
    st, page, ck = await _paced("GET", FINDER["url"])
    if st != 200:
        raise FinderRefused(f"SERMAS's finder answered HTTP {st}")
    code = municipalities(page).get(_norm(municipality))
    if not code:
        raise Choose([], f"SERMAS's finder has no town called “{municipality.title()}”")
    seen: Dict[str, dict] = {}
    numbers = [p["number"]] + ([p["portal"]] if p["portal"] and p["portal"] != p["number"] else [])
    for n in numbers:
        for q in A.queries(p):
            form = _form(page)
            form.update({"ctl00$ContenedorContenidoSeccion$txtDireccion": q, "ctl00$ContenedorContenidoSeccion$txtNumero": n,
                         "ctl00$ContenedorContenidoSeccion$cbxLocalidades": code,
                         "ctl00$ContenedorContenidoSeccion$btnBuscar": "Buscar"})
            st, got, ck = await _paced("POST", FINDER["url"], form, ck)
            if st != 200:
                raise FinderRefused(f"SERMAS's finder answered HTTP {st}")
            page = got if _form(got) else page
            for c in candidates(got):
                c["number"] = c["address"].rsplit(",", 1)[-1].strip()
                c["street"] = c["address"].rsplit(",", 1)[0].strip()
                seen.setdefault(f"{c['id']}|{c['address']}", c)     # the ID is the centre's area: two streets may share it
            exact = [c for c in seen.values() if A.same(p, c["street"]) and c["number"].upper() == n.upper()]
            if len(exact) == 1:
                return await detail(exact[0]["id"], ck)
            if len(exact) > 1:            # the same street listed twice (blocks of one address) → one centre, or ask
                found = [await detail(x["id"], ck) for x in exact[:4]]
                if len({f["code"] for f in found}) == 1:
                    return found[0]
                raise Choose(exact[:3], "SERMAS's finder lists more than one street by that name, with different centres")
    near = sorted(seen.values(), key=lambda c: -A.closeness(A.full(p), c["street"]))
    near = [c for c in near if A.closeness(A.full(p), c["street"]) > 0][:3]
    raise Choose(near, f"SERMAS's finder has no “{A.full(p).title()}, {p['number']}” in {municipality.title()}")


async def detail(cid: str, cookies=None) -> dict:
    hit = _CENTRES.get(cid)
    if hit and time.monotonic() - hit[0] < CACHE_S:
        return dict(hit[1])
    st, page, _ = await _paced("GET", FINDER["detail"].format(id=cid), None, cookies)
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
            f"No cita needed: walk into {c['name']} during public hours, 8:30–20:30 — the Comunidad's page: “{HAND_IN['words']}”")


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


AGAIN = re.compile(r"(?i)\b(find|look\s*up|search)\b.{0,12}\b(my\s+)?(health\s+)?(cent(re|er)|centro)\b|\bmi centro de salud\b")


async def resume(ctx: dict) -> bool:
    """CR 35 · "find my centre" after the form was prepared (or after the lookup failed): the address comes back from the
    citizen's own latest 1449F1 case, inside its 24 hours — never kept anywhere else. False: no such case."""
    from .. import store as ST
    from datetime import timezone
    from . import tarjeta as TS
    now = datetime.now(timezone.utc)
    mine = [c for c in await ST.STORE.of_product("health")
            if c.get("account_id") == ctx["account"] and (c["state"] or {}).get("kind") == "tarjeta"
            and (c["state"] or {}).get("rows") and not TS.expired(c["state"], now)]
    if not mine:
        return False
    st = max(mine, key=lambda c: c["state"].get("prepared_at") or "")["state"]
    r = {x["field"]: x["value"] for x in st["rows"]}
    line = " ".join(x for x in (r.get("TLTIPOVIAL_INTER", ""), r.get("TLNOMVIAL_INTER", ""), r.get("NMNUMVIAL_INTER", "")) if x)
    if r.get("TLNUMVIAL_INTER"):
        line += f", PORTAL {r['TLNUMVIAL_INTER']}"
    ctx["st"]["pending"]["ci"] = {"line": line, "municipality": r.get("DSMUNI_INTER") or "MADRID",
                                  "motive": r.get("ITMOTIVO_SOLIC", ""), "expire_at": st["values_expire_at"],
                                  "copy": {"nombre": r.get("TLNOMBRE_INTER", "").title(),
                                           "apellidos": f"{r.get('TLAPELLIDO1_INTER', '')} {r.get('TLAPELLIDO2_INTER', '')}".strip().title(),
                                           "dni": r.get("CDDOCIDENT_INTER", ""), "movil": r.get("TLTELF_MOVIL_INTER", ""),
                                           "correo": r.get("TLEMAIL_INTER", "")}}
    ctx["st"]["pending"]["step"] = "ci_offer"
    await on_offer(ctx, "yes", "hx:ci:find")
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
    await _look(ctx, ci["line"], ci["municipality"])


async def _look(ctx: dict, line: str, municipality: str) -> None:
    """The finder, then the centre — or the finder's own closest streets to pick from, or "type it as on your padrón". Never
    "look yourself"."""
    pend, out = ctx["st"]["pending"], ctx["out"]
    ci = pend["ci"]
    try:
        c = await find(line, municipality)
    except Choose as e:
        if e.cands:
            ci["choices"] = {f"{x['id']}|{i}": x["address"] for i, x in enumerate(e.cands, 1)}
            pend["step"] = "ci_pick"
            listed = "\n".join(f"{i}. {x['address'].title()}, {x['municipality'].title()}" for i, x in enumerate(e.cands, 1))
            out.text(f"{e.said}. Did you mean one of these (SERMAS's own spelling)?\n{listed}")
            out.ask("Which is yours?", [(f"{i}. {x['street'].title()[:16]}", f"hx:ci:pick:{x['id']}|{i}")
                                        for i, x in enumerate(e.cands, 1)])
        else:
            pend["step"] = "ci_street"
            out.text(f"{e.said}. Type your street and number as your padrón has them — e.g. “Calle de la Vereda de Palacio 1, "
                     f"Alcobendas” — and I'll look again.")
        return
    except FinderRefused as e:
        out.text(f"{e}. I'll try again when you say “find my centre”.")
        pend["step"] = "ci_offer"
        return
    except Exception as e:
        log.error("[cita] finder: %s", type(e).__name__)
        out.text(f"SERMAS's finder didn't answer just now ({type(e).__name__}). Say “find my centre” to try again.")
        pend["step"] = "ci_offer"
        return
    await _found(ctx, c)


async def _found(ctx: dict, c: dict) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    pend["ci"]["centre"] = c
    pend["ci"].pop("choices", None)
    pend["step"] = "ci_route"
    out.text(card(c))
    out.ask("How would you like to do it?", ROUTE_BUTTONS)


async def on_pick(ctx: dict, t: str, payload: str) -> None:
    """The citizen's pick among the finder's streets (a button, its number, or "none")."""
    pend, out = ctx["st"]["pending"], ctx["out"]
    ci = pend.get("ci") or {}
    ids = list((ci.get("choices") or {}).keys())
    cid = payload[len("hx:ci:pick:"):] if payload.startswith("hx:ci:pick:") else ""
    m = re.match(r"^\s*([1-3])\b", t)
    if not cid and m and int(m.group(1)) <= len(ids):
        cid = ids[int(m.group(1)) - 1]
    if cid not in ids:
        pend["step"] = "ci_street"
        out.text("Then type your street and number as your padrón has them — e.g. “Calle de la Vereda de Palacio 1, "
                 "Alcobendas”.")
        return
    try:
        c = await detail(cid.split("|")[0])
    except FinderRefused as e:
        out.text(f"{e}. Pick again in a moment.")
        return
    await _found(ctx, c)


async def on_street(ctx: dict, t: str) -> None:
    """The street typed as on the padrón ("…, Alcobendas" names the town; else the one on the form)."""
    pend = ctx["st"]["pending"]
    ci = pend["ci"]
    line, town = t, ci["municipality"]
    m = re.match(r"^(.*\d.*?)\s*,\s*([^,\d]+)$", t.strip())
    if m:
        line, town = m.group(1), m.group(2).strip()
    ci.update(line=line, municipality=town)
    await _look(ctx, line, town)


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
    """The Comunidad's own cita page, opened straight on "Solicitar cita" at SERMAS's registry office and its service; each
    personal detail as its own message (one tap copies it); the CAPTCHA and Enviar are the citizen's."""
    pend, out = ctx["st"]["pending"], ctx["out"]
    copy = ci.get("copy") or {}
    lines = [f"{k}: {v}" for k, v in (("Nombre", copy.get("nombre")), ("Apellidos", copy.get("apellidos")),
                                      ("DNI/NIE", copy.get("dni")), ("Móvil", copy.get("movil")), ("Correo", copy.get("correo"))) if v]
    o = SERMAS_REGISTRY
    ci["office"] = {"name": o["name"], "address": o["address"]}
    head = (f"📲 The Comunidad's own cita page, open on “Solicitar cita” at {o['name']}, service “{o['service']}”:\n{o['url']}\n"
            "Pick a day and a time, then your details — each one below, ready to copy. It ends with “No soy un robot” and "
            "Enviar: both yours. Then tell me the day and time (and the code they give you).")
    pend.update(step="ci_booked", ci_route="online")
    if ctx["frm"] == "web":
        sent = all([await _to_phone(ctx, head)] + [await _to_phone(ctx, x.split(": ", 1)[1]) for x in lines])
        out.text("I've sent the cita page and your details to your phone — " + ("open it there." if sent else
                 f"(your phone isn't linked, so here they are): {o['url']}"))
        if not sent:
            for x in lines:
                out.text(x.split(": ", 1)[1])
    else:
        out.text(head)
        for x in lines:                                   # each on its own: a long-press copies just that value
            out.text(x.split(": ", 1)[1])
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
    hm = re.search(r"\b([01]?\d|2[0-3])[:.h]([0-5]\d)\b", t or "")    # an explicit HH:MM wins ("8 de octubre … a las 10:30")
    at = parse_when(t, now if now.tzinfo else now.replace(tzinfo=MADRID))
    if at:
        at = at.astimezone(MADRID)
        got = (at.date(), at.strftime("%H:%M"))
    else:
        got = IT.parse_day_time(t, now.astimezone(MADRID).date() if now.tzinfo else now.date())
    if got and hm:
        got = (got[0], f"{int(hm.group(1)):02d}:{hm.group(2)}")
    return got


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
    office = ci.get("office") or {}
    place = c.get("name") if route != "online" else (office.get("name") or "Oficina de Registro (Comunidad de Madrid)")
    loc = (f"{c.get('address')}, {c.get('postcode')} {c.get('municipality', '').title()}" if route != "online"
           else office.get("address", ""))
    code = re.search(r"\b(?:code|c[oó]digo)(?:\s+de\s+(?:la\s+)?cita)?\s*[:#]?\s*([A-Z0-9]{3,8})\b", said or "", re.I)
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
