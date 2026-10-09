"""DIVE · CR 66 · TYLER'S START PAGE (/start, behind the console token): every beat of EU 212's 5-minute script as one link,
what to say at each, and one button that puts the demo back to its starting state. Nothing here sends anything:
  /start           the beats, in order, with where things stand now
  /start/reset     POST · the operator back to "Blue Kyma Diving (demo)" with an empty console (sandbox.reset, test mode only)
  /start/phone     → the customer's phone: the newest link their phone received (captured in test)
  /start/proof     → the console with the newest booking's Proof open"""
from __future__ import annotations

import html

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from . import channels as CH, config, model as M, ops as OPS
from .model import DiveError

SLUG = "blue-kyma"


async def reset_demo(s) -> dict:
    """The starting state, exactly as the rehearsal and the browser script set it: the operator, then an empty console."""
    o = M.put_operator(s, SLUG, "Blue Kyma Diving (demo)", "Europe/Athens", ["en", "el"], config.PUBLIC_URL + "/fake/blue-kyma", config.FOOTER)
    return await OPS.sandbox_reset(s, o, {}, None)


def _state(s) -> dict:
    o = s.one("select * from operators where slug = ?", SLUG)
    if not o:
        return {"suppliers": 0, "verified": 0, "published": False, "bookings": 0, "latest": None, "phone": 0}
    sups = s.q("select id from suppliers where operator_id = ? and status = 'confirmed'", o["id"])
    ver = s.one("select count(*) n from channels c join suppliers x on x.id = c.supplier_id where x.operator_id = ? and c.verified = 1", o["id"])["n"]
    pub = bool(s.one("select 1 from packages where operator_id = ? and published = 1", o["id"]))
    bs = s.q("select state, evidence_id from bundles where operator_id = ? order by created_at desc", o["id"])
    phone = s.one("select count(*) n from captured where channel = 'sms'")["n"]
    return {"suppliers": len(sups), "verified": ver, "published": pub, "bookings": len(bs), "latest": bs[0]["state"] if bs else None, "phone": phone}


def _local(t: str) -> str:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    d = datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(ZoneInfo(config.TIMEZONE))
    return d.strftime("%a %H:%M"), (d + timedelta(hours=24)).strftime("%a %H:%M")


def _arrivals(s) -> str:
    """CR 67 · the live check: did Jon's hi and the gear inbox's email reach DIVE? (times only, never a number or an address)"""
    w = config.switches()
    out = []
    if w["whatsapp_hook"]:
        last = s.one("select address, received_at t from inbound where channel = 'whatsapp' order by id desc limit 1")
        if last:
            is_open = CH.window_open(s, last["address"])
            out.append(f'<p data-testid="wa-window">Jon’s WhatsApp: last message {_local(last["t"])[0]} Mykonos · the 24-hour window is '
                       + (f'open until {_local(last["t"])[1]}' if is_open else '<b>closed</b>: ask Jon to send hi') + '</p>')
        else:
            out.append('<p data-testid="wa-window">Jon’s WhatsApp: <b>nothing received yet</b>. Ask Jon to send hi.</p>')
    if w["email_hook"]:
        t = s.one("select max(received_at) t from inbound where channel = 'email'")["t"]
        out.append(f'<p data-testid="mail-in">Gear inbox: last email received {_local(t)[0]} Mykonos</p>' if t else
                   '<p data-testid="mail-in">Gear inbox: <b>nothing received yet</b>.</p>')
    return "".join(out)


def _switches() -> str:
    """CR 67 · what is real right now (booleans only)."""
    w = config.switches()
    on = lambda b: '<span class="chip no">REAL</span>' if b else '<span class="chip ok">simulated</span>'
    return (f'<p data-testid="switches">Boat WhatsApp: {on(w["whatsapp_real"])} · Gear email: {on(w["email_real"])}'
            f'{"" if w["whatsapp_real"] or w["email_real"] else " · nothing on this demo sends a real message"}</p>')


