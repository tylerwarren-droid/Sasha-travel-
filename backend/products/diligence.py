"""CR 15 · Applied Diligence PREVIEW on WhatsApp: "diligence" (or "ad") → "check TotalEnergies in France" → AD's own
register lookup (the US tab's endpoint) → the identified register result, its SOURCE, the RETRIEVED date and AD's honest
SCOPE line, labelled PREVIEW. Nothing is added to what AD returns, nothing is kept beyond the message.

Contract (agreed with the US tab; docs/products/CR-15-ad-preview.md):
  POST {AD_PREVIEW_URL}/api/preview/register  headers X-Kanoe-Key: {AD_PREVIEW_KEY} (set by each side's tab via its CLI)
  {"country": ISO-3166 alpha-2, "name": str|None, "registration_number": str|None}   — exactly one of name / number
  → {"status": identified|ambiguous|not_found|not_covered|uncovered_preview|not_in_preview,
     "entity": {legal_name, registration_number, register, "status_raw": the register's own word verbatim, "status":
                normalised or null, address, incorporated}|null,
     "standing": {"value": active|ceased|null, "expressible": bool, "because": one line, always present},
     "candidates": [...] (resemble, never matches), "source": {"name", "url"}, "retrieved_at": when AD read it,
     "source_as_of": the publisher's own as-of or null, "scope": the PER-COUNTRY scope text, shown verbatim, "preview": true}
  not_covered = no rail · uncovered_preview = a rail, not certified for sale · not_in_preview = certified, licence forbids
  onward supply (NL, MT, AT…). Pinned with the US tab, 4 Oct 2026; the endpoint itself is the founder's decision.

Per-country rules (from the EU tab's measured work, 4 Oct 2026): a register's status is shown in ITS words (never only a
collapsed enum); "not found" is said only as the register's own answer; the Netherlands is NEVER queried or shown —
KVK's terms (Art. 3, 5.6) refuse onward transfer of Handelsregister data by any route.
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from datetime import datetime
from typing import Optional, Tuple

log = logging.getLogger("products.diligence")
TIMEOUT_S = 15.0

INTRO = ("Applied Diligence — PREVIEW 🔎 Tell me a company and its country — e.g. “check TotalEnergies in France”, or a "
         "registration number with its country. I show what the official register returns, with its source and date. "
         "A preview, not a due-diligence report.")

# country words → ISO 3166-1 alpha-2 (the names people type; the code is what AD's contract takes)
COUNTRIES = {
    "france": "FR", "francia": "FR", "spain": "ES", "espana": "ES", "españa": "ES", "united kingdom": "GB", "uk": "GB",
    "england": "GB", "great britain": "GB", "britain": "GB", "germany": "DE", "alemania": "DE", "deutschland": "DE",
    "italy": "IT", "italia": "IT", "portugal": "PT", "netherlands": "NL", "holland": "NL", "belgium": "BE",
    "ireland": "IE", "luxembourg": "LU", "switzerland": "CH", "austria": "AT", "sweden": "SE", "norway": "NO",
    "malta": "MT", "denmark": "DK", "the netherlands": "NL", "nederland": "NL", "países bajos": "NL", "finland": "FI", "poland": "PL", "united states": "US", "usa": "US", "us": "US", "america": "US",
    "canada": "CA", "mexico": "MX", "méxico": "MX", "brazil": "BR", "japan": "JP", "australia": "AU", "india": "IN",
    "singapore": "SG", "hong kong": "HK", "vietnam": "VN", "viet nam": "VN", "united arab emirates": "AE", "uae": "AE",
}
_ASK = re.compile(r"(?i)^\s*(?:please\s+)?(?:check|look\s*up|lookup|search|verify|find|who\s+is)?\s*(?P<what>.+?)\s*"
                  r"(?:,\s*|\s+in\s+|\s+\()(?P<where>[A-Za-zÀ-ÿ .'-]+?)\)?\s*[.?!]?\s*$")


REFUSED = {   # a second, local refusal — AD's own (catalogue-driven) is the first; a licence term deserves both (US tab)
    "NL": "the Dutch company register's terms don't allow passing on its records, by any route — so this preview never shows them.",
    "MT": "the Maltese register's terms limit passing its records on to a client — so this preview never shows them.",
    "AT": "the Austrian Firmenbuch's terms limit republishing its extracts — so this preview never shows them.",
}


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower().strip()


def parse(text: str) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
    """'check TotalEnergies in France' → ('FR', 'TotalEnergies', None); 'SIREN 542051180 in France' → ('FR', None, '542051180').
    None when there's no country we know (then we ask — never a guessed country)."""
    m = _ASK.match(text or "")
    if not m:
        return None
    where = _fold(m["where"])
    code = COUNTRIES.get(where) or COUNTRIES.get(_fold(m["where"].replace("the ", "")))
    if not code and re.fullmatch(r"[A-Za-z]{2}", m["where"].strip()):
        code = m["where"].strip().upper()
    if not code:
        return None
    what = re.sub(r"(?i)^(the\s+)?(company|firm)\s+", "", m["what"]).strip(" .\"'“”")
    num = re.sub(r"(?i)^(siren|siret|cif|nif|crn|company number|reg(istration)?\.?\s*(no|number)?)\s*:?\s*", "", what)
    if re.fullmatch(r"[A-Z0-9][A-Z0-9 .-]{4,20}", num, re.I) and re.search(r"\d{5,}", num):
        return code, None, re.sub(r"[ .-]", "", num)
    return (code, what, None) if what else None


