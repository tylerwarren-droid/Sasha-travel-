"""CR 72 · S2'S SUBSCRIPTION RADAR — "what am I subscribed to?" → the list → "cancel X" → done on their yes. /s2 ONLY: these three tools
are added in /s2's own tool selection (app/agent/sasha.py) and run there; S1 (/next) never sees them (its tool list is unchanged).
The work is AgAPI's (subscriptions.find / cancel_plan / cancel); Sasha only asks and says.

  find_subscriptions        the person's statement (uploaded on /s2: POST /api/agent/s2/statement → a statement_ref, kept in this server's
                            memory for 30 minutes, never on disk) — or, in test mode, the sample statement → the list, the monthly total,
                            "likely unused" with its reason
  plan_cancel_subscription  the merchant's own cancel routes (AgAPI reads the merchant's site live; a labelled stand-in in test mode)
  cancel_subscription       turn 1: AgAPI's read-back (Sasha reads it back) · turn 2, on their yes: their OWN words go to AgAPI as the
                            approval (test mode: sandbox.simulate_approval decides if it's a yes); live: AgAPI's approval link goes to their
                            phone and they tap it → "cancel requested" until the merchant confirms
Where: SASHA_SUBSCRIPTIONS_VIA = sandbox (default) | live.  Keys: SASHA_AGAPI_TEST_KEY (sandbox) / SASHA_AGAPI_KEY (live). Never printed."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import secrets
import time
from typing import Any, Awaitable, Callable, Dict, Optional

TOOL_NAMES = ("find_subscriptions", "plan_cancel_subscription", "cancel_subscription")
#: Sasha 259 · what she reads and that nothing is kept — ONE short statement, said before the list (never a question: connecting
#: the mailbox on the You page was their consent, Tyler row 883)
STATEMENT = {"gmail": "I read only the receipt and renewal emails in your Gmail, and I never store your emails.",
             "outlook": "I read only the receipt and renewal emails in your Outlook, and I never store your emails."}
TOOLS = [
    {"name": "find_subscriptions", "description": (
        "What the person is paying for: from their RECEIPT emails (from_gmail: true — use it when they ask 'what subscriptions am I paying "
        "for?') or from a bank statement they uploaded (statement_ref; use_sample in test mode); with neither, what's already known. From a connected Gmail it reads AT ONCE — never ask "
        "permission (connecting it was their consent); `say` starts with her one statement of what she reads. Their mail is Outlook / "
        "Microsoft 365 (they connected Outlook, or say Outlook / their work mail): from_outlook: true instead — the same steps, its own sentence. Each subscription: "
        "service, price, monthly/yearly, last charge, renews (quoted from the receipt; 'expected' when the email doesn't say). Say `say` as given."),
     "input_schema": {"type": "object", "properties": {"from_gmail": {"type": "boolean"}, "from_outlook": {"type": "boolean"}, "consent_yes": {"type": "boolean"},
                                                       "statement_ref": {"type": "string"}, "use_sample": {"type": "boolean"}}}},
    {"name": "plan_cancel_subscription", "description": (
        "How to cancel one subscription: the merchant's own cancel routes (their cancel page, an email). Call it before cancel_subscription."),
     "input_schema": {"type": "object", "properties": {"subscription_id": {"type": "string"}}, "required": ["subscription_id"]}},
    {"name": "cancel_subscription", "description": (
        "Cancel the ONE subscription they named (service, e.g. 'Spotify' — or its subscription_id). Its route is chosen for you: an email to the "
        "service when its receipt says it cancels by email; otherwise its own cancel page, handed over — they press cancel. The FIRST call "
        "returns what will be done — read it back and ask; call it again only after they say yes, in a later turn. Sasha never logs into "
        "anyone's account."),
     "input_schema": {"type": "object", "properties": {"service": {"type": "string"}, "subscription_id": {"type": "string"},
                                                       "route": {"type": "string", "enum": ["email", "page"]}, "account_email": {"type": "string"}}}},
]

_STATEMENTS: Dict[str, dict] = {}     # statement_ref → {account, media_type, b64, at} — memory only, 30 minutes
_USERS: Dict[str, str] = {}           # account → AgAPI end_user
_PENDING: Dict[str, dict] = {}        # account|subscription → {read_back_id, route, at} (the read-back said; their yes comes next turn)
_CONSENT_ASKED: Dict[str, float] = {}  # CR 84 · account → when the Gmail sentence was said (their yes must come in a later turn)
_CONSENTED: Dict[str, dict] = {}      # CR 84 · account → the sentence's version + sha256, and when they said yes
_LAST: Dict[str, list] = {}           # CR 84 · account → the last list (to find "Spotify" by name)
_SOURCE: Dict[str, str] = {}          # Sasha 243 · account → where their list last came from (a later plain call is said as that)
_NOT_YET = {"handed_over": "cancel page handed over — not cancelled yet", "cancel_requested": "cancel requested — not confirmed yet"}
STATEMENT_TTL_S, MAX_BYTES = 1800, 5_000_000
#: Sasha 260 · Tyler's /s2, 13 Oct 18:27 UTC — "What subscriptions am I paying for?" → a bank statement offered instead. His 60 receipts
#: reached Sasha in 10 s; AgAPI reads them in ONE model call (up to 12k tokens, its own 180 s limit), and this client hung up at 60 s
#: ("unreachable": the request never finished, so AgAPI's log has no line) — well inside the turn's 100 s. A mailbox read now runs as
#: its own job: up to READ_WAIT_S inside the turn; longer, she says she's reading and the list reaches the open page when it's done
#: (live_events "proactive", the same card). A second ask while it reads joins the same read.
READ_WAIT_S, READ_TIMEOUT_S, CALL_TIMEOUT_S = 40.0, 240.0, 60.0
READING_SAY = "I'm reading your receipts now — the list will appear here in a minute or two."
_READING: Dict[str, Any] = {}         # account → the read in progress (asyncio.Task), held so it isn't garbage-collected mid-read
#: an AgAPI that didn't answer, timed out or is out of budget: said as that — never a statement offered in its place
_NOT_ANSWERED = ("unreachable", "timeout", "budget_exhausted", "rate_limited", "upstream_unreachable", "internal")
NOT_ANSWERED_SAY = "I couldn't finish reading your receipts — the service didn't answer in time. Nothing was kept; ask me again in a minute."
MEDIA = {"text/csv", "text/plain", "application/pdf", "image/png", "image/jpeg", "image/webp"}


def via() -> str:
    """Sasha 244 · the subscriptions family's AgAPI (agapi_route: SASHA_AGAPI_ROUTE, else SASHA_SUBSCRIPTIONS_VIA, else the sandbox)."""
    from agapi import agapi_route as AR
    return AR.current("subscriptions")


