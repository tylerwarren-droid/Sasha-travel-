"""DIVE · CR 68 · "TRY A REAL WEBSITE": paste a real operator's address → the AI reader (reader.py) drafts their products and
suppliers → the operator edits → a PRIVATE test API + docs for them. Everything here is behind the console token and noindex, labelled
"Demo built from public information · test mode", never claims to be the business, and SENDS NOTHING: this module has no code that
sends a message, an email, a call or a form — a booking is a simulation recorded here and nowhere else. The Blue Kyma demo is untouched.
  /sites                          the list + "Try a real website"
  /sites/{slug}                   the editor: products, suppliers (Confirm · Not ours · edit · add · each supplier's channel, unverified)
  /sites/{slug}/docs              the private docs        /sites/{slug}/v1/{op}   the private TEST API (console token or a site test key)"""
from __future__ import annotations

import asyncio
import html
import json
import re
from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import config, model as M, reader as RD, rules as R
from .store import dumps, loads, ts

BANNER = ("Demo built from public information · test mode. This is not {host}’s official API and {host} has not been contacted. "
          "Nothing is ever sent to them or to anyone they work with.")
CHANNELS = ("none", "whatsapp", "email", "phone", "web_form")
SUP_KINDS = ("boat", "hotel", "restaurant", "transfer", "gear", "guide", "photographer", "florist", "caterer", "music", "venue", "activity",
             "beauty", "planner", "other")
_TASKS: Dict[str, asyncio.Task] = {}
e = html.escape


def _slug(host: str, s) -> str:
    base = "site-" + re.sub(r"[^a-z0-9]+", "-", host.removeprefix("www.").lower()).strip("-")[:40]
    slug, n = base, 2
    while s.one("select 1 from site_ops where slug = ?", slug):
        slug, n = f"{base}-{n}", n + 1
    return slug


def site(s, slug: str) -> Optional[dict]:
    return s.one("select * from site_ops where slug = ?", slug)


def items(s, site_id: str, kind: str, *, live: bool = False):
    q = "select * from site_items where site_id = ? and kind = ?" + (" and status = 'confirmed'" if live else " and status != 'rejected'")
    return [{**r, "data": loads(r["data"]), "channel": loads(r["channel"]) if r["channel"] else None}
            for r in s.q(q + " order by confidence desc, created_at", site_id, kind)]


def _upd(s, sid: str, **kw):
    sets = ", ".join(f"{k} = ?" for k in kw)
    s.x(f"update site_ops set {sets}, updated_at = ? where id = ?", *kw.values(), ts(), sid)


async def run_read(s, sid: str) -> None:
    """The background read: progress on the row; the draft into site_items; an unreadable site says why."""
    row = s.one("select * from site_ops where id = ?", sid)
    try:
        got = await RD.read_site(row["url"], progress=lambda m: _upd(s, sid, progress=m))
    except RD.Unreadable as x:
        _upd(s, sid, state="unreadable", why=x.say, progress=None)
        return
    except Exception as x:   # never "nothing found": the failure is said
        _upd(s, sid, state="ai_failed", why=f"The read stopped ({type(x).__name__}). Not 'nothing found': try again.", progress=None)
        return
    _upd(s, sid, coverage=dumps(got["coverage"]), progress=None)
    if got["state"] != "read":
        _upd(s, sid, state=got["state"], why=got["why"])
        return
    d = got["draft"]
    if got.get("usage"):
        _upd(s, sid, usage=dumps(got["usage"]))
        import logging
        logging.getLogger("dive.sites").warning("AI reader %s: %s pages, %s in / %s out tokens, $%.4f", row["host"], got["coverage"]["pages_read"],
                                                got["usage"]["input_tokens"], got["usage"]["output_tokens"], got["usage"]["usd"])
    s.x("delete from site_items where site_id = ? and added_by = 'reader' and status = 'draft'", sid)   # a re-read replaces only untouched drafts
    for k, rows in (("product", d["products"]), ("supplier", d["suppliers"])):
        for x in rows:
            data = {f: x.get(f) for f in (("title", "kind", "price_text", "price_amount", "currency", "price_unit", "duration_text", "times_text",
                                           "group_size_text", "includes", "how_to_book") if k == "product" else ("name", "kind", "role", "contacts"))
                    if x.get(f) not in (None, "", [])}
            data["notes"] = x.get("notes") or []
            s.x("insert into site_items (id, site_id, kind, status, data, source_url, quote, quote_found, instruction_like, confidence, added_by, created_at) "
                "values (?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, 'reader', ?)", R.new_id("sit"), sid, k, dumps(data), x["source_url"][:400], x["quote"][:600],
                int(x["quote_found"]), int(x["instruction_like"]), int(x["confidence"]), ts())
    op = d.get("operator") or {}
    _upd(s, sid, state="read", why=None, name=(op.get("name") or row["host"])[:120], model=config.READER_MODEL,
         summary=dumps({"summary": (op.get("summary") or "")[:600], "location": (op.get("location") or "")[:120],
                        "instruction_like": d.get("instruction_like") or []}))


