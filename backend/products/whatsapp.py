"""CR 1 → CR 10 · ONE SASHA, NOT ROOMS: CampusMe, relocation and health are SKILLS inside Sasha's one conversation.

Who answers a message (product_turn; True = a product answered, False = Sasha's own flow runs, in the same chat):
  1. a product's own BUTTON (cm…, rx:, hx…) or its KEYWORD at the start ("campus…", "relocation…", "salud…") → that
     product — started, or RESUMED where it was;
  2. the product ASKED LAST (Sasha's `pending` holds the product marker): an answer to its own question (its claims())
     → the product; a request Sasha's own detectors claim (a booking, a cancel, receipts, flights, a hotel…) → SASHA;
     her parsers may read context(wa_key) (minimum necessary: where, when, who — never a passport fact, never a health
     reason; nothing is written into her history); anything else → the product re-asks, plainly — never a wall;
  3. SASHA asked last (her own `pending`) → Sasha;
  4. nobody is waiting: a product set aside within MODE_IDLE resumes only if the message answers its question.
A product's state lives in product_cases ("conversation" rows), so Sasha's flow may use `pending` freely and the product
picks up exactly where it was. EXIT still ends a product, but it is never advertised.

⚠ DEMO DEVICE: production needs one WhatsApp number per product (Meta: one display name per number; CR-1-spec.md §1).
Called from booking_signer/guest_whatsapp.turn() — the guarded block marked "CR 1 products".
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

log = logging.getLogger("products.whatsapp")
MODE_IDLE = timedelta(hours=6)
#: Sasha 194 · STRICT SPACES (the founder, 7 Oct): a space is entered and left ONLY by its word or its button; inside a space every
#: request is that space's; outside, only a word enters one. No automatic switching either way. SASHA_SPACES=loose restores the old.
STRICT = os.getenv("SASHA_SPACES", "strict") != "loose"

_CAMPUS = re.compile(r"^\s*(campus\s*me|campusme|campus)\b", re.I)
_RELOC = re.compile(r"^\s*(relocation|relocate|relocating|reloc|ex-?01|residencia)\b", re.I)
_HEALTH = re.compile(r"^\s*(salud|health|sanidad|m[eé]dico\s+en\s+madrid|espa[nñ]a\s*me|espa[nñ]ame|espa[nñ]a)\b", re.I)
_DILIGENCE = re.compile(r"^\s*(applied\s+diligence|diligence|ad)(?![\w'’-])", re.I)   # CR 15 · AD preview; never "add", "Ad-hoc"
_AD_SHORT = re.compile(r"^\s*ad(?![\w'’-])", re.I)
_ESPANA = re.compile(r"^\s*(espa[nñ]a\s*me|espa[nñ]ame|espa[nñ]a)\b", re.I)   # CR 15 · EspañaMe: the health demo + concepts
_LATER = re.compile(r"^\s*(later|not now|another time|luego|m[aá]s tarde|despu[eé]s)\s*[.!]?\s*$", re.I)   # CR 30 · kept, set aside
_RESUME_WORD = {"relocation": "relocation", "campus": "campus", "health": "españa", "trip": "trip", "diligence": "diligence"}
_EXIT = re.compile(r"^\s*(exit|sasha|back|back to sasha|quit|salir)\s*[.!]?\s*$", re.I)



_KEYWORD = {"campus": _CAMPUS, "relocation": _RELOC, "health": _HEALTH, "diligence": _DILIGENCE}
#: Sasha 170 · START OVER: "start over", "restart relocate", "reset campus", "empezar de nuevo españa", "start over sasha" — the
#: named product (else the one asked last, else Sasha) starts from the beginning: its saved conversation is dropped, never
#: answered as a reply to its last question (live: "reset" in RelocateMe got its checklist question again)
_START_OVER = re.compile(r"^\s*(?:please\s+)?(?:start(?:\s+(?:it|again|over))?\s+over|start\s+again|restart|reset|begin\s+again|from\s+the\s+(?:start|beginning)|"
                         r"empezar\s+de\s+nuevo|empieza\s+de\s+nuevo|volver\s+a\s+empezar|reiniciar|de\s+cero)"
                         r"(?:\s+(?:the\s+|with\s+|en\s+|con\s+)?(?P<what>[a-zñáéíóú ]{2,30}?))?\s*[.!]?\s*$", re.I)
_START_NAME = [("relocation", re.compile(r"(?i)\b(relocat\w*|relocation|ex-?01)\b")), ("campus", re.compile(r"(?i)\bcampus(?:\s*me)?\b")),
               ("health", re.compile(r"(?i)\b(espa[nñ]a(?:\s*me)?|health|salud)\b")), ("sasha", re.compile(r"(?i)\b(sasha|bookings?|chat)\b"))]
START_WORD = {"relocation": "relocation", "campus": "campus", "health": "españa"}
PRODUCT_NAME = {"relocation": "RelocateMe", "campus": "CampusMe", "health": "EspañaMe"}


def _lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def typo_keyword(body: str) -> Optional[str]:
    """One word, one or two letters off a product's own word (never a real word of Sasha's) → that product."""
    w = (body or "").strip().lower().strip(".!?")
    if not w or " " in w or len(w) < 5:
        return None
    for prod, words in (("relocation", ("relocation", "relocate")), ("campus", ("campus", "campusme")),
                        ("health", ("españa", "espana", "españame"))):
        if any(0 < _lev(w, x) <= (1 if len(x) <= 6 else 2) for x in words):
            return prod
    return None


async def reset_modes(account: str) -> int:
    """CR 39 · "reset the demo" (the founder's, called from Sasha's reset): every product conversation on the account is
    closed — each opens on its opener next time. The files themselves (cases: the EX-01, the tour, the health card) are kept."""
    from . import store as ST
    n = 0
    for r in await ST.STORE.conversations(f"acct:{account}"):
        await ST.STORE.drop_conversation(f"acct:{account}", r["product"])
        n += 1
    for r in await ST.STORE.conversations(f"web:{account}"):
        await ST.STORE.drop_conversation(f"web:{account}", r["product"])
        n += 1
    return n


def start_over(body: str) -> Optional[str]:
    """"" for a bare "start over"; the product named ("relocation" | "campus" | "health" | "sasha"); None when it isn't one —
    "reset the demo" is Sasha's own command, not this."""
    m = _START_OVER.match(body or "")
    if not m:
        return None
    w = (m["what"] or "").strip()
    if not w:
        return ""
    return next((k for k, rx in _START_NAME if rx.search(w)), None)
