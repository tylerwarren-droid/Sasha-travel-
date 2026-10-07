"""CR 1 · relocation on WhatsApp: the EX-01 (Spain, non-lucrative residence), assembled from the applicant's own words —
one question at a time — checked field by field, and handed back to SIGN and LODGE themselves.

⛔ We never file anything in Spain (AD P807jy:14). ⛔ Section 5 (initial/renewal, holder/family), the Dehú consent and
the signature are never ticked or written by us: the file page shows them as the applicant's. The route the person tells
us (initial or renewal) is kept as THEIR answer for the checklist — it is never turned into a tick on the form.
The model is never called here (documents sent as photos: M3, docread.py).
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime
from typing import Dict, Optional

from .. import store as ST
from . import checker as CK
from . import ex01 as E
from . import facts as F

log = logging.getLogger("products.relocation")

INTRO = ("Relocation to Spain 🇪🇸 — the residence form EX-01 (non-lucrative residence). I assemble it from your answers, "
         "check every field, and hand you the official PDF. *You* sign it and *you* lodge it: I never file anything, and I "
         "never tick or sign the parts that are yours to decide. Ask me anything else at any time — a booking, a flight — and we'll come back to this.")
ROUTE_Q = ("First: is this your *first* application (made from outside Spain, at a consulate) or a *renewal* of a "
           "residence you already hold?")
RESOURCES_Q = "Who holds the economic resources the application relies on — *you*, or a *family member*?"
PRESENTER_Q = "Will you present the application *yourself*, or will a *representative* present it for you?"
NOTICES_Q = "Should official notices go to your own address in Spain (section 4 of the form)? Yes or no."
FICTIONAL = "fictional demo applicant (not a real person)"
DEMO = dict(passport_number="EXAMPLE000", surname_1="Ejemplo", surname_2="Prueba", given_names="Ana", sex="M",
            birth_date="1985-03-14", birth_place="Toronto", birth_country="Canadá", nationality="canadiense",
            passport_expiry="2031-06-30", marital_status="C", father_name="", mother_name="", nie="",
            address_street="Calle de Ejemplo", address_number="12", address_floor="3º B", address_town="Madrid",
            address_postcode="28010", address_province="Madrid", mobile="+34600000000", email="ana.ejemplo@example.com",
            home_address_abroad="100 Example Street, Princeton, NJ 08540, USA", occupation="Retired teacher",   # CR 44 · the Keep's
            passport_issued="2021-06-30", passport_issuer="Passport Canada",
            school_age_children_in_spain="no")


def web() -> str:
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/")


def _on(ctx) -> str:
    return ctx["now"].strftime("%-d %b %Y")


def _said(ctx) -> str:
    return "said on WhatsApp"


# EU 153 (founder, 4 Oct): phone line and utilities belong to RelocateMe — a CONCEPT, said as one, the file untouched
UTILITIES = re.compile(r"(?i)\b(movistar|phone line|mobile line|internet|home internet|fibre|fiber|wifi|utilities|electricity|"
                       r"gas and water|water bill|bank account|spanish bank|open (?:a )?bank|setting up (?:my|your|the) home)\b")
# CR 17 · "setting up your home" (moved here from EspañaMe by the founder): a CONCEPT, said as one
UTILITIES_CONCEPT = ("🏠 *Setting up your home* — your phone and internet (e.g. Movistar), electricity, and a Spanish bank account. "
                     "CONCEPT, not built yet, and no provider's or bank's pages have been read, so no plans, prices or "
                     "requirements here. The idea: I read each one's own pages, show you what each asks for, and prepare the "
                     "sign-up for you to press.")


async def turn(ctx: dict, body: str, payload: str, *, entering: bool) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    if body and UTILITIES.search(body) and not payload:
        out.text(UTILITIES_CONCEPT)
        if pend.get("last_said"):
            out.text(pend["last_said"])            # and where the file was, asked again
        return
    f = pend.setdefault("facts", {"applicant": {}, "choices": {}})
    if entering and not pend.get("step"):
        pend["step"] = "route"
        from .. import steps as STP                   # CR 52 · one short opening, the rest behind "More"
        STP.stash(pend, "intro", [INTRO])
        if not body:
            out.ask("RelocateMe 🇪🇸 — I fill Spain's residence forms with you; you sign and lodge them — I never file anything.\n"
                    "Is this your *first* application, or a renewal?", [("First application", "rx:route:first"), ("Renewal", "rx:route:renewal"),
                                                    STP.more("rx:", "intro")])
            return
    if ctx.get("media") and pend.get("step") not in ("done",):
        from . import docread
        if await docread.on_media(ctx, f):
            return
    step = pend.get("step")
    t = (body or "").strip()
    from .. import steps as STP
    if STP.is_more(payload or "", "rx:") and step in ("route", "resources", "presenter", "facts", "notices", "prepared", "doc_confirm"):
        STP.show(pend, STP.is_more(payload, "rx:"), out)
        return
    if payload.startswith("rx:route:"):               # CR 52 · the opening's buttons
        t = payload[9:]
    if step == "doc_confirm":
        from . import docread
        await docread.on_confirm(ctx, f, t, payload)
        return
    if re.fullmatch(r"(?i)demo", t) and step not in ("prepared", "signed", "done"):
        for k, v in DEMO.items():
            f["applicant"].setdefault(k, F.fact(v, FICTIONAL, _on(ctx)))
        f["choices"].setdefault("route", F.fact("initial", FICTIONAL, _on(ctx)))
        f["choices"].setdefault("resources", F.fact("self", FICTIONAL, _on(ctx)))
        f["choices"].setdefault("presenter", F.fact("self", FICTIONAL, _on(ctx)))
        f["choices"].setdefault("notices_to_own_address", F.fact("yes", FICTIONAL, _on(ctx)))
        out.text("Filled the rest with a *fictional* applicant, Ana Ejemplo Prueba — every value says so on the file.")
        await _prepare(ctx)
        return
    if step == "route":
        if re.search(r"(?i)\bfirst|initial|inicial|primer|new\b", t):
            f["choices"]["route"] = F.fact("initial", _said(ctx), _on(ctx))
        elif re.search(r"(?i)renew|renovaci", t):
            f["choices"]["route"] = F.fact("renewal", _said(ctx), _on(ctx))
            out.text("Noted: a renewal. Renewals are lodged electronically only (the form's footnote 6). Whether a renewal "
                     "uses this same form isn't something I've established — I'll prepare it, and the checklist says so.")
        else:                                                 # CR 40 · "not sure": the difference, not the same question
            out.text("A *first* application is made from outside Spain, in person at the Spanish consulate for where you live — "
                     "you don't hold this residence yet. A *renewal* is for someone already living in Spain on it. Which is yours: "
                     "first or renewal?")
            return
        pend["step"] = "resources"
        out.text(RESOURCES_Q)
        return
    if step in ("resources", "presenter") and re.search(r"(?i)\b(actually|no,? it'?s|wait)\b.*\b(renew\w*|renovaci\w*|first|primer\w*)", t):
        pend["step"] = "route"                                # CR 40 · a change of mind about the route: taken, never lectured
        return await turn(ctx, re.sub(r"(?i)^.*?\b(actually|no,? it'?s|wait)\b", "", t), payload, entering=False)
    if step == "resources":
        if re.search(r"(?i)\b(me|myself|i do|mine|yo)\b", t):
            f["choices"]["resources"] = F.fact("self", _said(ctx), _on(ctx))
        elif re.search(r"(?i)family|spouse|wife|husband|partner|parent|familiar", t):
            f["choices"]["resources"] = F.fact("family", _said(ctx), _on(ctx))
            out.text("Then section 2 is about that family member. This first version asks only about you; section 2 stays "
                     "blank on the file and the reviewer marks it as still to do.")
        else:
            out.text(RESOURCES_Q)
            return
        pend["step"] = "presenter"
        out.text(PRESENTER_Q)
        return
    if step == "presenter":
        if re.search(r"(?i)\b(me|myself|yourself|i will|i'll|yo)\b", t):
            f["choices"]["presenter"] = F.fact("self", _said(ctx), _on(ctx))
        elif re.search(r"(?i)represent|lawyer|abogad|gestor|someone", t):
            f["choices"]["presenter"] = F.fact("representative", _said(ctx), _on(ctx))
            out.text("Then section 3 is your representative's to complete, with proof they may act for you. I leave it blank "
                     "and the file says why.")
        else:
            out.text(PRESENTER_Q)
            return
        pend["step"] = "facts"
        from . import keep as KP
        kept = await KP.item(ctx["account"])                     # CR 44 · asked once, ever: a kept record fills this file
        if kept:
            pend.update(step="keep_use", keep_id=str(kept["id"]))
            out.ask(f"Your details are kept in your vault (“{KP.LABEL}”). Fill this file from them? I open them only under "
                    "your yes, and you check every value on the form.", [("Yes, use them", "rx:keep:use"), ("No, ask me", "rx:keep:ask")])
            return
        out.text("Now your details, as your passport shows them. (Or send a photo of your passport's photo page and I'll "
                 "read it — you confirm each value. Type DEMO to use a fictional applicant.)")
        _next_question(pend, out)
        return
    if step == "keep_use":
        from . import keep as KP
        if payload == "rx:keep:use" or (not payload and re.match(r"(?i)^\s*(yes|y|sí|si|ok|use)\b", t)):
            try:
                n = await KP.open_into(ctx["account"], pend["keep_id"], f, KP.approval(ctx["now"], "button" if payload else "text", t),
                                       _on(ctx))
                out.text(f"Filled {n} answers from your Keep — I'll ask only what's missing.")
            except Exception as e:
                log.warning("[relocation] keep not opened: %s", type(e).__name__)
                out.text("I couldn't open your Keep just now — I'll ask instead.")
        pend["step"] = "facts"
        _next_question(pend, out)
        if pend["step"] == "notices_done":
            await _keep_then_prepare(ctx)
        return
    if step == "facts":
        k = pend.get("asking")
        q = next((x for x in F.APPLICANT if x[0] == k), None)
        if q:
            v, bad = q[2](t)
            if bad:
                out.text(bad)
                return
            f["applicant"][k] = F.fact(v, _said(ctx), _on(ctx))
        _next_question(pend, out)
        if pend["step"] == "notices_done":
            await _keep_then_prepare(ctx)
        return
    if step == "notices":
        v, bad = F._yesno(t)
        if bad:
            out.text(NOTICES_Q)
            return
        f["choices"]["notices_to_own_address"] = F.fact(v, _said(ctx), _on(ctx))
        await _keep_then_prepare(ctx)
        return
    if step == "keep_offer":
        from . import keep as KP
        if payload == "rx:keep:yes" or (not payload and re.match(r"(?i)^\s*(yes|y|sí|si|ok|keep)\b", t)):
            if await KP.save(ctx["account"], f):
                out.text(f"Kept in your vault as “{KP.LABEL}” — the next form is one yes.")
            else:
                out.text("I couldn't keep them just now — nothing was saved; this file is unaffected.")
        await _prepare(ctx)
        return
    if step == "prepared" and (payload == "rx:signed" or re.match(r"(?i)^\s*(signed|i signed|firmado)\b", t)):
        from . import after
        await after.signed(ctx)
        return
    if step in ("prepared", "signed", "residence", "us_state", "us_county", "pack", "entry", "appointments", "done", "walk") \
            or (payload or "").startswith(("rx:go:", "rx:more:")):                    # CR 52 · a step's buttons, anywhere
        from . import after
        if await after.on_message(ctx, t, payload):
            return
    if step is None:
        pend["step"] = "route"
        out.text(ROUTE_Q)
        return
    return False   # CR 10 · not relocation's: Sasha answers it


def _next_question(pend: dict, out) -> None:
    f = pend["facts"]
    left = F.questions_for(f["applicant"])
    if left:
        pend["asking"] = left[0][0]
        out.text(left[0][1])
        return
    pend["asking"] = None
    if f["applicant"].get("address_street", {}).get("value"):
        pend["step"] = "notices"
        out.text(NOTICES_Q)
    else:
        f["choices"]["notices_to_own_address"] = F.fact("no", "you have no address in Spain yet", "")
        pend["step"] = "notices_done"


def applies(f: dict) -> Dict[str, bool]:
    c = f.get("choices") or {}
    return {"2": (c.get("resources") or {}).get("value") == "family",
            "3": False,   # a representative completes their own section: never filled from the applicant's answers
            "legal_rep": False}


async def _keep_then_prepare(ctx: dict) -> None:
    """CR 44 · once, before the first form: may these details be kept, so no form ever asks them again? A fictional applicant,
    or details that came from the Keep, are not offered."""
    from . import keep as KP
    pend, out = ctx["st"]["pending"], ctx["out"]
    a = pend["facts"].get("applicant") or {}
    own = any(x.get("source") not in (FICTIONAL, KP.SOURCE) for x in a.values())
    if own and not any(x.get("source") == FICTIONAL for x in a.values()) and not pend.get("keep_offered") \
            and not await KP.item(ctx["account"]):
        pend.update(step="keep_offer", keep_offered=True)
        out.ask("Keep these details in your vault (encrypted, deletable any time)? Every RelocateMe form — the visa form, EX-01, "
                "EX-17, padrón, Social Security — fills from them, and I never ask again.",
                [("Yes, keep them", "rx:keep:yes"), ("Just this file", "rx:keep:no")])
        return
    await _prepare(ctx)


async def _prepare(ctx: dict) -> None:
    pend, out, now = ctx["st"]["pending"], ctx["out"], ctx["now"]
    f = pend["facts"]
    rows = CK.review(E.rows(f, applies(f)), f, now.date())
    E.fill(rows)   # the guard runs here too: an irreducible value would raise before anything is kept
    c, s = E.counts(rows), CK.summary(rows)
    case = {"facts": f, "rows": rows, "counts": c, "checks": s, "status": "prepared", "prepared_at": now.isoformat(),
            "route": (f["choices"].get("route") or {}).get("value"), "fictional": any(
                x.get("source") == FICTIONAL for x in f["applicant"].values())}
    cid = pend.get("case_id")
    if cid and await ST.STORE.get(cid):
        await ST.STORE.update(cid, case)
    else:
        cid = await ST.STORE.put("relocation", ctx["account"], ctx["ch"]["wa_id_sha256"], case)
    pend.update(step="prepared", case_id=cid)
    link = f"{web()}/relocation-file/{cid}"
    verdict = (f"The reviewer checked every field: {s['ok']} fine, {s['check']} to look at, {s['problem']} problem"
               f"{'s' if s['problem'] != 1 else ''}.")
    from .. import formcard as FC                     # CR 33 · page 1 as a card, the filled boxes highlighted
    from .. import steps as STP                       # CR 52 · one step: the card, one line, what's next; the rest behind "More"
    FC.show(out, "Your EX-01, page 1 — highlighted: what I filled. Not signed, not filed.",
            f"{web()}/api/products/relocation/{cid}/EX-01-card.jpg", f"{web()}/api/products/relocation/{cid}/EX-01-prepared.pdf")
    STP.stash(pend, "ex01", [f"{verdict} The official PDF is on that page too.",
                             "Left for you: section 5, the Dehú consent, the place and date, and your signature in the FIRMA box."])
    out.ask(f"✅ Your EX-01 is ready: {c['filled']} boxes filled, {c['prepared_not_adopted']} left for you. Check it field by "
            f"field:\n{link}\nThen print it, sign it, and reply SIGNED.", [("I've signed it", "rx:signed"), STP.more("rx:", "ex01")])


# ── CR 10 · one Sasha: is this message an answer to relocation's own question? And what context goes to Sasha ──────

def claims(pend: dict, body: str, payload: str, media: list) -> bool:
    step, t = pend.get("step"), (body or "").strip()
    if UTILITIES.search(t):
        return True
    if payload.startswith("rx:") or (media and step not in (None, "done")):
        return True
    if re.fullmatch(r"(?i)demo", t) and step not in (None, "prepared", "signed", "residence", "us_state", "us_county", "pack", "entry", "done"):
        return True
    if step == "route":
        return bool(re.search(r"(?i)\bfirst|initial|inicial|primer|new\b|renew|renovaci", t))
    if step == "resources":
        return bool(re.search(r"(?i)\b(me|myself|i do|mine|yo)\b|family|spouse|wife|husband|partner|parent|familiar", t))
    if step == "presenter":
        return bool(re.search(r"(?i)\b(me|myself|yourself|i will|i'll|yo)\b|represent|lawyer|abogad|gestor|someone", t))
    if step == "facts":
        q = next((x for x in F.APPLICANT if x[0] == pend.get("asking")), None)
        return bool(q) and q[2](t)[1] is None
    if step == "notices":
        return F._yesno(t)[1] is None
    if step in ("keep_use", "keep_offer"):                # CR 44
        return bool(re.match(r"(?i)^\s*(yes|y|no|n|sí|si|ok|use|keep)\b", t))
    if step == "doc_confirm":
        return bool(re.match(r"(?i)^\s*(yes|no|y|n|sí|si)\b", t))
    if step in ("prepared", "signed", "entry", "appointments", "pack", "done"):   # CR 44 · after arrival, an NIE
        from . import arrival as AR
        if AR.ARRIVAL.search(t) or AR.NIE_SAID.search(t):
            return True
    if step == "prepared":
        return bool(re.match(r"(?i)^\s*(signed|i signed|firmado)\b", t))
    if step == "residence":
        return 0 < len(t.split()) <= 4 and not re.search(r"\d", t)
    if step in ("us_state", "us_county"):          # CR 12
        return 0 < len(t.split()) <= 4 and not re.search(r"\d", t)
    if step == "pack" or re.match(r"(?i)^\s*pack\b", t) and step in ("entry", "appointments", "done"):
        from . import consulates as CS
        return bool(re.match(r"(?i)^\s*(pack\b|skip\b)", t)) or CS.numbers_in(t, 30) is not None
    if step == "entry":
        return bool(F.parse_date(t)) or bool(re.match(r"(?i)^\s*skip\b", t))
    if step == "appointments":
        from .. import itinerary as IT
        from datetime import date as _date
        return bool(re.search(r"(?i)\b(booked|appointment|cita|consulate|consulado|tie|huellas?)\b", t)) and \
            IT.parse_day_time(t, _date.today()) is not None
    return False


def context(pend: dict) -> dict:
    """Minimum necessary for Sasha's other skills: where, when, who — never a passport fact."""
    f = pend.get("facts") or {}
    a = f.get("applicant") or {}
    town = (a.get("address_town") or {}).get("value") or "Madrid"
    name = " ".join(x for x in ((a.get("given_names") or {}).get("value"), (a.get("surname_1") or {}).get("value")) if x)
    street = " ".join(x for x in ((a.get("address_street") or {}).get("value"), (a.get("address_number") or {}).get("value")) if x)
    address = f"{street}, {town}, Spain" if street else None
    entry = pend.get("entry_date")
    return {"product": "relocation", "city": town, "country": "Spain", "dates": [d for d in [entry] if d],
            "name": name or None, "applicant": name or None, "entry_date": entry, "address": address,   # CR 13
            "consulate": pend.get("consulate_office"),
            "trip_hint": {"to_city": town, "around_date": entry,
                          "nights_near": [{"place": address or f"{town}, Spain", "night_before": None, "from": entry}] if entry else []}, "line": f"[Relocation: moving to {town}, Spain"
            + (f"; planned entry {pend['entry_date']}" if pend.get("entry_date") else "")
            + (f"; applicant {name}" if name else "") + "]"}
