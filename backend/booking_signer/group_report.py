"""Sasha 385 · THE GROUP FINISH — ONE "so what" in the chat and ONE final report, traveller by traveller, both drawn from the ONE source: the
master list (groups.view — AgAPI's booking record for every status, the trip rows for the rest) and the send record (each itinerary
emailed, kept on the trip). KANOE_DECISIONS 13 Nov 15:12: "never a wall of text … The report is drawn from the one trip record / master
list, never a second copy."

Found (Tyler's Yerevan demo, 13 Nov 15:07): one paragraph — "1 of 7 booked … Confirmations have been sent to each traveller's registered
email …" — while 1 of 7 was booked, 6 of 7 named, and "part of the trip is booked" offered no fix.

  buckets(rows)        every traveller in exactly ONE bucket: fully booked · waiting on the airline · need a new flight / hotel · not booked
  line(mv, b, missing) "Yerevan, 15–20 Dec: 1 of 7 fully booked · 2 waiting on the airline · 3 need a new flight · 1 not booked." — by code;
                       a traveller selected for the trip but absent from the list is said as missing (a failure, never silence)
  question(b)          the ONE grouped question, with its taps ("Rebook the 3 on the next flights?" · Rebook them / Release their hotels)
  report(…)            the rows: flight · hotel · status · references · itinerary emailed (from the send record) · what's missing · the fix
  send_itineraries     each FULLY booked traveller's own itinerary, once, through the one sender (live_events.send_email); recorded
                       (rules "itinerary:<member>") — "sent" is said only from that record
  report_url / page    the report's own page: a signed link (like the calendar's .ics), served from the list as it is now"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import logging
import os
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("booking_signer.group_report")

#: the buckets, in the order the line says them — every traveller in exactly one
BUCKETS = (("booked", "fully booked"), ("waiting", "waiting on the airline"), ("new_flight", "need a new flight"),
           ("new_hotel", "need a new hotel"), ("not_booked", "not booked"))
LABEL = dict(BUCKETS)
#: each bucket's fix, offered in the report (the grouped question offers it in the chat)
FIX = {"booked": "", "waiting": "I'm checking with the airline — nothing will be ordered twice",
       "new_flight": "book the next flights through the booking engine, or release the hotel within its terms",
       "new_hotel": "book another hotel within the limits, or release the flight within its terms"}
REPORT_DAYS = 30
#: the not-booked statuses that are the manager's decision (book anyway / another option / leave off) — never a passport still to come
DECIDE = ("over limit", "planned")
SENT_KEY = "itinerary:"


def bucket(r: Dict[str, Any]) -> str:
    """ONE bucket per traveller, from the master list's own status (AgAPI's record decides booked / confirming / incomplete)."""
    s = r.get("status")
    if s == "booked":
        return "booked"
    if s == "confirming":
        return "waiting"
    if s == "incomplete":   # part of the trip is booked: the part that ISN'T is what they need
        have = set(r.get("booked_parts") or [])
        return "new_hotel" if "flight" in have and "stay" not in have else "new_flight"
    return "not_booked"


def buckets(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {k: [] for k, _ in BUCKETS}
    for r in rows:
        out[bucket(r)].append(r)
    return out


def _span(mv: Dict[str, Any]) -> str:
    """"15–20 Dec" · "28 Dec–3 Jan" — the trip's own dates."""
    try:
        a, b = date.fromisoformat(str(mv.get("starts_on"))[:10]), date.fromisoformat(str(mv.get("ends_on"))[:10])
    except ValueError:
        return ""
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.day}–{b.day} {b:%b}"
    return f"{a.day} {a:%b}–{b.day} {b:%b}"


def missing(view: Dict[str, Any], members: List[Dict[str, Any]]) -> List[str]:
    """Travellers on the trip (its members) with NO row on the master list — said as missing, never left out."""
    have = {r.get("member_id") for r in view.get("rows") or []}
    return [m["name"] for m in members if m.get("id") not in have]