PREFIX = {"campus": ("cm:", "cmyes:", "cmno:"), "relocation": ("rx:",), "health": ("hx:", "hxyes:", "hxno:", "hxv:", "hxvno:"),
          "trip": ("tp:",), "diligence": ("ad:",)}
_FLIGHT = re.compile(r"\b(flights?|fly(?:ing)? (?:to|from)|plane|airfare|vuelos?|volar|avi[oó]n|hotel|hostel|apartment|car hire|rent a car)\b", re.I)


def _module(product: str):
    if product == "campus":
        from .campus import turn as M
    elif product == "health":
        from .health import turn as M
    elif product == "trip":                 # CR 13 · the plan that hands bookings to Sasha's travel flow
        from . import trip as M
    elif product == "diligence":            # CR 15 · the AD preview
        from . import diligence as M
    else:
        from .relocation import turn as M
    return M


# CR 20 (5) · words that only mean something with the product's context: "near my hotel", "on arrival"…
_REL = re.compile(r"(?i)\b(near (?:my|the) hotel|near where i(?:'m| am) staying|on (?:my )?arrival|when i (?:arrive|land|get there)|"
                  r"the day i arrive|on my first (?:day|night)|near (?:my|the) (?:new )?(?:address|flat|apartment|home|place|campus))\b")
_BACK = {"relocation": "“relocation”", "campus": "“campus”", "health": "“españa”", "trip": "NEXT"}


