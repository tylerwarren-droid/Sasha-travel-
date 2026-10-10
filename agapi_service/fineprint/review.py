"""CR 74 · the ACCEPT SURFACE (EU 216 §1 "who confirms"): a Kanoe person checks each card product's FIRST read before any answer uses
it — every fact with its quote and source link, the documents read and the ones not read (with why). Accept / Not usable.

Entry is a one-time link (signed admin action review_link → /fineprint/review/start/{code}, 15 minutes, used once) that sets a
12-hour session cookie. Nothing secret is shown here; the page is noindex and every decision is recorded with when and how."""
from __future__ import annotations

import hashlib
import secrets
from html import escape
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ..store import later, loads, ts
from . import model as M, ops as O, pacioli as PC

router = APIRouter()
_get_store = lambda: None
COOKIE = "agapi_review"


def bind(get_store) -> None:
    global _get_store
    _get_store = get_store


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _tables(store) -> None:
    store.x("create table if not exists review_codes (code_hash text primary key, expires_at text not null, used_at text)")
    store.x("create table if not exists review_sessions (token_hash text primary key, expires_at text not null, created_at text not null)")


def new_code(store) -> str:
    _tables(store)
    code = secrets.token_urlsafe(24)
    store.x("insert into review_codes (code_hash, expires_at) values (?, ?)", _h(code), later(minutes=15))
    return code


def _session(store, req: Request) -> Optional[str]:
    tok = req.cookies.get(COOKIE) or ""
    if not tok:
        return None
    _tables(store)
    row = store.one("select expires_at from review_sessions where token_hash = ?", _h(tok))
    return _h(tok)[:12] if row and row["expires_at"] > ts() else None


@router.get("/fineprint/review/start/{code}")
async def start(code: str):
    store = _get_store()
    _tables(store)
    row = store.one("select * from review_codes where code_hash = ?", _h(code))
    if not row or row["used_at"] or row["expires_at"] < ts():
        return HTMLResponse("<p>This link has expired or was already used. Ask for a new one.</p>", status_code=403)
    store.x("update review_codes set used_at = ? where code_hash = ?", ts(), _h(code))
    tok = secrets.token_urlsafe(32)
    store.x("insert into review_sessions (token_hash, expires_at, created_at) values (?, ?, ?)", _h(tok), later(minutes=12 * 60), ts())
    r = RedirectResponse("/fineprint/review", status_code=303)
    r.set_cookie(COOKIE, tok, max_age=12 * 3600, httponly=True, secure=True, samesite="strict", path="/fineprint")
    return r


@router.post("/fineprint/review/decide")
async def decide(req: Request):
    store = _get_store()
    who = _session(store, req)
    if not who:
        return JSONResponse({"ok": False, "why": "not signed in"}, status_code=401)
    from urllib.parse import urlsplit
    if req.headers.get("origin") and urlsplit(req.headers["origin"]).hostname != (req.headers.get("host") or "").split(":")[0]:
        return JSONResponse({"ok": False, "why": "origin"}, status_code=403)   # only this page's own clicks
    body = await req.json()
    pid, d = str(body.get("product_id") or ""), body.get("decision")
    p = store.one("select * from card_products where id = ?", pid)
    if not p or d not in ("accept", "reject") or not p["last_read_at"]:
        return JSONResponse({"ok": False, "why": "no such read"}, status_code=404)
    if d == "accept":
        store.x("update card_products set accepted_at = ?, accepted_by = ?, rejected_at = null where id = ?", ts(), f"kanoe review · session {who}", pid)
    else:
        store.x("update card_products set rejected_at = ?, accepted_at = null, accepted_by = ? where id = ?", ts(), f"kanoe review · session {who}", pid)
    return JSONResponse({"ok": True})


def _same_origin(req: Request) -> bool:
    from urllib.parse import urlsplit
    return not req.headers.get("origin") or urlsplit(req.headers["origin"]).hostname == (req.headers.get("host") or "").split(":")[0]


@router.get("/fineprint/review/source")
async def source(req: Request, claim: str = "", copy: str = "", fmt: str = "original"):
    """CR 77 · "Download source": the kept copy (signed, 10 minutes) of the source a fact came from — for a signed-in reviewer."""
    store = _get_store()
    if not _session(store, req):
        return HTMLResponse("<p>Open this page from your one-time link.</p>", status_code=401)
    try:
        out, _, _ = await O.sources_get(type("C", (), {"store": store})(), {"claim_id": claim} if claim else {"copy_id": copy, "format": fmt})
    except Exception as e:
        return HTMLResponse(f"<p>{escape(getattr(e, 'message', None) or str(e))}</p>", status_code=404)
    return RedirectResponse(out["url"], status_code=303, headers={"Cache-Control": "no-store"})


