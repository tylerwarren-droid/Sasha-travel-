"""DIVE · the demo service (its own Railway service, its own volume and DB). Routes:
  /fake/blue-kyma[/partners]     the operator's (fake) site — what Magellan reads
  /op/v1/{op}                    the operator's API (Bearer DIVE_CONSOLE_TOKEN; the console calls it server-side)
  /o/{slug}/v1/{op}              the GENERATED API (Bearer opk_test_…, scoped to that operator) · /o/{slug}/docs its docs
  /o/{slug}/book                 the end customer's booking page · /o/{slug}/a/{token} the approval tap · /o/{slug}/b/{id} live status
  /console                       the operator console (a cookie from DIVE_CONSOLE_TOKEN)
Everything AgAPI is reached through the sandbox's PUBLIC API (sandbox.py)."""
from __future__ import annotations

import asyncio
import hmac
import html
import json
import secrets
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import bundles as BN, config, fakesite, model as M, ops as OPS, rules as R
from .model import DiveError
from .store import Store, loads, ts

app = FastAPI(title="DIVE · an operator's own API on AgAPI (demo)", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(fakesite.router)
_STORE: Optional[Store] = None


def db() -> Store:
    global _STORE
    if _STORE is None:
        _STORE = Store(config.DB_PATH)
    return _STORE


def use_store(s: Store) -> None:
    global _STORE
    _STORE = s


def _env(request_id: str, ok: bool, result=None, error=None) -> dict:
    return {"agapi": "1.2-draft (DIVE)", "request_id": request_id, "ok": ok, **({"result": result} if ok else {"error": error})}


async def _body(req: Request) -> Dict[str, Any]:
    raw = await req.body()
    try:
        v = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        raise DiveError("invalid_input", "The body isn't valid JSON.")
    if not isinstance(v, dict):
        raise DiveError("invalid_input", "The body is the operation's input object.")
    try:
        R.canonical(v)
    except R.Refused as e:
        raise DiveError("invalid_input", f"The input can't be canonicalised ({e}).", {"path": "/", "rule": "canonical"})
    return v


def _check_schema(op: str, v: dict) -> None:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    sch = json.loads((R.SPEC / "dive.schema.json").read_text())
    reg = Registry().with_resource(sch["$id"], Resource.from_contents(sch))
    name = op.replace(".", "_") + "_in"
    if name not in sch["$defs"]:
        return
    errs = sorted(Draft202012Validator({"$ref": sch["$id"] + "#/$defs/" + name}, registry=reg).iter_errors(v), key=lambda e: list(e.absolute_path))
    if errs:
        path = "/" + "/".join(str(p) for p in errs[0].absolute_path)
        raise DiveError("invalid_input", f"The input doesn't match {op}'s schema at {path}.", {"path": path, "rule": errs[0].validator})


def _console_ok(req: Request) -> bool:
    tok = config.CONSOLE_TOKEN or ("" if config.deployed() else "dive-local")
    got = (req.headers.get("authorization") or "").removeprefix("Bearer ").strip() or req.cookies.get("dive_console", "")
    return bool(tok) and hmac.compare_digest(got, tok)


# ── the operator's API ──────────────────────────────────────────────────────────────────────────────────────────────────

@app.post("/op/v1/{op}")
async def operator_api(op: str, req: Request):
    rid = R.new_id("req")
    if not _console_ok(req):
        return JSONResponse(_env(rid, False, error={"code": "unauthenticated", "message": "The operator's console token is needed."}), 401)
    try:
        v = await _body(req)
        slug = str(v.pop("_operator", "blue-kyma"))                 # one operator in the demo minimum; the field is the console's, not the schema's
        _check_schema(op, v)
        o = None if op == "operators.put" else OPS.operator(db(), slug)
        return JSONResponse(_env(rid, True, await OPS.run(db(), o, op, v)))
    except DiveError as e:
        return JSONResponse(_env(rid, False, error=e.body()), e.http)


# ── the generated API: /o/{slug}/v1/{op} ────────────────────────────────────────────────────────────────────────────────

@app.post("/o/{slug}/v1/{op}")
async def generated_api(slug: str, op: str, req: Request):
    rid = R.new_id("req")
    s = db()
    key = M.resolve_key(s, slug, (req.headers.get("authorization") or "").removeprefix("Bearer ").strip())
    if not key:
        return JSONResponse(_env(rid, False, error={"code": "unauthenticated", "message": f"Send Authorization: Bearer opk_test_… — a key {slug} issued."}), 401)
    if op not in OPS.GENERATED:
        return JSONResponse(_env(rid, False, error={"code": "unknown_operation", "message": f"{slug}'s API has no {op}."}), 404)
    try:
        v = await _body(req)
        _check_schema(op, v)
        o = OPS.operator(s, slug)
        idem = req.headers.get("idempotency-key")
        if op in ("bookings.quote", "bookings.confirm"):
            if not idem or len(idem) < 16:
                raise DiveError("idempotency_key_required", "This operation needs an Idempotency-Key header (16+ characters).")
            rsha = R.sha256(v)
            row = s.one("select * from idempotency where operator_id = ? and op = ? and idem_key = ?", key["key_id"], op, idem)
            if row:
                if row["request_sha256"] != rsha:
                    raise DiveError("idempotency_conflict", "That Idempotency-Key was used with a different request.")
                return JSONResponse({**json.loads(row["response"]), "replayed": True}, row["status"])
        if op == "bookings.confirm":
            res = await OPS.bookings_confirm(s, o, v, key["key_id"], (req.headers.get("agapi-approval-id") or "").strip() or None)
        else:
            res = await OPS.GENERATED[op](s, o, v, key["key_id"])
        body = _env(rid, True, res)
        if op in ("bookings.quote", "bookings.confirm"):
            s.x("insert into idempotency (operator_id, op, idem_key, request_sha256, response, status) values (?, ?, ?, ?, ?, ?)",
                key["key_id"], op, idem, R.sha256(v), json.dumps(body), 200)
        return JSONResponse(body)
    except DiveError as e:
        return JSONResponse(_env(rid, False, error=e.body()), e.http)


# ── shared page chrome ──────────────────────────────────────────────────────────────────────────────────────────────────

CSS = """:root{--bg:#f3f7fa;--fg:#0e2532;--mut:#5d7482;--line:#d9e3ea;--card:#fff;--ok:#16794a;--okbg:#e5f5ec;--no:#b42318;--nobg:#fdecea;
--amb:#8a5a00;--ambbg:#fff4dd;--acc:#0b4f6c}
@media (prefers-color-scheme:dark){:root{--bg:#0d1a21;--fg:#e9f1f5;--mut:#9ab0bc;--line:#22343e;--card:#13232c;--ok:#4ade80;--okbg:#0f2a1c;
--no:#f87171;--nobg:#2c1414;--amb:#fbbf24;--ambbg:#2a210b;--acc:#7cc4e4}}
*{box-sizing:border-box}[hidden]{display:none!important}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.45 -apple-system,system-ui,sans-serif}
a{color:var(--acc)}main{max-width:62rem;margin:0 auto;padding:1rem}.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:1rem;margin:.7rem 0}
button,.btn{font:600 15px system-ui;padding:.65rem 1rem;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button.go{background:var(--acc);color:#fff;border-color:var(--acc)}input,select{font:16px system-ui;padding:.6rem;border-radius:9px;border:1px solid var(--line);
background:var(--card);color:var(--fg);width:100%}.mut{color:var(--mut);font-size:.9rem}.chip{display:inline-block;padding:.15rem .6rem;border-radius:99px;
font-size:.85rem;font-weight:600}.ok{background:var(--okbg);color:var(--ok)}.no{background:var(--nobg);color:var(--no)}.amb{background:var(--ambbg);color:var(--amb)}
.big{font-size:1.4rem;font-weight:700}table{width:100%;border-collapse:collapse}td,th{padding:.5rem;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
footer{text-align:center;color:var(--mut);font-size:.85rem;padding:1.5rem}.q{font-style:italic}"""


def page(title: str, body: str, *, footer: str = config.FOOTER, status: int = 200) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{html.escape(title)}</title><style>{CSS}</style></head><body><main>{body}</main>
<footer>{html.escape(footer)} · test mode</footer></body></html>""", status_code=status, headers={"Cache-Control": "no-store"})


def _h(x: Any) -> str:
    return html.escape(str(x))


# ── the generated API's docs (from the PUBLISHED packages) ──────────────────────────────────────────────────────────────

@app.get("/o/{slug}/docs", response_class=HTMLResponse)
async def docs(slug: str):
    s = db()
    o = s.one("select * from operators where slug = ?", slug)
    if not o:
        return page("Not found", "<h1>No such API</h1>", status=404)
    pk = s.q("select * from packages where operator_id = ? and published = 1", o["id"])
    name = o["name"].split(" (")[0]
    base = f"{config.PUBLIC_URL}/o/{slug}/v1"
    cards = "".join(f"<div class='card'><b>{_h(p['title'])}</b> · <code>{_h(p['id'])}</code><p class='mut'>{_h(p['description'] or '')}</p>"
                    f"<p>{_h(BN._money(loads(p['price'])['amount_minor']))} per person</p></div>" for p in pk) or "<p class='mut'>No packages published yet.</p>"
    opsdoc = [("packages.list", "{}", "Your packages, with what's included and how each part is confirmed."),
              ("packages.get", '{"package_id":"pkg_…"}', "One package's recipe: its parts, which are optional, cut-offs."),
              ("availability.check", '{"package_id":"pkg_…","date":"2026-10-21","start_time":"09:00","party":4}',
               "Per part: available (instant) · likely (the supplier confirms within ~2 h) · unknown when a channel is down — never 'unavailable' for an outage."),
              ("bookings.quote", '{"package_id":"pkg_…","date":"2026-10-21","start_time":"09:00","party":4,"customer":{"name":"Marta Ruiz","phone":"+15005550101"}}',
               "A bundle with ONE read-back covering every part. Show its lines to the customer, verbatim. Needs an Idempotency-Key."),
              ("approvals.request", '{"bundle_id":"bnd_…"}', "Sends the read-back link to the customer's phone. Their tap is the yes — you never approve for them."),
              ("bookings.confirm", '{"bundle_id":"bnd_…"}', "With AgAPI-Approval-Id (from bookings.status once they tapped) and an Idempotency-Key: each supplier is asked through its own channel."),
              ("bookings.status", '{"bundle_id":"bnd_…"}', "The bundle and each part: requested · confirmed · declined · no_answer · unreachable (never 'no'), with proof ids.")]
    rows = "".join(f"<tr><td><code>{o_}</code></td><td>{_h(w)}<br><code class='mut'>{_h(i)}</code></td></tr>" for o_, i, w in opsdoc)
    return page(f"{name} API", f"""<h1>{_h(name)} API</h1><p>Book {_h(name)}'s packages from your app or site. Base URL <code>{_h(base)}</code> ·
every call is <code>POST {_h(base)}/{{operation}}</code> with <code>Authorization: Bearer opk_test_…</code> (a key {_h(name)} issued you).
Every answer is the same envelope: <code>{{ok, result | error, request_id}}</code>.</p><h2>Packages</h2>{cards}<h2>Operations</h2><table>{rows}</table>
<h2>What the customer is told</h2><p>Each supplier answers in its own words; a <b>no</b> is said straight ("Nothing has been charged"), and if a supplier
can't be reached we say <b>"This isn't a no"</b> — never "sold out".</p>""", footer=o["footer"] or config.FOOTER)


