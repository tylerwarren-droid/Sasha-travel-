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

import base64
import json
import os
import secrets
import time
from typing import Any, Awaitable, Callable, Dict, Optional

TOOL_NAMES = ("find_subscriptions", "plan_cancel_subscription", "cancel_subscription")
TOOLS = [
    {"name": "find_subscriptions", "description": (
        "What the person is paying for: from their RECEIPT emails (from_gmail: true — use it when they ask 'what subscriptions am I paying "
        "for?') or from a bank statement they uploaded (statement_ref; use_sample in test mode); with neither, what's already known. From Gmail: the FIRST time it returns a consent "
        "sentence — say it exactly and ask; call again with consent_yes: true only after they say yes, in a later turn. Each subscription: "
        "service, price, monthly/yearly, last charge, renews (quoted from the receipt; 'expected' when the email doesn't say). Say `say` as given."),
     "input_schema": {"type": "object", "properties": {"from_gmail": {"type": "boolean"}, "consent_yes": {"type": "boolean"},
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
STATEMENT_TTL_S, MAX_BYTES = 1800, 5_000_000
MEDIA = {"text/csv", "text/plain", "application/pdf", "image/png", "image/jpeg", "image/webp"}


def via() -> str:
    return "live" if os.getenv("SASHA_SUBSCRIPTIONS_VIA", "sandbox").strip().lower() == "live" else "sandbox"


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
    live = via() == "live"
    url = (os.getenv("SASHA_AGAPI_URL", "https://agapi-live-production.up.railway.app") if live
           else os.getenv("SASHA_AGAPI_TEST_URL", "https://agapi-sandbox-production.up.railway.app")).rstrip("/")
    key = os.getenv("SASHA_AGAPI_KEY" if live else "SASHA_AGAPI_TEST_KEY", "").strip()
    if not key:
        return {"ok": False, "error": {"code": "not_configured", "message": "the subscription radar isn't switched on yet"}}
    h = {"Authorization": f"Bearer {key}", "content-type": "application/json", "Idempotency-Key": "s2sub_" + secrets.token_hex(12)}
    if approval:
        h["AgAPI-Approval-Id"] = approval
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as c:
            r = await c.post(f"{url}/v1/{op}", headers=h, content=json.dumps(body))
        return r.json()
    except Exception as e:
        return {"ok": False, "error": {"code": "unreachable", "message": type(e).__name__}}


CALL: Callable[..., Awaitable[Dict[str, Any]]] = _agapi   # tests replace it


async def _end_user(account: str) -> Optional[str]:
    if account in _USERS:
        return _USERS[account]
    r = await CALL("users.register", {"external_ref": f"sasha:{account}"})
    if r.get("ok"):
        _USERS[account] = r["result"]["end_user_id"]
        return _USERS[account]
    return None


def _fail(r: dict) -> Dict[str, Any]:
    e = r.get("error") or {}
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
        lines.append(f"{b['service']}: {b['amount']}{' ' + per if per else ' (the receipt doesn’t say how often)'}{renew}")
    unknown = [b["service"] for b in subs if b["how_often"] not in ("monthly", "yearly", "weekly", "quarterly")]
    return (f"From your {source}, you're paying for {len(subs)}: " + "; ".join(lines) + f". That's about {tot} a month"
            + (f", not counting {', '.join(unknown)}." if unknown else "."))


async def run_tool(ctx, name: str, args: dict) -> Dict[str, Any]:
    uid = await _end_user(ctx.account)
    if not uid:
        return {"ok": False, "error": {"code": "unavailable", "message": "the subscription radar didn't answer"}}
    if name == "find_subscriptions":
        body: Dict[str, Any] = {"end_user": uid}
        ref = args.get("statement_ref")
        source = "statement"
        if args.get("from_gmail") and not ref:   # CR 84 · receipts in their Gmail (read-only)
            from agapi import s2_gmail_receipts as GR
            c = GR.consent()
            if ctx.account not in _CONSENTED:
                asked = _CONSENT_ASKED.get(ctx.account)
                if not (args.get("consent_yes") and asked and asked < ctx.started.timestamp()):
                    _CONSENT_ASKED[ctx.account] = time.time()
                    return {"ok": True, "result": {"status": "needs_consent", "ask": c["text"],
                                                   "how": "Say this sentence exactly and ask; look only after they say yes, in their next message."}}
                _CONSENTED[ctx.account] = {"version": c["version"], "text_sha256": c["text_sha256"], "at": time.time()}
            if await GR.connected(ctx.account):
                msgs = await GR.receipts(ctx.account)
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
        elif args.get("use_sample"):
            if via() == "live":
                return {"ok": False, "error": {"code": "sample_test_only", "message": "the sample statement is for test mode"}}
            body["statement"] = {"sample": True}
        r = await CALL("subscriptions.find", body)
        body.pop("emails", None)                           # the emails are dropped here, as soon as AgAPI has answered
        if ref:
            _STATEMENTS.pop(ref, None)                     # read once; never kept
        if not r.get("ok"):
            return _fail(r)
        res = r["result"]
        tot = ", ".join(f"{t['currency']} {t['amount_minor'] / 100:.2f}" for t in res["monthly_total"])
        subs = [_brief(s) for s in res["subscriptions"] if s["status"] == "active"]
        _LAST[ctx.account] = subs
        return {"ok": True, "result": {"subscriptions": subs, "monthly_total": tot, "say": _say_list(subs, tot, source),
                                       "likely_unused": res["likely_unused"], "note": res.get("note"),
                                       **({"emails": res["emails"]} if res.get("emails") else {}),
                                       "render": {"kind": "subscriptions", "items": [{"service": b["service"], "price": b["amount"], "how_often": b["how_often"],
                                                  "renews": b.get("renews"), "expected": (b.get("renews_basis") or "").startswith("expected"),
                                                  "subscription_id": b["subscription_id"]} for b in subs], "total": tot, "source": source}}}
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
                return {"ok": True, "result": {"status": "handed_over", "service": s["merchant"], "page": (s.get("routes") or [{}])[0].get("value"),
                                               "line": r["result"]["outcome"]["target_words"]["text"]}}
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
