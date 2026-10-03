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

from .. import store as ST
from . import facts as F

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
        if key == "ex01":
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


def reminders(entry: Optional[str], today: date) -> List[dict]:
    """From the sheet's own dates: apply from 90 days before entry; the two certificates no older than 3 months when you
    apply; the TIE within a month of entering Spain."""
    if not entry:
        return []
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
    if step == "residence":
        residence = "united kingdom" if _UK.search(body) else F.fold(body).strip(" .")
        c = CONSULATES.get(residence)
        f.setdefault("choices", {})["residence"] = F.fact(residence, "said on WhatsApp", now.strftime("%-d %b %Y"))
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
            await _save(ctx, {"after": {"residence": residence, "consulate": c, "checklist": items}})
        pend["step"] = "entry"
        out.text("When do you plan to enter Spain? (a date, e.g. 1 March 2027 — or SKIP)")
        return True
    if step == "entry":
        if re.match(r"(?i)^\s*skip\b", body):
            pend["step"] = "done"
            out.text("OK — no reminders. Your file page has everything. Say EXIT to go back to Sasha.")
            return True
        d = F.parse_date(body)
        if not d or d <= now.date().isoformat():
            out.text("A future date please, like 1 March 2027 — or SKIP.")
            return True
        rs = reminders(d, now.date())
        case = await ST.STORE.get(pend.get("case_id") or "")
        after = (case or {}).get("state", {}).get("after") or {}
        await _save(ctx, {"after": {**after, "entry_date": d, "reminders": rs,
                                    "wa": ctx["ch"]["wa_id_sha256"], "number_from": ctx["frm"]}})
        pend["step"] = "done"
        lines = "\n".join(f"• {date.fromisoformat(r['on']).strftime('%-d %b %Y')}: {r['text'].split(' — ')[0].split(': ')[0]}"
                          for r in rs)
        out.text(f"I'll remind you here:\n{lines}\n(WhatsApp lets me write first only within 24 hours of your last message; "
                 "otherwise the reminder waits for your next message, and it's always on your file page.)")
        return True
    out.text("Your file and checklist are on your file page. Say EXIT to go back to Sasha.")
    return True


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
            ch = await GW.STORE.channel_for(after.get("wa", ""))
            st = await GW.STORE.get_state(after.get("wa", "")) if ch else {}
            res = await GW.deliver(ch, after.get("number_from"), GW.Out().text("🇪🇸 " + r["text"]), st.get("last_inbound_at")) \
                if ch else ["no channel"]
            if res and all(x == "sent" for x in res):
                r["sent"] = True
                sent += 1
        await ST.STORE.update(c["id"], c["state"])
    return sent