async def _post(url: str, key: str, body: dict) -> Tuple[int, dict]:
    import httpx
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as c:
        r = await c.post(url, json=body, headers={"X-Kanoe-Key": key, "Content-Type": "application/json"})
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {}


HTTP = _post   # tests replace it


def _when(iso: Optional[str]) -> str:
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).strftime("%-d %b %Y, %H:%M UTC")
    except (TypeError, ValueError):
        return iso or "not given"


def _natural_person(e: dict) -> bool:
    cat = str(e.get("legal_category") or e.get("categorie_juridique") or "")
    return bool(e.get("natural_person")) or cat == "1000"


def render(j: dict, asked: str, label: str = "PREVIEW") -> str:
    """AD's answer in WhatsApp words — only what it returned. The SCOPE line comes right after the heading, so a cut
    message never loses it (US tab); standing is said with its reason when the register can't express it — an absent
    status would read as "nothing adverse"; both dates are shown: when AD read it, and the source's own as-of."""
    st = j.get("status")
    src = j.get("source") or {}
    head = f"🔎 *Applied Diligence — {label}*" + (f"\nScope: {j['scope']}" if j.get("scope") else "")
    dates = f"\nRead from the register: {_when(j.get('retrieved_at'))}" + \
        (f"\nThe source's own data as of: {j['source_as_of']}" if j.get("source_as_of") else "")
    foot = f"\nSource: {src.get('name') or 'not given'}" + (f" — {src['url']}" if src.get("url") else "") + dates
    if st == "identified" and j.get("entity") and _natural_person(j["entity"]):
        # e.g. SIRENE catégorie juridique 1000 = entrepreneur individuel: a PERSON, not a company (EU tab) — never shown
        return head + "\nThat name belongs to a sole trader — a person, not a company — so this preview doesn't show it."
    if st == "identified" and j.get("entity"):
        e, lines = j["entity"], []
        lines.append(f"*{e.get('legal_name') or asked}*")
        for lab, k in (("Register", "register"), ("Registration no.", "registration_number")):
            if e.get(k):
                lines.append(f"{lab}: {e[k]}")
        if e.get("status_raw"):                     # a register's own status words, verbatim (EU tab) — never the bare normalised word
            lines.append(f"Register status (its own words): {e['status_raw']}")
        sd = j.get("standing") or {}
        expressible = sd.get("expressible") if "expressible" in sd else e.get("standing_expressible")
        if expressible and (sd.get("value") or e.get("status")):
            lines.append(f"Standing: {sd.get('value') or e.get('status')}")
        else:                                       # never silent: a missing status would read as "nothing adverse"
            lines.append("Standing: not shown — " + (sd.get("because") or "this register doesn't publish insolvency or "
                         "winding-up, so its status means registered, not solvent (see Scope)."))
        for lab, k in (("Address", "address"), ("Incorporated", "incorporated")):
            if e.get(k):
                lines.append(f"{lab}: {e[k]}")
        return head + "\n" + "\n".join(lines) + foot
    if st == "ambiguous":
        c = "\n".join(f"• {x.get('legal_name')} — {x.get('registration_number')}" for x in (j.get("candidates") or [])[:5])
        return head + f"\nNames that resemble “{asked}” — possible matches, not confirmed:\n{c}\nSend the registration number to check one." + foot
    if st == "not_found":
        return head + f"\nThe register's own answer: no company matching “{asked}”." + foot
    if st == "uncovered_preview":
        return head + "\nThis country's register can be reached, but the check isn't certified for sale — so no result is shown here."
    if st == "not_in_preview":   # AD covers it, certified — but the register's LICENCE forbids passing records on
        return head + "\nApplied Diligence covers that country's register, but its licence doesn't allow passing its records on — so this preview doesn't show them."
    if st in ("not_covered", "unsupported_country"):
        return head + "\nThis preview doesn't cover that country's register."
    return head + "\nThe service's answer wasn't in a form I can show — nothing claimed."