# ── the end customer: booking page → read-back → the tap on their phone → live status ───────────────────────────────────

@app.get("/o/{slug}/book", response_class=HTMLResponse)
async def book_page(slug: str):
    s = db()
    o = s.one("select * from operators where slug = ?", slug)
    pk = o and s.q("select * from packages where operator_id = ? and published = 1", o["id"])
    if not o or not pk:
        return page("Not open", "<h1>Bookings aren't open yet</h1>", status=404)
    opts = "".join(f"<option value='{_h(p['id'])}'>{_h(p['title'])} — {_h(BN._money(loads(p['price'])['amount_minor']))} per diver</option>" for p in pk)
    name = o["name"].split(" (")[0]
    return page(f"Book · {name}", f"""<h1>{_h(name)}</h1><form class="card" method="post" action="/o/{_h(slug)}/book">
<label>Package<select name="package_id">{opts}</select></label><p class="mut">{_h(pk[0]['description'] or '')}</p>
<label>Date<input type="date" name="date" required></label><label>Time<select name="start_time"><option>09:00</option><option>10:00</option></select></label>
<label>Divers<select name="party">{''.join(f'<option{" selected" if n == 4 else ""}>{n}</option>' for n in range(1, 9))}</select></label>
<label>Your name<input name="name" required maxlength="80" autocomplete="name"></label><label>Your phone (WhatsApp)<input name="phone" required inputmode="tel"></label>
<p><button class="go" title="Shows you exactly what will be booked. Nothing is booked yet.">See the read-back</button></p></form>""", footer=o["footer"])


