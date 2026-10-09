"""CR 63 · THE KEEP in the sandbox — keep.put, keep.list (masked), keep.use (a fill token to Austen, never the value), keep.delete,
on the shared logic (backend/agapi/keep.py: tiers, validation, masks, refusals, the envelope).

  · The envelope: one data key per end user, wrapped by the KMS stand-in (AGAPI_KEEP_KEK — on Railway its own variable, never
    printed; refused on a deployed service without it). Values: AES-256-GCM under that key, bound to account/person/item/type.
  · Nothing here stores, logs, hashes plainly or returns a value. keep.put is NOT idempotent at the HTTP layer (that layer keeps a
    plain hash of the request): a re-save of the same value is found by its KEYED fingerprint and returns the same item.
  · A fill happens at the moment of use, inside the act (trip.complete for a free booking, the payment for a paid one): the value
    is opened, handed to the provider stand-in, and dropped. Tier `yes` needs the hold's read-back to NAME the item — keep.use
    re-issues it with that line, so the booking's one yes covers it and an earlier yes is void. Tier `read_back` is only shown,
    once, on the end user's own phone (/k/{token}). Every save, use, show and deletion writes evidence + an Activity row.
"""
from __future__ import annotations

import base64
import os
import secrets
from typing import Dict, List, Optional

from . import config, rules as R
from .registry import AgapiError
from .store import dumps, later, loads, ts

FILL_TTL_MIN, SHOW_TTL_MIN = 15, 10


def _K():
    from agapi import keep as K
    return K


_KMS = None


def kms():
    """The KMS stand-in. Tests set config.KEEP_KEK; a deployed sandbox must have AGAPI_KEEP_KEK (never a built-in key there)."""
    global _KMS
    raw = os.getenv("AGAPI_KEEP_KEK", "").strip()
    if not raw:
        if os.getenv("RAILWAY_ENVIRONMENT_NAME"):
            raise AgapiError("upstream_unreachable", "The Keep's key service isn't set up on this sandbox; nothing was stored or opened.",
                             {"service": "kms"})
        raw = base64.b64encode(__import__("hashlib").sha256(b"agapi-sandbox-local-keep-kek").digest()).decode()   # local only
    if _KMS is None or _KMS[0] != raw:
        _KMS = (raw, _K().LocalKms(base64.b64decode(raw)))
    return _KMS[1]


async def _dek(ctx, uid: str, create: bool) -> Optional[bytes]:
    K = _K()
    row = ctx.store.one("select * from keep_keys where account = ? and end_user = ?", ctx.account, uid)
    try:
        if row:
            return await kms().unwrap(bytes(row["wrapped_dek"]), K.dek_aad(ctx.account, uid), row["kek_version"])
        if not create:
            return None
        dek = K.new_dek()
        wrapped, version = await kms().wrap(dek, K.dek_aad(ctx.account, uid))
    except AgapiError:
        raise
    except Exception:
        raise AgapiError("upstream_unreachable", "The Keep's key service couldn't open this person's key; nothing was changed.",
                         {"service": "kms"}) from None
    ctx.store.x("insert into keep_keys (account, end_user, wrapped_dek, kek_version, created_at) values (?, ?, ?, ?, ?)",
                ctx.account, uid, wrapped, version, ts())
    return dek


def _refused(e) -> AgapiError:
    return AgapiError("invalid_input", e.message, {"path": e.path, "rule": e.rule})


def _item(ctx, uid: str, item_id: str) -> dict:
    it = ctx.store.one("select * from keep_items where account = ? and end_user = ? and id = ?", ctx.account, uid, item_id)
    if not it:
        raise AgapiError("not_found", "No such item in this person's Keep.", {"item_id": item_id})
    return it


def _event(store, account: str, uid: str, kind: str, item: dict, evidence_id: Optional[str]) -> None:
    store.x("insert into keep_events (account, id, end_user, kind, item_id, masked, evidence_id, at) values (?, ?, ?, ?, ?, ?, ?, ?)",
            account, R.new_id("kev"), uid, kind, item["id"], item["masked"], evidence_id, ts())


def _evidence(ctx, operation: str, digest_of: dict, item: dict, *, act_id=None, intent_id=None, apv=None, outcome=None,
              service: str = "keep", reference: Optional[str] = None) -> str:
    """Evidence with NO value in it: the input digest is over a redacted input (the masked item, never the value)."""
    from .engine import _evidence as ev
    retrieved = ts()[:19] + "Z"
    src = {"service": service, "retrieved_at": retrieved, "sha256": R.sha256({"item_id": item["id"], "masked": item["masked"],
                                                                              **({"reference": reference} if reference else {})})}
    return ev(ctx, operation, act_id, intent_id, digest_of, outcome, apv, [src])