@router.post("/fineprint/review/fact")
async def fact(req: Request):
    """CR 77 · a person's decision on ONE exception (a fact Pacioli's check didn't pass): use it, or not."""
    store = _get_store()
    who = _session(store, req)
    if not who:
        return JSONResponse({"ok": False, "why": "not signed in"}, status_code=401)
    if not _same_origin(req):
        return JSONResponse({"ok": False, "why": "origin"}, status_code=403)
    body = await req.json()
    if body.get("decision") not in ("accept", "reject") or not PC.decide(store, str(body.get("claim_id") or ""), body["decision"], f"kanoe review · session {who}"):
        return JSONResponse({"ok": False, "why": "no such exception"}, status_code=404)
    return JSONResponse({"ok": True})


@router.post("/fineprint/review/switch")
async def switch(req: Request):
    """CR 77 · Pacioli's automatic acceptance on / off (checks still run; off = only a person accepts)."""
    store = _get_store()
    who = _session(store, req)
    if not who:
        return JSONResponse({"ok": False, "why": "not signed in"}, status_code=401)
    if not _same_origin(req):
        return JSONResponse({"ok": False, "why": "origin"}, status_code=403)
    on = bool((await req.json()).get("on"))
    PC.set_auto(store, on, f"kanoe review · session {who}")
    M._AUTO["on"] = on
    return JSONResponse({"ok": True, "on": on})


