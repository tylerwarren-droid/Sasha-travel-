"""The key-less surfaces (Part 4 §3), opened by the end user on their own phone — never by an API key:
  /a/{token}   the approval link: GET renders the read-back lines EXACTLY and records the presentation event (never approves —
               a link unfurler can't approve); POST "Yes, go ahead" (with the CSRF token the GET issued) creates the Approval in a
               separate action. Single-use, 15 minutes, token stored hashed.
  /v/{token}   destination verification: the one-time code the end user received (sandbox: captured in sandbox.messages).
  /pay/{token} the payment link (sandbox: Stripe test, simulated — the only sandbox payment method)."""
from __future__ import annotations

import hashlib
import hmac
import html
import secrets
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from . import config, engine as E, rules as R, webhooks as W
from .store import Store, loads, now, parse_ts, ts

router = APIRouter()
_store = None


def bind(get_store) -> None:
    global _store
    _store = get_store


def _h(t: str) -> str:
    return hashlib.sha256((t or "").encode()).hexdigest()


_CSS = """:root{--bg:#fbfaf7;--fg:#1d1b17;--mut:#6b665c;--line:#e4e0d6;--ok:#1f6f43;--card:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#151412;--fg:#f1eee7;--mut:#a39e93;--line:#2c2a26;--ok:#5fc08a;--card:#1d1c19}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,system-ui,sans-serif}
main{max-width:30rem;margin:0 auto;padding:1.5rem 1rem 3rem}.tag{display:inline-block;font-size:.75rem;letter-spacing:.06em;
text-transform:uppercase;color:var(--mut);border:1px solid var(--line);border-radius:99px;padding:.1rem .6rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:1rem 1.1rem;margin:1rem 0}.card p{margin:.35rem 0}
.mut{color:var(--mut);font-size:.85rem}button,input{font:inherit;width:100%;box-sizing:border-box;padding:.9rem;border-radius:12px;
border:1px solid var(--line);margin:.35rem 0;background:var(--card);color:var(--fg)}button{cursor:pointer}
button.ok{background:var(--ok);color:#fff;border-color:var(--ok)}.st{font-weight:600}"""


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>{html.escape(title)}</title><style>{_CSS}</style></head><body><main>
<span class="tag">Sandbox · test mode</span><h1 style="font-size:1.3rem;margin:.8rem 0 .2rem">{html.escape(title)}</h1>{body}</main></body></html>""",
                        status_code=status, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


def _lines(rb: dict) -> str:
    return "".join(f"<p>{html.escape(x)}</p>" for x in loads(rb["lines"]))


def _link(store: Store, token: str) -> Optional[dict]:
    return store.one("select * from approval_links where token_hash = ?", _h(token))


@router.get("/a/{token}", response_class=HTMLResponse)
async def approval_get(token: str):
    store = _store()
    ln = _link(store, token)
    if not ln:
        return _page("This link isn't valid", "<p>Ask for a new one.</p>", 404)
    rb = store.one("select * from read_backs where account = ? and id = ?", ln["account"], ln["read_back_id"])
    if ln["used_at"]:
        return _page("Already answered", f'<p class="st">This request was {html.escape(ln["outcome"] or "answered")}.</p>')
    if ln["expires_at"] < ts():
        return _page("This link expired", "<p>Ask for a new one.</p>", 410)
    if not rb["presented_at"]:     # the PRESENTATION event (AP3): its time and its own turn
        p = now()
        store.x("update read_backs set presented_at = ?, presented_turn_id = ?, presented_via = 'link', state = 'presented', expires_at = ? "
                "where account = ? and id = ?", ts(p), R.new_id("trn"),
                ts(p + timedelta(minutes=E._rb_ttl(bool(rb["irreversible"])))), ln["account"], rb["id"])
        rb = store.one("select * from read_backs where account = ? and id = ?", ln["account"], rb["id"])
        W.emit(store, ln["account"], "approval.presented", {"intent_id": rb["intent_id"], "read_back_id": rb["id"]})
    csrf = secrets.token_urlsafe(24)
    store.x("update approval_links set csrf_hash = ?, presented_at = coalesce(presented_at, ?) where token_hash = ?", _h(csrf), ts(), ln["token_hash"])
    return _page("Approve this?", f"""<p class="mut">Read it, then decide. Nothing happens unless you tap “Yes, go ahead”.</p>