def start_read(db, sid: str) -> None:
    async def go():
        await run_read(db(), sid)
    t = asyncio.get_event_loop().create_task(go())
    _TASKS[sid] = t
    t.add_done_callback(lambda _t: _TASKS.pop(sid, None))


# ── the private test API (simulated bookings only) ─────────────────────────────────────────────────────────────────────

def _product_out(r: dict) -> dict:
    d = r["data"]
    return {"product_id": r["id"], "title": d.get("title", ""), "kind": d.get("kind", "other"),
            **{k: d[k] for k in ("price_text", "price_amount", "currency", "price_unit", "duration_text", "times_text", "group_size_text",
                                 "includes", "how_to_book") if d.get(k) not in (None, "", [])},
            "source": {"url": r["source_url"], "quote": r["quote"]}, "confidence": r["confidence"]}


async def api(s, srow: dict, op: str, v: dict) -> dict:
    host = srow["host"]
    note = f"Test mode: built from {host}'s public information. Nothing is sent to {host} or anyone they work with."
    prods = {r["id"]: r for r in items(s, srow["id"], "product", live=True)}
    if op == "products.list":
        return {"products": [_product_out(r) for r in prods.values()], "note": note}
    if op in ("products.get", "availability.check", "bookings.quote"):
        p = prods.get(str(v.get("product_id") or ""))
        if not p:
            raise M.DiveError("not_found", "No such product in this demo.")
        if op == "products.get":
            return {**_product_out(p), "note": note}
        if op == "availability.check":
            return {"product_id": p["id"], "availability": "unknown", "why": f"{host} isn't connected: this demo only knows their public pages.", "note": note}
        day, party = str(v.get("date") or ""), v.get("party")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or not isinstance(party, int) or not 1 <= party <= 60:
            raise M.DiveError("invalid_input", "A quote needs date (YYYY-MM-DD) and party (1–60).", {"path": "/date", "rule": "format"})
        d = p["data"]
        lines = [f"{srow['name']} · {d.get('title', '')} (demo built from public information)", f"{day} · {party} " + ("person" if party == 1 else "people")]
        if isinstance(d.get("price_amount"), (int, float)) and d.get("currency"):
            each = d["price_amount"]
            total = each * (party if d.get("price_unit") == "person" else 1)
            lines.append(f"Price on their site: {d.get('price_text') or each} → about {total:g} {d['currency']} (not charged)")
        elif d.get("price_text"):
            lines.append(f"Price on their site: {d['price_text']} (not charged)")
        for x in items(s, srow["id"], "supplier", live=True):
            ch = x["channel"] or {}
            how = f"would be asked by {ch['kind'].replace('_', ' ')} (not verified)" if ch.get("kind") not in (None, "none") else "no channel set"
            lines.append(f"{x['data'].get('name')} ({x['data'].get('kind')}) · {how} · nothing sent")
        lines.append(note)
        qid = R.new_id("sbq")
        body = {"quote_id": qid, "product_id": p["id"], "date": day, "party": party, "lines": lines, "state": "quoted", "sent": 0}
        s.x("insert into site_bookings (id, site_id, item_id, body, created_at) values (?, ?, ?, ?, ?)", qid, srow["id"], p["id"], dumps(body), ts())
        return body
    if op == "bookings.confirm":
        b = s.one("select * from site_bookings where id = ? and site_id = ?", str(v.get("quote_id") or ""), srow["id"])
        if not b:
            raise M.DiveError("not_found", "No such quote in this demo.")
        body = {**loads(b["body"]), "state": "simulated", "sent": 0, "confirmed_at": ts()[:19] + "Z",
                "what_happened": f"Nothing. In test mode this booking is only recorded here: no message, email, call or form went to {host} or anyone."}
        s.x("update site_bookings set body = ? where id = ?", dumps(body), b["id"])
        return body
    raise M.DiveError("not_found", f"There is no operation {op} in this demo.")