@app.post("/o/{slug}/book", response_class=HTMLResponse)
async def book_quote(slug: str, req: Request):
    s = db()
    o = s.one("select * from operators where slug = ?", slug)
    f = dict((await req.form()).items())
    try:
        b = await BN.quote(s, o, str(f.get("package_id")), str(f.get("date")), str(f.get("start_time")), int(f.get("party") or 0),
                           {"name": str(f.get("name") or "")[:80], "phone": str(f.get("phone") or "")[:24]}, None)
    except (DiveError, ValueError) as e:
        return page("Not booked", f"<h1>Not booked</h1><p>{_h(getattr(e, 'message', 'Please check the form.'))}</p><p><a href='/o/{_h(slug)}/book'>Back</a></p>", status=409)
    await OPS.approvals_request(s, o, {"bundle_id": b["bundle_id"]}, None)
    link = s.one("select * from captured where channel = 'sms' order by id desc")["body"].rsplit(" ", 1)[-1]
    lines = "".join(f"<p>{_h(l)}</p>" for l in b["read_back"]["lines"])
    return page("Your read-back", f"""<h1>Check it, then say yes on your phone</h1><div class="card">{lines}</div>
<p class="big">We sent the link to your phone.</p><p class="mut">Test mode: the message is captured, not sent —
<a href="{_h(link)}" target="_blank" title="Opens the customer's phone screen">open it as the customer's phone</a>.</p>
<p><a class="btn" href="/o/{_h(slug)}/b/{_h(b['bundle_id'])}">Follow your booking</a></p>""", footer=o["footer"])


