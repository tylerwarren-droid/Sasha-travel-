"""CR 1 · after the form: the applicant signs (we never do) → where and how THEY lodge it → the checklist → reminders.

Everything here comes from an official page that was READ, with its date (docs/products/reads/):
  · the Spanish Consulate General in London's own sheet for this visa, "Actualizado 11/02/2022" (sha256 31ca97e4…),
    read 3 Oct 2026: the documents, the 90-day window, the appointment route, the TIE within a month of entry;
  · the Spanish government's "Cita previa de extranjería" page (sede.administracionespublicas.gob.es), read 3 Oct 2026.
A consulate whose own page hasn't been read gets NO link: we say so, and never compose one ("locate, never book",
AD P807id §3.1; hosts never composed from memory, P807id:23). Nothing is ever pressed, booked or filed by us.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import logging

from .. import store as ST
from . import consulates as CS
from . import facts as F

log = logging.getLogger("products.relocation.after")
LONDON_SHEET = {
    "name": "Consulado General de España en Londres — Visado de residencia no lucrativa (requirements sheet)",
    "url": "https://www.exteriores.gob.es/Consulados/londres/en/Information-consular-services/Documents/RES%20ES-EN.pdf",
    "dated": "11 Feb 2022", "read": "3 Oct 2026", "sha256": "31ca97e470f3b0d8b6aa7beae12db42bb635098b6b761406faad0bcce996622f",
}
CONSULATES = {
    "united kingdom": {
        "office": "Consulado General de España en Londres",
        "appointment_url": "http://www.exteriores.gob.es/Consulados/LONDRES/en/Consulado/Pages/Visas.aspx",
        "appointment_words": "Applicants must request their appointment following the instructions on the Consulate's website",
        "one_per_person": "each appointment is for one person only — family members applying need their own",
        "source": LONDON_SHEET,
    },
}
_UK = re.compile(r"(?i)\b(uk|u\.k\.|united kingdom|england|scotland|wales|northern ireland|britain|great britain|london)\b")
CITA_EXTRANJERIA = {
    "name": "Cita previa de extranjería (Secretaría de Estado de Función Pública)",
    "url": "https://sede.administracionespublicas.gob.es/pagina/index/directorio/icpplus",
    "words": "Cita previa para la presentación de autorizaciones en las oficinas de extranjeros.",
    "read": "3 Oct 2026",
}

# the London sheet's REQUISITOS, in its own order and words (shortened, never changed in meaning)
CHECKLIST = [
    ("visa_form", "National visa application form, completed, dated and signed (item 1)"),
    ("photo", "A recent passport photo with a white background — no digital retouching (item 2)"),
    ("passport", "Passport valid for at least one year, with at least two blank pages, plus copies of every page with "
                 "information (item 3)"),
    ("uk_permit", "Your valid UK residence permit and a copy — only if you aren't British (item 4)"),
    ("criminal_record", "Criminal record certificate from every country you lived in for the last five years — over-18s; "
                        "no older than 3 months; legalised or apostilled; with a sworn translation into Spanish (item 5)"),
    ("insurance", "Public or private health insurance with an insurer authorised to operate in Spain (item 6)"),
    ("medical", "Medical certificate from a registered doctor, issued within the 3 months before you apply, in the "
                "wording the sheet gives; apostilled; with a sworn translation (item 7)"),
    ("means", "Proof of economic means for one year, set as a percentage of IPREM — the sheet's own figures are from 2022, "
              "so check the current amount on the consulate's page (item 8)"),
    ("fee_790", "Form 790-052, the fee self-assessment for the initial residence authorisation (item 9)"),
    ("ex01", "The EX-01, completed (item 10) — prepared by Kanoe; signed by you"),
    ("visa_fee", "The visa fee, paid at the Consulate on the day your application is accepted (item 11)"),
]


def london_items(items: List[dict]) -> List[dict]:
    """London's checklist rows in the shape the pack uses: the sheet's own item number, our label, its words."""
    out = []
    for it in items:
        m = re.search(r"\(item (\d+)\)", it["words"])
        out.append({**it, "n": int(m.group(1)) if m else len(out) + 1, "label": it["words"].split(" — ")[0].split(" (item")[0].split(",")[0],
                    "copies": None})
    return out


US_STATE_Q = ("Which US state do you live in? Each Spanish consulate in the US covers its own states — I match yours from the "
              "consulate's own page, never a guess.")


def pack_q(items: List[dict]) -> str:
    lines = "\n".join(f"{it['n']}. {it.get('label') or it['words'][:60]}" + (" — prepared by me, signed by you" if it["key"] == "ex01" else "")
                      for it in items)
    return ("Your *document pack* — which of these have you gathered? Reply with the numbers (e.g. 1 3 4-6), ALL, or "
            f"SKIP:\n{lines}")


def web() -> str:
    import os
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/")


def checklist(f: dict, today: date, residence: Optional[str]) -> List[dict]:
    """Each item with its source; three of them carry a status we can actually compute from the file."""
    a = f.get("applicant") or {}
    out = []
    for key, words in CHECKLIST:
        item = {"key": key, "words": words, "source": f"{LONDON_SHEET['name']}, dated {LONDON_SHEET['dated']}",
                "status": "yours", "why": None}
        if key == "uk_permit" and F.fold((a.get("nationality") or {}).get("value", "")) in ("british", "britanica", "britanico",
                                                                                            "reino unido", "united kingdom"):
            item.update(status="not_needed", why="you're British")
        if key in CS.PREPARED_KEYS:                    # CR 45 · the national visa form and the 790 too, not only the EX-01
            item.update(status="prepared", why="prepared by Kanoe from your answers — you sign it")
        if key == "passport":
            exp = (a.get("passport_expiry") or {}).get("value")
            if exp:
                ok = exp >= (today + timedelta(days=365)).isoformat()
                item.update(status="ok" if ok else "problem",
                            why=f"your passport is valid until {exp}: " + ("at least a year from today" if ok else
                                "LESS than a year from today — the sheet asks for at least one year"))
        out.append(item)
    return out


ENTRY_Q = "When do you plan to enter Spain? (a date, e.g. 1 March 2027 — or SKIP)"


def reminders(entry: Optional[str], today: date, consulate: Optional[dict] = None) -> List[dict]:
    """From the sheet's own dates: apply from 90 days before entry; the two certificates no older than 3 months when you
    apply; the TIE within a month of entering Spain. CR 12 · a US consulate: ONLY what its own page says — the TIE
    within its stated months of entry (no 90-day window: none of their pages states one)."""
    if not entry:
        return []
    if consulate and consulate.get("id"):
        r = CS.READ.get(consulate["id"]) or {}
        n = r.get("tie_within_months")
        if not n:
            return []
        d = date.fromisoformat(entry) + timedelta(days=21 if n == 1 else 30 * n - 9)
        words = (f"You entered Spain about {'three weeks' if n == 1 else f'{n} months'} ago: {consulate['office']}'s own page "
                 f"gives you {n} month{'s' if n > 1 else ''} from entry to request your TIE at the Oficina de Extranjeros or "
                 f"the police station. Book it on the official cita previa page: {CITA_EXTRANJERIA['url']}")
        return [{"on": d.isoformat(), "text": words, "sent": False}] if d >= today else []
    e = date.fromisoformat(entry)
    rs = [(e - timedelta(days=90), "You can apply for your visa from today — up to 90 days before your entry date "
                                   "(London consulate sheet)."),
          (e - timedelta(days=90 + 60), "Your criminal record and medical certificates must be no older than 3 months when "
                                        "you apply — get them from about now, not earlier."),
          (e + timedelta(days=21), "You entered Spain about three weeks ago: the sheet gives you one month from entry to go "
                                   "to the Oficina de Extranjería or a police station for your TIE. Book it on the "
                                   f"official cita previa page: {CITA_EXTRANJERIA['url']}")]
    return [{"on": d.isoformat(), "text": t, "sent": False} for d, t in sorted(rs) if d >= today]


async def _save(ctx: dict, upd: dict) -> None:
    pend = ctx["st"]["pending"]
    case = await ST.STORE.get(pend.get("case_id") or "")
    if case:
        st = case["state"]
        st.update(upd)
        await ST.STORE.update(case["id"], st)


async def signed(ctx: dict) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    await _save(ctx, {"status": "signed_on_your_word", "signed_at": ctx["now"].isoformat()})
    pend["step"] = "residence"
    out.text("Noted — signed by you, on your word. I didn't sign or tick anything for you. You lodge it yourself; "
             "I never file anything in Spain.")
    route = ((pend.get("facts") or {}).get("choices", {}).get("route") or {}).get("value")
    if route == "renewal":
        out.text("A renewal is lodged electronically only (the form's footnote 6) — with your certificate or Cl@ve, by you. "
                 "I haven't read the renewal channel's own page, so I won't give you a link I haven't checked.")
        pend["step"] = "done"
        return
    out.text("A first application is lodged in person, at the Spanish consulate for where you live. Which country do you "
             "live in now?")


async def on_message(ctx: dict, body: str, payload: str) -> bool:
    pend, out, now = ctx["st"]["pending"], ctx["out"], ctx["now"]
    step = pend.get("step")
    f = pend.get("facts") or {}
    from . import arrival as AR                                    # CR 44 · after arrival: padrón → EX-17 + 790-012 → TA.1
    nie = AR.NIE_SAID.search(body or "")
    if nie and step not in ("residence", "us_state", "us_county"):
        val = re.sub(r"[\s-]", "", nie.group(1)).upper()
        if not F._nie(val)[1]:
            f.setdefault("applicant", {})["nie"] = F.fact(val, "said on WhatsApp", now.strftime("%-d %b %Y"))
            await _save(ctx, {"facts": f})
            out.text(f"Noted: NIE {val} — the 790-012, the TA.1 and the EX-17 use it now.")
            await AR.present(ctx, web())
            return True
    if AR.ARRIVAL.search(body or "") and step in ("prepared", "signed", "entry", "appointments", "pack", "done"):
        await AR.present(ctx, web())
        return True
    if step == "residence" and (CS.is_us(body) or CS.state_from(body)):
        state = CS.state_from(body)
        f.setdefault("choices", {})["residence"] = F.fact("united states", "said on WhatsApp", now.strftime("%-d %b %Y"))
        if not state:
            pend["step"] = "us_state"
            out.text(US_STATE_Q)
            return True
        return await _us(ctx, state)
    if step == "us_county":
        sp = CS.split(pend.get("us_state") or "")
        county = CS.county_in(body, sp["counties"]) if sp else None
        if not sp:
            pend["step"] = "us_state"
            out.text(US_STATE_Q)
            return True
        return await _us(ctx, pend["us_state"], cid=sp["named"] if county else sp["rest"], county=county or body.strip())
    if step == "us_state":
        state = CS.state_from(body)
        if not state:
            out.text("The state, please — e.g. New York, NJ, Florida.")
            return True
        return await _us(ctx, state)
    if step == "pack" or (step in ("entry", "appointments", "done") and re.match(r"(?i)^\s*pack\b", body)):
        return await _pack(ctx, re.sub(r"(?i)^\s*pack\b[:\s]*", "", body))
    if step == "residence":
        residence = "united kingdom" if _UK.search(body) else F.fold(body).strip(" .")
        c = CONSULATES.get(residence)
        f.setdefault("choices", {})["residence"] = F.fact(residence, "said on WhatsApp", now.strftime("%-d %b %Y"))
        if residence == "united kingdom":                    # CR 37 · London, read live: fees, BLS, the 790, one pack
            from . import three as TH
            await TH.present(ctx, "london", {"residence": residence}, web(), _save)
            pend["step"] = "pack"
            out.text(pack_q(TH.items("london")))
            return True
        if not c:
            out.text(f"I haven't read the Spanish consulate's own page for {body.strip()} yet, so I won't give you a link I "
                     "haven't checked. It's the Consulado General de España that covers where you live, on exteriores.gob.es.")
            await _save(ctx, {"after": {"residence": residence, "consulate": None}})
        else:
            s = c["source"]
            out.text(f"Your consulate: *{c['office']}*. Its own sheet says: “{c['appointment_words']}”:\n{c['appointment_url']}\n"
                     f"You book it and you go in person — {c['one_per_person']}. I don't book or press anything.\n"
                     f"(From the consulate's sheet dated {s['dated']}, read {s['read']}; its website didn't answer when I "
                     f"checked today, so open the link yourself.)")
            items = checklist(f, now.date(), residence)
            todo = [i for i in items if i["status"] in ("yours", "problem")]
            flag = next((i for i in items if i["status"] == "problem"), None)
            out.text(f"Your checklist from that sheet: {len(items)} items — {len(todo)} for you to gather, the EX-01 done. "
                     f"It's on your file page:\n{web()}/relocation-file/{pend.get('case_id')}")
            if flag:
                out.text(f"⚠ {flag['why']}.")
            pend["consulate_office"] = c["office"]   # CR 13 · context for Sasha's travel
            await _save(ctx, {"after": {"residence": residence, "consulate": c, "checklist": items}})
            pend["step"] = "pack"
            out.text(pack_q(london_items(items)))
            return True
        pend["step"] = "entry"
        out.text(ENTRY_Q)
        return True
    if step == "entry":
        if re.match(r"(?i)^\s*skip\b", body):
            pend["step"] = "appointments"
            out.text("OK — no reminders. Your file page has everything.")
            out.text('When you\'ve booked your consulate appointment — and later, in Spain, your TIE one — tell me the day and time (e.g. "consulate booked 12 November 10:00") and I\'ll put it in your itinerary.')
            return True
        d = F.parse_date(body)
        if not d or d <= now.date().isoformat():
            out.text("A future date please, like 1 March 2027 — or SKIP.")
            return True
        pend["entry_date"] = d   # CR 10 · context for Sasha's other skills (e.g. flights)
        case = await ST.STORE.get(pend.get("case_id") or "")
        after = (case or {}).get("state", {}).get("after") or {}
        rs = reminders(d, now.date(), after.get("consulate"))
        await _save(ctx, {"after": {**after, "entry_date": d, "reminders": rs,
                                    "wa": ctx["ch"]["wa_id_sha256"], "number_from": ctx["frm"]}})
        pend["step"] = "appointments"
        lines = "\n".join(f"• {date.fromisoformat(r['on']).strftime('%-d %b %Y')}: {r['text'].split(' — ')[0].split(': ')[0]}"
                          for r in rs) or "(none — the dates your consulate's page gives have passed or aren't stated)"
        out.text(f"I'll remind you here:\n{lines}\n(WhatsApp lets me write first only within 24 hours of your last message; "
                 "otherwise the reminder waits for your next message, and it's always on your file page.)")
        out.text('When you\'ve booked your consulate appointment — and later, in Spain, your TIE one — tell me the day and time (e.g. "consulate booked 12 November 10:00") and I\'ll put it in your itinerary.')
        return True
    if step == "appointments":
        return await _appointment(ctx, body)
    return False   # CR 10 · not relocation's: Sasha answers it, in the same chat


async def due(now: Optional[datetime] = None) -> int:
    """Daily: send each reminder whose day has come (in-session only — the sandbox has no templates)."""
    from booking_signer import guest_whatsapp as GW
    now = now or datetime.utcnow()
    sent = 0
    rows = await ST.STORE.of_product("relocation")
    for c in rows:
        after = c["state"].get("after") or {}
        for r in after.get("reminders") or []:
            if r["sent"] or r["on"] > now.date().isoformat():
                continue
            from .. import whatsapp as PW
            ch, wkey, frm = await PW.reach(after.get("wa", ""), after.get("number_from"), c.get("account_id"))   # CR 20
            st = await GW.STORE.get_state(wkey) if ch else {}
            res = await GW.deliver(ch, frm, GW.Out().text("🇪🇸 " + r["text"]), st.get("last_inbound_at")) \
                if ch else ["no channel"]
            if res and all(x == "sent" for x in res):
                r["sent"] = True
                sent += 1
        await ST.STORE.update(c["id"], c["state"])
    return sent


_TIE = re.compile(r"(?i)\b(tie|huellas?|fingerprints?|extranjer[ií]a|polic[ií]a|police)\b")


async def _appointment(ctx: dict, body: str) -> bool:
    """CR 10 · an appointment the person booked THEMSELVES, into their itinerary: guest_booked, type 'visa' (Sasha tab's
    rules). Confirmed only on the office's own words — forwarded."""
    from .. import itinerary as IT
    out, now = ctx["out"], ctx["now"]
    when = IT.parse_day_time(body, now.date())
    if not when:
        out.text("The day and the time, please — e.g. \"consulate booked 12 November 10:00\".")
        return True
    on, at = when
    tie = bool(_TIE.search(body))
    case = await ST.STORE.get(ctx["st"]["pending"].get("case_id") or "")
    cons = ((case or {}).get("state", {}).get("after") or {}).get("consulate") or {}
    th = None
    if cons.get("three"):
        from . import three as TH
        th = TH.CONSULATES[cons["three"]]
    if tie:
        name, tz, where = IT.TIE, "Europe/Madrid", None
    elif th:                                                 # CR 37 · its own name, clock and the place you actually go
        name, tz, where = IT.consulate_name(th["office"]), th["tz"], th["booking"]["who"]
    elif cons.get("id"):                                     # CR 12 · a US consulate: its own name, its own clock
        name, tz, where = IT.consulate_name(cons["office"]), CS.TZ[cons["id"]], cons["office"]
    else:
        name, tz, where = IT.CONSULATE, "Europe/London", "Spanish Consulate General, London"
    item = await IT.guest_booked(ctx["account"], type_="visa", provider_name=name, on=on, at=at, tz=tz, location=where)
    what = "your TIE appointment" if tie else "your consulate appointment"
    if th and not tie:                                       # CR 37 · on the "Move to Madrid" trip, with what to bring
        on_trip = await _on_trip(ctx["account"], on, at, th)
        bring = ", ".join(n for k, n, _, _ in th["checklist"] if k not in ("termination", "accommodation", "school"))
        out.text(("On your “Move to Madrid” trip" if on_trip else "Noted for your trip") + f" — {th['booking']['who']}, "
                 f"{on.strftime('%A %-d %B %Y')} at {at}. Bring, in the consulate's order: {bring}. Your pack: "
                 f"{web()}/api/products/relocation/{ctx['st']['pending'].get('case_id')}/pack.pdf")
    if item:
        out.text(f"Added to your itinerary: {what}, {on.strftime('%A %-d %B %Y')} at {at} — booked by you. I'll remind you the "
                 "day before. Forward their confirmation email to me to add the reference.")
    else:
        out.text(f"Noted: {what}, {on.strftime('%A %-d %B %Y')} at {at}. I couldn't add it to your itinerary just now.")
    return True