def line(mv: Dict[str, Any], b: Dict[str, List[Dict[str, Any]]], gone: List[str]) -> str:
    """THE "so what", by code — every traveller counted exactly once."""
    total = sum(len(v) for v in b.values()) + len(gone)
    parts = [f"{len(b['booked'])} of {total} fully booked"] + [f"{len(b[k])} {label}" for k, label in BUCKETS[1:] if b[k]]
    if gone:
        parts.append(f"{len(gone)} missing from the list ({_and(gone)})")
    head = ", ".join(x for x in (str(mv.get("destination") or "The trip"), _span(mv)) if x)
    return f"{head}: " + " · ".join(parts) + "."


def _and(xs: List[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


def _who(rows: List[Dict[str, Any]]) -> Tuple[str, str]:
    """("the 3" / "Ana", "Ana García, Carmen Castro and Luis Pérez") — how the question names them, and the words a tap says."""
    names = [r["name"] for r in rows]
    return (f"the {len(names)}" if len(names) > 1 else names[0].split()[0]), _and(names)


def question(b: Dict[str, List[Dict[str, Any]]], named: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """THE ONE grouped question, with its taps (each tap says its own words — the instruction, through the one engine). The most pressing
    first: a flight to replace, a hotel to replace, then those not booked. Nothing to decide (all booked, or only waiting) → None."""
    if b["new_flight"]:
        short, names = _who(b["new_flight"])
        return {"ask": f"Rebook {short} on the next flights?",
                "choices": [{"title": "Rebook them" if len(b["new_flight"]) > 1 else "Rebook", "route": f"say:Rebook {names} on the next flights"},
                            {"title": "Release the hotels" if len(b["new_flight"]) > 1 else "Release the hotel",
                             "route": f"say:Release the hotel for {names}"}]}
    if b["new_hotel"]:
        short, names = _who(b["new_hotel"])
        return {"ask": f"Find {short} another hotel?",
                "choices": [{"title": "Find a hotel", "route": f"say:Find another hotel for {names}"},
                            {"title": "Release the flights" if len(b["new_hotel"]) > 1 else "Release the flight",
                             "route": f"say:Release the flight for {names}"}]}
    decide = [r for r in b["not_booked"] if r.get("status") in DECIDE]   # a passport to come, or a plan to make, is no decision of theirs
    if named:   # the reasons this run met (AgAPI's refusals, a missing mobile or limit), each named — group_book.one_question's ONE sentence
        decide = decide or b["not_booked"]
        short, names = _who(decide)
        return {"ask": named, "choices": [{"title": "Book anyway", "route": f"say:Book {names} anyway"},
                                          {"title": "Another option", "route": f"say:Find another option for {names}"},
                                          {"title": "Leave off", "route": f"say:Leave {names} off this trip"}]}
    if decide:
        short, names = _who(decide)
        return {"ask": f"What would you like for {short} not booked?",
                "choices": [{"title": "Book anyway", "route": f"say:Book {names} anyway"},
                            {"title": "Another option", "route": f"say:Find another option for {names}"},
                            {"title": "Leave them off", "route": f"say:Leave {names} off this trip"}]}
    return None


def card(mv: Dict[str, Any], q: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The grouped question as the card every door draws (S2 / /next: its choices; WhatsApp: its buttons) — a typed-word tap each."""
    if not q:
        return None
    return {"read_back": [], "ask": q["ask"], "choices": q["choices"], "read_back_id": f"gfin_{str(mv.get('id') or '')[:36]}"}


# ── what the trip record keeps beside the list: each reason, each fare's conditions, each invitation (one key per traveller) ─

async def keep(account: str, mv: Dict[str, Any], rows: List[Dict[str, Any]], failed: List[Dict[str, Any]], done: List[Dict[str, Any]]) -> None:
    """The reasons this run met (why:<member>) and each booked fare's conditions (cond:<member>), ON the trip — so the report, read later
    from the trip, says them; never a second copy anywhere else."""
    from . import groups as G, group_book as GB
    ids = {r["name"]: str(r.get("member_id")) for r in rows if r.get("member_id")}
    st = G.store()
    for f in failed:
        mid = ids.get(f.get("name"))
        code = f.get("code") or f.get("kind") or ""
        if mid:
            why = f.get("why") or GB.FACTS.get(code) or GB.MANDATE_FACTS.get(code) or "not booked just now"
            await st.set_rule(account, mv["id"], f"why:{mid}", {"code": code, "why": str(why)[:300]})
    for d in done:
        mid, words = ids.get(d.get("name")), []
        for c in d.get("conditions") or []:
            for w in (("only the airline can cancel it" if c.get("cancel_by") == "airline" else ""),
                      ("it can't be refunded" if c.get("refund") in (False, "none", "no") else ""),
                      ("it can't be changed" if c.get("change") in (False, "none", "no") else "")):
                if w and f"{c.get('kind') or 'booking'}: {w}" not in words:   # each fact once (both legs say it)
                    words.append(f"{c.get('kind') or 'booking'}: {w}")
        if mid and words:
            await st.set_rule(account, mv["id"], f"cond:{mid}", words)


async def invited(account: str, movement_id: str, names: List[str], rows: List[Dict[str, Any]]) -> None:
    """Each passport invitation that WENT by email (invite_missing's own `emailed`), on the trip (invite:<member>)."""
    from . import groups as G
    ids = {r["name"]: str(r.get("member_id")) for r in rows if r.get("member_id")}
    for n in names:
        if ids.get(n):
            await G.store().set_rule(account, movement_id, f"invite:{ids[n]}", {"at": datetime.now(timezone.utc).isoformat()})


# ── the send record: each itinerary emailed, kept on the trip (one key per traveller) ─────────────────────────────────────

async def sent_record(account: str, movement_id: str) -> Dict[str, Dict[str, Any]]:
    """member_id → {at, to} for each itinerary that WENT (the one sender said sent) — the only source of "emailed"."""
    from . import groups as G
    mv = await G.store().movement(account, movement_id) or {}
    rules = mv.get("rules") or {}
    return {k[len(SENT_KEY):]: v for k, v in rules.items() if k.startswith(SENT_KEY) and isinstance(v, dict) and v.get("at")}


def _mask(email: str) -> str:
    local, _, dom = str(email or "").partition("@")
    return (local[:1] + "•••@" + dom) if dom else ""


async def send_itineraries(account: str, mv: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Each FULLY booked traveller's own itinerary, once (never twice: the record says who already has it), to their registered email,
    through the one sender (live_events.send_email), TEST-tagged — recorded when it went. → {sent, already, no_email, not_sent} (names)."""
    from . import groups as G, live_events as LE
    done = await sent_record(account, mv["id"])
    people = {p["name"]: p for p in (await G.roster(account)).get("people") or []}
    out: Dict[str, List[str]] = {"sent": [], "already": [], "no_email": [], "not_sent": []}
    for r in [x for x in rows if bucket(x) == "booked"]:
        mid, name = str(r.get("member_id") or ""), r["name"]
        if mid in done:
            out["already"].append(name)
            continue
        email = (people.get(name) or {}).get("email")
        if not email:
            out["no_email"].append(name)
            continue
        msg = {"from": os.getenv("SASHA_EMAIL_FROM", "").strip(), "to": email,
               "subject": f"Your itinerary (TEST): {mv.get('destination')} {str(mv.get('starts_on') or '')[:10]} – {str(mv.get('ends_on') or '')[:10]}",
               "text": "\n".join([f"Hello {name.split()[0]},", "", f"Your trip with {mv.get('company')} to {mv.get('destination')} is booked (TEST).",
                                  "", f"Travel: {r.get('transport') or '—'}", f"Hotel: {r.get('hotel') or '—'}",
                                  "References: " + (", ".join(r.get("references") or []) or "on the trip's master list"), "",
                                  "TEST: a demo booking — no airline or hotel charge.", "", "— Sasha (AI concierge, Kanoe Technologies SL)"])}
        try:
            got = await LE.send_email(msg)
        except Exception as e:
            got = {"sent": False, "why": type(e).__name__}
        if got.get("sent"):
            try:
                await G.store().set_rule(account, mv["id"], SENT_KEY + mid, {"at": datetime.now(timezone.utc).isoformat(), "to": _mask(email)})
            except Exception as e:   # sent but not recorded: never said as sent (the record is the claim), logged loudly
                log.error("[group_report] %s's itinerary went but wasn't recorded: %s", name, type(e).__name__)
                out["not_sent"].append(name)
                continue
            out["sent"].append(name)
        else:
            out["not_sent"].append(name)
    return out


# ── the report: one page per trip, from the list as it is now ─────────────────────────────────────────────────────────────

def _key() -> bytes:
    k = os.getenv("SASHA_ICS_KEY", "").strip() or os.getenv("SASHA_BOOKING_KEY", "").strip()
    return hashlib.sha256(("sasha-group-report|" + k).encode()).digest()


def token(account: str, movement_id: str, now: Optional[float] = None) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"a": account, "m": movement_id, "x": int((now or time.time()) + REPORT_DAYS * 86400)},
                                               separators=(",", ":")).encode()).decode().rstrip("=")
    return body + "." + hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()[:32]


def read_token(tok: str, now: Optional[float] = None) -> Optional[Tuple[str, str]]:
    body, _, sig = (tok or "").rpartition(".")
    if not body or not hmac.compare_digest(sig, hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()[:32]):
        return None
    try:
        d = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except Exception:
        return None
    if int(d.get("x") or 0) < (now or time.time()):
        return None
    return str(d["a"]), str(d["m"])


def report_url(account: str, movement_id: str) -> str:
    base = os.getenv("SASHA_PUBLIC_API_URL", "https://sasha-travel-production.up.railway.app").rstrip("/")
    return f"{base}/api/agent/group-report/{token(account, movement_id)}"


def _missing_of(r: Dict[str, Any], k: str) -> str:
    from . import group_book as GB
    if k == "new_flight":
        return "the flight" + (f" ({GB.FACTS.get(r['record_why'], str(r['record_why']).replace('_', ' '))})" if r.get("record_why") else "")
    if k == "new_hotel":
        return "the hotel" + (f" ({GB.FACTS.get(r['record_why'], str(r['record_why']).replace('_', ' '))})" if r.get("record_why") else "")
    if k == "not_booked":
        return GB.FACTS.get(r.get("record_why") or "", "") or {"over limit": "over the company's limit", "needs vault": "no passport in their vault yet",
                                                               "not planned": "not planned yet", "planned": "not booked yet",
                                                               "cancelled": "cancelled"}.get(str(r.get("status")), str(r.get("status") or ""))
    return ""


def _fix_of(r: Dict[str, Any], k: str) -> str:
    if k == "not_booked":
        return {"over limit": "book anyway, another option, or leave them off", "needs vault": "their secure passport link (then they're booked)",
                "planned": "book them", "not planned": "plan them", "cancelled": ""}.get(str(r.get("status")), "book anyway, another option, or leave them off")
    return FIX.get(k, "")


async def report(account: str, movement_id: str) -> Dict[str, Any]:
    """The report's content — the master list as it is now, the send record, the invoice: {movement, line, question, rows, invoice}."""
    from . import groups as G, group_book as GB
    st = G.store()
    mv = await st.movement(account, movement_id)
    if not mv:
        return {"why": "no such trip"}
    view = await G.view(account, movement_id)
    if view.get("record_unread"):
        return {"movement": mv, "unread": True, "line": GB.UNREAD_SAY, "rows": []}
    rows = view.get("rows") or []
    b = buckets(rows)
    gone = missing(view, await st.members(movement_id))
    sent = await sent_record(account, movement_id)
    kept = mv.get("rules") or {}
    emails = {p["name"]: p.get("email") for p in (await G.roster(account)).get("people") or []}
    try:
        inv = await GB.invoice(account, movement_id)
    except Exception:
        inv = {}

    def row(r: Dict[str, Any]) -> Dict[str, Any]:
        k, went = bucket(r), str(r.get("member_id")) in sent
        no_mail = k == "booked" and not went and not emails.get(r["name"])
        mid = str(r.get("member_id"))
        why = (kept.get(f"why:{mid}") or {}).get("why") if k == "not_booked" else None
        cond = kept.get(f"cond:{mid}") if k == "booked" else None
        fix = _fix_of(r, k)
        if r.get("status") == "needs vault":
            fix = ("their secure passport link was emailed — they're booked once it's in" if kept.get(f"invite:{mid}")
                   else "their secure passport link is on the Group page to forward (no email on file)")
        return {"name": r["name"], "flight": (r.get("transport") or "—") + (f" ({'; '.join(cond)})" if cond else ""),
                "hotel": r.get("hotel") or "—", "status": LABEL[k],
                "references": list(r.get("references") or []), "emailed": ("yes" if went else "no") if k == "booked" else "—",
                "missing": "their email, for the itinerary" if no_mail else (why or _missing_of(r, k)),
                "fix": "add their email on the Group page — their itinerary goes then" if no_mail else fix}
    out_rows = [row(r) for r in rows]
    out_rows += [{"name": n, "flight": "—", "hotel": "—", "status": "missing from the list", "references": [], "emailed": "—",
                  "missing": "everything — not on the master list", "fix": "add them back on the Group page"} for n in gone]
    return {"movement": {k: mv.get(k) for k in ("id", "company", "destination", "starts_on", "ends_on")}, "line": line(mv, b, gone),
            "question": question(b), "rows": out_rows, "invoice": {k: inv.get(k) for k in ("number", "total") if inv.get(k)}}


def page(rep: Dict[str, Any]) -> str:
    """The report as one page (no script; every value escaped)."""
    e = lambda x: html.escape(str(x if x is not None else ""))   # noqa: E731
    mv = rep.get("movement") or {}
    head = f"{e(mv.get('company'))} → {e(mv.get('destination'))}"
    rows = "".join(f"<tr><td>{e(r['name'])}</td><td>{e(r['flight'])}</td><td>{e(r['hotel'])}</td><td>{e(r['status'])}</td>"
                   f"<td>{e(', '.join(r['references']) or '—')}</td><td>{e(r['emailed'])}</td><td>{e(r['missing'] or '—')}</td>"
                   f"<td>{e(r['fix'] or '—')}</td></tr>" for r in rep.get("rows") or [])
    inv = rep.get("invoice") or {}
    q = rep.get("question") or {}
    return ("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Trip report — {e(mv.get('destination'))}</title><style>body{{font:15px/1.45 system-ui,sans-serif;margin:16px;color:#111}}"
            "table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-bottom:1px solid #ddd;padding:6px 8px;text-align:left;"
            "vertical-align:top}th{background:#f6f6f6}.wrap{overflow-x:auto}.dim{color:#666}</style></head><body>"
            f"<h1>{head}</h1><p class='dim'>{e(str(mv.get('starts_on') or '')[:10])} – {e(str(mv.get('ends_on') or '')[:10])} · TEST</p>"
            f"<p><b>{e(rep.get('line'))}</b></p>" + (f"<p>{e(q.get('ask'))}</p>" if q else "")
            + (f"<p>Invoice {e(inv.get('number'))}: {e(inv.get('total'))}</p>" if inv.get("number") else "")
            + "<div class='wrap'><table><tr><th>Traveller</th><th>Flight</th><th>Hotel</th><th>Status</th><th>Reference</th>"
              "<th>Itinerary emailed</th><th>What's missing</th><th>The fix</th></tr>" + rows + "</table></div>"
            "<p class='dim'>From the trip's master list, as it is now.</p></body></html>")


__all__ = ["BUCKETS", "bucket", "buckets", "line", "question", "card", "missing", "keep", "invited", "send_itineraries", "sent_record", "report", "page",
           "report_url", "token", "read_token"]