async def _in_context(ch: dict, product: Optional[str], pend: dict, body: str, now) -> Optional[tuple]:
    """A booking asked from inside a product, in words that need its context: rewritten with the product's own city, date and
    place, as a sentence Sasha's booking flow parses ("book me a 60-minute massage in Madrid near Hotel X on 2027-03-01").
    → (sentence, the line said first) or None (nothing to fill in: Sasha gets the guest's own words). Nothing invented:
    a date the product doesn't know is left for Sasha to ask."""
    if not product or not _REL.search(body or ""):
        return None
    from booking_signer import handoff as HO
    from datetime import date as _date, timedelta as _td
    from . import itinerary as IT
    f = HO.find_request(body, now) or {}
    what = f.get("what")
    if not what:
        return None
    city, on, place, why = None, None, None, ""
    if product == "relocation":
        a = (pend.get("facts") or {}).get("applicant") or {}
        city = (a.get("address_town") or {}).get("value") or "Madrid"
        street = " ".join(x for x in ((a.get("address_street") or {}).get("value"), (a.get("address_number") or {}).get("value")) if x)
        if pend.get("entry_date"):
            on, why = _date.fromisoformat(pend["entry_date"]), "your entry date"
        place = street or None
    elif product in ("campus", "trip"):
        from . import trip as TP
        vs = await TP._visits(ch["account_id"])
        if vs:
            city = vs[0]["city"].split(",")[0]
            on, why = _date.fromisoformat(vs[0]["day"]) - _td(days=1), f"the day before {vs[0]['name']}"
            place = vs[0]["full_name"]
    elif product == "health":
        city = "Madrid"
    if not city:
        return None
    hotel = await IT.hotel_on(ch["account_id"], on) if on else None
    near = hotel or place
    sentence = re.sub(r"(?i)^\s*(.*?)\b" + re.escape(what) + r".*$", lambda m: m.group(1), body).strip() or "book me"
    sentence = f"{sentence} {what} in {city}" + (f" near {near}" if near else "") + (f" on {on.isoformat()}" if on else "")
    where = f"in {city}" + (f", near {'your hotel, ' + hotel if hotel else near}" if near else "") + \
        (f", on {on.strftime('%a %-d %b %Y')} ({why})" if on else "")
    line = (f"{what[0].upper() + what[1:]} {where} — Sasha's booking takes it from here, one yes as always. When it's done, "
            f"say {_BACK.get(product, 'what’s next')} to come back to where we were.")
    return sentence, line


def for_sasha(body: str, history: list, now) -> bool:
    """Sasha's OWN detectors (guest_whatsapp's scope gate), read-only: would her flow take this message?"""
    from booking_signer import guest_whatsapp as GW, handoff as HO
    t = body or ""
    try:
        if not t.strip():
            return False
        if GW.cancel_intent(t) is not None or GW._RECEIPTS.search(t) or _FLIGHT.search(t) or GW.COMBO.search(t) \
                or GW.ITINERARY_Q.search(t):   # CR 20 · "what do I have on 12 November?" is Sasha's itinerary, never a re-ask
            return True
        if HO.booking_handoff(t, history or []) is not None:
            return True
        from booking_signer.chat_request import booking_turn
        if booking_turn(t, history or []) is not None:
            return True
        return bool(GW.maybe_booking(t))
    except Exception as e:   # a detector failing never strands the message: Sasha's flow gets it
        log.error("[products] a Sasha detector failed (%s): handing the message to Sasha", type(e).__name__)
        return True


def _key(ch: dict) -> str:
    """CR 20 · ONE conversation per ACCOUNT, whichever channel the guest types on (WhatsApp, the web tab): the product's
    state lives here, keyed by the account — never by the phone number or the browser — so a file started on the phone
    continues on the laptop at the same question, with the same answers."""
    return f"acct:{ch['account_id']}"


async def _key_of(wa_key: str) -> Optional[str]:
    """The account key behind a channel key (Sasha's parsers call context() with the WhatsApp key)."""
    if wa_key.startswith("acct:"):
        return wa_key
    if wa_key.startswith("web:"):
        return "acct:" + wa_key[4:]
    from booking_signer import guest_whatsapp as GW
    ch = await GW.STORE.channel_for(wa_key)
    return _key(ch) if ch else None


async def reach(wa: str, frm: Optional[str], account: Optional[str]):
    """CR 20 · where a product's reminder goes: the WhatsApp channel the case started on, or — for a case started on the
    web tab — the same account's linked WhatsApp. → (channel, its key, the number we send from) or (None, None, None)."""
    from booking_signer import guest_whatsapp as GW
    ch = await GW.STORE.channel_for(wa) if wa and not wa.startswith(("web:", "acct:")) else None
    if ch:
        return ch, wa, frm
    if account and hasattr(GW.STORE, "channel_of_account"):
        ch = await GW.STORE.channel_of_account(account)
        if ch:
            nums = sorted(GW.guest_numbers())
            return ch, ch["wa_id_sha256"], (frm if frm and frm != "web" else (nums[0] if nums else None))
    return None, None, None


async def _set_aside(st: dict, ch: dict) -> Optional[dict]:
    """The product that asked last steps aside: its state is kept (product_cases), Sasha's `pending` is hers again, and
    ONE context line joins her history. Returns the context."""
    from . import store as ST
    pend = st.get("pending") or {}
    product = pend.get("product")
    if not product:
        return None
    await ST.STORE.put_conversation(_key(ch), ch["account_id"], product, pend)
    st["pending"] = None          # Sasha's again; her history is NOT written to (Sasha tab, CR 10: context() only)
    return _module(product).context(pend)