<div class="card">{_lines(rb)}</div><p class="mut">Fingerprint {html.escape(rb['read_back_sha256'][7:19])} · approve by {html.escape(rb['expires_at'][11:16])} UTC</p>
<form method="post"><input type="hidden" name="csrf" value="{csrf}">
<button class="ok" name="decision" value="yes">Yes, go ahead</button><button name="decision" value="no">No</button></form>""")


@router.post("/a/{token}", response_class=HTMLResponse)
async def approval_post(token: str, req: Request):
    store = _store()
    ln = _link(store, token)
    form = dict((await req.form()).items())
    if not ln:
        return _page("This link isn't valid", "<p>Ask for a new one.</p>", 404)
    if ln["used_at"]:
        return _page("Already answered", f'<p class="st">This request was {html.escape(ln["outcome"] or "answered")}.</p>')
    if ln["expires_at"] < ts():
        return _page("This link expired", "<p>Ask for a new one.</p>", 410)
    if not ln["csrf_hash"] or not hmac.compare_digest(ln["csrf_hash"], _h(str(form.get("csrf") or ""))):
        return _page("Open the request first", "<p>Open the link to read the request, then answer it there.</p>", 400)
    rb = store.one("select * from read_backs where account = ? and id = ?", ln["account"], ln["read_back_id"])
    if form.get("decision") != "yes":
        store.x("update approval_links set used_at = ?, outcome = 'declined' where token_hash = ? and used_at is null", ts(), ln["token_hash"])
        return _page("Declined", "<p class='st'>Nothing will happen.</p>")
    if E._rb_state(rb) != "presented":
        return _page("This request can't be approved", f"<p>It is {html.escape(E._rb_state(rb))}. Ask for a new one.</p>", 409)
    approved_at = ts()
    if not approved_at > rb["presented_at"]:
        return _page("One moment", "<p>Read the request, then tap again.</p>", 409)
    with store.tx():
        n = store.x("update approval_links set used_at = ?, outcome = 'approved' where token_hash = ? and used_at is null", ts(), ln["token_hash"])
    if n != 1:
        return _page("Already answered", "<p class='st'>This request was already answered.</p>")
    E._create_approval(store, ln["account"], rb, method="tap", said=None, lang=None, device={"channel": "link"}, approved_at=approved_at)
    return _page("Approved", "<p class='st'>Thank you — it can now go ahead, exactly as you read it.</p>")


@router.get("/v/{token}", response_class=HTMLResponse)
async def verify_get(token: str):
    d = _store().one("select * from destinations where verify_token_hash = ?", _h(token))
    if not d:
        return _page("This link isn't valid", "", 404)
    if d["verified"]:
        return _page("Verified", "<p class='st'>This destination is verified.</p>")
    return _page("Verify it's you", f"""<p>Enter the code sent to {html.escape(d['value'])}.</p><form method="post">
<input name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="123456"><button class="ok">Verify</button></form>""")


@router.post("/v/{token}", response_class=HTMLResponse)
async def verify_post(token: str, req: Request):
    store = _store()
    d = store.one("select * from destinations where verify_token_hash = ?", _h(token))
    if not d:
        return _page("This link isn't valid", "", 404)
    if d["verified"]:
        return _page("Verified", "<p class='st'>This destination is verified.</p>")
    if d["attempts"] >= 5 or (d["otp_expires_at"] or "") < ts():
        return _page("This code expired", "<p>Register the destination again for a new code.</p>", 410)
    code = str((dict((await req.form()).items())).get("code") or "").strip()
    if not hmac.compare_digest(d["otp_hmac"] or "", E._otp_hmac(code)):
        store.x("update destinations set attempts = attempts + 1 where verify_token_hash = ?", _h(token))
        return _page("That code isn't right", "<p>Check it and try again.</p>", 400)
    store.x("update destinations set verified = 1, otp_hmac = null where verify_token_hash = ?", _h(token))
    return _page("Verified", "<p class='st'>Thank you — approvals can now be sent here.</p>")


@router.get("/pay/{token}", response_class=HTMLResponse)
async def pay_get(token: str):
    store = _store()
    act = store.one("select * from acts where pay_token_hash = ?", _h(token))
    if not act:
        return _page("This payment link isn't active", "<p>It was paid, cancelled, or never existed.</p>", 404)
    hold = store.one("select * from holds where account = ? and id = ?", act["account"], act["hold_id"])
    rb = store.one("select * from read_backs where account = ? and id = ?", act["account"], hold["read_back_id"])
    t = loads(hold["total"])
    return _page(f"Pay {t['currency']} {t['amount_minor'] // 100}.{t['amount_minor'] % 100:02d}",
                 f"""<div class="card">{_lines(rb)}</div><p class="mut">Sandbox: Stripe test — no money moves.</p>
<form method="post"><button class="ok">Pay (test)</button></form>""")


@router.post("/pay/{token}", response_class=HTMLResponse)
async def pay_post(token: str):
    store = _store()
    with store.tx():
        act = store.one("select * from acts where pay_token_hash = ?", _h(token))
        if act:
            store.x("update acts set pay_token_hash = null where account = ? and id = ?", act["account"], act["id"])
    if not act:
        return _page("This payment link isn't active", "<p>It was paid, cancelled, or never existed.</p>", 404)
    outcome = await E.pay(store, act)
    if outcome["kind"] == "CONFIRMED":
        return _page("Paid", f"<p class='st'>Booked — reference {html.escape(outcome['reference'])}.</p>")
    return _page("Not booked", f"<p class='st'>The provider answered: {html.escape(outcome['kind'].lower())}. Nothing was charged.</p>")
