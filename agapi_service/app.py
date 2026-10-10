"""AgAPI v1 over HTTP (Part 1 §1): POST /v1/{operation}, body = input; headers AgAPI-Version, AgAPI-Request-Id, Idempotency-Key,
AgAPI-Approval-Id; the account, principal and mode come ONLY from the key. Every response — errors included — is the envelope
{agapi, request_id, ok, result|error, replayed?, evidence_id?, trace}. Never a non-envelope body (E1).

Order (Part 1 I6): authenticate → resolve the account → limits → validate → claim the idempotency key → act → store.
    uvicorn agapi_service.app:app --port 8787          (from the repo root)"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import time
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from . import adapters as AD, config, engine as E, gen, providers as PV, rules as R, surface, webhooks as W
from .registry import AgapiError, check_input, operations
from .store import Store, dumps, later, loads, now, ts

app = FastAPI(title="AgAPI sandbox", version=config.SPEC_DRAFT, docs_url=None, redoc_url=None, openapi_url=None)
_DB: Optional[Store] = None


def db() -> Store:
    global _DB
    if _DB is None:
        _DB = Store()
    return _DB


def use_store(store: Store) -> None:
    global _DB
    _DB = store


surface.bind(db)
app.include_router(surface.router)
from . import fixtures as _fixtures   # noqa: E402 · CR 64 · DIVE prep: a hosted fake supplier
_fixtures.bind(db)
app.include_router(_fixtures.router)
from . import demo as _demo  # noqa: E402  (CR 59 · the VC demo console)
app.include_router(_demo.router)
_LOOP: Optional[asyncio.Task] = None


@app.on_event("startup")
async def _startup() -> None:
    global _LOOP
    config.pepper()                    # refuses to start deployed without AGAPI_KEY_PEPPER
    if db().kind == "postgres" and config.IMPORT_SQLITE:   # CR 69 · the one-time move of the volume's SQLite rows into Postgres
        from .store import import_sqlite
        import logging
        counts = import_sqlite(config.DB_PATH, db())
        logging.getLogger("agapi").warning("sqlite → postgres import: %s", counts if counts is not None else "already done (or no SQLite file)")
    PV.install_live() if config.LIVE_SERVICE else PV.install()   # CR 70 · agapi-live: no fixtures, only the live providers' hosts
    if config.LIVE_SERVICE:
        from . import adapters_live
        from .adapters_live import payments as _LPAY
        adapters_live.bind(db)
        asyncio.create_task(_LPAY.poll(db))    # CR 70 · Stripe TEST sessions settle from Stripe's own record
    _migrate_scopes(db())
    ensure_products(db())              # CR 69
    W.allow_endpoint_hosts(db())
    if _LOOP is None:
        _LOOP = asyncio.create_task(W.loop(db))


def _migrate_scopes(store: Store) -> None:
    """A key that holds exactly an earlier default set of scopes gains the scopes added since (additive; nothing removed)."""
    earlier = set(config.DEFAULT_SCOPES) - set(config.SCOPES_ADDED)
    for k in store.q("select key_id, scopes from api_keys where state = 'active'"):
        have = set(loads(k["scopes"]))
        if earlier <= have <= set(config.DEFAULT_SCOPES) and have != set(config.DEFAULT_SCOPES):
            store.x("update api_keys set scopes = ? where key_id = ?", dumps(sorted(have | set(config.SCOPES_ADDED))), k["key_id"])


# ── keys (Part 4 K1–K7) ────────────────────────────────────────────────────────────────────────────────────────────────

_KEY = re.compile(r"^agp_(test|live)_[A-Za-z0-9]{32}$")
_B62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def key_hmac(full_key: str) -> str:
    return hmac.new(config.pepper(), full_key.encode(), hashlib.sha256).hexdigest()


def create_key(store: Store, account: str, label: str, mode: str = "test", scopes: Optional[list] = None) -> str:
    """→ the key, shown ONCE (agp_test_/agp_live_ + 32 base62); stored only as HMAC(pepper, key). At most 2 active per account per mode (K5).
    CR 69: live keys exist (separate from test); every provider a live key could reach refuses until phase 2 connects it."""
    import secrets
    if mode not in ("test", "live"):
        raise ValueError("mode is test or live")
    active = store.q("select key_id from api_keys where account = ? and mode = ? and state = 'active'", account, mode)
    if len(active) >= 2:
        raise ValueError(f"this account already has 2 active {mode} keys — revoke one first (K5)")
    full = f"agp_{mode}_" + "".join(secrets.choice(_B62) for _ in range(32))
    store.x("insert into api_keys (key_id, account, mode, prefix, secret_hmac, scopes, budget_units, rate_per_min, label, state, created_at) "
            "values (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)", R.new_id("key"), account, mode, full[:15], key_hmac(full),
            dumps(scopes or config.DEFAULT_SCOPES), config.DEFAULT_BUDGET_UNITS, config.DEFAULT_RATE_PER_MIN, label, ts())
    return full


def ensure_products(store: Store) -> None:
    """CR 69 · one account per product (sasha, ad, dive, campusme); DIVE's existing 'DIVE-demo' account is dive's; every other account is a
    partner. Additive: nothing is renamed or removed."""
    for p in config.PRODUCTS:
        if store.one("select 1 as y from accounts where product = ?", p):
            continue
        dive = store.one("select id from accounts where name = 'DIVE-demo' and product is null") if p == "dive" else None
        if dive:
            store.x("update accounts set product = 'dive' where id = ?", dive["id"])
        else:
            store.x("insert into accounts (id, name, created_at, product) values (?, ?, ?, ?)", R.new_id("acct"), f"{p} (product)", ts(), p)
    store.x("update accounts set product = 'partner' where product is null")


def create_account(store: Store, name: str) -> str:
    aid = R.new_id("acct")
    store.x("insert into accounts (id, name, created_at) values (?, ?, ?)", aid, name, ts())
    return aid


def _auth(store: Store, header: Optional[str]) -> dict:
    m = re.fullmatch(r"Bearer (\S+)", (header or "").strip())
    if not m or not _KEY.match(m.group(1)):
        raise AgapiError("unauthenticated", "Send Authorization: Bearer agp_test_… with a valid key.")
    row = store.one("select * from api_keys where secret_hmac = ?", key_hmac(m.group(1)))
    if not row or row["state"] != "active":
        raise AgapiError("unauthenticated", "That key isn't valid, or it was revoked.")
    return row


def _scoped(key: dict, op: str) -> bool:
    dom = op.split(".")[0]
    return any(s == op or s == f"{dom}.*" for s in loads(key["scopes"]))


# ── the envelope ───────────────────────────────────────────────────────────────────────────────────────────────────────

def _env(version: str, request_id: str, body: dict, trace: Optional[dict]) -> dict:
    out = {"agapi": version, "request_id": request_id, **body}
    if trace:
        out["trace"] = trace
    return out


def _headers(store: Store, key: Optional[dict], replayed: bool = False, retry_after: Optional[int] = None) -> dict:
    h = {"AgAPI-Version": config.CONTRACT}
    if replayed:
        h["AgAPI-Replayed"] = "true"
    if retry_after:
        h["Retry-After"] = str(retry_after)
    if key:
        used = _per_minute(store, key)
        h.update({"RateLimit-Limit": str(key["rate_per_min"]), "RateLimit-Remaining": str(max(0, key["rate_per_min"] - used)),
                  "RateLimit-Reset": "60", "AgAPI-Budget-Remaining": str(E.budget_remaining(store, key))})
    return h


def _per_minute(store: Store, key: dict) -> int:
    return store.one("select count(*) as n from usage_records where key_id = ? and at >= ?", key["key_id"],
                     ts(now() - __import__("datetime").timedelta(seconds=60)))["n"]


def _charge(op: dict, ok: bool, code: Optional[str], replayed: bool) -> int:
    """Part 4 M3: ok results and upstream_refused on act classes are charged; replays, our errors and outages never are."""
    if replayed:
        return 0
    if ok or (code == "upstream_refused" and op["cost_class"] in ("act", "act_prepare")):
        return config.COST_UNITS[op["cost_class"]]
    return 0


def _record(store: Store, key: dict, request_id: str, op_name: str, op: Optional[dict], units: int, replayed: bool, ok: bool,
            code: Optional[str], ms: Optional[int] = None) -> None:
    store.x("insert into usage_records (request_id, key_id, account, mode, operation, cost_class, cost_units, replayed, ok, error_code, at, ms) "
            "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", request_id, key["key_id"], key["account"], key["mode"], op_name,
            (op or {}).get("cost_class", "free"), units, int(replayed), int(ok), code, ts(), ms)
    store.x("update api_keys set last_used_at = ? where key_id = ?", ts(), key["key_id"])


def _scope(store: Store, account: str, op_name: str, inp: dict) -> str:
    """(account, operation, key). ⚠ Part 1 I3 says intent-or-operation ("the same key under two intents is two keys"), but Part 3
    vector I-2 requires the same key with a different hold_id to be idempotency_conflict — only an operation scope passes it.
    The vectors are what conformance is measured on; the conflict is reported to EU (CR 58)."""
    return op_name


@app.post("/v1/{op_name}")
async def call(op_name: str, req: Request):
    return await execute(op_name, {k.lower(): v for k, v in req.headers.items()}, await req.body())


async def execute(op_name: str, headers: dict, raw: bytes, principal: Optional[dict] = None) -> JSONResponse:
    """The whole pipeline for one request — the HTTP route and the /demo console both come through here. `principal` (the demo
    console only) is a key's row resolved server-side; the key itself is never held or shown."""
    t0 = time.perf_counter()
    store = db()
    rid_h = (headers.get("agapi-request-id") or "").strip()
    request_id = rid_h if re.fullmatch(r"req_[0-9A-HJKMNP-TV-Z]{26}", rid_h) else R.new_id("req")
    version = (headers.get("agapi-version") or config.CONTRACT).strip()
    key, op, replayed, claimed = None, None, False, None
    ctx: Optional[E.Ctx] = None

    def fail(e: AgapiError, units_ok: bool = True) -> JSONResponse:
        body = {"ok": False, "error": e.body()}
        trace = {"operation": op_name, "agent": op["agent"], "ms": int((time.perf_counter() - t0) * 1000),
                 "upstream": ctx.up.calls if ctx else [], "cost_units": _charge(op, False, e.code, False)} if op else None
        if key and op:
            _record(store, key, request_id, op_name, op, trace["cost_units"] if trace else 0, False, False, e.code,
                    int((time.perf_counter() - t0) * 1000))
        return JSONResponse(_env(version if version in config.SUPPORTED else config.CONTRACT, request_id, body, trace),
                            status_code=e.http, headers=_headers(store, key, retry_after=e.retry_after_s))

    try:
        if version not in config.SUPPORTED:
            raise AgapiError("version_unsupported", "That AgAPI-Version isn't served here.", {"supported": list(config.SUPPORTED)})
        key = principal or _auth(store, headers.get("authorization"))
        op = operations().get(op_name)
        if not op:
            raise AgapiError("unknown_operation", f"There is no operation {op_name} in AgAPI v1.")
        if not _scoped(key, op_name):
            raise AgapiError("forbidden", "This key's scopes don't include that operation.")
        if op.get("test_only") and key["mode"] != "test":
            raise AgapiError("mode_not_available", "That operation exists in test mode only.")
        if config.LIVE_SERVICE and key["mode"] != "live":   # CR 70 · agapi-live serves live keys only
            raise AgapiError("mode_not_available", "This is AgAPI live: use a live key here (test keys go to the sandbox).")
        if key["mode"] == "live":
            if op_name not in ("trip.hold", "trip.complete", "trip.cancel", "users.register"):   # CR 70/71: checked by their input, below
                AD.require_live(op_name)   # CR 69 · refused BEFORE anything happens until phase 2 connects the provider
            _live_inp = True               # CR 70 · re-checked item-aware once the input is read (below)
        else:
            _live_inp = False
        if _per_minute(store, key) >= key["rate_per_min"]:
            raise AgapiError("rate_limited", "Too many requests for this key; slow down.", retry_after_s=30)
        if config.COST_UNITS[op["cost_class"]] > 0 and E.budget_remaining(store, key) <= 0:
            raise AgapiError("budget_exhausted", "This key's budget for the month is spent.")
        try:
            inp = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            raise AgapiError("invalid_request", "The body isn't valid JSON.")
        if not isinstance(inp, dict):
            raise AgapiError("invalid_request", "The body is the operation's input object.")
        try:
            R.canonical(inp)       # §4.1: no floats, no odd keys, no lone surrogates in anything we hash
        except R.Refused as e:
            raise AgapiError("invalid_input", f"The input can't be canonicalised ({e}).", {"path": "/", "rule": "canonical"})
        check_input(op_name, inp)
        gtok = (headers.get("x-sasha-guest-token") or "").strip()
        if gtok and config.LIVE_SERVICE and key["mode"] == "live":   # CR 71 · S2's guest token: only from the sasha product's key
            prod = store.one("select product from accounts where id = ?", key["account"])
            if prod and prod.get("product") == "sasha" and len(gtok) <= 4096:
                from . import adapters_live as _AL
                _AL.GUEST_TOKEN.set(gtok)
        if _live_inp:
            AD.require_live(op_name, inp, store, key["account"])   # CR 70 · the items decide which providers a live act needs
            AD.precheck_live(op_name, inp, store, key["account"])  # CR 70 · live sends only to allow-listed addresses/numbers
        idem = headers.get("idempotency-key")
        approval_id = (headers.get("agapi-approval-id") or "").strip() or None
        if approval_id and not re.fullmatch(r"apv_[0-9A-HJKMNP-TV-Z]{26}", approval_id):
            raise AgapiError("invalid_request", "AgAPI-Approval-Id is an apv_ id.")
        if op["idempotent"]:
            if not idem:
                raise AgapiError("idempotency_key_required", "This operation needs an Idempotency-Key header.")
            if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", idem):
                raise AgapiError("invalid_request", "The Idempotency-Key is 16–128 characters of A–Z a–z 0–9 _ -.")
            scope = _scope(store, key["account"], op_name, inp)
            rsha = R.request_sha256(op_name, inp)
            store.x("delete from idempotency where account = ? and created_at < ?", key["account"],
                    ts(now() - __import__("datetime").timedelta(hours=config.IDEMPOTENCY_RETENTION_H)))
            with store.tx():
                row = store.one("select * from idempotency where account = ? and scope = ? and idem_key = ?", key["account"], scope, idem)
                if not row:
                    store.x("insert into idempotency (account, scope, idem_key, request_sha256, state, created_at) values (?, ?, ?, ?, 'in_flight', ?)",
                            key["account"], scope, idem, rsha, ts())
            if row:
                if row["request_sha256"] != rsha:
                    raise AgapiError("idempotency_conflict", "That Idempotency-Key was used with a different request.")
                if row["state"] == "in_flight":
                    raise AgapiError("idempotency_in_flight", "That request is still being processed (or its outcome is being checked).",
                                     {"act_id": row["act_id"]} if row["act_id"] else None, retry_after_s=2)
                body = loads(row["response"])
                trace = {"operation": op_name, "agent": op["agent"], "ms": int((time.perf_counter() - t0) * 1000), "upstream": [], "cost_units": 0}
                _record(store, key, request_id, op_name, op, 0, True, body["ok"], (body.get("error") or {}).get("code"), trace["ms"])
                return JSONResponse(_env(version, request_id, {**body, "replayed": True}, trace), status_code=row["status"],
                                    headers=_headers(store, key, replayed=True))
            claimed = (key["account"], scope, idem)
        ctx = E.Ctx(store, key, request_id, approval_id, idem)
        result, status, evidence_id = await E.OPS[op_name](ctx, inp)
        body = {"ok": True, "result": result, **({"evidence_id": evidence_id} if evidence_id else {})}
        units = _charge(op, True, None, False)
        if claimed:
            store.x("update idempotency set state = 'done', status = ?, response = ? where account = ? and scope = ? and idem_key = ?",
                    status, dumps(body), *claimed)
        _record(store, key, request_id, op_name, op, units, False, True, None, int((time.perf_counter() - t0) * 1000))
        trace = {"operation": op_name, "agent": op["agent"], "ms": int((time.perf_counter() - t0) * 1000), "upstream": ctx.up.calls,
                 "cost_units": units}
        return JSONResponse(_env(version, request_id, body, trace), status_code=status, headers=_headers(store, key))
    except AgapiError as e:
        _settle(store, claimed, e, ctx)
        return fail(e)
    except Exception as e:   # E1: never a non-envelope body; `internal` only when nothing was changed by this call
        import logging
        logging.getLogger("agapi").exception("internal: %s", type(e).__name__)
        err = AgapiError("internal", "Something failed on our side; nothing was changed by this call.")
        _settle(store, claimed, err, ctx)
        return fail(err)