async def _resume(ch: dict, product: str) -> Optional[dict]:
    from . import store as ST
    for r in await ST.STORE.conversations(_key(ch)):
        if r["product"] == product:
            return r["state"].get("pending")
    return None


async def _waiting(ch: dict, now) -> list:
    """Set-aside products touched within MODE_IDLE, most recent first: (product, pending)."""
    from . import store as ST
    out = []
    for r in await ST.STORE.conversations(_key(ch)):
        pend = r["state"].get("pending") or {}
        try:
            fresh = now - datetime.fromisoformat(pend.get("touched")) <= MODE_IDLE
        except (TypeError, ValueError):
            fresh = False
        if fresh and pend.get("step") not in (None, "done") and not pend.get("parked"):   # parked: only its word resumes it
            out.append((r["product"], pend))
    return out


async def context(wa_key: str) -> Optional[dict]:
    """For Sasha's parsers (e.g. a default city): the most recently touched product conversation's context, or None.
    Minimum necessary — where, when, who; never a passport fact, never a health reason. Read-only."""
    from . import store as ST
    key = await _key_of(wa_key)
    rows = await ST.STORE.conversations(key) if key else []
    best = max(rows, key=lambda r: (r["state"].get("pending") or {}).get("touched") or "", default=None)
    if not best:
        return None
    c = _module(best["product"]).context(best["state"].get("pending") or {})
    if best["product"] == "campus":                       # CR 13 · every visit of the account, not just the one chosen
        from . import trip as TP
        vs = await TP._visits(best["account_id"])
        first_names = [r["state"].get("student_first") for r in await ST.STORE.of_account(best["account_id"], "campus")
                       if r["state"].get("student_first")]
        c.update(visits=[{k: v[k] for k in ("name", "day", "start", "location", "city")} | {"school": v["name"]} for v in vs],
                 student=first_names[0] if first_names else None,
                 trip_hint={"to_city": vs[0]["city"].split(",")[0] if vs else None,
                            "around_date": vs[0]["day"] if vs else None,
                            "nights_near": [{"place": f"{v['full_name']}, {v['city']}, United States",
                                             "night_before": v["day"]} for v in vs]})
    return {k: v for k, v in c.items() if k != "line"}


