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
from . import model as M, ops as O

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


@router.get("/fineprint/review", response_class=HTMLResponse)
async def page(req: Request):
    store = _get_store()
    if not _session(store, req):
        return HTMLResponse("<p>Open this page from your one-time link.</p>", status_code=401)
    rows = [p for p in M.products(store) if M.is_beta(p)]                # CR 74b · only the beta set is checked
    rows = sorted(rows, key=lambda p: (bool(p["accepted_at"]), not p["last_read_at"], p["issuer"], p["product"]))
    cards = []
    for p in rows:
        d = loads(p["data"])
        lr = d.get("last_read") or {}
        state = ("accepted · " + escape((p["accepted_by"] or ""))) if p["accepted_at"] else ("not usable" if p["rejected_at"] else
                                                                                           "waiting for your check" if p["last_read_at"] else "not read")
        facts = []
        for c in M.claims(store, p["id"]):
            co = O.claim_out(c, p)
            v = co["value"]
            facts.append(f"<tr><td>{escape(c['benefit'].replace('_', ' '))}</td><td>{escape(c['field'].replace('_', ' '))}</td><td><b>{escape(str(v))}</b></td>"
                         f"<td><q>{escape(co['quote']['text'])}</q><br><a href='{escape(c['source_url'])}' target='_blank' rel='noopener noreferrer'>"
                         f"{escape(c['source_url'][:80])}</a></td></tr>")
        unread = "".join(f"<li>{escape(u['url'][:90])} — {escape(u['why'])}</li>" for u in (lr.get("unread") or []))
        srcs = "".join(f"<li>{escape(s['kind'])}: <a href='{escape(s['url'])}' target='_blank' rel='noopener noreferrer'>{escape(s['url'][:90])}</a>"
                       f"{(' (linked from ' + escape(s['linked_from'][:60]) + ')') if s['linked_from'] else ''}</li>"
                       for s in store.q("select * from card_sources where product_id = ?", p["id"]))
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
button{{font:inherit;padding:7px 12px;border-radius:8px;border:0;background:var(--fg);color:var(--bg);cursor:pointer}}button.no{{background:none;color:var(--no);border:1px solid var(--no)}}
</style></head><body><main><h1>Card terms: check the first reads</h1>
<p>Each card's facts were read from its issuer's own terms; every one quotes its sentence word for word. Accept a card only if the facts match
their quotes. Until you accept, no answer uses it. Later re-reads are automatic.</p>{''.join(cards)}</main>
<script>document.addEventListener('click',async e=>{{const b=e.target;if(!b.dataset.p)return;b.disabled=true;
const r=await fetch('/fineprint/review/decide',{{method:'POST',headers:{{'content-type':'application/json'}},body:JSON.stringify({{product_id:b.dataset.p,decision:b.dataset.d}})}});
b.textContent=r.ok?(b.dataset.d==='accept'?'Accepted ✓':'Marked not usable'):'Failed — reload';}});</script></body></html>""",
                        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"})