async def _on_trip(account: str, on: date, at: str, th: dict) -> bool:
    """CR 37 · the consulate appointment as a dated day on the account's "Move to Madrid" plan (Sasha's plan_store: add_day,
    then the item on it). False when there's no such plan or it can't be reached — the itinerary item stands either way."""
    try:
        from booking_signer import plan_store as PS
        from .move import TITLE
        p = await PS.latest(account, hint=TITLE)
        if not p or (p.get("title") or "") != TITLE:
            return False
        await PS.add_day(account, p["trip_id"], on.isoformat(), th["city"])
        p = await PS.latest(account, hint=TITLE)
        day = next((d.get("day") for d in ((p or {}).get("plan") or {}).get("days") or [] if str(d.get("date") or "")[:10] == on.isoformat()), None)
        if day is None:
            return False
        return await PS.add_place(account, p["trip_id"], day, {"time": PS._part(at), "name": f"Visa appointment — {th['booking']['who']}",
                                                               "blurb": f"{at}. {th['office']}. Bring your pack (EX-01 and 790-052 signed)."})
    except Exception as e:
        log.warning("[relocation] not on the trip: %s: %s", type(e).__name__, e)
        return False


async def _us(ctx: dict, state: str, cid: Optional[str] = None, county: Optional[str] = None) -> bool:
    """CR 12 · the US: the consulate whose OWN territory page names the state; its own list and its own route — or, where
    its page can't be read or publishes nothing, that said plainly."""
    pend, out, now = ctx["st"]["pending"], ctx["out"], ctx["now"]
    f = pend.get("facts") or {}
    f.setdefault("choices", {})["state"] = F.fact(state, "said on WhatsApp", now.strftime("%-d %b %Y"))
    sp = CS.split(state) if not cid else None
    if sp:                                           # California: the published list splits it by county
        pend["us_state"], pend["step"] = state, "us_county"
        out.text(f"{state} is split between two consulates by county. Which county do you live in?")
        return True
    cid = cid or CS.for_state(state)
    base = {"residence": "united states", "state": state, **({"county": county} if county else {})}
    if not cid:
        out.text(f"None of the US consulate pages I could read names {state} in its territory, so I won't guess which "
                 "consulate is yours. It's the Consulado General de España that covers your state, on exteriores.gob.es.")
        await _save(ctx, {"after": {**base, "consulate": None, "unread": CS.unread_offices()}})
        pend["step"] = "entry"
        out.text(ENTRY_Q)
        return True
    if cid in ("newyork", "washington"):                    # CR 37 · read live today (Washington's stored page was New York's)
        from . import three as TH
        await TH.present(ctx, cid, base, web(), _save)
        pend["step"] = "pack"
        out.text(pack_q(TH.items(cid)))
        return True
    c = CS.consulate(cid)
    r = CS.READ[cid]
    terr = CS.territory(cid)
    named = f"{county} County, {state}" if county and county in " ".join(CS.split(state)["counties"] if CS.split(state) else []) else \
        (f"{state} (outside the southern counties the other consulate covers)" if county else state)
    where = f"{terr.get('from', 'its page')}{' (dated ' + terr['dated'] + ')' if terr.get('dated') else ''} names {named}"
    if not c:
        out.text(f"Your consulate is the *{r['office']}* — {where}. But {r['error']}, so I have no checklist from it, and I "
                 f"won't make one up. Its own website: {r['pages'][0]['url'] if r.get('pages') else 'exteriores.gob.es'}")
        await _save(ctx, {"after": {**base, "consulate": None, "consulate_unreadable": {"office": r["office"], "why": r["error"]}}})
        pend["step"] = "entry"
        out.text(ENTRY_Q)
        return True
    items = us_checklist(f, now.date(), cid)
    a = f.get("applicant") or {}
    draft = CS.email_draft(c, {"name": " ".join(x for x in ((a.get("given_names") or {}).get("value"),
                                                               (a.get("surname_1") or {}).get("value"),
                                                               (a.get("surname_2") or {}).get("value")) if x) or None,
                               "contact": " / ".join(x for x in ((a.get("email") or {}).get("value"),
                                                                 (a.get("mobile") or {}).get("value")) if x) or None,
                               "passport": None,   # never put in an email by us: theirs to type
                               "visa": "Visado de residencia no lucrativa"})
    out.text(f"Your consulate: *{c['office']}* — {where}. Its non-lucrative visa page, read {c['source']['read']} "
             f"({c['source']['dated']}).")
    if c["appointment_email"]:
        first = re.split(r"(?<=\.)\s", c["appointment_words"])[0]
        out.text(f"How it takes appointments — its page: “{first}”\nI've drafted that email in Spanish with the details it asks "
                 f"for; you send it from your own address and attach the two PDFs it asks for. I never send it.")
    elif c["appointment_url"]:
        out.text(f"How it takes appointments — its page: “{c['appointment_words'][:300]}”\n{c['appointment_url']}\nYou book it; I don't.")
    else:
        out.text("Its page has the heading “Lugar de presentación” with nothing under it, so I can't tell you how it takes "
                 f"appointments — and I won't guess. Ask the consulate directly: {r['pages'][0]['url']}")
    if not c["localised"]:
        out.text("Its page is the ministry's standard text for this visa, with nothing of its own added — so local details "
                 "(how it books, what it accepts as proof you live there) are the consulate's to tell you.")
    flag = next((i for i in items if i["status"] == "problem"), None)
    out.text(f"Its own list: {len(items)} documents, in its order — its words in Spanish, my short English label beside "
             f"each. On your file page:\n{web()}/relocation-file/{pend.get('case_id')}")
    if flag:
        out.text(f"⚠ {flag['why']}.")
    pend["consulate_office"] = c["office"]   # CR 13 · context for Sasha's travel
    await _save(ctx, {"after": {**base, "consulate": c, "checklist": items, "email_draft": draft}})
    pend["step"] = "pack"
    out.text(pack_q(items))
    return True