# (time, the step, the link, what to click there, what to say) — EU 212 demo-script.md, in test mode
BEATS = [
    ("0:00", "The opening", None, "Nothing to click. The console is open on the left screen, the customer's phone on the right.",
     "Most of the world's travel isn't on an API. A dive shop, a boat, a taverna take bookings on WhatsApp and paper. "
     "An operator who packages them has no API to sell through. AgAPI gives them one."),
    ("0:30", "Find suppliers", "/console#find",
     "Click Find suppliers on my site. Five businesses appear, each quoting the sentence it came from. Confirm four; "
     "Rival Boats: Not ours. Pick each one's channel and click Send verification.",
     "Blue Kyma's suppliers have no APIs. AgAPI reads his website, lists the businesses he works with, and he confirms them. "
     "Nothing is sent to anyone he didn't confirm."),
    ("0:55", "The boat says yes (test drawer)", "/console#drawer",
     "In test mode, click Supplier: YES for Aegean Boats and Kyma Gear. On rehearsal day this is Jon's phone instead.",
     "In test mode we can play the supplier. The boat just agreed to receive bookings, on WhatsApp."),
    ("1:15", "Publish, then his docs", "/o/blue-kyma/docs",
     "Back in the console: Packages → Create “Discover Mykonos” → Publish. Then open this link: his docs, under his name.",
     "One click, and he has an API: his packages, his name, his keys. A travel app or an OTA can sell his dives tomorrow."),
    ("1:45", "The customer books", "/o/blue-kyma/book",
     "On the right screen: Discover Mykonos, a Tuesday at 09:00, 4 divers, a name and phone, then continue to the read-back.",
     "The customer sees every leg, who provides it, and how it'll be confirmed."),
    ("2:10", "The customer's phone", "/start/phone",
     "Opens the newest link the customer's phone received. Tap Yes, book it.",
     "And says yes once."),
    ("2:30", "The suppliers answer (test drawer)", "/console#drawer",
     "Click Supplier: YES on the gear shop and ΝΑΙ on the boat. Then the Bookings tab: every leg turns ✓, then Confirmed.",
     "Three suppliers, three channels: a web form, an email, a WhatsApp. Each answer is the supplier's own. "
     "One booking, confirmed by businesses that have never seen an API."),
    ("3:30", "Proof", "/start/proof",
     "Opens the newest booking's proof. Click Verify: “✓ The record matches.”",
     "Every leg has proof: what we sent, what they answered, when. If there's ever a dispute, the operator has the record."),
    ("4:00", "The failure beat (test drawer)", "/console#drawer",
     "Click Prepare the Thursday booking. Back in the drawer, click Supplier: NO, full on the boat. Bookings shows ✕ Couldn't confirm "
     "and one button: Offer another time.",
     "When a supplier says no, the customer hears it straight, nothing is charged, nothing half-booked, and the operator gets one "
     "button to offer another time. If WhatsApp were down, AgAPI would say 'couldn't reach them', never 'sold out'."),
    ("4:40", "Close on Activity", "/console#activity",
     "Nothing to click. Every step is listed, each with its proof.",
     "AgAPI gives an API to businesses that don't have one. DIVE is the operator's own API on top of it."),
]


