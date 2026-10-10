"""CR 64 · DIVE PREP — a hosted FAKE SUPPLIER: /fixtures/taverna, a restaurant's own booking form (date, time, party size, name →
a confirmation page with a reference). Generic: it doesn't depend on EU 212's DIVE design, and the DIVE model/API isn't built here.

It behaves like a real small supplier, so an agent filling it meets real outcomes — and NOT like a booking platform (no real
restaurant, no network, nothing leaves the sandbox; robots told to stay away):
  · closed on Mondays → a refusal page that says so;  · a party over 8 → "message us on WhatsApp" (its number is a fixture:
    sandbox.simulate_reply plays its YES / NO);  · Saturday 21:00 is full → that page;  · otherwise CONFIRMED, reference TAV-XXXXXX.
Every page carries stable ids (#booking-form, #confirmation, #reference, #refusal) so a filled booking can be proven.
"""
from __future__ import annotations

import html
import re
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()
_store = None
WHATSAPP = "+447700900555"                      # the taverna's WhatsApp (Ofcom's drama range): a fixture, never a real number
SLOTS = [f"{h:02d}:{m:02d}" for h in (13, 14) for m in (0, 30)] + ["15:00"] + [f"{h:02d}:{m:02d}" for h in (20, 21, 22) for m in (0, 30)]
MAX_PARTY, AHEAD_DAYS = 8, 90


def bind(get_store) -> None:
    global _store
    _store = get_store


def _db():
    s = _store()
    s.x("create table if not exists fixture_bookings (ref text primary key, venue text not null, day text not null, time text not null, "
        "party int not null, name text not null, created_at text not null)")
    return s


_CSS = """:root{--bg:#fbf7f0;--fg:#2a2118;--mut:#7a6d5e;--line:#e6dccd;--ok:#2f6b3a;--no:#9b2c2c;--card:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#17130f;--fg:#f3ece2;--mut:#b2a594;--line:#352c22;--ok:#7fcf8e;--no:#f19a9a;--card:#1f1a15}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 Georgia,serif}main{max-width:30rem;margin:0 auto;padding:1.2rem 1rem 3rem}
.fx{font:12px/1.4 system-ui,sans-serif;color:var(--mut);border:1px dashed var(--line);border-radius:8px;padding:.4rem .6rem;margin-bottom:1rem}
h1{margin:.2rem 0}label{display:block;margin:.8rem 0 .2rem;font:600 14px system-ui,sans-serif}
input,select,button{font:16px system-ui,sans-serif;width:100%;box-sizing:border-box;padding:.75rem;border-radius:10px;border:1px solid var(--line);
background:var(--card);color:var(--fg)}button{margin-top:1.2rem;background:var(--fg);color:var(--bg);border:0;cursor:pointer;font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:1rem;margin:1rem 0}.ok{color:var(--ok)}.no{color:var(--no)}"""


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{html.escape(title)} · Taverna Sandbox</title><style>{_CSS}</style></head><body><main>
<p class="fx">AgAPI sandbox fixture — not a real restaurant. Nothing here is sent anywhere.</p>{body}</main></body></html>""",
                        status_code=status, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"})


@router.get("/fixtures/taverna", response_class=HTMLResponse)
async def taverna_form():
    opts_t = "".join(f'<option value="{t}">{t}</option>' for t in SLOTS)
    opts_p = "".join(f'<option value="{n}"{" selected" if n == 2 else ""}>{n}</option>' for n in range(1, 13))
    return _page("Book a table", f"""<h1>Taverna Sandbox</h1><p>Calle de la Prueba 1, Madrid · lunch 13:00–15:00, dinner 20:00–22:30 ·
closed Mondays · WhatsApp <span id="whatsapp">{WHATSAPP}</span></p>
<form id="booking-form" method="post" action="/fixtures/taverna/book">
<label for="date">Date</label><input id="date" name="date" type="date" required>
<label for="time">Time</label><select id="time" name="time" required>{opts_t}</select>
<label for="party_size">Party size</label><select id="party_size" name="party_size" required>{opts_p}</select>
<label for="name">Name for the booking</label><input id="name" name="name" type="text" maxlength="80" autocomplete="name" required>
<button id="book" type="submit">Book table</button></form>""")


def _refuse(why: str, status: int = 409) -> HTMLResponse:
    return _page("Not booked", f'<h1 class="no">Not booked</h1><p id="refusal">{html.escape(why)}</p>'
                               f'<p><a href="/fixtures/taverna">Choose another time</a></p>', status)


@router.post("/fixtures/taverna/book", response_class=HTMLResponse)
async def taverna_book(req: Request):
    f = dict((await req.form()).items())
    try:
        day = date.fromisoformat(str(f.get("date") or ""))
    except ValueError:
        return _refuse("Please choose a date.", 400)
    t, name = str(f.get("time") or ""), re.sub(r"\s+", " ", str(f.get("name") or "")).strip()
    try:
        party = int(str(f.get("party_size") or ""))
    except ValueError:
        return _refuse("Please choose a party size.", 400)
    today = datetime.now(timezone.utc).date()
    if t not in SLOTS:
        return _refuse("Please choose one of our times.", 400)
    if not 1 <= len(name) <= 80 or re.search(r"https?://|[<>]", name):
        return _refuse("Please give a name for the booking.", 400)
    if not today <= day <= today + timedelta(days=AHEAD_DAYS):
        return _refuse(f"We take bookings from today up to {AHEAD_DAYS} days ahead.")
    if day.weekday() == 0:
        return _refuse("We're closed on Mondays.")
    if party > MAX_PARTY:
        return _refuse(f"For more than {MAX_PARTY} people, please message us on WhatsApp ({WHATSAPP}).")
    if day.weekday() == 5 and t == "21:00":
        return _refuse("Sorry — we're full at 21:00 that Saturday. 20:30 or 22:00?")
    ref = "TAV-" + secrets.token_hex(3).upper()
    _db().x("insert into fixture_bookings (ref, venue, day, time, party, name, created_at) values (?, 'taverna', ?, ?, ?, ?, ?)",
            ref, day.isoformat(), t, party, name, datetime.now(timezone.utc).isoformat())
    return _confirmed(ref, 201)


def _confirmed(ref: str, status: int = 200) -> HTMLResponse:
    b = _db().one("select * from fixture_bookings where ref = ?", ref)
    if not b:
        return _page("Not found", '<h1>No such booking</h1><p id="refusal">We have no booking with that reference.</p>', 404)
    d = date.fromisoformat(b["day"])
    return _page("Booking confirmed", f"""<h1 class="ok">Booking confirmed</h1><div class="card" id="confirmation"