async def product_turn(ch: dict, frm: str, p: Dict[str, str], st: dict, out, now, early=None, media=None) -> bool:
    """True: a product answered (the caller stores the state and delivers `out`). False: Sasha's own flow answers."""
    body = (p.get("Body") or "").strip()
    payload = (p.get("ButtonPayload") or "").strip()
    media = media if media is not None else _media(p)   # CR 30 · the web passes its photos' bytes; WhatsApp's come from Twilio
    pend = st.get("pending") or {}
    asked_last = pend.get("product") if pend.get("kind") == "product" else None
    if asked_last:
        # CR 20 · this channel's copy may be stale (the guest went on on the other channel): the shared row wins; a product
        # finished or dropped elsewhere is not resumed from an old copy
        fresh = await _resume(ch, asked_last)
        if fresh is None or fresh.get("parked"):                  # CR 40 · parked elsewhere ("sasha"): only its word resumes it
            asked_last, st["pending"], pend = None, None, {}
        elif (fresh.get("touched") or "") >= (pend.get("touched") or ""):
            st["pending"] = pend = {**fresh, "kind": "product", "product": asked_last}
    if asked_last:
        try:
            if not STRICT and now - datetime.fromisoformat(pend.get("touched")) > MODE_IDLE:
                asked_last, st["pending"] = None, None
        except (TypeError, ValueError):
            pass
    if payload.startswith("so:"):                              # CR 39 · the answer to "Start <product> from the beginning?"
        _, yes_no, prod = (payload.split(":", 2) + ["", ""])[:3]
        if prod in START_WORD:
            from . import store as ST
            if yes_no == "yes":
                await ST.STORE.drop_conversation(_key(ch), prod)   # the conversation goes; its file (the case) is kept
                st["pending"] = None
                body, payload = START_WORD[prod], ""
                p["Body"], p["ButtonPayload"] = body, ""
                asked_last, pend = None, {}
            else:
                saved = await _resume(ch, prod)
                if saved:
                    st["pending"] = {**saved, "kind": "product", "product": prod, "touched": now.isoformat()}
                    _say_back(out, prod, saved)
                    await _store_put(ch, prod, st["pending"])
                else:
                    out.text("OK — nothing changed.")
                return True
    so = start_over(body) if not payload else None
    if so is not None:
        prod = so or asked_last or "sasha"
        from . import store as ST
        if prod in START_WORD:
            under_way = asked_last == prod or bool(await _resume(ch, prod))
            if under_way:                                         # CR 39 · asked once, never silently
                if asked_last == prod:
                    await _store_put(ch, prod, {**st["pending"], "touched": now.isoformat()})
                st["pending"] = None
                out.ask(f"Start {PRODUCT_NAME[prod]} from the beginning? Your old file is kept, not deleted.",
                        [("Yes, start over", f"so:yes:{prod}"), ("No, carry on", f"so:no:{prod}")])
                return True
            st["pending"] = None
            body = START_WORD[prod]
            p["Body"] = body
            asked_last, pend = None, {}
        else:
            if asked_last:
                await _set_aside(st, ch)                        # a product left open is kept; Sasha starts afresh
            st["pending"] = None
            out.text("Fresh start — what would you like? A table, a spa, a trip, a flight…")
            return True
    # 1 · a product's button or keyword
    target, entering = None, False
    for prod, prefixes in PREFIX.items():
        if payload.startswith(prefixes):
            target = prod
    sashas_question = bool(pend) and pend.get("kind") != "product"
    for prod, rx in (("campus", _CAMPUS), ("relocation", _RELOC), ("health", _HEALTH), ("diligence", _DILIGENCE)):
        if not target and rx.match(body):
            if prod == "diligence" and _AD_SHORT.match(body):
                from . import diligence as DG
                rest = _AD_SHORT.sub("", body, count=1).strip(" :,")
                if sashas_question or (rest and not DG.is_ask(rest)):
                    continue                                     # bare "ad": alone or "ad check …" only; never over Sasha's question
            target, entering = prod, True
    if not target and not payload:                              # CR 40 · "relocaton", "campsu", "espña": the word, mistyped
        guess = typo_keyword(body)
        if guess:
            target, entering = guess, True
            body = START_WORD[guess]
            p["Body"] = body
    if not target and not payload and (not STRICT or asked_last == "health"):   # CR 35 · "find my centre": health's (strict: in it)
        from .health import cita as CI
        if CI.AGAIN.search(body):
            target = "health"
    if not target and not payload:
        # Sasha 167 · a CLEAR booking / search / trip request is Sasha's, whatever mode was left open (a stale CampusMe took
        # "a restaurant in Hoi An, October 27" as a visit date). The mode is set aside, kept, and resumes when the guest
        # returns to it. Not "book my flights" (CR 13's trip) and not "near my hotel" (CR 20's in-context hand-off).
        from booking_signer import wa_brain as _WB
        from . import trip as _TP
        if (_WB.RESET.match(body) or (not STRICT and _WB.sasha_clear(body, st.get("history") or [], now))) and not _REL.search(body) \
                and not _TP.wants_plan(body):   # Sasha 194 · strict: only "reset the demo" leaves a space this way   # Sasha 170 · "reset the demo" too (live: RelocateMe answered it)
            if asked_last:
                await _set_aside(st, ch)
            return False
    if not target and not payload and _STATUS.search(body) and (not STRICT or asked_last):
        named = next((prod for prod, rx in _NAMES if rx.search(body)), None)
        waiting = [prod for prod, _ in await _waiting(ch, now)]
        prod = named if named in waiting else (asked_last or (waiting[0] if waiting and not named else None))
        saved = await _resume(ch, prod) if prod else None
        if saved:
            st["pending"] = {**saved, "kind": "product", "product": prod, "touched": now.isoformat()}
            _say_back(out, prod, saved)
            await _store_put(ch, prod, st["pending"])
            return True
    if asked_last and _LATER.match(body) and not payload:
        await _store_put(ch, asked_last, {**st["pending"], "touched": now.isoformat()})
        await _set_aside(st, ch)
        out.text(f"Kept — everything you've given me stays. Say “{_RESUME_WORD.get(asked_last, asked_last)}” when you want to "
                 "carry on. Back to Sasha meanwhile.")
        return True
    if asked_last and _EXIT.match(body) and not payload:
        st["pending"] = {**st["pending"], "touched": now.isoformat(), "parked": True}
        await _set_aside(st, ch)                                # CR 40 · kept, parked: only its word brings it back
        st["pending"] = None
        out.text("Back to Sasha — ask me anything: a booking, a flight, your plans.")   # CR 15 · "sasha" returns
        return True
    plan_for = None
    if payload.startswith("tp:go:") and payload[6:] in ("relocation", "campus"):   # CR 50 · "Getting there": the product's
        plan_for, target, entering = payload[6:], "trip", True                  # own plan, its dates and place pre-filled
        payload, p["ButtonPayload"] = "", ""
        if asked_last != "trip":
            from . import store as ST
            await ST.STORE.drop_conversation(_key(ch), "trip")
    if not target and not payload:
        # CR 13 · "book my flights" / "plan the trip around the visits": the products' context, acted on by Sasha's travel
        from . import trip as TP
        in_product = not STRICT or asked_last in ("relocation", "campus", "trip")
        waiting = [w for w, _ in await _waiting(ch, now) if in_product or w == "trip"]
        if in_product and TP.wants_plan(body):
            plan_for = await TP.which(ch["account_id"], body, asked_last, waiting)
            if plan_for:
                target, entering = "trip", True
                if asked_last != "trip":
                    from . import store as ST
                    await ST.STORE.drop_conversation(_key(ch), "trip")   # a new plan starts afresh
        elif "trip" in waiting and asked_last != "trip" and (in_product or not TP.wants_plan(body)):
            saved = await _resume(ch, "trip")
            # strict (Sasha 194): with Sasha's own flow asking, only the plan's OWN words bring it back — "NEXT" / "stop
            # the plan" on the step it handed to Sasha (its flights); nothing else typed there enters it
            if saved and (in_product or saved.get("step") == "handed") and TP.claims(saved, body, payload, media):
                target = "trip"                                   # "NEXT" — even after Sasha's own flow asked last
    if not target and asked_last:
        # 2 · the product asked last: its answer, Sasha's request, or a plain re-ask
        if _module(asked_last).claims(pend, body, payload, media):
            target = asked_last
        elif for_sasha(body, st.get("history") or [], now):
            handed = await _in_context(ch, asked_last, pend, body, now)       # CR 20 (5): "near my hotel on arrival"
            if STRICT and not handed:
                target = asked_last   # Sasha 194 · strict: the space keeps it (its re-ask) — only ITS OWN hand-off goes to Sasha
            else:
                await _set_aside(st, ch)
                if handed:
                    out.text(handed[1])
                    p["KanoeSaid"], p["Body"] = body, handed[0]
                return False
        else:
            # CR 35 · one conversation per account, two devices: when the product that asked last doesn't recognise this,
            # a set-aside product waiting for exactly this answer takes it ("28010" on the laptop's relocation, while the
            # phone's EspañaMe asked last); otherwise the re-ask goes to the one that asked last, as before
            other = None if STRICT else next((prod for prod, saved in await _waiting(ch, now)
                                              if prod != asked_last and _module(prod).claims(saved, body, payload, media)), None)
            target = other or asked_last
    if not STRICT and not target and not asked_last and not payload and _REL.search(body) and for_sasha(body, st.get("history") or [], now):
        # CR 20 (5) · a product set aside (e.g. after a trip hand-off) still lends its context to "near my hotel on arrival"
        for prod, saved in await _waiting(ch, now):
            handed = await _in_context(ch, prod, saved, body, now)
            if handed:
                out.text(handed[1])
                p["KanoeSaid"], p["Body"] = body, handed[0]
                return False
    if not STRICT and not target and not st.get("pending"):
        # 4 · nobody is waiting: a set-aside product resumes only on an answer to its own question
        for prod, saved in await _waiting(ch, now):
            if _module(prod).claims(saved, body, payload, media):
                target = prod
                break
    if not target:
        return False                                            # 3 · Sasha asked last, or nothing of ours
    from booking_signer.vault import guard as G
    if body and G.looks_like_secret(body):
        out.text(G.CARD_REPLY if G.looks_like_secret(body) == "card" else G.SECRET_REPLY)
        return True
    if asked_last and asked_last != target:
        await _set_aside(st, ch)                                # another product steps in: the first one is kept
    cur = st.get("pending") or {}
    if entering and not payload and target != "trip" and cur.get("product") == target and cur.get("step") not in (None, "done") \
            and not _KEYWORD.get(target, re.compile("$^")).sub("", body, count=1).strip(" :,-"):
        cur["touched"] = now.isoformat()                         # CR 36 · its own name while it's asking: where we were,
        _say_back(out, target, cur)                              # never the same question re-asked (the never-ask-twice line)
        return True
    if not (st.get("pending") or {}).get("product") == target:
        saved = await _resume(ch, target)
        if saved:
            st["pending"] = {**{k: v for k, v in saved.items() if k != "parked"}, "kind": "product", "product": target}
            words = _KEYWORD.get(target, re.compile("$^")).sub("", body, count=1).strip(" :,-")
            if entering and not words and not payload and target != "trip":          # "relocation" alone: where we were, said again
                st["pending"]["touched"] = now.isoformat()
                _say_back(out, target, saved)
                await _store_put(ch, target, st["pending"])     # CR 40 · un-parked in the shared row too
                return True
            entering = False if not words else entering
        else:
            st["pending"] = {"kind": "product", "product": target, "step": None, "since": now.isoformat()}
    st["pending"]["touched"] = now.isoformat()
    rest = body
    if entering:
        rx = _KEYWORD.get(target)
        rest = rx.sub("", body, count=1).strip(" :,-") if rx else body
        rest = body if rest and not re.match(r"^(me|mode)\b", rest, re.I) else rest   # "campus visits at Yale…": all of it
    ctx = {"account": ch["account_id"], "ch": ch, "frm": frm, "st": st, "now": now, "out": out, "media": media,
           "early": early or _no_early, "plan_for": plan_for, "espana": bool(entering and _ESPANA.match(body))}
    import json as _json
    before = (st["pending"].get("step"), _json.dumps(st["pending"].get("facts"), sort_keys=True, default=str))
    handled = await _module(target).turn(ctx, rest, payload, entering=entering)
    if ctx.get("handoff"):
        # CR 13 · a booking step: Sasha's own flow answers this sentence as if typed (her hand-off line, marked "CR 13
        # products"); the plan is kept, set aside, and resumes on "NEXT"
        from . import store as ST
        st["pending"]["touched"] = now.isoformat()
        await ST.STORE.put_conversation(_key(ch), ch["account_id"], target, st["pending"])
        st["pending"] = None
        p["KanoeSaid"], p["Body"] = body, ctx["handoff"]
        return False
    if handled is False and not out.items:                      # the product says it isn't its message: Sasha's
        await _set_aside(st, ch)
        return False
    from . import store as ST
    if (st.get("pending") or {}).get("step") in (None, "done"):   # finished, or never begun: nothing is kept
        await ST.STORE.drop_conversation(_key(ch), target)
        st["pending"] = None
        return True
    if st.get("pending"):
        st["pending"]["touched"] = now.isoformat()
        if out.items:
            _guard(out, st["pending"], before, bool(body or payload or media))
        if out.items:                                             # its last question, to say again on resuming
            # CR 20 · the whole of the last turn's question (e.g. the passport read-back AND "Is every line right?"), so the
            # other channel resumes with what it is being asked about — capped from the end, the question kept
            st["pending"]["last_said"] = _last_said([str(it[1]) for it in out.items if it[0] in ("text", "ask")])
            last = out.items[-1]
            st["pending"]["last_ask"] = [list(b) for b in last[2]] if last[0] == "ask" else None
        from . import store as ST
        await ST.STORE.put_conversation(_key(ch), ch["account_id"], target, st["pending"])
    return True