# ── pages ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

_CSS = """<style>.row{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}.k{font-family:ui-monospace,monospace;font-size:.82rem;overflow-wrap:anywhere}
.banner{background:#fff6e0;border:1px solid #f0d79a;border-radius:12px;padding:.6rem .9rem;font-size:.9rem}.q{color:var(--mut);font-style:italic}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(12rem,1fr));gap:.4rem}.grid label{font-size:.8rem;color:var(--mut)}
.badge{border:1px solid var(--line);border-radius:99px;padding:.05rem .5rem;font-size:.75rem}</style>"""


def _banner(host: str) -> str:
    return f'<p class="banner" data-testid="banner">{e(BANNER.format(host=host))}</p>'


def _src(r: dict) -> str:
    u = r["source_url"] or ""
    link = f'<a href="{e(u)}" target="_blank" rel="noopener noreferrer nofollow">{e(u)}</a>' if re.match(r"^https?://", u) else e(u)
    flags = "".join(f'<span class="chip no">{e(n)}</span> ' for n in r["data"].get("notes", []) if n)
    return f'<p class="q">“{e(r["quote"] or "")}”<br><span class="k">{link}</span></p>{flags}'


def _conf(r: dict) -> str:
    c = r["confidence"]
    who = "added by you" if r["added_by"] == "operator" else f"{c}% sure"
    return f'<span class="chip {"amb" if c < RD.LOW and r["added_by"] != "operator" else "ok"}" data-testid="confidence">{"low confidence · " if c < RD.LOW and r["added_by"] != "operator" else ""}{who}</span>'


def _inp(name: str, val, label: str, w: str = "") -> str:
    v = ", ".join(val) if isinstance(val, list) else ("" if val is None else str(val))
    return f'<div><label>{e(label)}</label><input name="{name}" value="{e(v)}" maxlength="300" {w}></div>'


def _product_card(slug: str, r: dict) -> str:
    d = r["data"]
    st = '<span class="chip ok">✓ Confirmed</span>' if r["status"] == "confirmed" else '<span class="badge">draft</span>'
    return f"""<div class="card" data-testid="product" data-status="{r['status']}"><form method="post" action="/sites/{slug}/items/{r['id']}">
<div class="row" style="justify-content:space-between"><b>{e(d.get('title', ''))}</b><span>{st} {_conf(r)}</span></div>
<div class="grid">{_inp('title', d.get('title'), 'Title')}{_inp('price_text', d.get('price_text'), 'Price (as on the site)')}
{_inp('duration_text', d.get('duration_text'), 'Duration')}{_inp('times_text', d.get('times_text'), 'Times')}
{_inp('group_size_text', d.get('group_size_text'), 'Group size')}{_inp('includes', d.get('includes'), 'Included (comma-separated)')}
{_inp('how_to_book', d.get('how_to_book'), 'How to book')}</div>{_src(r) if r['quote'] else ''}
<div class="row"><button class="go" name="action" value="confirm" title="Keeps this product, with your edits" data-testid="confirm">Confirm</button>
<button name="action" value="save" title="Saves your edits">Save</button>
<button name="action" value="reject" title="Removes it from the demo" data-testid="not-ours">Not ours</button></div></form></div>"""