@router.get("/fineprint/review", response_class=HTMLResponse)
async def page(req: Request):
    store = _get_store()
    if not _session(store, req):
        return HTMLResponse("<p>Open this page from your one-time link.</p>", status_code=401)
    rows = [p for p in M.products(store) if M.is_beta(p)]                # CR 74b · only the beta set is checked
    auto = PC.auto_on(store)
    exc = [e for e in PC.exceptions(store) if e["key"] in {p["key"] for p in rows}]
    exc_html = "".join(f"<div class='ex'><b>{escape(e['product'])}</b> · {escape(e['benefit'].replace('_', ' '))} · {escape(e['field'].replace('_', ' '))}: "
                       f"<b>{escape(str(loads(e['value'])))}</b><br><q>{escape(e['quote'][:300])}</q><br>"
                       f"<small>{escape('; '.join(loads(e['results']).get('why') or []))}</small><br>"
                       f"<a href='/fineprint/review/source?claim={escape(e['claim_id'])}'>Download source</a> "
                       f"<button data-c='{escape(e['claim_id'])}' data-d='accept'>Use this fact</button> "
                       f"<button data-c='{escape(e['claim_id'])}' data-d='reject' class='no'>Not usable</button></div>" for e in exc)
    rows = sorted(rows, key=lambda p: (bool(p["accepted_at"]), not p["last_read_at"], p["issuer"], p["product"]))
    cards = []
    for p in rows:
        d = loads(p["data"])
        lr = d.get("last_read") or {}
        state = (("accepted · " + escape((p["accepted_by"] or ""))) + ("" if M.accepted(p) else " (auto-accept is OFF: not used)")) if p["accepted_at"] else ("not usable" if p["rejected_at"] else
                                                                                           "waiting for your check" if p["last_read_at"] else "not read")
        facts = []
        checks = {k["claim_id"]: k for k in store.q("select * from card_checks where product_id = ?", p["id"])}
        for c in M.claims(store, p["id"], every=True):
            co = O.claim_out(c, p)
            v = co["value"]
            k = checks.get(c["id"])
            res = loads(k["results"]) if k else {}
            chk = ("<span class='ok'>✓ checked by Pacioli</span>" if k and k["passed"] else
                   f"<span class='no'>exception{(' · ' + escape(k['decision'])) if k and k['decision'] else ''}</span><br><small>{escape('; '.join(res.get('why') or []))}</small>"
                   if k else "<small>not checked</small>")
            facts.append(f"<tr><td>{escape(c['benefit'].replace('_', ' '))}</td><td>{escape(c['field'].replace('_', ' '))}</td><td><b>{escape(str(v))}</b></td>"
                         f"<td><q>{escape(co['quote']['text'])}</q><br><a href='{escape(c['source_url'])}' target='_blank' rel='noopener noreferrer'>"
                         f"{escape(c['source_url'][:80])}</a> · <a href='/fineprint/review/source?claim={escape(c['id'])}' rel='noopener'>Download source</a></td>"
                         f"<td>{chk}</td></tr>")
        unread = "".join(f"<li>{escape(u['url'][:90])} — {escape(u['why'])}</li>" for u in (lr.get("unread") or []))
        srcs = "".join(f"<li>{escape(s['kind'])}: <a href='{escape(s['url'])}' target='_blank' rel='noopener noreferrer'>{escape(s['url'][:90])}</a>"
                       f"{(' (linked from ' + escape(s['linked_from'][:60]) + ')') if s['linked_from'] else ''}</li>"
                       for s in store.q("select * from card_sources where product_id = ?", p["id"]))
        from . import copies as CP
        CP.ensure(store)
        kept = store.q("select * from source_copies where subject = ? order by read_at desc, role, final_url", p["key"])
        srcs += "".join(f"<li>kept copy · {escape(k['role'].replace('_', ' '))} · {escape(k['read_at'][:10])} · {escape(k['sha256'][7:19])}… "
                        f"{escape(k['final_url'][:80])} — <a href='/fineprint/review/source?copy={escape(k['id'])}'>Download source</a>"
                        f"{(' · <a href=' + chr(39) + '/fineprint/review/source?copy=' + escape(k['id']) + '&fmt=pdf' + chr(39) + '>as PDF</a>') if k['render_key'] else ''}</li>"
                        for k in kept)
        btn = (f"<button data-p='{p['id']}' data-d='accept'>Accept this read</button> <button data-p='{p['id']}' data-d='reject' class='no'>Not usable</button>"
               if p["last_read_at"] else "")
        cards.append(f"<section><h2>{escape(p['product'])} <small>{escape(p['issuer'])} · {escape(p['network'])} · {escape(p['country'])}</small></h2>"
                     f"<p class='st'>{state} · read {escape((p['last_read_at'] or '—')[:10])} · {len(facts)} facts</p>"
                     f"{('<table>' + ''.join(facts) + '</table>') if facts else '<p>No fact could be quoted.</p>'}"
                     f"<details><summary>Documents read</summary><ul>{srcs or '<li>none</li>'}</ul></details>"
                     f"{('<details><summary>Not read — why</summary><ul>' + unread + '</ul></details>') if unread else ''}<p>{btn}</p></section>")
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Card terms check</title><style>
:root{{--bg:#f6f4ef;--fg:#1c1a16;--mut:#6d675c;--card:#fff;--line:#e3ded3;--no:#b42318}}
@media (prefers-color-scheme:dark){{:root{{--bg:#121110;--fg:#f2efe8;--mut:#a59f93;--card:#1b1a17;--line:#2d2b27;--no:#f87171}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}}main{{max-width:1100px;margin:0 auto;padding:20px 16px}}
section{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:12px 0;overflow-x:auto}}
h2{{font-size:17px;margin:0}}small,.st{{color:var(--mut);font-weight:400;font-size:13px}}table{{border-collapse:collapse;font-size:13px;width:100%}}
td{{border-top:1px solid var(--line);padding:6px 6px;vertical-align:top}}q{{font-style:italic}}
button{{font:inherit;padding:7px 12px;border-radius:8px;border:0;background:var(--fg);color:var(--bg);cursor:pointer}}button.no{{background:none;color:var(--no);border:1px solid var(--no)}}.ok{{color:#15803d}}.no{{color:var(--no)}}.ex{{border-top:1px solid var(--line);padding:8px 0}}
</style></head><body><main><h1>Card terms: check the first reads</h1>
<p>Each fact is read from the issuer's / rental company's / government's own source, and a copy of that source is kept as read (Download
source). Pacioli accepts a fact automatically only when its quote is in the kept copy word for word, the source is the official domain (or a
file you supplied), every number, amount, currency, deadline and phone is in its quote, and the copy's sha256 matches. Only the exceptions
below need you. Your earlier acceptances stay.</p>
<p class='sw'>Automatic acceptance: <b>{'on' if auto else 'off'}</b> <button data-sw='{'0' if auto else '1'}' class='no'>{'Turn off' if auto else 'Turn on'}</button></p>
<section><h2>Exceptions <small>{len(exc)} · only these need you</small></h2>{exc_html or '<p>None — every fact passed.</p>'}</section>
{''.join(cards)}</main>
<script>document.addEventListener('click',async e=>{{const b=e.target;
if(b.dataset.sw){{b.disabled=true;const r=await fetch('/fineprint/review/switch',{{method:'POST',headers:{{'content-type':'application/json'}},body:JSON.stringify({{on:b.dataset.sw==='1'}})}});
if(r.ok)location.reload();else b.textContent='Failed — reload';return;}}
if(b.dataset.c){{b.disabled=true;const r=await fetch('/fineprint/review/fact',{{method:'POST',headers:{{'content-type':'application/json'}},body:JSON.stringify({{claim_id:b.dataset.c,decision:b.dataset.d}})}});
b.textContent=r.ok?(b.dataset.d==='accept'?'Using it ✓':'Marked not usable'):'Failed — reload';return;}}
if(!b.dataset.p)return;b.disabled=true;
const r=await fetch('/fineprint/review/decide',{{method:'POST',headers:{{'content-type':'application/json'}},body:JSON.stringify({{product_id:b.dataset.p,decision:b.dataset.d}})}});
b.textContent=r.ok?(b.dataset.d==='accept'?'Accepted ✓':'Marked not usable'):'Failed — reload';}});</script></body></html>""",
                        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"})