# ── CR 30 · NEVER ASK TWICE: about to repeat the last question with nothing learned → say what's held and what's missing, once

_NEVER_SAY = re.compile(r"(?i)tarjeta|cipa|\bsip\b|nuss|naf|health|salud|card_?code|cvv|iban|password|pin")
_LABELS = {"passport_number": "Passport number", "surname_1": "First surname", "surname_2": "Second surname", "given_names": "Given names",
           "birth_date": "Date of birth", "nationality": "Nationality", "email": "Email", "phone": "Phone"}


def _norm(q: str) -> str:
    return re.sub(r"\W+", " ", (q or "").lower()).strip()


def held(facts, prefix: str = "") -> list:
    """What a product holds, as 'Label: value' lines — leaves {"value": …} anywhere in its facts; never a health or
    payment identifier."""
    out = []
    if isinstance(facts, dict):
        if "value" in facts and not isinstance(facts["value"], (dict, list)):
            if facts["value"] not in (None, "") and not _NEVER_SAY.search(prefix):
                name = prefix.rsplit(".", 1)[-1]
                out.append(f"{_LABELS.get(name, name.replace('_', ' ').capitalize())}: {facts['value']}")
            return out
        for k, v in facts.items():
            if not _NEVER_SAY.search(str(k)):
                out += held(v, f"{prefix}.{k}" if prefix else str(k))
    return out