def keep_statement(account: str, raw: bytes, media_type: str) -> str:
    if media_type not in MEDIA:
        raise ValueError("a statement is a CSV, a PDF or a photo")
    if len(raw) > MAX_BYTES:
        raise ValueError("the statement is too large (5 MB at most)")
    now = time.time()
    for k in [k for k, v in _STATEMENTS.items() if now - v["at"] > STATEMENT_TTL_S]:
        _STATEMENTS.pop(k, None)
    ref = "st_" + secrets.token_urlsafe(12)
    _STATEMENTS[ref] = {"account": account, "media_type": media_type, "b64": base64.b64encode(raw).decode(), "at": now}
    return ref


async def _agapi(op: str, body: dict, approval: Optional[str] = None) -> Dict[str, Any]:
    import httpx
    from agapi import agapi_route as AR
    url, key = await AR.client_for("subscriptions")   # Sasha 249 · ONE ROUTE (the copied URL/key block is gone)
    if not key:
        return {"ok": False, "error": {"code": "not_configured", "message": "the subscription radar isn't switched on yet"}}
    h = {"Authorization": f"Bearer {key}", "content-type": "application/json", "Idempotency-Key": "s2sub_" + secrets.token_hex(12)}
    if approval:
        h["AgAPI-Approval-Id"] = approval
    try:   # Sasha 260 · reading a mailbox's receipts takes AgAPI longer than any other call (READ_TIMEOUT_S)
        async with httpx.AsyncClient(timeout=httpx.Timeout(READ_TIMEOUT_S if body.get("emails") else CALL_TIMEOUT_S)) as c:
            r = await c.post(f"{url}/v1/{op}", headers=h, content=json.dumps(body))
        return r.json()
    except httpx.TimeoutException as e:
        return {"ok": False, "error": {"code": "timeout", "message": type(e).__name__}}
    except Exception as e:
        return {"ok": False, "error": {"code": "unreachable", "message": type(e).__name__}}