def _supplier_card(slug: str, r: dict) -> str:
    d, ch = r["data"], r["channel"] or {}
    st = '<span class="chip ok">✓ Confirmed</span>' if r["status"] == "confirmed" else '<span class="badge">draft</span>'
    kinds = "".join(f'<option {"selected" if k == d.get("kind") else ""}>{k}</option>' for k in SUP_KINDS)
    chans = "".join(f'<option value="{k}" {"selected" if k == (ch.get("kind") or "none") else ""}>{k.replace("_", " ")}</option>' for k in CHANNELS)
    contacts = ", ".join(d.get("contacts") or [])
    return f"""<div class="card" data-testid="supplier" data-status="{r['status']}"><form method="post" action="/sites/{slug}/items/{r['id']}">
<div class="row" style="justify-content:space-between"><b>{e(d.get('name', ''))}</b><span>{st} {_conf(r)}</span></div>
<div class="grid">{_inp('name', d.get('name'), 'Name')}<div><label>Kind</label><select name="kind">{kinds}</select></div>{_inp('role', d.get('role'), 'What they do for you')}
<div><label>How bookings would reach them</label><select name="channel_kind">{chans}</select></div>{_inp('channel_address', ch.get('address'), 'Number / address / form')}</div>
{f'<p class="k">On the site: {e(contacts)}</p>' if contacts else ''}{_src(r) if r['quote'] else ''}
<p class="mut" style="font-size:.85rem">Channel: <b>not verified</b> — in this demo nothing is ever sent to them.</p>
<div class="row"><button class="go" name="action" value="confirm" title="Keeps this supplier, with your edits" data-testid="confirm">Confirm</button>
<button name="action" value="save" title="Saves your edits">Save</button>
<button name="action" value="reject" title="Removes it from the demo" data-testid="not-ours">Not ours</button></div></form></div>"""


STATES = {"reading": "Reading their website…", "read": "Read", "ai_off": "Pages read · the AI reader is off", "ai_failed": "The AI reader failed",
          "unreadable": "Couldn't read this site"}