def _guard(out, pend: dict, before: tuple, said_something: bool) -> None:
    """The turn ends on the SAME question as the last one, the step and the facts unchanged, and the person did say
    something → once per question: what Sasha has, what is missing, and how to move on — the question's buttons kept."""
    import json as _json
    last = out.items[-1]
    q = str(last[1]) if last[0] in ("ask", "text") else ""
    turn = _norm(" ".join(str(it[1]) for it in out.items if it[0] in ("text", "ask")))   # the WHOLE reply: a menu's new card isn't a loop
    now_ = (pend.get("step"), _json.dumps(pend.get("facts"), sort_keys=True, default=str))
    same = q and turn == pend.get("last_turn") and now_ == before and said_something
    pend["last_turn"] = turn
    if not same or pend.get("guarded_q") == _norm(q):
        return
    pend["guarded_q"] = _norm(q)
    have = held(pend.get("facts"))[:8]
    line = ("I asked that a moment ago and didn't get an answer I could use — so you don't go round in circles:\n"
            + ("What I have: " + "; ".join(have) + ".\n" if have else "")
            + f"Still missing: {q.strip()}\n"
            + "Answer in your own words, send a photo if it's on a document, or say “later” and I'll keep everything for when you're back.")
    out.items = [it for it in out.items[:-1] if it[0] == "media"]
    if last[0] == "ask":
        out.ask(line, list(last[2]))
    else:
        out.text(line)