CALL: Callable[..., Awaitable[Dict[str, Any]]] = _agapi   # tests replace it


async def _end_user(account: str) -> Optional[str]:
    k = account if via() == "sandbox" else f"live|{account}"   # Sasha 244 · each AgAPI has its own end users
    if k in _USERS:
        return _USERS[k]
    r = await CALL("users.register", {"external_ref": f"sasha:{account}"})
    if r.get("ok"):
        _USERS[k] = r["result"]["end_user_id"]
        return _USERS[k]
    return None


def _fail(r: dict) -> Dict[str, Any]:
    e = r.get("error") or {}
    if (e.get("code") or "unavailable") in _NOT_ANSWERED:   # Sasha 260 · said as what happened (an exception's class name told her nothing)
        return {"ok": False, "error": {"code": e.get("code"), "message": NOT_ANSWERED_SAY + " Say exactly that; don't offer a bank statement "
                                                                                          "instead unless they ask."}}
    return {"ok": False, "error": {"code": e.get("code") or "unavailable", "message": e.get("message") or "the subscription radar didn't answer"}}


def _brief(s: dict) -> dict:
    return {"subscription_id": s["subscription_id"], "service": s["merchant"], "amount": f"{s['amount']['currency']} {s['amount']['amount_minor'] / 100:.2f}",
            "how_often": s["cadence"], "last_charge": s["last_charge"], "likely_unused": s["likely_unused"],
            **({"why": s["why"]} if s["why"] else {}), "status": s["status"],
            **({"renews": s.get("next_renewal") or s.get("next_expected"), "renews_basis": s.get("next_basis")} if (s.get("next_renewal") or s.get("next_expected")) else {}),
            **({"plan": s["service"]} if s.get("service") else {}), **({"source": s["source"]} if s.get("source") else {})}


def _say_list(subs: list, tot: str, source: str) -> str:
    """CR 84 · one line per subscription, every price and date as AgAPI gave it; 'expected' said when the email didn't state the renewal."""
    if not subs:
        return "I didn't find any subscription receipts."
    lines = []
    for b in subs:
        per = {"monthly": "a month", "yearly": "a year", "weekly": "a week", "quarterly": "a quarter"}.get(b["how_often"], "")
        renew = (f", renews {b['renews']}" + (" (expected — the email doesn't say)" if (b.get("renews_basis") or "").startswith("expected") else "")
                 if b.get("renews") else "")
        lines.append(f"{b['service']}: {b['amount']}{' ' + per if per else ' (the receipt doesn’t say how often)'}{renew}"
                     + (f" ({_NOT_YET[b['status']]})" if b.get("status") in _NOT_YET else ""))
    unknown = [b["service"] for b in subs if b["how_often"] not in ("monthly", "yearly", "weekly", "quarterly")]
    lead = "From what I found earlier" if source == "subscriptions I found earlier" else f"From your {source}"
    return (f"{lead}, you're paying for {len(subs)}: " + "; ".join(lines) + f". That's about {tot} a month"
            + (f", not counting {', '.join(unknown)}." if unknown else "."))