def _editor(s, srow: dict, note: str = "") -> str:
    slug, host = srow["slug"], srow["host"]
    cov = loads(srow["coverage"]) if srow["coverage"] else None
    summ = loads(srow["summary"]) if srow["summary"] else {}
    head = f"""{_CSS}{_banner(host)}<div class="row" style="justify-content:space-between"><h1 style="margin:.3rem 0">{e(srow['name'])}</h1><span class="badge">TEST · PRIVATE</span></div>
<p class="mut">From <a href="{e(srow['url'])}" target="_blank" rel="noopener noreferrer nofollow">{e(srow['url'])}</a> · <span data-testid="state">{e(STATES.get(srow['state'], srow['state']))}</span></p>{note}"""
    if srow["state"] == "reading":
        return head + f'<div class="card"><p class="big" data-testid="progress">{e(srow["progress"] or "Starting…")}</p><p class="mut">Public pages only, robots.txt first, at most 15 pages. This page refreshes itself.</p></div><meta http-equiv="refresh" content="3">'
    out = [head]
    if srow["why"]:
        out.append(f'<div class="card"><p class="chip {"no" if srow["state"] in ("unreadable", "ai_failed") else "amb"} big" data-testid="why">{e(srow["why"])}</p></div>')
    if cov:
        failed = f' · {len(cov.get("failed") or [])} couldn’t be read' if cov.get("failed") else ""
        out.append(f'<p class="mut" data-testid="coverage">Read {cov["pages_read"]} of at most {cov["limit"]} pages{failed}'
                   f'{" · " + str(cov["skipped_by_robots"]) + " skipped (robots.txt)" if cov.get("skipped_by_robots") else ""}'
                   f'{" · more pages not read (limit)" if cov.get("more_links_unread") else ""}</p>')
    if srow.get("usage"):
        u = loads(srow["usage"])
        out.append(f'<p class="mut" data-testid="cost">AI reader ({e(u["model"])}): {u["input_tokens"]:,} tokens in, {u["output_tokens"]:,} out · about ${u["usd"]:.2f}</p>')
    if summ.get("summary"):
        out.append(f'<p>{e(summ["summary"])}</p>')
    for f in summ.get("instruction_like") or []:
        out.append(f'<p class="chip no">Instruction-like text on their site, ignored: “{e(f.get("quote", "")[:200])}”</p>')
    prods, sups = items(s, srow["id"], "product"), items(s, srow["id"], "supplier")
    out.append(f'<h2>Products · {len(prods)}</h2>' + "".join(_product_card(slug, r) for r in prods))
    out.append(f"""<form class="card row" method="post" action="/sites/{slug}/add" data-testid="add-product"><input type="hidden" name="kind" value="product">
<b>Add a product</b><input name="title" placeholder="e.g. Two boat dives" required maxlength="120"><input name="price_text" placeholder="Price, e.g. €170 per person" maxlength="80">
<button class="go" title="Adds it, confirmed">Add</button></form>""")
    out.append(f'<h2>Suppliers · {len(sups)}</h2>' + "".join(_supplier_card(slug, r) for r in sups))
    kinds = "".join(f"<option>{k}</option>" for k in SUP_KINDS)
    out.append(f"""<form class="card row" method="post" action="/sites/{slug}/add" data-testid="add-supplier"><input type="hidden" name="kind" value="supplier">
<b>Add a supplier</b><input name="name" placeholder="e.g. Delos Boats" required maxlength="120"><select name="supplier_kind">{kinds}</select>
<button class="go" title="Adds it, confirmed; its channel stays unverified">Add</button></form>""")
    conf = sum(1 for r in prods if r["status"] == "confirmed")
    pub = (f'<p>Published: <a href="/sites/{slug}/docs" data-testid="docs-link">the private docs</a> · API <span class="k">{e(config.PUBLIC_URL)}/sites/{slug}/v1</span></p>'
           if srow["published"] else "")
    out.append(f"""<div class="card"><b>Publish a private test API</b><p class="mut">{conf} confirmed product(s). Behind the console token, never public; bookings are simulated.</p>{pub}
<div class="row"><form method="post" action="/sites/{slug}/publish"><button class="go" data-testid="publish" title="Publishes the private docs and test API">{"Publish again" if srow["published"] else "Publish"}</button></form>
<form method="post" action="/sites/{slug}/key"><button title="A test key for the private API, shown once" data-testid="issue-key">Issue a test key</button></form>
<form method="post" action="/sites/{slug}/reread"><button title="Reads the site again (keeps what you confirmed or added)">Read again</button></form></div></div>""")
    return "".join(out)