def item_out(it: dict) -> dict:
    return {"item_id": it["id"], "type": it["type"], "tier": it["tier"], "masked": it["masked"], "created_at": it["created_at"],
            **({"last_used_at": it["last_used_at"]} if it["last_used_at"] else {})}


async def keep_put(ctx, inp: dict):
    from .engine import _end_user
    K = _K()
    _end_user(ctx, inp["end_user"])
    try:
        values = K.normalise(inp["type"], inp["value"])
    except K.Refused as e:
        raise _refused(e)
    kind, uid = inp["type"].strip().lower(), inp["end_user"]
    dek = await _dek(ctx, uid, create=True)
    fp = K.fingerprint(dek, kind, values)
    same = ctx.store.one("select * from keep_items where account = ? and end_user = ? and fingerprint = ?", ctx.account, uid, fp)
    if same:
        return {**item_out(same), "created": False}, 200, None
    iid = R.new_id("kpi")
    nonce, ct = K.seal(dek, K.item_aad(ctx.account, uid, iid, kind), values)
    masked = K.mask(kind, values)
    values = None   # the value is not held a line longer than the seal
    ctx.store.x("insert into keep_items (account, id, end_user, type, tier, masked, fingerprint, nonce, ciphertext, created_at) "
                "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ctx.account, iid, uid, kind, K.tier_of(kind), masked, fp, nonce, ct, ts())
    it = ctx.store.one("select * from keep_items where account = ? and id = ?", ctx.account, iid)
    eid = _evidence(ctx, "keep.put", {"end_user": uid, "type": kind, "item_id": iid}, it)
    _event(ctx.store, ctx.account, uid, "keep_save", it, eid)
    return {**item_out(it), "created": True, "evidence_id": eid}, 201, eid


async def keep_list(ctx, inp: dict):
    from .engine import _end_user
    _end_user(ctx, inp["end_user"])
    rows = ctx.store.q("select * from keep_items where account = ? and end_user = ? order by created_at", ctx.account, inp["end_user"])
    return {"items": [item_out(r) for r in rows], "values_shown": False}, 200, None


def keep_lines(store, account: str, hold_id: str) -> List[str]:
    """The lines a hold's read-back gains for its bound tier-`yes` fills (also used to re-derive it at act time)."""
    rows = store.q("select line from keep_fills where account = ? and hold_id = ? and state = 'bound' and line is not null "
                   "order by created_at", account, hold_id)
    return [r["line"] for r in rows]


def keep_payload(store, account: str, hold_id: str) -> Dict:
    rows = store.q("select item_id from keep_fills where account = ? and hold_id = ? and state = 'bound' and line is not null "
                   "order by created_at", account, hold_id)   # only what the read-back names (a tier-free fill changes nothing)
    return {"keep": [r["item_id"] for r in rows]} if rows else {}


async def keep_use(ctx, inp: dict):
    from . import engine as E
    K = _K()
    E._end_user(ctx, inp["end_user"])
    it = _item(ctx, inp["end_user"], inp["item_id"])
    try:
        K.check_use(it["type"], inp["purpose"])
    except K.Refused as e:
        raise _refused(e)
    token = "kf_" + secrets.token_urlsafe(24)
    th = R.sha256({"keep_token": token})
    if inp["purpose"] == "show":
        dests = ctx.store.q("select * from destinations where account = ? and end_user = ? and verified = 1", ctx.account, inp["end_user"])
        if not dests:
            raise AgapiError("invalid_input", "It's shown only on the person's own verified phone or email; none is verified.",
                             {"path": "/end_user", "rule": "destination_not_verified"})
        ctx.store.x("insert into keep_fills (account, token_hash, item_id, end_user, purpose, hold_id, line, state, expires_at, created_at) "
                    "values (?, ?, ?, ?, 'show', null, null, 'bound', ?, ?)", ctx.account, th, it["id"], inp["end_user"], later(SHOW_TTL_MIN), ts())
        url = f"{config.PUBLIC_URL}/k/{token}"
        d = dests[0]
        ctx.store.x("insert into messages (account, end_user, to_, channel, sent_at, body, approval_link) values (?, ?, ?, ?, ?, ?, ?)",
                    ctx.account, inp["end_user"], d["value"], d["channel"], ts(),
                    f"Your saved {it['masked']} — open to see it (once, {SHOW_TTL_MIN} minutes): {url}", None)
        return {"state": "sent_to_phone", "masked": it["masked"], "channel": d["channel"], "expires_at": later(SHOW_TTL_MIN)}, 200, None
    if not inp.get("hold_id"):
        raise AgapiError("invalid_input", "A saved item is filled into a booking: say which hold (hold_id).", {"path": "/hold_id", "rule": "required"})
    hold = ctx.store.one("select * from holds where account = ? and id = ?", ctx.account, inp["hold_id"])
    intent = hold and ctx.store.one("select * from intents where account = ? and id = ?", ctx.account, hold["intent_id"])
    if not hold or intent["end_user"] != inp["end_user"]:
        raise AgapiError("not_found", "No such hold for this person.", {"hold_id": inp["hold_id"]})
    if intent["state"] != "open":
        raise AgapiError("already_completed", "That booking is already done; a saved item can't be added to it now.", {"act_id": ""})
    if ctx.store.one("select 1 from keep_fills where account = ? and hold_id = ? and item_id = ? and state = 'bound'",
                     ctx.account, hold["id"], it["id"]):
        raise AgapiError("invalid_input", "That item is already set to be filled into this booking.", {"path": "/item_id", "rule": "already_bound"})
    line = K.use_line(it["masked"]) if it["tier"] == K.YES else None
    ctx.store.x("insert into keep_fills (account, token_hash, item_id, end_user, purpose, hold_id, line, state, expires_at, created_at) "
                "values (?, ?, ?, ?, 'fill', ?, ?, 'bound', ?, ?)", ctx.account, th, it["id"], inp["end_user"], hold["id"], line,
                later(FILL_TTL_MIN), ts())
    out = {"fill_token": token, "masked": it["masked"], "tier": it["tier"], "expires_at": later(FILL_TTL_MIN)}
    if line:   # the hold's read-back now NAMES the item: one yes covers the booking and this use; an earlier yes is void
        rb = ctx.store.one("select * from read_backs where account = ? and id = ?", ctx.account, hold["read_back_id"])
        held = loads(hold["items"])
        priced, lines = await E._priced(ctx, held["items"], held["travellers"], at_act=False)
        total = E._total(priced)
        new = E._new_read_back(ctx, intent["id"], "trip.complete", lines + keep_lines(ctx.store, ctx.account, hold["id"]) +
                               E._closing(total, bool(rb["irreversible"])), {**E._payload(priced, total), **keep_payload(ctx.store, ctx.account, hold["id"])},
                               total, inp["end_user"], bool(rb["irreversible"]))
        ctx.store.x("update read_backs set state = 'void' where account = ? and id = ? and state in ('created', 'presented')",
                    ctx.account, rb["id"])
        ctx.store.x("update holds set read_back_id = ? where account = ? and id = ?", new["id"], ctx.account, hold["id"])
        out.update(state="needs_yes", line=line, read_back=E.read_back_out(new))
    else:
        out["state"] = "ready"
    return out, 200, None


async def fill_for_act(store, account: str, hold: dict, apv: Optional[dict], act_id: str, intent_id: str, service: str, up) -> List[dict]:
    """AT THE MOMENT OF USE, inside the act: each bound fill is opened, handed to the provider stand-in, dropped, and proven.
    A tier-`yes` item only under an approval whose read-back named it. Raises (nothing booked) if any can't be filled."""
    from . import engine as E, providers as PV
    K = _K()
    rows = store.q("select * from keep_fills where account = ? and hold_id = ? and state = 'bound' and purpose = 'fill'", account, hold["id"])
    if not rows:
        return []
    rb = store.one("select * from read_backs where account = ? and id = ?", account, hold["read_back_id"])
    approved = loads(rb["lines"]) if apv and apv["read_back_sha256"] == rb["read_back_sha256"] else []
    done = []
    ctx = E.Ctx(store, {"account": account, "key_id": "keep_fill"}, R.new_id("req"), None, None)
    for f in rows:
        it = store.one("select * from keep_items where account = ? and id = ?", account, f["item_id"])
        if not it:
            raise AgapiError("not_found", "A saved item set for this booking was deleted; nothing was booked.", {"item_id": f["item_id"]})
        if f["expires_at"] < ts():
            raise AgapiError("approval_expired", "The saved item's fill expired; use it again for this booking.")
        if it["tier"] == K.YES and f["line"] not in approved:
            raise AgapiError("approval_void", "The yes didn't name this saved item, so it isn't used.", {"void_reason": "keep_not_approved"})
        dek = await _dek(ctx, f["end_user"], create=False)
        try:
            values = K.open_(dek, K.item_aad(account, f["end_user"], it["id"], it["type"]), bytes(it["nonce"]), bytes(it["ciphertext"]))
        except Exception:
            raise AgapiError("upstream_unreachable", "A saved item couldn't be opened; nothing was booked.", {"service": "kms"}) from None
        try:
            got = await PV.send_documents(service, it["type"], values, up)
        finally:
            values = None
        store.x("update keep_fills set state = 'used', used_at = ? where account = ? and token_hash = ?", ts(), account, f["token_hash"])
        store.x("update keep_items set last_used_at = ? where account = ? and id = ?", ts(), account, it["id"])
        outcome = {"kind": "CONFIRMED", "reference": got["reference"],
                   "target_words": R.wrap(got["words"], got["service"], ts()[:19] + "Z")}
        eid = _evidence(ctx, "keep.use", {"item_id": it["id"], "hold_id": hold["id"], "purpose": "fill"}, it, act_id=act_id,
                        intent_id=intent_id, apv=apv if it["tier"] == K.YES else None, outcome=outcome, service=got["service"],
                        reference=got["reference"])
        _event(store, account, f["end_user"], "keep_use", it, eid)
        done.append({"item_id": it["id"], "masked": it["masked"], "evidence_id": eid})
    return done


async def show_value(store, token: str) -> Optional[dict]:
    """/k/{token} POST: the end user's own tap → the value, ONCE. → {masked, values} or None. The page renders it, no-store."""
    K = _K()
    th = R.sha256({"keep_token": token})
    with store.tx():
        f = store.one("select * from keep_fills where token_hash = ? and purpose = 'show' and state = 'bound'", th)
        if f:
            store.x("update keep_fills set state = 'used', used_at = ? where token_hash = ?", ts(), th)
    if not f or f["expires_at"] < ts():
        return None
    it = store.one("select * from keep_items where account = ? and id = ?", f["account"], f["item_id"])
    if not it:
        return None
    from . import engine as E
    ctx = E.Ctx(store, {"account": f["account"], "key_id": "keep_show"}, R.new_id("req"), None, None)
    dek = await _dek(ctx, f["end_user"], create=False)
    values = K.open_(dek, K.item_aad(f["account"], f["end_user"], it["id"], it["type"]), bytes(it["nonce"]), bytes(it["ciphertext"]))
    store.x("update keep_items set last_used_at = ? where account = ? and id = ?", ts(), f["account"], it["id"])
    eid = _evidence(ctx, "keep.use", {"item_id": it["id"], "purpose": "show"}, it)
    _event(store, f["account"], f["end_user"], "keep_show", it, eid)
    return {"masked": it["masked"], "type": it["type"], "values": values}


async def keep_delete(ctx, inp: dict):
    """One item (its ciphertext deleted), or everything (the items AND the person's wrapped key — every value shredded)."""
    from .engine import _end_user
    uid = inp["end_user"]
    _end_user(ctx, uid)
    if inp.get("item_id"):
        it = _item(ctx, uid, inp["item_id"])
        ctx.store.x("delete from keep_fills where account = ? and item_id = ?", ctx.account, it["id"])
        ctx.store.x("delete from keep_items where account = ? and id = ?", ctx.account, it["id"])
        eid = _evidence(ctx, "keep.delete", {"end_user": uid, "item_id": it["id"]}, it)
        _event(ctx.store, ctx.account, uid, "keep_delete", it, eid)
        return {"deleted": 1, "key_destroyed": False, "evidence_id": eid}, 200, eid
    rows = ctx.store.q("select * from keep_items where account = ? and end_user = ?", ctx.account, uid)
    ctx.store.x("delete from keep_fills where account = ? and end_user = ?", ctx.account, uid)
    ctx.store.x("delete from keep_items where account = ? and end_user = ?", ctx.account, uid)
    gone = ctx.store.x("delete from keep_keys where account = ? and end_user = ?", ctx.account, uid)
    marker = {"id": "all", "masked": f"Everything in your Keep ({len(rows)})"}
    eid = _evidence(ctx, "keep.delete", {"end_user": uid, "all": True}, marker)
    _event(ctx.store, ctx.account, uid, "keep_delete", marker, eid)
    return {"deleted": len(rows), "key_destroyed": bool(gone), "evidence_id": eid}, 200, eid


OPS = {"keep.put": keep_put, "keep.list": keep_list, "keep.use": keep_use, "keep.delete": keep_delete}