def _pending_of(account: str) -> Optional[dict]:
    return {k.split("|", 1)[1]: v for k, v in _PENDING.items() if k.startswith(account + "|")} or None


async def run_tool(ctx, name: str, args: dict) -> Dict[str, Any]:
    """Sasha 249 · ONE MEMORY: a cancel's read-back waiting for their yes is kept in s2_memory (kind subs_pending) as well as in this
    process — after a restart their yes still finds it."""
    from agapi import s2_memory as M
    if not _pending_of(ctx.account):
        kept = await M.kind(ctx.account, "subs_pending")
        for sid, v in (kept or {}).items() if isinstance(kept, dict) else ():
            if isinstance(v, dict) and v.get("read_back_id"):
                _PENDING.setdefault(f"{ctx.account}|{sid}", {"read_back_id": v["read_back_id"], "route": v.get("route"),
                                                              "at": float(v.get("at") or 0)})
    before = _pending_of(ctx.account)
    from agapi import agapi_route as AR
    with AR.using(await AR.target_for("subscriptions", ctx.account)):   # Sasha 256 · ONE ROUTE: the person's (a test person → the sandbox)
        r = await _run_tool(ctx, name, args)
    after = _pending_of(ctx.account)
    if after != before:
        await M.put_kind(ctx.account, "subs_pending", after)
    return r


def _found(account: str, r: dict, source: str, said_first: Optional[str]) -> Dict[str, Any]:
    """subscriptions.find's answer → the tool's result (the list, its say, its card) — in the turn or, for a slow read, on the page."""
    if not r.get("ok"):
        return _fail(r)
    res = r["result"]
    tot = ", ".join(f"{t['currency']} {t['amount_minor'] / 100:.2f}" for t in res["monthly_total"])
    subs = [_brief(s) for s in res["subscriptions"] if s["status"] != "cancelled"]   # Sasha 243 · still paid until it's cancelled: AgAPI's
    _SOURCE[account] = source                                                        # total counts it (live: Spotify left out, its €10.99 kept in)
    _LAST[account] = subs
    return {"ok": True, "result": {"subscriptions": subs, "monthly_total": tot,
                                   "say": (said_first + " " if said_first else "") + _say_list(subs, tot, source),
                                   "likely_unused": res["likely_unused"], "note": res.get("note"),
                                   **({"emails": res["emails"]} if res.get("emails") else {}),
                                   "render": {"kind": "subscriptions", "items": [{"service": b["service"], "price": b["amount"], "how_often": b["how_often"],
                                              "renews": b.get("renews"), "expected": (b.get("renews_basis") or "").startswith("expected"),
                                              "subscription_id": b["subscription_id"], **({"not_yet": _NOT_YET[b["status"]]} if b["status"] in _NOT_YET else {})}
                                             for b in subs], "total": tot, "source": source}}}


def _tell(account: str, out: Dict[str, Any], said_first: Optional[str]) -> None:
    """Sasha 260 · a read that finished after the turn: the list (or what went wrong) reaches the open page by itself."""
    from booking_signer import live_events as LE
    if out.get("ok"):
        say = out["result"]["say"]
        if said_first and say.startswith(said_first):   # her statement was said in the turn; not twice
            say = say[len(said_first):].lstrip()
        LE.publish(account, {"type": "proactive", "kind": "subscriptions", "say": say, "render": out["result"]["render"]})
    else:
        code = (out.get("error") or {}).get("code")
        LE.publish(account, {"type": "proactive", "kind": "subscriptions_failed",
                             "say": NOT_ANSWERED_SAY if code in _NOT_ANSWERED else "I couldn't read your receipts just now — nothing was kept."})


async def _wait_read(account: str) -> Dict[str, Any]:
    task, late = _READING[account]
    done, _ = await asyncio.wait({task}, timeout=READ_WAIT_S)
    if task in done:
        return task.result()
    late["said"] = True
    return {"ok": True, "result": {"status": "reading", "say": (late["first"] + " " if late["first"] else "") + READING_SAY,
                                   "note": "Say `say` as given. The list reaches their screen by itself when it's read — don't call "
                                           "find_subscriptions again for it, and don't offer a bank statement instead."}}