# "where are we …" is Sasha's itinerary question (itinerary_q.QUESTION), never taken here
_STATUS = re.compile(r"(?i)\b(what'?s next|what now|what do i do next|where was i|where am i up to|status of|next step)\b")
_NAMES = [("campus", re.compile(r"(?i)\b(campus|visit|yale|penn|tour|college|universit)")),
          ("relocation", re.compile(r"(?i)\b(relocat|ex-?01|visa|residenc|consulate|file|application|move)")),
          ("health", re.compile(r"(?i)\b(health|doctor|salud|sermas|clinic)")), ("trip", re.compile(r"(?i)\b(trip|plan|flight|hotel)"))]


async def _store_put(ch: dict, product: str, pend: dict) -> None:
    from . import store as ST
    await ST.STORE.put_conversation(_key(ch), ch["account_id"], product, pend)


def _say_back(out, product: str, saved: dict) -> None:
    """Where we were, said again — with the last question's own buttons when it had some (CR 20: the other channel can
    press them too)."""
    text = _welcome_back(product, saved)
    if saved.get("last_ask"):
        out.ask(text, [tuple(b) for b in saved["last_ask"]])
    else:
        out.text(text)


_RESUME_Q = {"relocation": "Back to your EX-01.", "campus": "Back to your campus visits.", "health": "Back to your health appointment.",
             "trip": "Back to your trip plan.", "diligence": "Back to Applied Diligence."}


def _last_said(parts: List[str], cap: int = 1500) -> str:
    """CR 41 · the last turn's words for the say-back, capped from the END by whole messages (live: a cut mid-way through
    Princeton's details read "…/2009 Kanoe Test High School"); one message too long alone keeps its last whole paragraphs."""
    keep: List[str] = []
    for t in reversed([x for x in parts if x.strip()]):
        if sum(len(k) + 2 for k in keep) + len(t) > cap:
            if not keep:
                for para in reversed(t.split("\n\n")):
                    if sum(len(k) + 2 for k in keep) + len(para) > cap:
                        break
                    keep.append(para)
            break
        keep.append(t)
    return "\n\n".join(reversed(keep))


def _welcome_back(product: str, saved: dict) -> str:
    """Resuming: where we were, in one line — the product's last question, said again."""
    last = (saved.get("last_said") or "").strip()
    return f"{_RESUME_Q[product]} {last}" if last else _RESUME_Q[product]


async def _no_early(text: str) -> None:
    return None


def _media(p: Dict[str, str]) -> list:
    """What the person sent besides words: [{url, type}] — Twilio's MediaUrlN / MediaContentTypeN."""
    try:
        n = int(p.get("NumMedia") or 0)
    except ValueError:
        n = 0
    return [{"url": p.get(f"MediaUrl{i}"), "type": p.get(f"MediaContentType{i}") or ""} for i in range(min(n, 5))
            if p.get(f"MediaUrl{i}")]