def _docs(s, srow: dict) -> str:
    host, slug = srow["host"], srow["slug"]
    base = f"{config.PUBLIC_URL}/sites/{slug}/v1"
    prods = items(s, srow["id"], "product", live=True)
    rows = "".join(f'<tr><td><b>{e(r["data"].get("title", ""))}</b><br><span class="k">{r["id"]}</span></td><td>{e(r["data"].get("price_text") or "—")}</td>'
                   f'<td>{e(r["data"].get("duration_text") or "—")}</td><td>' + (f'<a href="{e(r["source_url"])}" rel="noopener noreferrer nofollow" target="_blank">source</a>'
                   if re.match(r"^https?://", r["source_url"] or "") else "added by the operator") + '</td></tr>' for r in prods) or '<tr><td colspan="4">No confirmed products yet.</td></tr>'
    return f"""{_CSS}{_banner(host)}<h1>{e(srow['name'])} — test API (demo)</h1>
<p>A private, test-mode API built from {e(host)}’s public website, to show what AgAPI would give them. It is not {e(host)}’s API; they haven’t been
contacted; bookings are simulated and nothing is sent to anyone.</p>
<div class="card"><p>Every call is <code>POST {e(base)}/{{operation}}</code> with <code>Authorization: Bearer &lt;a test key from the console&gt;</code> and a JSON body.</p>
<table><tr><th>Operation</th><th>What it does</th></tr>
<tr><td><code>products.list</code></td><td>The confirmed products, each with its source sentence and page.</td></tr>
<tr><td><code>products.get</code></td><td><code>{{"product_id"}}</code> → one product.</td></tr>
<tr><td><code>availability.check</code></td><td>Always <code>unknown</code>: the business isn’t connected.</td></tr>
<tr><td><code>bookings.quote</code></td><td><code>{{"product_id", "date", "party"}}</code> → a read-back: the product, the price on their site, and who would be asked (nothing is sent).</td></tr>
<tr><td><code>bookings.confirm</code></td><td><code>{{"quote_id"}}</code> → <code>"state": "simulated", "sent": 0</code>.</td></tr></table>
<pre class="k">curl -s {e(base)}/products.list -H "Authorization: Bearer $KEY" -d '{{}}'</pre></div>
<h2>Products</h2><table data-testid="docs-products"><tr><th>Product</th><th>Price (as on their site)</th><th>Duration</th><th></th></tr>{rows}</table>"""