async def _read_mail(account: str, body: dict, source: str, said_first: Optional[str]) -> Dict[str, Any]:
    """Sasha 260 · their receipts to AgAPI as one job (its own READ_TIMEOUT_S): in the turn if it's done within READ_WAIT_S, else on the page."""
    late = {"said": False, "first": said_first}

    async def job() -> Dict[str, Any]:
        try:
            r = await CALL("subscriptions.find", body)
        finally:
            body.pop("emails", None)                       # the emails are dropped here, as soon as AgAPI has answered
        try:
            out = _found(account, r, source, said_first)
        except Exception as e:   # an answer of an unexpected shape: said, never a crashed job
            out = {"ok": False, "error": {"code": "unavailable", "message": type(e).__name__}}
        if late["said"]:
            _tell(account, out, said_first)
        return out
    task = asyncio.get_running_loop().create_task(job())
    _READING[account] = (task, late)
    task.add_done_callback(lambda t: _READING.pop(account, None) if (_READING.get(account) or (None,))[0] is t else None)
    return await _wait_read(account)


async def _run_tool(ctx, name: str, args: dict) -> Dict[str, Any]:
    if name == "find_subscriptions" and (args.get("from_gmail") or args.get("from_outlook")) and not args.get("statement_ref") \
            and ctx.account in _READING:                   # Sasha 260 · asked again while their receipts are being read: the same read
        return await _wait_read(ctx.account)
    uid = await _end_user(ctx.account)
    if not uid:
        return {"ok": False, "error": {"code": "unavailable", "message": "the subscription radar didn't answer"}}
    if name == "find_subscriptions":
        body: Dict[str, Any] = {"end_user": uid}
        said_first = None
        ref = args.get("statement_ref")
        source = _SOURCE.get(ctx.account, "subscriptions I found earlier")   # Sasha 243 · /next said "From statement" for a receipts list
        outlook = False
        if (args.get("from_outlook") or args.get("from_gmail")) and not ref:   # CR 86 · Outlook: asked for, or the only mail connected
            from agapi import s2_gmail_receipts as GR, s2_outlook_receipts as OR
            outlook = bool(args.get("from_outlook")) or (not await GR.connected(ctx.account) and await OR.connected(ctx.account))
        if outlook:   # CR 86 · receipts in their Outlook / Microsoft 365 (Graph, delegated Mail.Read) — the same steps as Gmail's
            c, ck = OR.consent(), ctx.account + "|outlook"
            # Sasha 259 · Tyler (row 883): CONNECTING the mailbox is the consent — no question; one short statement instead (STATEMENT)
            _CONSENTED[ck] = {"version": c["version"], "text_sha256": c["text_sha256"], "at": time.time(), "by": "connected"}
            said_first = STATEMENT["outlook"]
            if await OR.connected(ctx.account):
                msgs = await OR.receipts(ctx.account)
                if msgs is None:
                    return {"ok": False, "error": {"code": "outlook_unavailable", "message": "their Outlook connection needs reconnecting on the You page"}}
                body["emails"] = {"messages": msgs, "provider": "outlook", "consent": {"text_sha256": c["text_sha256"], "version": c["version"]}}
                source = "receipts in your Outlook"
            elif via() == "sandbox":
                body["emails"] = {"sample": True, "provider": "outlook", "consent": {"text_sha256": c["text_sha256"], "version": c["version"]}}
                source = "receipts (a fake Outlook inbox — test mode)"
            else:
                return {"ok": False, "error": {"code": "outlook_not_connected", "message": "connect Outlook (read-only) on the You page first"}}
        elif args.get("from_gmail") and not ref:   # CR 84 · receipts in their Gmail (read-only)
            from agapi import s2_gmail_receipts as GR
            c = GR.consent()
            # Sasha 259 · Tyler (row 883): CONNECTING Gmail is the consent — no question; one short statement instead (STATEMENT)
            _CONSENTED[ctx.account] = {"version": c["version"], "text_sha256": c["text_sha256"], "at": time.time(), "by": "connected"}
            said_first = STATEMENT["gmail"]
            if await GR.connected(ctx.account):
                try:
                    msgs = await GR.receipts(ctx.account)
                except GR.Unreachable:   # Sasha 259 · Gmail didn't answer: said plainly, nothing read, never "lost connection"
                    return {"ok": False, "error": {"code": "gmail_unreachable", "message": "I couldn't reach your Gmail just now — nothing was "
                                                   "read. Try again in a minute."}}
                if msgs is None:
                    return {"ok": False, "error": {"code": "gmail_unavailable", "message": "their Gmail connection needs reconnecting on the You page"}}
                body["emails"] = {"messages": msgs, "consent": {"text_sha256": c["text_sha256"], "version": c["version"]}}
                source = "receipts in your Gmail"
            elif via() == "sandbox":
                body["emails"] = {"sample": True, "consent": {"text_sha256": c["text_sha256"], "version": c["version"]}}
                source = "receipts (a fake inbox — test mode)"
            else:
                return {"ok": False, "error": {"code": "gmail_not_connected", "message": "connect Gmail (read-only) on the You page first"}}
        elif ref:
            st = _STATEMENTS.get(ref)
            if not st or st["account"] != ctx.account:
                return {"ok": False, "error": {"code": "statement_unknown", "message": "that statement isn't here any more — ask them to upload it again"}}
            body["statement"] = {"media_type": st["media_type"], "content_base64": st["b64"]}
            source = "statement"
        elif args.get("use_sample"):
            if via() == "live":
                return {"ok": False, "error": {"code": "sample_test_only", "message": "the sample statement is for test mode"}}
            body["statement"] = {"sample": True}
            source = "statement"
        if body.get("emails"):                             # Sasha 260 · a mailbox read: its own job (READ_WAIT_S here, then the page)
            return await _read_mail(ctx.account, body, source, said_first)
        r = await CALL("subscriptions.find", body)
        if ref:
            _STATEMENTS.pop(ref, None)                     # read once; never kept
        return _found(ctx.account, r, source, said_first)
    if name == "plan_cancel_subscription":
        r = await CALL("subscriptions.cancel_plan", {"end_user": uid, "subscription_id": args["subscription_id"]})
        if not r.get("ok"):
            return _fail(r)
        return {"ok": True, "result": {"service": r["result"]["merchant"], "routes": [{"route": rt["kind"], "where": rt["value"]} for rt in r["result"]["routes"]
                                                                                      if rt["kind"] in ("email", "page")], "never": r["result"]["never"]}}
    # cancel_subscription — the one named (CR 84: by its service's name too), its route from its own plan
    sid = args.get("subscription_id")
    if not sid and args.get("service"):
        want = str(args["service"]).lower().strip()
        subs = _LAST.get(ctx.account)
        if subs is None:
            r0 = await CALL("subscriptions.find", {"end_user": uid})
            subs = [_brief(s) for s in ((r0.get("result") or {}).get("subscriptions") or [])] if r0.get("ok") else []
        hits = [b for b in subs if want in b["service"].lower() or want in (b.get("plan") or "").lower()]
        if len(hits) != 1:
            return {"ok": False, "error": {"code": "which_subscription", "message": "ask which one — " + (", ".join(b["service"] for b in hits) if hits else
                                                                                                      "it isn't in their list; find their subscriptions first")}}
        sid = hits[0]["subscription_id"]
    if not sid:
        return {"ok": False, "error": {"code": "which_subscription", "message": "ask which subscription to cancel"}}
    key = f"{ctx.account}|{sid}"
    pend = _PENDING.get(key)
    route = args.get("route") or (pend or {}).get("route")
    if not route:
        pl = await CALL("subscriptions.cancel_plan", {"end_user": uid, "subscription_id": sid})
        if not pl.get("ok"):
            return _fail(pl)
        kinds = [rt["kind"] for rt in pl["result"]["routes"]]
        route = "email" if "email" in kinds else "page" if "page" in kinds else None   # it cancels by email → the email; else its own page
        if not route:
            return {"ok": False, "error": {"code": "no_cancel_route", "message": "their own pages don't say how to cancel"}}
    inp = {"end_user": uid, "subscription_id": sid, "route": route, **({"account_email": args["account_email"]} if args.get("account_email") else {})}
    if pend and pend["at"] < ctx.started.timestamp():     # their yes, in a LATER turn than the read-back
        if via() == "sandbox":
            a = await CALL("sandbox.simulate_approval", {"read_back_id": pend["read_back_id"], "said": ctx.user_said or ""})
            if not a.get("ok"):
                return {"ok": False, "error": {"code": (a.get("error") or {}).get("code") or "no_explicit_yes",
                                               "message": "that wasn't a clear yes — ask them again before cancelling"}}
            r = await CALL("subscriptions.cancel", inp, approval=a["result"]["approval_id"])
            if not r.get("ok"):
                return _fail(r)
            _PENDING.pop(key, None)
            s = r["result"]["subscription"]
            if s["status"] == "handed_over":   # CR 84 · the page is theirs to press
                page = (s.get("routes") or [{}])[0].get("value")
                # Sasha 243 · the page reaches the chat as a card (live: she said "it's in the chat now" and nothing was there)
                return {"ok": True, "result": {"status": "handed_over", "service": s["merchant"], "page": page,
                                               "line": r["result"]["outcome"]["target_words"]["text"],
                                               **({"render": {"kind": "handover", "url": page, "external": True}}
                                                  if isinstance(page, str) and page.startswith("https://") else {})}}
            return {"ok": True, "result": {"status": "cancel_requested", "service": s["merchant"],
                                           "line": f"Cancellation requested from {s['merchant']} — it's not cancelled until they confirm."}}
        st = await CALL("approvals.status", {"read_back_id": pend["read_back_id"]})   # live: their tap on AgAPI's link decides
        ap = ((st.get("result") or {}).get("approval") or {}) if st.get("ok") else {}
        if not ap.get("approval_id") or ap.get("state") != "valid":
            return {"ok": True, "result": {"status": "waiting_for_their_tap", "line": "It's on their phone: they tap Yes there, then it goes."}}
        r = await CALL("subscriptions.cancel", inp, approval=ap["approval_id"])
        if not r.get("ok"):
            return _fail(r)
        _PENDING.pop(key, None)
        return {"ok": True, "result": {"status": "cancel_requested", "service": r["result"]["subscription"]["merchant"]}}
    r = await CALL("subscriptions.cancel", inp)
    e = r.get("error") or {}
    if e.get("code") != "approval_required":
        return _fail(r) if not r.get("ok") else {"ok": True, "result": {"status": "cancel_requested"}}
    d = e.get("details") or {}
    _PENDING[key] = {"read_back_id": d["read_back_id"], "route": route, "at": time.time()}
    if via() == "live":
        await CALL("approvals.request", {"read_back_id": d["read_back_id"], "channel": "link_sms"})
    return {"ok": True, "result": {"status": "awaiting_yes", "read_back": (d.get("read_back") or {}).get("lines") or [],
                                   "ask": "Read this back and ask; cancel only on their yes, in their next message."}}


def wrap(base: Callable[..., Awaitable[Dict[str, Any]]]) -> Callable[..., Awaitable[Dict[str, Any]]]:
    """/s2's runner: the radar's three tools here; every other tool exactly as `base` runs it."""
    async def run(ctx, name: str, args: dict) -> Dict[str, Any]:
        if name in TOOL_NAMES:
            return await run_tool(ctx, name, args)
        return await base(ctx, name, args)
    return run


__all__ = ["TOOLS", "TOOL_NAMES", "wrap", "keep_statement", "via"]