@app.get("/o/{slug}/a/{token}", response_class=HTMLResponse)
async def approve_get(slug: str, token: str):
    s = db()
    l = s.one("select * from approval_links where token_hash = ?", R.text_sha256(token))
    if not l or l["used_at"] or l["expires_at"] < ts():
        return page("Link not active", "<h1>This link isn't active</h1><p>It was used, it expired, or it never existed.</p>", status=404)
    b = s.one("select * from bundles where id = ?", l["bundle_id"])
    csrf = secrets.token_urlsafe(16)
    s.x("update approval_links set csrf = ? where token_hash = ?", csrf, R.text_sha256(token))
    lines = "".join(f"<p>{_h(x)}</p>" for x in loads(b["lines"]))
    return page("Approve", f"""<h1>Your booking</h1><div class="card">{lines}</div><form method="post"><input type="hidden" name="csrf" value="{csrf}">
<button class="go big" title="Books exactly the lines above — nothing else.">Yes, book it</button></form>
<p class="mut">Nothing happens until you tap. Each supplier is asked after your yes.</p>""")


@app.post("/o/{slug}/a/{token}", response_class=HTMLResponse)
async def approve_post(slug: str, token: str, req: Request):
    s = db()
    th = R.text_sha256(token)
    l = s.one("select * from approval_links where token_hash = ?", th)
    f = dict((await req.form()).items())
    if not l or l["used_at"] or l["expires_at"] < ts() or not l["csrf"] or not hmac.compare_digest(str(f.get("csrf") or ""), l["csrf"]):
        return page("Link not active", "<h1>This link isn't active</h1>", status=404)
    if s.x("update approval_links set used_at = ? where token_hash = ? and used_at is null", ts(), th) != 1:
        return page("Link not active", "<h1>This link was already used</h1>", status=409)
    b = s.one("select * from bundles where id = ?", l["bundle_id"])
    o = s.one("select * from operators where id = ?", b["operator_id"])
    aid = BN.approve(s, b, method="tap")
    if not b["key_id"]:   # the operator's OWN booking page: its yes goes straight on (a partner's API call confirms it itself)
        try:
            await BN.confirm(s, o, b["id"], aid)
        except DiveError as e:
            return page("Not booked", f"<h1>Not booked</h1><p>{_h(e.message)}</p>", status=409)
    return RedirectResponse(f"/o/{slug}/b/{b['id']}", status_code=303)