data-date="{b['day']}" data-time="{b['time']}" data-party="{b['party']}"><p>Table for {b['party']} on {d.strftime('%a %d %b %Y')} at {b['time']},
in the name of {html.escape(b['name'])}.</p><p>Reference <strong id="reference">{b['ref']}</strong></p></div>
<p>To change it, message us on WhatsApp ({WHATSAPP}).</p>""", status)


@router.get("/fixtures/taverna/booking/{ref}", response_class=HTMLResponse)
async def taverna_booking(ref: str):
    """The confirmation again (as a supplier's confirmation link would show it)."""
    return _confirmed(ref if re.fullmatch(r"TAV-[0-9A-F]{6}", ref) else "")


# ── CR 72 · the subscription radar's demo: a sample statement, and a STAND-IN cancel page (never the merchant's) ──────────

@router.get("/fixtures/statement/sample.csv")
async def sample_statement():
    """A fictional person's three months: ~10 subscriptions among ordinary spending (test mode's sample)."""
    from fastapi.responses import PlainTextResponse
    from . import subscriptions as SB
    return PlainTextResponse(SB.sample_csv(), media_type="text/csv", headers={"Content-Disposition": 'inline; filename="sample-statement.csv"'})


@router.get("/fixtures/cancel/{slug}", response_class=HTMLResponse)
async def cancel_standin(slug: str):
    """Test mode's stand-in for a merchant's cancel page — labelled as such; it is NOT the merchant's site and cancels nothing."""
    name = html.escape(re.sub(r"[^a-z0-9 -]+", "", slug.replace("-", " ")).title()[:60])
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Sandbox stand-in · cancel {name}</title>
<style>body{{font:17px/1.5 system-ui;max-width:32rem;margin:3rem auto;padding:0 1.2rem}}.t{{background:#fff3cd;border:1px solid #e0c36b;border-radius:6px;padding:.2rem .5rem}}</style>
</head><body><p class="t">AgAPI sandbox · test mode</p><h1>Cancel {name} — a stand-in</h1>
<p>This page stands in for {name}'s own cancel page in test mode. It is <b>not</b> {name}'s site, and nothing here cancels anything.</p>
<p>In live mode, AgAPI reads {name}'s own help pages for the real cancel route, and you finish it there yourself.</p></body></html>""",
                        headers={"X-Robots-Tag": "noindex, nofollow"})


# ── CR 74 · fine print's demo: "Example Bank" (NOT a real bank — every page says so), two cards with Guides to Benefits as PDFs ─

@router.get("/fixtures/cards/{slug}", response_class=HTMLResponse)
async def card_product_page(slug: str):
    from .fineprint import fixture as FX
    if slug not in FX.CARDS:
        return HTMLResponse("Not found", status_code=404)
    return HTMLResponse(FX.product_page(slug), headers={"X-Robots-Tag": "noindex, nofollow"})


@router.get("/fixtures/cards/{slug}/guide-to-benefits.pdf")
async def card_guide_pdf(slug: str):
    from fastapi.responses import Response
    from .fineprint import fixture as FX
    if slug not in FX.CARDS:
        return HTMLResponse("Not found", status_code=404)
    return Response(FX.guide_pdf(slug), media_type="application/pdf", headers={"X-Robots-Tag": "noindex, nofollow"})


@router.get("/fixtures/rentals/{slug}", response_class=HTMLResponse)
async def rental_terms_page(slug: str):
    """CR 74b · the demo's fake rental company's country terms — labelled as not a real company."""
    from .fineprint import fixture as FX
    if slug not in FX.RENTALS:
        return HTMLResponse("Not found", status_code=404)
    return HTMLResponse(FX.rental_page(slug), headers={"X-Robots-Tag": "noindex, nofollow"})
