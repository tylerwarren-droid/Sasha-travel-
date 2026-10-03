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
         "never tick or sign the parts that are yours to decide. Say EXIT at any time to go back to Sasha.")
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
            school_age_children_in_spain="no")


def web() -> str:
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/")


def _on(ctx) -> str:
    return ctx["now"].strftime("%-d %b %Y")


def _said(ctx) -> str:
    return "said on WhatsApp"


async def turn(ctx: dict, body: str, payload: str, *, entering: bool) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    f = pend.setdefault("facts", {"applicant": {}, "choices": {}})
    if entering and not pend.get("step"):
        out.text(INTRO)
        pend["step"] = "route"
        if not body:
            out.text(ROUTE_Q)
            return
    if ctx.get("media") and pend.get("step") not in ("done",):
        from . import docread
        if await docread.on_media(ctx, f):
            return
    step = pend.get("step")
    t = (body or "").strip()
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
        if re.search(r"(?i)\bfirst|initial|inicial|new\b", t):
            f["choices"]["route"] = F.fact("initial", _said(ctx), _on(ctx))
        elif re.search(r"(?i)renew|renovaci", t):
            f["choices"]["route"] = F.fact("renewal", _said(ctx), _on(ctx))
            out.text("Noted: a renewal. Renewals are lodged electronically only (the form's footnote 6). Whether a renewal "
                     "uses this same form isn't something I've established — I'll prepare it, and the checklist says so.")
        else:
            out.text(ROUTE_Q)
            return
        pend["step"] = "resources"
        out.text(RESOURCES_Q)
        return
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
        out.text("Now your details, as your passport shows them. (Or send a photo of your passport's photo page and I'll "
                 "read it — you confirm each value. Type DEMO to use a fictional applicant.)")
        _next_question(pend, out)
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
            await _prepare(ctx)
        return
    if step == "notices":
        v, bad = F._yesno(t)
        if bad:
            out.text(NOTICES_Q)
            return
        f["choices"]["notices_to_own_address"] = F.fact(v, _said(ctx), _on(ctx))
        await _prepare(ctx)
        return
    if step == "prepared" and re.match(r"(?i)^\s*(signed|i signed|firmado)\b", t):
        from . import after
        await after.signed(ctx)
        return
    if step in ("prepared", "signed", "residence", "entry", "done"):
        from . import after
        if await after.on_message(ctx, t, payload):
            return
    if step is None:
        pend["step"] = "route"
        out.text(ROUTE_Q)
        return
    out.text("Say EXIT to go back to Sasha, or answer the question above.")


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
    out.text(f"✅ Your EX-01 is prepared: {c['filled']} boxes filled from your answers, each naming its source; "
             f"{c['prepared_not_adopted']} left for you (section 5, the Dehú consent, your signature).")
    verdict = (f"The reviewer checked every field: {s['ok']} fine, {s['check']} to look at, {s['problem']} problem"
               f"{'s' if s['problem'] != 1 else ''}.")
    out.text(f"{verdict} Read it field by field here, with the official PDF to download:\n{link}")
    out.media("The official EX-01, prepared — not signed, not filed.", f"{web()}/api/products/relocation/{cid}/EX-01-prepared.pdf")
    out.text("When you've checked it: print it, complete section 5 yourself, decide on the Dehú consent, write the place "
             "and date, and sign in the FIRMA box. Reply SIGNED when that's done.")