def bind(app, db, ok):
    from .app import page

    def door(req: Request):
        return None if ok(req) else RedirectResponse("/console/login?next=/start", status_code=303)

    def pg(title: str, body: str, host: str = "", status: int = 200):
        r = page(title, body, footer="Demo built from public information · test mode · powered by AgAPI", status=status)
        r.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return r

    @app.get("/sites", response_class=HTMLResponse)
    async def list_sites(req: Request):
        if (r := door(req)):
            return r
        rows = "".join(f'<p><a href="/sites/{x["slug"]}">{e(x["name"])}</a> <span class="mut">· {e(x["host"])} · {e(STATES.get(x["state"], x["state"]))}</span></p>'
                       for x in db().q("select * from site_ops order by created_at desc limit 30"))
        return pg("Try a real website", f"""{_CSS}<h1>Try a real website</h1>
<p>Paste a real operator’s website. AgAPI reads its public pages (robots.txt first, at most 15 pages), drafts their products and the businesses
they work with, and you edit it into a <b>private test API</b>. Nobody is contacted; nothing is ever sent.</p>
<form class="card row" method="post" action="/sites/read" data-testid="read-form"><input name="url" placeholder="https://www.their-website.com" required style="min-width:18rem;flex:1">
<button class="go" title="Reads their public pages from our server">Read it</button></form>{('<div class="card"><b>Read before</b>' + rows + '</div>') if rows else ''}
<p><a href="/start">← Back to the Blue Kyma demo</a></p>""")

    @app.post("/sites/read")
    async def read(req: Request):
        if (r := door(req)):
            return r
        url = str(dict((await req.form()).items()).get("url") or "")
        try:
            u = RD.normalise(url)
        except RD.Unreadable as x:
            return pg("Try a real website", f'<p class="chip no big">{e(x.say)}</p><p><a href="/sites">Back</a></p>', status=400)
        from urllib.parse import urlsplit
        host = urlsplit(u).hostname
        s = db()
        sid, slug = R.new_id("sit"), _slug(host, s)
        s.x("insert into site_ops (id, slug, url, host, name, state, progress, created_at, updated_at) values (?, ?, ?, ?, ?, 'reading', 'Starting…', ?, ?)",
            sid, slug, u, host, host.removeprefix("www."), ts(), ts())
        start_read(db, sid)
        return RedirectResponse(f"/sites/{slug}", status_code=303)

    @app.get("/sites/{slug}", response_class=HTMLResponse)
    async def editor(slug: str, req: Request, done: str = ""):
        if (r := door(req)):
            return r
        srow = site(db(), slug)
        if not srow:
            return pg("Not found", "<h1>No such demo</h1>", status=404)
        notes = {"published": '<p class="chip ok big" data-testid="published">✓ Published: private docs and a test API. Nothing was sent to anyone.</p>',
                 "need_product": '<p class="chip no big">Confirm or add at least one product first.</p>'}
        note = notes.get(done, "")
        if done.startswith("key:"):
            note = f'<p class="chip ok" data-testid="key">Test key, shown once: <span class="k">{e(done[4:])}</span></p>'
        return pg(srow["name"] + " · demo", _editor(db(), srow, note), srow["host"])

    @app.get("/sites/{slug}/state.json")
    async def state_json(slug: str, req: Request):
        """The demo as data (behind the console token): what was read, found, with what confidence, and what it cost."""
        if not ok(req):
            return JSONResponse({"error": "unauthenticated"}, 401)
        s = db()
        srow = site(s, slug)
        if not srow:
            return JSONResponse({"error": "not_found"}, 404)
        return JSONResponse({k: srow[k] for k in ("slug", "url", "host", "name", "state", "why", "published", "model")} |
                            {"coverage": loads(srow["coverage"]) if srow["coverage"] else None, "usage": loads(srow["usage"]) if srow.get("usage") else None,
                             "summary": loads(srow["summary"]) if srow["summary"] else None,
                             "products": [{**r["data"], "status": r["status"], "confidence": r["confidence"], "quote_found": bool(r["quote_found"]),
                                           "source_url": r["source_url"], "quote": r["quote"]} for r in items(s, srow["id"], "product")],
                             "suppliers": [{**r["data"], "status": r["status"], "confidence": r["confidence"], "quote_found": bool(r["quote_found"]),
                                            "instruction_like": bool(r["instruction_like"]), "source_url": r["source_url"], "quote": r["quote"]}
                                           for r in items(s, srow["id"], "supplier")]}, headers={"X-Robots-Tag": "noindex"})

    @app.post("/sites/{slug}/items/{item_id}")
    async def edit_item(slug: str, item_id: str, req: Request):
        if (r := door(req)):
            return r
        s = db()
        srow = site(s, slug)
        it = srow and s.one("select * from site_items where id = ? and site_id = ?", item_id, srow["id"])
        if not it:
            return pg("Not found", "<h1>No such item</h1>", status=404)
        f = {k: str(v)[:300] for k, v in (await req.form()).items()}
        d = loads(it["data"])
        if it["kind"] == "product":
            for k in ("title", "price_text", "duration_text", "times_text", "group_size_text", "how_to_book"):
                if k in f:
                    d[k] = f[k].strip()
            if "includes" in f:
                d["includes"] = [x.strip() for x in f["includes"].split(",") if x.strip()][:12]
        else:
            for k in ("name", "role"):
                if k in f:
                    d[k] = f[k].strip()
            if f.get("kind") in SUP_KINDS:
                d["kind"] = f["kind"]
        ch = it["channel"]
        if it["kind"] == "supplier" and f.get("channel_kind") in CHANNELS:
            ch = dumps({"kind": f["channel_kind"], "address": f.get("channel_address", "").strip()[:200], "verified": False})
        status = {"confirm": "confirmed", "reject": "rejected"}.get(f.get("action", ""), it["status"])
        s.x("update site_items set data = ?, channel = ?, status = ? where id = ?", dumps(d), ch, status, it["id"])
        return RedirectResponse(f"/sites/{slug}#{it['kind']}s", status_code=303)

    @app.post("/sites/{slug}/add")
    async def add(slug: str, req: Request):
        if (r := door(req)):
            return r
        s = db()
        srow = site(s, slug)
        if not srow:
            return pg("Not found", "<h1>No such demo</h1>", status=404)
        f = {k: str(v)[:200].strip() for k, v in (await req.form()).items()}
        if f.get("kind") == "product" and f.get("title"):
            data = {"title": f["title"], "kind": "other", **({"price_text": f["price_text"]} if f.get("price_text") else {})}
        elif f.get("kind") == "supplier" and f.get("name"):
            data = {"name": f["name"], "kind": f.get("supplier_kind") if f.get("supplier_kind") in SUP_KINDS else "other", "role": ""}
        else:
            return RedirectResponse(f"/sites/{slug}", status_code=303)
        s.x("insert into site_items (id, site_id, kind, status, data, source_url, quote, confidence, added_by, created_at) values "
            "(?, ?, ?, 'confirmed', ?, '', '', 100, 'operator', ?)", R.new_id("sit"), srow["id"], f["kind"], dumps(data), ts())
        return RedirectResponse(f"/sites/{slug}", status_code=303)

    @app.post("/sites/{slug}/publish")
    async def publish(slug: str, req: Request):
        if (r := door(req)):
            return r
        s = db()
        srow = site(s, slug)
        if not srow:
            return pg("Not found", "<h1>No such demo</h1>", status=404)
        if not items(s, srow["id"], "product", live=True):
            return RedirectResponse(f"/sites/{slug}?done=need_product", status_code=303)
        _upd(s, srow["id"], published=1)
        return RedirectResponse(f"/sites/{slug}?done=published", status_code=303)

    @app.post("/sites/{slug}/key")
    async def key(slug: str, req: Request):
        if (r := door(req)):
            return r
        s = db()
        srow = site(s, slug)
        if not srow:
            return pg("Not found", "<h1>No such demo</h1>", status=404)
        k = M.issue_key(s, "site:" + srow["id"], "site test key")
        return pg(srow["name"] + " · demo", _editor(s, srow, f'<p class="chip ok" data-testid="key">Test key, shown once: <span class="k">{e(k["key"])}</span></p>'), srow["host"])

    @app.post("/sites/{slug}/reread")
    async def reread(slug: str, req: Request):
        if (r := door(req)):
            return r
        s = db()
        srow = site(s, slug)
        if srow and srow["state"] != "reading":
            _upd(s, srow["id"], state="reading", progress="Starting…", why=None)
            start_read(db, srow["id"])
        return RedirectResponse(f"/sites/{slug}", status_code=303)

    @app.get("/sites/{slug}/docs", response_class=HTMLResponse)
    async def docs(slug: str, req: Request):
        if (r := door(req)):
            return r
        srow = site(db(), slug)
        if not srow or not srow["published"]:
            return pg("Not published", "<h1>Not published yet</h1>", status=404)
        return pg(srow["name"] + " — test API (demo)", _docs(db(), srow), srow["host"])

    @app.post("/sites/{slug}/v1/{op}")
    async def site_api(slug: str, op: str, req: Request):
        s = db()
        srow = site(s, slug)
        presented = (req.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        key_ok = presented.startswith("opk_test_") and srow and s.one("select 1 from op_keys where secret_hmac = ? and operator_id = ? and state = 'active'",
                                                                       M._hmac(presented), "site:" + srow["id"])
        if not (srow and srow["published"] and (ok(req) or key_ok)):
            return JSONResponse({"ok": False, "error": {"code": "unauthenticated" if srow else "not_found",
                                                        "message": "A private demo: the console token or this demo's test key is needed."}}, 401 if srow else 404)
        try:
            raw = await req.body()
            v = json.loads(raw) if raw.strip() else {}
            if not isinstance(v, dict):
                raise ValueError
        except ValueError:
            return JSONResponse({"ok": False, "error": {"code": "invalid_input", "message": "The body is a JSON object."}}, 400)
        try:
            return JSONResponse({"ok": True, "mode": "test", "demo": "built from public information", "result": await api(s, srow, op, v)},
                                headers={"X-Robots-Tag": "noindex"})
        except M.DiveError as x:
            return JSONResponse({"ok": False, "error": x.body()}, x.http)