def _settle(store: Store, claimed: Optional[tuple], e: AgapiError, ctx: Optional[E.Ctx]) -> None:
    """Part 1 I7/I8: store a definitive refusal for replay; keep outcome_unknown in flight; release everything else (and the yes)."""
    if ctx and ctx.consumed and (e.category in ("upstream", "internal") and e.code != "upstream_refused"):
        E.release_approval(store, ctx.account, ctx.consumed)
    if not claimed:
        return
    if e.code == "outcome_unknown":
        store.x("update idempotency set act_id = ? where account = ? and scope = ? and idem_key = ?", e.details.get("act_id"), *claimed)
    elif e.store_for_replay:
        store.x("update idempotency set state = 'done', status = ?, response = ? where account = ? and scope = ? and idem_key = ?",
                e.http, dumps({"ok": False, "error": e.body()}), *claimed)
    else:
        store.x("delete from idempotency where account = ? and scope = ? and idem_key = ?", *claimed)


# ── generated docs (Part 4 §7) ─────────────────────────────────────────────────────────────────────────────────────────

@app.get("/openapi.json")
async def openapi():
    return JSONResponse(gen.openapi(config.PUBLIC_URL))


@app.get("/mcp.json")
async def mcp():
    return JSONResponse(gen.mcp_manifest(config.PUBLIC_URL))


