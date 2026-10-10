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
        "What the person is subscribed to, from a bank or card statement: each recurring charge (service, amount, how often, last charge), the "
        "monthly total, and 'likely unused' with its reason. Use the statement_ref they uploaded on this page; if none and they want to try it, "
        "use_sample (test mode). Without either: what's already known for them. Say the list briefly; the reasons are the statement's, never yours."),
     "input_schema": {"type": "object", "properties": {"statement_ref": {"type": "string"}, "use_sample": {"type": "boolean"}}}},
    {"name": "plan_cancel_subscription", "description": (
        "How to cancel one subscription: the merchant's own cancel routes (their cancel page, an email). Call it before cancel_subscription."),
     "input_schema": {"type": "object", "properties": {"subscription_id": {"type": "string"}}, "required": ["subscription_id"]}},
    {"name": "cancel_subscription", "description": (
        "Cancel one subscription by a planned route ('email' to the merchant, or 'page': their cancel page to the person's phone). The FIRST call "
        "returns what will be done — read it back and ask; call it again only after they say yes, in a later turn. It's 'cancel requested' until "
        "the merchant confirms. Sasha never logs into anyone's account."),
     "input_schema": {"type": "object", "properties": {"subscription_id": {"type": "string"}, "route": {"type": "string", "enum": ["email", "page"]},
                                                       "account_email": {"type": "string"}}, "required": ["subscription_id"]}},
]

_STATEMENTS: Dict[str, dict] = {}     # statement_ref → {account, media_type, b64, at} — memory only, 30 minutes
_USERS: Dict[str, str] = {}           # account → AgAPI end_user
_PENDING: Dict[str, dict] = {}        # account|subscription → {read_back_id, route, at} (the read-back said; their yes comes next turn)
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
            **({"why": s["why"]} if s["why"] else {}), "status": s["status"]}


async def run_tool(ctx, name: str, args: dict) -> Dict[str, Any]:
    uid = await _end_user(ctx.account)
    if not uid:
        return {"ok": False, "error": {"code": "unavailable", "message": "the subscription radar didn't answer"}}
    if name == "find_subscriptions":
        body: Dict[str, Any] = {"end_user": uid}
        ref = args.get("statement_ref")
        if ref:
            st = _STATEMENTS.get(ref)
            if not st or st["account"] != ctx.account:
                return {"ok": False, "error": {"code": "statement_unknown", "message": "that statement isn't here any more — ask them to upload it again"}}
            body["statement"] = {"media_type": st["media_type"], "content_base64": st["b64"]}
        elif args.get("use_sample"):
            if via() == "live":
                return {"ok": False, "error": {"code": "sample_test_only", "message": "the sample statement is for test mode"}}
            body["statement"] = {"sample": True}
        r = await CALL("subscriptions.find", body)
        if ref:
            _STATEMENTS.pop(ref, None)                     # read once; never kept
        if not r.get("ok"):
            return _fail(r)
        res = r["result"]
        tot = ", ".join(f"{t['currency']} {t['amount_minor'] / 100:.2f}" for t in res["monthly_total"])
        return {"ok": True, "result": {"subscriptions": [_brief(s) for s in res["subscriptions"]], "monthly_total": tot,
                                       "likely_unused": res["likely_unused"], "note": "from their statement; 'likely unused' gives the statement's reason"}}
    if name == "plan_cancel_subscription":
        r = await CALL("subscriptions.cancel_plan", {"end_user": uid, "subscription_id": args["subscription_id"]})
        if not r.get("ok"):
            return _fail(r)
        return {"ok": True, "result": {"service": r["result"]["merchant"], "routes": [{"route": rt["kind"], "where": rt["value"]} for rt in r["result"]["routes"]
                                                                                      if rt["kind"] in ("email", "page")], "never": r["result"]["never"]}}
    # cancel_subscription
    sid, key = args["subscription_id"], f"{ctx.account}|{args['subscription_id']}"
    pend = _PENDING.get(key)
    route = args.get("route") or (pend or {}).get("route") or "email"
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