@app.get("/o/{slug}/b/{bundle_id}", response_class=HTMLResponse)
async def status_page(slug: str, bundle_id: str):
    return page("Your booking", f"""<h1>Your booking</h1><div id="out" class="card">Loading…</div>
<script>
async function tick(){{try{{const r=await fetch('/o/{_h(slug)}/s/{_h(bundle_id)}');const j=await r.json();
const ic=s=>({{confirmed:'✓',booked:'✓',declined:'✕',no_answer:'✕',released:'–',unreachable:'…',requested:'…',pending:'…',held:'…'}})[s]||'…';
const cls=s=>['confirmed','booked'].includes(s)?'ok':['declined','no_answer'].includes(s)?'no':'amb';
document.getElementById('out').innerHTML='<p class="big">'+j.customer_sentence.replace(/[<&]/g,'')+'</p>'+j.legs.map(l=>'<p><span class="chip '+cls(l.state)+'">'+ic(l.state)+'</span> '+
l.title.replace(/[<&]/g,'')+' · '+l.supplier.replace(/[<&]/g,'')+' · '+l.state.replace('_',' ')+'</p>').join('');
if(!['confirmed','failed','cancelled'].includes(j.state))setTimeout(tick,3000);}}catch(e){{document.getElementById('out').textContent='We couldn\\'t load your booking just now — retrying.';setTimeout(tick,5000);}}}}
tick();</script>""")


@app.get("/o/{slug}/s/{bundle_id}")
async def status_json(slug: str, bundle_id: str):
    s = db()
    o = s.one("select * from operators where slug = ?", slug)
    b = o and s.one("select * from bundles where id = ? and operator_id = ?", bundle_id, o["id"])
    if not b:
        return JSONResponse({"error": "not_found"}, 404)
    out = await BN.sync(s, o, b["id"])
    return JSONResponse({k: out[k] for k in ("state", "customer_sentence")} | {"legs": [{k: l[k] for k in ("title", "supplier", "state")} for l in out["legs"]]})


# ── the console ─────────────────────────────────────────────────────────────────────────────────────────────────────────

from . import console as _console   # noqa: E402
_console.bind(app, db, _console_ok)


@app.on_event("startup")
async def _loop():
    async def run():
        while True:
            await asyncio.sleep(20)
            try:
                s = db()
                for b in s.q("select * from bundles where state = 'in_progress'"):
                    await BN.sync(s, s.one("select * from operators where id = ?", b["operator_id"]), b["id"])
            except Exception:
                pass
    if config.deployed():
        asyncio.create_task(run())


@app.get("/health")
async def health():
    return {"ok": True, "service": "dive", "mode": config.MODE, "sandbox": config.SANDBOX_URL, "sandbox_key_set": bool(config.SANDBOX_KEY)}