# a FIXED example (the US tab's sample, 4 Oct 2026) — shown only when no live service is connected and AD_PREVIEW_SAMPLE=1,
# only for the company it is about, and labelled SAMPLE so it can never pass for a live lookup
SAMPLE = {
    "match": ("FR", "totalenergies"),
    "response": {
        "status": "identified",
        "entity": {"legal_name": "TOTALENERGIES SE", "registration_number": "542051180", "register": "INSEE SIRENE",
                   "address": "2 PLACE JEAN MILLIER, 92400 COURBEVOIE, FRANCE", "incorporated": "1924-03-28"},
        "standing": {"value": None, "expressible": False,
                     "because": "SIRENE publishes establishment and activity data, not insolvency or winding-up proceedings, so "
                                "this check cannot speak to the company's standing."},
        "candidates": [], "source": {"name": "INSEE SIRENE", "url": "https://api.insee.fr/entreprises/sirene"},
        "retrieved_at": None, "source_as_of": None,
        "scope": "This preview identifies the company on the French national register and reports what that register "
                 "publishes. It is not a sanctions, PEP or adverse-media check, it says nothing about the company's standing "
                 "or solvency, and it is not a due-diligence report.",
        "preview": True}}
_PERSON = re.compile(r"(?i)^\s*(mr|mrs|ms|miss|dr|sr|sra|m\.|mme|herr|frau)\.?\s|\b(person|individual|director named|ceo named)\b")


async def lookup(country: str, name: Optional[str], number: Optional[str]) -> str:
    url, key = os.getenv("AD_PREVIEW_URL", "").strip(), os.getenv("AD_PREVIEW_KEY", "").strip()
    asked = name or number or ""
    if country in REFUSED:                         # never queried, never shown — whatever the service would answer
        return f"🔎 Applied Diligence — PREVIEW: not available for this country — {REFUSED[country]}"
    if name and _PERSON.search(name):              # companies only: a person changes the lawful basis (US tab)
        return "🔎 Applied Diligence — PREVIEW checks companies only — not people. Send a company name or registration number."
    if not url or not key:
        if os.getenv("AD_PREVIEW_SAMPLE", "").strip() == "1" and (country, _fold(asked).replace(" ", "")) == SAMPLE["match"]:
            r = dict(SAMPLE["response"])
            return render(r, asked, label="SAMPLE (a fixed example response, not a live register lookup)").replace(
                "\nRead from the register: not given", "\nRead from the register: — (sample, not read live)")
        return "🔎 Applied Diligence — PREVIEW: the register service isn't connected here yet, so nothing was checked."
    try:
        status, j = await HTTP(url.rstrip("/") + "/api/preview/register", key,
                               {"country": country, "name": name, "registration_number": number})
    except Exception as e:
        log.error("[diligence] AD unreachable: %s", type(e).__name__)
        return "🔎 Applied Diligence — PREVIEW: the register couldn't be reached just now — nothing was checked."
    if status != 200 or not isinstance(j, dict):
        msg = (j or {}).get("message") if isinstance(j, dict) else None
        return f"🔎 Applied Diligence — PREVIEW: the lookup was refused or failed ({status}{': ' + msg if msg else ''}) — nothing claimed."
    return render(j, asked)


# ── the skill (CR 10's router: a mode inside the one conversation, no walls) ───────────────────────────────────────────

async def turn(ctx: dict, body: str, payload: str, *, entering: bool) -> Optional[bool]:
    pend, out = ctx["st"]["pending"], ctx["out"]
    t = re.sub(r"(?i)^\s*(applied\s+diligence|diligence|ad)\b[\s:,-]*", "", body or "").strip()   # "ad check …": the mode word off
    if entering and not t:
        pend["step"] = "ask"
        out.text(INTRO)
        return True
    got = parse(t) if (entering or is_ask(t)) else None
    if not got:
        if entering:
            pend["step"] = "ask"
            out.text("A company and its country, please — e.g. “check TotalEnergies in France”.")
            return True
        return False                               # not a lookup: Sasha answers it, in the same chat
    country, name, number = got
    await ctx["early"](f"Checking {name or number} in the register ({country})…")
    out.text(await lookup(country, name, number))
    pend["step"] = "ask"                           # another company? same mode; "sasha" goes back
    return True


_VERB = re.compile(r"(?i)^\s*(?:please\s+)?(check|look\s*up|lookup|verify|search|who\s+is)\b")


def is_ask(text: str) -> bool:
    """A lookup said as one ('check X in Y', or a registration number) — so "dinner in Spain" is never taken for a company."""
    got = parse(text or "")
    return bool(got) and (bool(_VERB.match(text or "")) or got[2] is not None)


def claims(pend: dict, body: str, payload: str, media: list) -> bool:
    return pend.get("step") == "ask" and is_ask(body)


def context(pend: dict) -> dict:
    return {"product": "diligence", "city": None, "country": None, "dates": [], "name": None, "line": "[AD preview]"}