def us_checklist(f: dict, today: date, cid: str) -> List[dict]:
    """The consulate's own items, with the two statuses we can compute: the EX-01 (prepared) and the passport's validity
    against the year ITS page asks for."""
    a = f.get("applicant") or {}
    out = []
    for it in CS.checklist(cid):
        it = {**it, "status": "yours", "why": None}
        if it["key"] in CS.prepared_for(cid):          # CR 45 · the visa form and 790 only where Kanoe fills them
            it.update(status="prepared", why="prepared by Kanoe from your answers — you sign it")
        if it["key"] == "passport" and re.search(r"validez m[ií]nima de 1 año", it["words"]):
            exp = (a.get("passport_expiry") or {}).get("value")
            if exp:
                ok = exp >= (today + timedelta(days=365)).isoformat()
                it.update(status="ok" if ok else "problem",
                          why=f"your passport is valid until {exp}: " + ("at least a year from today" if ok else
                              "LESS than a year from today — the consulate's page asks for at least one year"))
        out.append(it)
    return out


async def _pack(ctx: dict, body: str) -> bool:
    """CR 12 · the document pack: what the applicant has gathered, numbered and named in the consulate's own order."""
    pend, out = ctx["st"]["pending"], ctx["out"]
    case = await ST.STORE.get(pend.get("case_id") or "")
    after = ((case or {}).get("state") or {}).get("after") or {}
    cons = after.get("consulate") or {}
    items = after.get("checklist") or []
    items = items if (cons.get("id") or cons.get("three")) else london_items(items)
    if not items:
        out.text("There's no consulate list on your file to build a pack from.")
        return True
    skip = bool(re.match(r"(?i)^\s*skip\b", body))
    have = set() if skip else CS.numbers_in(body, max(i["n"] for i in items))
    if have is None:
        out.text("The numbers of what you've gathered, please — e.g. 1 3 4-6 — or ALL, or SKIP.")
        return True
    pk = CS.pack(items, have, CS.prepared_for(cons.get("three") or cons.get("id")))
    after["pack"] = pk
    await _save(ctx, {"after": after})
    office = cons.get("office", "the consulate")
    mark = {"gathered": "✓", "prepared": "✓", "missing": "☐"}
    lines = "\n".join(f"{mark[x['status']]} {x['name']}" + (f" — {x['copies']}" if x["copies"] and x["status"] != "missing" else "")
                      + (" — still to gather" if x["status"] == "missing" else "") + (" (prepared; you sign it)" if x["status"] == "prepared" else "")
                      for x in pk)
    missing = sum(1 for x in pk if x["status"] == "missing")
    out.text(f"Your document pack, in {office}'s own order — name your files like this and they sort the way it asks:\n{lines}\n"
             + (f"{missing} still to gather. Say PACK and the numbers any time to update it." if missing else "Everything it lists is gathered.")
             + (f"\nIts page, on every foreign document: “{cons['general']}”" if cons.get("general") else ""))
    if pend.get("step") == "pack":
        pend["step"] = "entry"
        out.text(ENTRY_Q)
    return True