@app.get("/collection.http", response_class=PlainTextResponse)
async def collection():
    return PlainTextResponse(gen.http_collection(config.PUBLIC_URL), media_type="text/plain; charset=utf-8")


@app.get("/", response_class=HTMLResponse)
async def docs():
    """The earlier one-page docs (kept; also at /docs/reference). /docs is the docs SITE (CR 66, docs_site.py)."""
    return HTMLResponse(gen.docs_page(config.PUBLIC_URL))


from . import docs_site as _docs_site   # noqa: E402 · CR 66 · AgAPI's public docs, EU 211's table of contents
app.include_router(_docs_site.router)


# ── issuing by hand, remotely (Part 4 K6) — signed with the service's own pepper, so no second secret exists ────────────

@app.post("/admin/{action}")
async def admin(action: str, req: Request):
    """AgAPI-Admin-Signature: t=<unix>,n=<nonce>,v1=<hex HMAC-SHA256(pepper, "<t>.<n>.<raw body>")>. Stale after 5 minutes; a nonce
    is used once. `key` {name, label?} → {account, key_id, prefix, key} — the key appears in THIS response only. `list` → prefixes."""
    store = db()
    raw = (await req.body()).decode()
    m = re.fullmatch(r"t=(\d+),n=([A-Za-z0-9_-]{16,64}),v1=([0-9a-f]{64})", (req.headers.get("agapi-admin-signature") or "").strip())
    if not m or abs(int(time.time()) - int(m.group(1))) > 300:
        return JSONResponse({"ok": False}, status_code=401)
    want = hmac.new(config.pepper(), f"{m.group(1)}.{m.group(2)}.{raw}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(want, m.group(3)):
        return JSONResponse({"ok": False}, status_code=401)
    store.x("create table if not exists admin_nonces (n text primary key, at text not null)")
    if store.x("insert or ignore into admin_nonces (n, at) values (?, ?)", m.group(2), ts()) != 1:
        return JSONResponse({"ok": False, "why": "nonce reused"}, status_code=401)
    body = json.loads(raw or "{}")
    if action == "key":
        name = str(body.get("name") or "").strip()[:80]
        product = str(body.get("product") or "").strip()
        if not name and product in config.PRODUCTS:        # CR 69 · a product's own account
            row = store.one("select id, name from accounts where product = ?", product)
            name = row["name"] if row else ""
        if not name:
            return JSONResponse({"ok": False, "why": "name"}, status_code=400)
        row = store.one("select id from accounts where name = ?", name)
        acct = row["id"] if row else create_account(store, name)
        mode = str(body.get("mode") or "test")
        scopes = body.get("scopes")
        allowed = set(config.DEFAULT_SCOPES) | {config.METRICS_SCOPE, "magellan.*"}
        if scopes is not None and (not isinstance(scopes, list) or not scopes or not set(scopes) <= allowed):
            return JSONResponse({"ok": False, "why": "scopes"}, status_code=400)
        try:
            k = create_key(store, acct, str(body.get("label") or name)[:80], mode, scopes)
        except ValueError as e:
            return JSONResponse({"ok": False, "why": str(e)}, status_code=409)
        kr = store.one("select key_id, prefix from api_keys where secret_hmac = ?", key_hmac(k))
        return JSONResponse({"ok": True, "account": acct, "key_id": kr["key_id"], "prefix": kr["prefix"], "key": k},
                            headers={"Cache-Control": "no-store"})
    if action == "smoke" and config.LIVE_SERVICE:   # CR 70 · a live adapter's smoke check: spends nothing, contacts nobody
        from . import adapters_live
        kind = str(body.get("provider") or "")
        if kind == "flights_cancel":   # CR 71 · a TEST order made here, then cancelled (Duffel test mode only)
            try:
                out = await adapters_live.ADAPTERS["flights"].smoke_cancel()
            except Exception as e:
                out = {"ok": False, "why": type(e).__name__}
            return JSONResponse({"ok": True, "provider": kind, "smoke": out}, headers={"Cache-Control": "no-store"})
        ad = adapters_live.ADAPTERS.get(kind)
        if not ad or not hasattr(ad, "smoke"):
            return JSONResponse({"ok": False, "why": "no such live adapter"}, status_code=404)
        try:
            out = await ad.smoke()
        except Exception as e:
            out = {"ok": False, "why": type(e).__name__}
        return JSONResponse({"ok": True, "provider": kind, "connected": kind in AD.CONNECTED_LIVE, "smoke": out}, headers={"Cache-Control": "no-store"})
    if action == "registry_read" and not config.LIVE_SERVICE:   # CR 73 · Magellan reads one jurisdiction's official pages FROM THIS SERVER
        from .registers import model as _RM, reader as _RR
        code = str(body.get("jurisdiction") or "").strip().upper()
        ex, se, _ = _RM.files()
        seeds = (se["jurisdictions"].get(code) or {}).get("seeds") or []
        if not seeds:
            return JSONResponse({"ok": False, "why": "no seeds for that jurisdiction"}, status_code=404)
        checks = [c["api_endpoint"] for c in ex["cells"] if c["jurisdiction"] == code and c["api_endpoint"].startswith("http")]
        try:
            out = await _RR.read_jurisdiction(code, seeds, checks)
        except Exception as e:
            return JSONResponse({"ok": False, "why": f"{type(e).__name__}: {str(e)[:200]}"}, status_code=502)
        return JSONResponse({"ok": True, "read": out}, headers={"Cache-Control": "no-store"})
    if action == "list":
        out = []
        for a in store.q("select * from accounts order by created_at"):
            out.append({"account": a["id"], "name": a["name"], "keys": store.q("select key_id, prefix, label, state, created_at, last_used_at "
                                                                               "from api_keys where account = ?", a["id"])})
        return JSONResponse({"ok": True, "accounts": out})
    return JSONResponse({"ok": False}, status_code=404)


_demo.bind(db, lambda *a, **k: execute(*a, **k))
from .registers import page as _registry_page   # noqa: E402 · CR 73 · /registry, the registry survey's demo (read-only)
_registry_page.bind(db)
app.include_router(_registry_page.router)


@app.get("/ics/{token}.ics")
async def ics_file(token: str):
    """CR 60 · the event file behind "Apple / any calendar" — key-less, by an unguessable token, nothing personal beyond the event."""
    from fastapi.responses import Response
    row = db().one("select ics, act_id from calendar_files where token_hash = ?", hashlib.sha256(token.encode()).hexdigest())
    if not row:
        return PlainTextResponse("Not found", status_code=404)
    return Response(row["ics"], media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{row["act_id"]}.ics"', "Cache-Control": "no-store"})


@app.get("/health")
async def health():
    return {"ok": True, "mode": "live" if config.LIVE_SERVICE else config.MODE, "spec": config.SPEC_DRAFT, "store": db().kind,
            **({"service": "live", "connected": sorted(AD.CONNECTED_LIVE)} if config.LIVE_SERVICE else {})}   # CR 70 · additive   # CR 69 · + which store (additive)


def _pct(xs: list, p: float) -> Optional[int]:
    """Nearest-rank percentile (p in 0–100) of a list of ms."""
    if not xs:
        return None
    s = sorted(xs)
    import math
    return s[max(0, min(len(s) - 1, math.ceil(p / 100 * len(s)) - 1))]


@app.get("/metrics")
async def metrics(req: Request, hours: int = 24):
    """CR 69 · per-operation timing for Falguni: count, p50/p95 ms, errors, units — behind a key that holds metrics.* (no other key)."""
    store = db()
    try:
        key = _auth(store, req.headers.get("authorization"))
    except AgapiError as e:
        return JSONResponse({"ok": False, "error": e.body()}, status_code=e.http)
    if config.METRICS_SCOPE not in loads(key["scopes"]):
        return JSONResponse({"ok": False, "error": {"code": "forbidden", "message": "This key can't read metrics.", "retryable": False}}, status_code=403)
    hours = max(1, min(int(hours), 24 * 31))
    since = ts(now() - __import__("datetime").timedelta(hours=hours))
    rows = store.q("select u.operation, u.ms, u.ok, u.replayed, u.cost_units, u.mode, a.product from usage_records u "
                   "left join accounts a on a.id = u.account where u.at >= ?", since)
    ops: dict = {}
    for r in rows:
        o = ops.setdefault(r["operation"], {"calls": 0, "errors": 0, "replayed": 0, "units": 0, "_ms": []})
        o["calls"] += 1
        o["errors"] += 0 if r["ok"] else 1
        o["replayed"] += r["replayed"]
        o["units"] += r["cost_units"]
        if r["ms"] is not None:
            o["_ms"].append(r["ms"])
    out = {k: {**{x: v[x] for x in ("calls", "errors", "replayed", "units")}, "p50_ms": _pct(v["_ms"], 50), "p95_ms": _pct(v["_ms"], 95),
               "timed": len(v["_ms"])} for k, v in sorted(ops.items())}
    by = {}
    for r in rows:
        by.setdefault(r["product"] or "partner", 0)
        by[r["product"] or "partner"] += 1
    allms = [r["ms"] for r in rows if r["ms"] is not None]
    return JSONResponse({"ok": True, "window_hours": hours, "since": since, "store": store.kind, "calls": len(rows),
                         "p50_ms": _pct(allms, 50), "p95_ms": _pct(allms, 95), "by_product": by, "by_mode": {
                             m: sum(1 for r in rows if r["mode"] == m) for m in ("test", "live")},
                         "operations": out, "adapters": AD.status()}, headers={"Cache-Control": "no-store"})