def _page(st: dict, note: str, s=None) -> str:
    e = html.escape
    rows = []
    for i, (t, name, link, do, say) in enumerate(BEATS, 1):
        a = (f'<a class="btn go" href="{e(link)}" target="_blank" rel="noopener" data-testid="beat-{i}" title="Opens this step in a new tab">Open</a> '
             f'<span class="k">{e(config.PUBLIC_URL + link)}</span>') if link else '<span class="mut">No link: just talk.</span>'
        rows.append(f'<div class="card" data-testid="beat"><div class="row"><span class="badge">{t}</span><b>{i}. {e(name)}</b></div>'
                    f'<p>{a}</p><p><b>Do:</b> {e(do)}</p><p><b>Say:</b> “{e(say)}”</p></div>')
    now = (f"{st['suppliers']} suppliers confirmed · {st['verified']} channels verified · package "
           f"{'published' if st['published'] else 'not published'} · {st['bookings']} booking(s)"
           + (f", the newest {e(st['latest'].replace('_', ' '))}" if st["latest"] else "") + f" · {st['phone']} link(s) on the customer's phone")
    return f"""<style>.row{{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap}}.k{{font-family:ui-monospace,monospace;font-size:.8rem;overflow-wrap:anywhere;color:var(--mut)}}
.badge{{border:1px solid var(--line);border-radius:99px;padding:.1rem .6rem;font-size:.8rem}}</style>
<div class="row" style="justify-content:space-between"><h1 style="margin:.2rem 0">Run the DIVE demo</h1><span class="badge">TEST</span></div>
<p class="mut">Five minutes, ten steps. Each step is one link. Nothing on this page sends a real message.</p>
{note}
<div class="card"><b>Where things stand</b><p data-testid="state">{now}</p>{_switches()}{_arrivals(s) if s is not None else ""}
<form method="post" action="/start/reset"><button class="go" data-testid="reset" title="Empties the console: no suppliers, packages, bookings, keys or activity. The operator stays Blue Kyma Diving (demo).">Reset demo</button>
<span class="mut"> Before each run. Takes a second.</span></form></div>
{''.join(rows)}
<div class="card"><b>Also open</b><p><a href="/console" target="_blank" rel="noopener">The console</a> ·
<a href="/o/blue-kyma/docs" target="_blank" rel="noopener">Blue Kyma's API docs</a> ·
<a href="{e(config.SANDBOX_URL)}/docs" target="_blank" rel="noopener">AgAPI's docs</a> ·
<a href="/fake/blue-kyma" target="_blank" rel="noopener">Blue Kyma's website (ours)</a></p></div>"""


def bind(app, db, ok):
    from .app import page

    def door(req: Request):
        return None if ok(req) else RedirectResponse("/console/login?next=/start", status_code=303)

    @app.get("/start", response_class=HTMLResponse)
    async def start(req: Request, done: str = ""):
        if (r := door(req)):
            return r
        note = '<p class="chip ok big" data-testid="reset-done">✓ Reset. The console is empty and ready for step 1.</p>' if done == "reset" else ""
        return page("Run the DIVE demo", _page(_state(db()), note, db()))

    @app.post("/start/reset")
    async def reset(req: Request):
        if (r := door(req)):
            return r
        try:
            await reset_demo(db())
        except DiveError as e:
            return page("Run the DIVE demo", f'<p class="chip no">{html.escape(e.message)}</p><p><a href="/start">Back</a></p>', status=e.http)
        return RedirectResponse("/start?done=reset", status_code=303)

    @app.get("/start/phone")
    async def phone(req: Request):
        if (r := door(req)):
            return r
        m = db().one("select body from captured where channel = 'sms' order by id desc")
        link = m and m["body"].rsplit(" ", 1)[-1]
        if link and link.startswith(config.PUBLIC_URL + "/o/"):
            return RedirectResponse(link[len(config.PUBLIC_URL):], status_code=303)
        return page("The customer's phone", '<div class="card"><p class="big">Nothing on the customer\'s phone yet.</p>'
                    '<p>It gets a link once the customer continues to the read-back on the booking page (step 5).</p>'
                    '<p><a class="btn" href="/start">Back to the steps</a></p></div>')

    @app.get("/start/proof")
    async def proof(req: Request):
        if (r := door(req)):
            return r
        s = db()
        o = s.one("select id from operators where slug = ?", SLUG)
        b = o and s.one("select evidence_id from bundles where operator_id = ? and evidence_id is not null order by created_at desc", o["id"])
        if b:
            return RedirectResponse("/console#proof=" + b["evidence_id"], status_code=303)
        return page("Proof", '<div class="card"><p class="big">No booking has proof yet.</p>'
                    '<p>A booking gets its proof once every supplier has answered (step 7).</p><p><a class="btn" href="/start">Back to the steps</a></p></div>')
