"""The 14 v1 operations (operations.json), test mode. Each takes (ctx, input) and returns (result, http_status, evidence_id) or raises
AgapiError. The envelope, auth, limits, validation and idempotency are app.py's; the approval surface (key-less pages) is surface.py's.

The yes is never the caller's: trip.complete / trip.cancel re-derive the payload and read-back from the CURRENT state and check the
Approval in the normative order (rules.decide). An Approval comes only from the end user's tap on the approval link (surface.py) or,
in test mode, sandbox.simulate_approval — never from an API key."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import config, providers as PV, rules as R, webhooks as W
from .registry import AgapiError
from .store import Store, dumps, later, loads, now, parse_ts, ts
from . import keep_ops as KO


class Ctx:
    def __init__(self, store: Store, key: dict, request_id: str, approval_id: Optional[str], idem_key: Optional[str]):
        self.store, self.key, self.account = store, key, key["account"]
        self.request_id, self.approval_id, self.idem_key = request_id, approval_id, idem_key
        self.up = PV.Upstream()
        self.unknown_act: Optional[str] = None           # outcome_unknown keeps the idempotency key in flight on this act
        self.consumed: Optional[str] = None              # an Approval this request consumed (released on a transient failure)


def _strip(o: dict) -> dict:
    return {k: v for k, v in o.items() if not k.startswith("_")}


def _money(m: dict) -> str:
    a = abs(m["amount_minor"])
    return f"{'-' if m['amount_minor'] < 0 else ''}{m['currency']} {a // 100:,}.{a % 100:02d}"


def _token() -> Tuple[str, str]:
    t = secrets.token_urlsafe(32)                  # 256 bits; only its hash is stored
    return t, hashlib.sha256(t.encode()).hexdigest()


# ── Magellan ───────────────────────────────────────────────────────────────────────────────────────────────────────────

async def _find(ctx: Ctx, sources: List[dict], kind: str, key: str, ref_field: str) -> Tuple[dict, int, None]:
    got = R.classify(sources)
    if got[0] == "error":
        failed = next((s for s in sources if not s["ok"] and s["code"] == got[1]), sources[0])
        raise AgapiError(got[1], {"upstream_unreachable": "The search service couldn't be reached; this is not 'no results'.",
                                  "upstream_timeout": "The search service didn't answer in time; this is not 'no results'.",
                                  "upstream_rate_limited": "The search service is rate-limiting us; try again shortly.",
                                  "upstream_failed": "The search service answered with an error; this is not 'no results'.",
                                  "upstream_refused": "The search service refused the question."}[got[1]],
                         {"service": failed["source"]}, retry_after_s=30 if got[1] != "upstream_refused" else None)
    items = [i for s in sources if s["ok"] for i in s.get("items", [])]
    for i in items:
        ctx.store.x("insert or replace into offers (account, ref, kind, data, created_at) values (?, ?, ?, ?, ?)",
                    ctx.account, i[ref_field], kind, dumps(i), ts())
    return {key: [_strip(i) for i in items], "coverage": got[1]}, 200, None


async def find_flights(ctx: Ctx, inp: dict):
    return await _find(ctx, await PV.find_flights(inp, ctx.up), "flight", "offers", "offer_ref")


async def find_stays(ctx: Ctx, inp: dict):
    return await _find(ctx, await PV.find_stays(inp, ctx.up), "stay", "stays", "stay_ref")


async def find_venues(ctx: Ctx, inp: dict):
    return await _find(ctx, await PV.find_venues(inp, ctx.up), "venue", "venues", "venue_ref")


# ── the read-back: built the same way at hold time and at act time (so any change voids the Approval) ────────────────────

def _offer(ctx: Ctx, kind: str, ref: str) -> dict:
    if kind == "flight" and ref in PV.MAGIC:
        return PV.magic_offer(ref)
    row = ctx.store.one("select * from offers where account = ? and ref = ? and kind = ?", ctx.account, ref, kind)
    if not row:
        raise AgapiError("not_found", f"No {kind} with that ref for this account; find it first.", {"ref": ref})
    return loads(row["data"])


async def _priced(ctx: Ctx, items: List[dict], travellers: List[dict], *, at_act: bool) -> Tuple[List[dict], List[dict]]:
    """Each item re-checked at the provider now → (priced items for the payload, lines). Never a silent swap."""
    priced, lines = [], []
    for it in items:
        o = _offer(ctx, it["kind"], it["ref"])
        if it["kind"] == "flight":
            need = len((o.get("_card") or {}).get("passengers") or []) or 1
            if len(travellers) < need:
                raise AgapiError("travellers_missing", "The airline needs each traveller's full name, title and date of birth.",
                                 {"have": len(travellers), "need": need})
            o, checked = await PV.recheck_flight(o, ctx.up, need)
            price = dict(o["price"])
            if at_act and o.get("_magic") == "off_test_price_jump":
                price["amount_minor"] += 1500           # Part 4 §5: the fare moved since the read-back → payload_changed
            who = ", ".join(f"{t['given_name']} {t['family_name']}" for t in travellers[:need])
            d = datetime.fromisoformat(o["departs"])
            lines.append(f"Flight {o['carrier']['name']['text']} {' + '.join(o['flight_numbers'])}, {o['from']} → {o['to']}, "
                         f"{d.strftime('%a %-d %b %Y')}, departs {o['departs'][11:16]}, arrives {o['arrives'][11:16]}, for {who}: "
                         f"{_money(price)}.")
            priced.append({"kind": "flight", "ref": it["ref"], "price": price, "price_source": "quoted", "rechecked_at": checked,
                           "travellers": travellers[:need]})
        elif it["kind"] == "stay":
            if not it.get("at") or not it.get("nights"):
                raise AgapiError("invalid_input", "A stay needs its check-in (at) and nights.", {"path": "/items", "rule": "required"})
            n = o["price_per_night"]
            price = {"amount_minor": n["amount_minor"] * it["nights"], "currency": n["currency"]}
            party = it.get("party") or 1
            lines.append(f"Stay at {o['name']['text']}, {it['nights']} night{'s' if it['nights'] != 1 else ''} from "
                         f"{it['at'][:10]}, party of {party}: {_money(price)}.")
            priced.append({"kind": "stay", "ref": it["ref"], "price": price, "price_source": "quoted", "rechecked_at": ts(),
                           "at": it["at"], "nights": it["nights"], "party": party})
        else:
            if not it.get("at") or not it.get("party"):
                raise AgapiError("invalid_input", "A venue booking needs its time (at) and party.", {"path": "/items", "rule": "required"})
            price = {"amount_minor": 0, "currency": "EUR"}
            d = datetime.fromisoformat(it["at"])
            lines.append(f"Table for {it['party']} at {o['name']['text']}, {d.strftime('%a %-d %b %Y')} at {it['at'][11:16]} "
                         f"(sandbox fixture venue — nothing is sent to a real venue).")
            priced.append({"kind": "venue", "ref": it["ref"], "price": price, "price_source": "quoted", "rechecked_at": ts(),
                           "at": it["at"], "party": it["party"]})
    return priced, lines


def _total(priced: List[dict]) -> dict:
    cur = {p["price"]["currency"] for p in priced}
    if len(cur) > 1:
        raise AgapiError("invalid_input", "One hold is one currency; hold these items separately.", {"path": "/items", "rule": "currency"})
    return {"amount_minor": sum(p["price"]["amount_minor"] for p in priced), "currency": cur.pop()}


def _payload(priced: List[dict], total: dict) -> dict:
    return {"items": [{k: v for k, v in p.items() if k != "rechecked_at"} for p in priced], "total": total}


def _closing(total: dict, irreversible: bool) -> List[str]:
    out = [f"Total {_money(total)}, paid by a payment link on your phone (sandbox: Stripe test)." if total["amount_minor"] > 0
           else "Nothing is charged."]
    if irreversible:
        out.append("Non-refundable: once booked, this can't be undone.")
    return out


def _rb_ttl(irreversible: bool) -> int:
    return config.READ_BACK_TTL_IRREVERSIBLE_MIN if irreversible else config.READ_BACK_TTL_MIN


def read_back_out(rb: dict) -> dict:
    out = {"read_back_id": rb["id"], "intent_id": rb["intent_id"], "account": rb["account"], "operation": rb["operation"],
           "lines": loads(rb["lines"]), "payload_sha256": rb["payload_sha256"], "read_back_sha256": rb["read_back_sha256"],
           "presented_to": rb["presented_to"], "presented_at": rb["presented_at"], "presented_turn_id": rb["presented_turn_id"],
           "presented_via": rb["presented_via"], "expires_at": rb["expires_at"], "irreversible": bool(rb["irreversible"]),
           "state": _rb_state(rb)}
    if rb["total"]:
        out["total"] = loads(rb["total"])
    return out


def _rb_state(rb: dict) -> str:
    if rb["state"] in ("created", "presented") and rb["expires_at"] < ts():
        return "expired"
    return rb["state"]


def _new_read_back(ctx: Ctx, intent_id: str, operation: str, lines: List[str], payload: dict, total: Optional[dict],
                   end_user: str, irreversible: bool) -> dict:
    rid, psha = R.new_id("rb"), R.sha256(payload)
    rsha = R.read_back_sha256(ctx.account, intent_id, operation, lines, psha)
    ctx.store.x("insert into read_backs (account, id, intent_id, operation, lines, payload, payload_sha256, read_back_sha256, total, "
                "presented_to, expires_at, irreversible, state, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'created', ?)",
                ctx.account, rid, intent_id, operation, dumps(lines), dumps(payload), psha, rsha, dumps(total) if total else None,
                end_user, later(_rb_ttl(irreversible)), int(irreversible), ts())
    return ctx.store.one("select * from read_backs where account = ? and id = ?", ctx.account, rid)


# ── Austen ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

def _end_user(ctx: Ctx, uid: str) -> dict:
    u = ctx.store.one("select * from end_users where account = ? and id = ?", ctx.account, uid)
    if not u:
        raise AgapiError("not_found", "No such end user for this account; users.register first.", {"end_user": uid})
    return u


async def trip_hold(ctx: Ctx, inp: dict):
    _end_user(ctx, inp["end_user"])
    travellers = inp.get("travellers") or []
    priced, lines = await _priced(ctx, inp["items"], travellers, at_act=False)
    total = _total(priced)
    irreversible = bool(inp.get("irreversible")) or any(p["kind"] == "flight" for p in priced)
    iid = R.new_id("int")
    ctx.store.x("insert into intents (account, id, operation, end_user, state, created_at) values (?, ?, 'trip.complete', ?, 'open', ?)",
                ctx.account, iid, inp["end_user"], ts())
    rb = _new_read_back(ctx, iid, "trip.complete", lines + _closing(total, irreversible), _payload(priced, total), total,
                        inp["end_user"], irreversible)
    hid = R.new_id("hold")
    expires = min([later(config.HOLD_TTL_MIN)] + [_offer(ctx, p["kind"], p["ref"]).get("expires_at") or later(config.HOLD_TTL_MIN)
                                                   for p in priced if p["kind"] == "flight"])
    ctx.store.x("insert into holds (account, id, intent_id, read_back_id, items, total, expires_at, created_at) values (?, ?, ?, ?, ?, ?, ?, ?)",
                ctx.account, hid, iid, rb["id"], dumps({"items": inp["items"], "travellers": travellers}), dumps(total), expires, ts())
    return ({"hold_id": hid, "intent_id": iid, "read_back": read_back_out(rb),
             "items": [{k: p[k] for k in ("kind", "ref", "price", "price_source", "rechecked_at")} for p in priced],
             "total": total, "expires_at": expires}, 201, None)


_DEST = {"link_sms": "sms", "link_whatsapp": "whatsapp", "link_email": "email"}


async def approvals_request(ctx: Ctx, inp: dict):
    rb = ctx.store.one("select * from read_backs where account = ? and id = ?", ctx.account, inp["read_back_id"])
    if not rb:
        raise AgapiError("not_found", "No such read-back for this account.", {"read_back_id": inp["read_back_id"]})
    it = ctx.store.one("select * from intents where account = ? and id = ?", ctx.account, rb["intent_id"])
    if it["state"] == "confirmed":
        act = ctx.store.one("select id from acts where account = ? and intent_id = ? order by created_at desc", ctx.account, it["id"])
        raise AgapiError("already_completed", "This intent's act is already confirmed.", {"act_id": act["id"] if act else ""})
    if _rb_state(rb) == "expired":
        raise AgapiError("approval_expired", "The read-back expired; hold again for a fresh one.")
    if _rb_state(rb) in ("approved", "void"):
        raise AgapiError("invalid_input", f"That read-back is already {_rb_state(rb)}.", {"path": "/read_back_id", "rule": "state"})
    if inp["channel"] not in _DEST:
        raise AgapiError("invalid_input", "In the sandbox an approval goes by link (SMS, WhatsApp or email); partners' end users tap.",
                         {"path": "/channel", "rule": "sandbox_link_channels_only"})
    dests = ctx.store.q("select * from destinations where account = ? and end_user = ? and channel = ? and verified = 1",
                        ctx.account, rb["presented_to"], _DEST[inp["channel"]])
    want = _norm_dest(inp.get("destination")) if inp.get("destination") else None
    dest = next((d for d in dests if want is None or _norm_dest(d["value"]) == want), None)
    if not dest:
        raise AgapiError("invalid_input", "An approval link is only ever sent to a verified destination of this end user.",
                         {"path": "/destination", "rule": "destination_not_verified"})
    token, h = _token()
    sent, expires = ts(), later(config.LINK_TTL_MIN)
    ctx.store.x("insert into approval_links (token_hash, account, read_back_id, end_user, channel, destination, expires_at, created_at) "
                "values (?, ?, ?, ?, ?, ?, ?, ?)", h, ctx.account, rb["id"], rb["presented_to"], inp["channel"], dest["value"], expires, sent)
    url = f"{config.PUBLIC_URL}/a/{token}"
    ctx.store.x("insert into messages (account, end_user, to_, channel, sent_at, body, approval_link) values (?, ?, ?, ?, ?, ?, ?)",
                ctx.account, rb["presented_to"], dest["value"], _DEST[inp["channel"]], sent,
                f"Please review and approve this request: {url} (single use, expires in {config.LINK_TTL_MIN} minutes).", url)
    return {"read_back_id": rb["id"], "presentation": {"channel": inp["channel"], "sent_at": sent, "link_expires_at": expires}}, 200, None


def _norm_dest(v: str) -> str:
    v = (v or "").strip().lower()
    return v if "@" in v else "+" + "".join(ch for ch in v if ch.isdigit())


def _act_kind(rb: dict) -> Optional[str]:
    """1.1 AP6 act_kind — from the read-back's OWN operation, never from the caller: only a cancellation is 'cancel'."""
    return "cancel" if rb.get("operation") == "trip.cancel" else None


def _approval_case(ctx: Ctx, rb: dict, apv: Optional[dict], current: dict, acts_in_request: int) -> dict:
    a = None
    if apv:
        a = {"account": apv["account"], "intent_id": apv["intent_id"], "read_back_sha256": apv["read_back_sha256"],
             "payload_sha256": apv["payload_sha256"], "method": apv["method"], "approved_by": apv["approved_by"],
             "approved_at": apv["approved_at"], "approved_turn_id": apv["approved_turn_id"], "device": loads(apv["device"]),
             "expires_at": apv["expires_at"], "irreversible": bool(apv["irreversible"]), "state": apv["state"]}
        if apv["said"] is not None:
            a["said"] = apv["said"]
    return {"account": ctx.account, "lang": (apv or {}).get("lang") or "en", "now": ts(), "acts_in_request": acts_in_request,
            "act_kind": _act_kind(rb),
            "read_back": {"presented_to": rb["presented_to"], "presented_at": rb["presented_at"],
                          "presented_turn_id": rb["presented_turn_id"], "expires_at": rb["expires_at"]},
            "approval": a, "current": current}


_DECISION_WORDS = {"approval_not_found": "No such Approval for this account.",
                   "approval_untrusted_origin": "That Approval didn't come from the end user's own device.",
                   "approval_consumed": "That Approval was already used; one Approval authorises one act.",
                   "approval_same_turn": "The yes must come in a later turn, after the read-back was shown.",
                   "no_explicit_yes": "The words given are not an explicit yes.",
                   "approval_expired": "The read-back or the Approval expired; hold again for a fresh yes.",
                   "approval_void": "Something changed since the read-back, so the Approval is void and is never corrected."}


def _check_and_consume(ctx: Ctx, rb: dict, current: dict, acts_in_request: int) -> dict:
    """AP10 (missing) → approval_required; else rules.decide in the normative order; a valid Approval is consumed atomically."""
    if not ctx.approval_id:
        raise AgapiError("approval_required", "This act needs the end user's Approval of the read-back below.",
                         {"read_back_id": rb["id"], "read_back": {"lines": loads(rb["lines"])}})
    apv = ctx.store.one("select * from approvals where account = ? and id = ?", ctx.account, ctx.approval_id)
    decision, why = R.decide(_approval_case(ctx, rb, apv, current, acts_in_request), test_mode=config.MODE == "test")
    if decision == "approval_void":
        ctx.store.x("update approvals set state = 'void', void_reason = ? where account = ? and id = ?", why, ctx.account, apv["id"])
        ctx.store.x("update read_backs set state = 'void' where account = ? and id = ?", ctx.account, rb["id"])
        W.emit(ctx.store, ctx.account, "approval.void", {"intent_id": apv["intent_id"], "read_back_id": rb["id"],
                                                         "approval_id": apv["id"], "void_reason": why})
        raise AgapiError("approval_void", _DECISION_WORDS["approval_void"], {"void_reason": why})
    if decision != "valid":
        raise AgapiError(decision, _DECISION_WORDS[decision])
    if apv["state"] == "void":            # AP2: void is permanent — never revived, never corrected
        raise AgapiError("approval_void", _DECISION_WORDS["approval_void"], {"void_reason": apv["void_reason"] or "superseded"})
    with ctx.store.tx():
        n = ctx.store.x("update approvals set state = 'consumed', consumed_by_request_id = ? where account = ? and id = ? and state = 'valid'",
                        ctx.request_id, ctx.account, apv["id"])
    if n != 1:
        raise AgapiError("approval_consumed", _DECISION_WORDS["approval_consumed"])
    ctx.consumed = apv["id"]
    return apv


def release_approval(store: Store, account: str, approval_id: str) -> None:
    """A transient failure after consuming: nothing happened, so the end user's yes stays usable (Part 1 I7: the key is released)."""
    store.x("update approvals set state = 'valid', consumed_by_request_id = null where account = ? and id = ? and state = 'consumed'",
            account, approval_id)


def _evidence(ctx: Ctx, operation: str, act_id: str, intent_id: str, inp: dict, outcome: dict, apv: Optional[dict],
              sources: List[dict]) -> str:
    eid = R.new_id("evd")
    ev: Dict[str, Any] = {"evidence_id": eid, "basis": "measured", "states_no_conclusion": True, "operation": operation,
                          **({"act_id": act_id} if act_id else {}), **({"intent_id": intent_id} if intent_id else {}),
                          "input_digest": R.sha256(inp),
                          "produced_at": ts()[:19] + "Z", "sources": sources}
    if outcome is not None:
        ev["outcome"] = outcome
    if apv:
        ev["approval"] = {"approval_id": apv["id"], "read_back_sha256": apv["read_back_sha256"], "payload_sha256": apv["payload_sha256"],
                          "approved_at": apv["approved_at"], "method": apv["method"], **({"said": apv["said"]} if apv["said"] else {})}
    ev["body_sha256"] = R.evidence_body_sha256(ev)
    ctx.store.x("insert into evidence (account, id, body, created_at) values (?, ?, ?, ?)", ctx.account, eid, dumps(ev), ts())
    return eid


def _source(res: dict) -> dict:
    s = {"service": res["service"], "retrieved_at": ts()[:19] + "Z", "sha256": res["sha256"]}
    s["snippet"] = R.wrap(res["words"], res["service"], s["retrieved_at"])
    return s


def _confirmed(res: dict) -> dict:
    return {"kind": "CONFIRMED", "reference": res["reference"], "target_words": R.wrap(res["words"], res["service"], ts()[:19] + "Z")}


async def trip_complete(ctx: Ctx, inp: dict):
    hold = ctx.store.one("select * from holds where account = ? and id = ?", ctx.account, inp["hold_id"])
    if not hold:
        raise AgapiError("not_found", "No such hold for this account.", {"hold_id": inp["hold_id"]})
    it = ctx.store.one("select * from intents where account = ? and id = ?", ctx.account, hold["intent_id"])
    if it["state"] == "confirmed":
        act = ctx.store.one("select id from acts where account = ? and intent_id = ? and kind = 'complete' order by created_at desc",
                            ctx.account, it["id"])
        raise AgapiError("already_completed", "This intent's act is already confirmed.", {"act_id": act["id"]})
    rb = ctx.store.one("select * from read_backs where account = ? and id = ?", ctx.account, hold["read_back_id"])
    held = loads(hold["items"])
    method = (inp.get("payment") or {}).get("method")
    # re-derive from the CURRENT state (AP1): a moved price, a gone offer, a changed traveller all void the Approval
    priced, lines = await _priced(ctx, held["items"], held["travellers"], at_act=True)
    total = _total(priced)
    current = {"intent_id": it["id"], "operation": rb["operation"],
               "lines": lines + KO.keep_lines(ctx.store, ctx.account, hold["id"]) + _closing(total, bool(rb["irreversible"])),
               "payload": {**_payload(priced, total), **KO.keep_payload(ctx.store, ctx.account, hold["id"])}}   # CR 63: the Keep's lines
    apv = _check_and_consume(ctx, rb, current, len(priced))
    if hold["expires_at"] < ts():
        release_approval(ctx.store, ctx.account, apv["id"])
        raise AgapiError("hold_expired", "The hold's prices or inventory expired; hold again (a new read-back and Approval follow).")
    if total["amount_minor"] > 0 and method not in (None, "payment_link"):
        raise AgapiError("invalid_input", "payment_link is the only payment method in the sandbox.", {"path": "/payment/method", "rule": "enum"})
    aid, magic = R.new_id("act"), next((p["ref"] for p in priced if p["ref"] in PV.MAGIC), None)
    # the provider's own answer for a forced outcome (Part 4 §5 magic refs) comes first, before any payment page
    if magic in ("off_test_sold_out", "off_test_timeout_before", "off_test_timeout_after"):
        import time as _t
        try:
            PV._magic_act(magic, ctx.up, "duffel", _t.perf_counter())
        except PV._Unknown as u:
            _unknown(ctx, aid, it, hold, inp, apv, u.service, magic)
        except AgapiError as e:
            if e.code == "upstream_refused":
                outcome = {"kind": "REFUSED"}
                _new_act(ctx, aid, it, "complete", hold["id"], outcome)
                eid = _evidence(ctx, "trip.complete", aid, it["id"], inp, outcome, apv, [])
                W.emit(ctx.store, ctx.account, "act.refused", {"intent_id": it["id"], "act_id": aid, "evidence_id": eid, "outcome_kind": "REFUSED"})
            raise
    if total["amount_minor"] > 0:
        token, h = _token()
        outcome = {"kind": "AWAITING_PAYMENT", "payment_url": f"{config.PUBLIC_URL}/pay/{token}"}
        _new_act(ctx, aid, it, "complete", hold["id"], outcome, pay_hash=h)
        eid = _evidence(ctx, "trip.complete", aid, it["id"], inp, outcome, apv, [])
        ctx.store.x("update acts set evidence_id = ? where account = ? and id = ?", eid, ctx.account, aid)
        W.emit(ctx.store, ctx.account, "act.awaiting_payment", {"intent_id": it["id"], "act_id": aid, "evidence_id": eid,
                                                                "outcome_kind": "AWAITING_PAYMENT"})
        return {"act_id": aid, "intent_id": it["id"], "outcome": outcome, "evidence_id": eid}, 201, eid
    try:
        await KO.fill_for_act(ctx.store, ctx.account, hold, apv, aid, it["id"], "sandbox_" + priced[0]["kind"], ctx.up)   # CR 63
        res = await PV.book_fixture(priced[0]["kind"], priced[0], ctx.up) if len(priced) == 1 else await _book_all(ctx, priced)
    except PV._Unknown as u:
        _unknown(ctx, aid, it, hold, inp, apv, u.service, None)
    except AgapiError as e:
        if e.code == "upstream_refused":
            outcome = {"kind": "REFUSED"}
            _new_act(ctx, aid, it, "complete", hold["id"], outcome)
            eid = _evidence(ctx, "trip.complete", aid, it["id"], inp, outcome, apv, [])
            W.emit(ctx.store, ctx.account, "act.refused", {"intent_id": it["id"], "act_id": aid, "evidence_id": eid, "outcome_kind": "REFUSED"})
        raise
    outcome = _confirmed(res)
    _new_act(ctx, aid, it, "complete", hold["id"], outcome)
    eid = _evidence(ctx, "trip.complete", aid, it["id"], inp, outcome, apv, [_source(res)])
    _confirm(ctx.store, ctx.account, aid, it["id"], eid)
    return {"act_id": aid, "intent_id": it["id"], "outcome": outcome, "evidence_id": eid}, 201, eid


def _unknown(ctx: Ctx, aid: str, it: dict, hold: dict, inp: dict, apv: dict, service: str, magic: Optional[str]) -> None:
    """Part 1 R5: the act may have happened but its answer was lost → outcome_unknown; the key stays in flight until status says."""
    outcome = {"kind": "UNKNOWN"}
    _new_act(ctx, aid, it, "complete", hold["id"], outcome, magic=magic)
    eid = _evidence(ctx, "trip.complete", aid, it["id"], inp, outcome, apv, [])
    ctx.store.x("update acts set evidence_id = ? where account = ? and id = ?", eid, ctx.account, aid)
    W.emit(ctx.store, ctx.account, "act.unknown", {"intent_id": it["id"], "act_id": aid, "evidence_id": eid, "outcome_kind": "UNKNOWN"})
    ctx.unknown_act = aid
    raise AgapiError("outcome_unknown", "The provider may have acted but its answer was lost; call acts.status before retrying.",
                     {"act_id": aid, "service": service})


async def _book_all(ctx: Ctx, priced: List[dict]) -> dict:
    got = [await PV.book_fixture(p["kind"], p, ctx.up) for p in priced]
    return {"reference": " · ".join(g["reference"] for g in got), "service": got[0]["service"],
            "words": " ".join(g["words"] for g in got), "sha256": R.sha256([g["sha256"] for g in got])}


def _new_act(ctx: Ctx, aid: str, it: dict, kind: str, hold_id: Optional[str], outcome: dict, pay_hash: Optional[str] = None,
             target: Optional[str] = None, refund: Optional[dict] = None, magic: Optional[str] = None) -> None:
    ctx.store.x("insert into acts (account, id, intent_id, kind, target_act, hold_id, end_user, outcome, refund, pay_token_hash, magic, "
                "created_at, updated_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ctx.account, aid, it["id"], kind, target,
                hold_id, it["end_user"], dumps(outcome), dumps(refund) if refund else None, pay_hash, magic, ts(), ts())


def _confirm(store: Store, account: str, act_id: str, intent_id: str, evidence_id: str) -> None:
    store.x("update acts set evidence_id = ?, updated_at = ? where account = ? and id = ?", evidence_id, ts(), account, act_id)
    store.x("update intents set state = 'confirmed' where account = ? and id = ?", account, intent_id)
    act = store.one("select outcome from acts where account = ? and id = ?", account, act_id)
    W.emit(store, account, "act.confirmed", {"intent_id": intent_id, "act_id": act_id, "evidence_id": evidence_id,
                                             "outcome_kind": "CONFIRMED", "reference": loads(act["outcome"]).get("reference")})


async def pay(store: Store, act: dict) -> dict:
    """The end user paid on the payment link (sandbox: Stripe test, simulated) → the provider act, then Pacioli."""
    ctx = Ctx(store, {"account": act["account"], "key_id": "pay_page"}, R.new_id("req"), None, None)
    hold = store.one("select * from holds where account = ? and id = ?", act["account"], act["hold_id"])
    held = loads(hold["items"])
    priced = [dict(i, price=None) for i in held["items"]]
    flights = [i for i in held["items"] if i["kind"] == "flight"]
    apv = store.one("select * from approvals where account = ? and consumed_by_request_id is not null and intent_id = ? order by approved_at desc",
                    act["account"], act["intent_id"])
    try:
        await KO.fill_for_act(store, act["account"], hold, apv, act["id"], act["intent_id"], "duffel" if flights else "sandbox_" +
                              held["items"][0]["kind"], ctx.up)   # CR 63: at the moment of use, under the booking's yes
        if flights:
            res = await PV.order_flight(_offer(ctx, "flight", flights[0]["ref"]), held["travellers"], ctx.up)
        else:
            res = await PV.book_fixture(priced[0]["kind"], priced[0], ctx.up)
        outcome = _confirmed(res)
        sources = [{"service": "stripe_test", "retrieved_at": ts()[:19] + "Z", "sha256": R.sha256({"paid": act["id"]})}, _source(res)]
    except AgapiError as e:
        outcome = {"kind": "REFUSED" if e.code == "upstream_refused" else "UNREACHABLE" if e.code.startswith("upstream") else "FAILED"}
        sources = []
    store.x("update acts set outcome = ?, pay_token_hash = null, updated_at = ? where account = ? and id = ?", dumps(outcome), ts(),
            act["account"], act["id"])
    eid = _evidence(ctx, "trip.complete", act["id"], act["intent_id"], {"act_id": act["id"], "payment": {"method": "payment_link"}},
                    outcome, apv, sources)
    if outcome["kind"] == "CONFIRMED":
        _confirm(store, act["account"], act["id"], act["intent_id"], eid)
    else:
        store.x("update acts set evidence_id = ? where account = ? and id = ?", eid, act["account"], act["id"])
        W.emit(store, act["account"], "act." + {"REFUSED": "refused", "UNREACHABLE": "failed", "FAILED": "failed"}[outcome["kind"]],
               {"intent_id": act["intent_id"], "act_id": act["id"], "evidence_id": eid, "outcome_kind": outcome["kind"]})
    return outcome


async def trip_cancel(ctx: Ctx, inp: dict):
    act = ctx.store.one("select * from acts where account = ? and id = ? and kind = 'complete'", ctx.account, inp["act_id"])
    if not act:
        raise AgapiError("not_found", "No such act for this account.", {"act_id": inp["act_id"]})
    done = ctx.store.one("select a.id from acts a join intents i on i.account = a.account and i.id = a.intent_id where a.account = ? "
                         "and a.kind = 'cancel' and a.target_act = ? and i.state = 'confirmed'", ctx.account, act["id"])
    if done:
        raise AgapiError("already_completed", "That act is already cancelled.", {"act_id": done["id"]})
    kind = loads(act["outcome"])["kind"]
    if kind not in ("CONFIRMED", "AWAITING_PAYMENT"):
        raise AgapiError("not_cancellable", f"An act that is {kind} can't be cancelled.")
    paid = kind == "CONFIRMED" and loads(ctx.store.one("select total from holds where account = ? and id = ?", ctx.account, act["hold_id"])["total"])
    refund = paid if paid and paid["amount_minor"] > 0 else {"amount_minor": 0, "currency": "EUR"}
    original = loads(ctx.store.one("select lines from read_backs r join holds h on h.account = r.account and h.read_back_id = r.id "
                                   "where h.account = ? and h.id = ?", ctx.account, act["hold_id"])["lines"])
    lines = [f"Cancel: {original[0]}", f"Refund {_money(refund)} (sandbox: Stripe test)." if refund["amount_minor"] else
             "Nothing was charged, so nothing is refunded."]
    payload = {"act_id": act["id"], "refund": refund}
    it = ctx.store.one("select * from intents where account = ? and target_act = ? and state = 'open' order by created_at desc",
                       ctx.account, act["id"])
    rb = it and ctx.store.one("select * from read_backs where account = ? and intent_id = ? order by created_at desc", ctx.account, it["id"])
    if not rb or _rb_state(rb) in ("expired", "void"):
        iid = R.new_id("int")
        ctx.store.x("insert into intents (account, id, operation, end_user, target_act, state, created_at) "
                    "values (?, ?, 'trip.cancel', ?, ?, 'open', ?)", ctx.account, iid, act["end_user"], act["id"], ts())
        it = ctx.store.one("select * from intents where account = ? and id = ?", ctx.account, iid)
        rb = _new_read_back(ctx, iid, "trip.cancel", lines, payload, refund, act["end_user"], True)
    current = {"intent_id": it["id"], "operation": "trip.cancel", "lines": lines, "payload": payload}
    apv = _check_and_consume(ctx, rb, current, 1)
    cid = R.new_id("act")
    try:
        res = await PV.cancel_fixture("duffel" if "Flight" in original[0] else "sandbox_venue", act["id"], ctx.up)
    except PV._Unknown as u:
        _unknown(ctx, cid, it, {"id": None}, inp, apv, u.service, None)
    outcome = _confirmed(res)
    _new_act(ctx, cid, it, "cancel", None, outcome, target=act["id"], refund=refund)
    if kind == "AWAITING_PAYMENT":
        ctx.store.x("update acts set pay_token_hash = null where account = ? and id = ?", ctx.account, act["id"])
    eid = _evidence(ctx, "trip.cancel", cid, it["id"], inp, outcome, apv, [_source(res)])
    ctx.store.x("update acts set evidence_id = ? where account = ? and id = ?", eid, ctx.account, cid)
    ctx.store.x("update intents set state = 'confirmed' where account = ? and id = ?", ctx.account, it["id"])
    W.emit(ctx.store, ctx.account, "act.cancelled", {"intent_id": act["intent_id"], "act_id": act["id"], "evidence_id": eid,
                                                     "reference": res["reference"]})
    return {"act_id": cid, "outcome": outcome, "refund": refund, "evidence_id": eid}, 201, eid


# ── Pacioli ────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def acts_status(ctx: Ctx, inp: dict):
    if inp.get("act_id"):
        rows = ctx.store.q("select * from acts where account = ? and id = ?", ctx.account, inp["act_id"])
    elif inp.get("intent_id"):
        rows = ctx.store.q("select * from acts where account = ? and intent_id = ?", ctx.account, inp["intent_id"])
    else:
        rows = ctx.store.q("select * from acts where account = ? order by created_at desc limit 50", ctx.account)
    if (inp.get("act_id") or inp.get("intent_id")) and not rows:
        raise AgapiError("not_found", "No act for that id on this account.")
    for r in rows:
        if loads(r["outcome"])["kind"] == "UNKNOWN":
            resolve_unknown(ctx, r)
    rows = [ctx.store.one("select * from acts where account = ? and id = ?", ctx.account, r["id"]) for r in rows]
    return {"acts": [{"act_id": r["id"], "intent_id": r["intent_id"], "outcome": loads(r["outcome"]), "updated_at": r["updated_at"],
                      **({"evidence_id": r["evidence_id"]} if r["evidence_id"] else {})}   # CR 59 (finding 4): the latest proof
                     for r in rows],
            "coverage": {"complete": True, "answered": ["agapi_ledger"], "unavailable": []}}, 200, None


def resolve_unknown(ctx: Ctx, act: dict) -> None:
    """Part 1 I8: the provider is asked; the act's real outcome is recorded and the in-flight idempotency key resolves to it."""
    res = PV.resolve_unknown("duffel")
    outcome = _confirmed(res)
    ctx.store.x("update acts set outcome = ?, updated_at = ? where account = ? and id = ?", dumps(outcome), ts(), ctx.account, act["id"])
    apv = ctx.store.one("select * from approvals where account = ? and intent_id = ? and state = 'consumed' order by approved_at desc",
                        ctx.account, act["intent_id"])
    eid = _evidence(ctx, "trip.complete", act["id"], act["intent_id"], {"act_id": act["id"], "resolved_by": "acts.status"},
                    outcome, apv, [_source(res)])
    _confirm(ctx.store, ctx.account, act["id"], act["intent_id"], eid)
    body = {"ok": True, "result": {"act_id": act["id"], "intent_id": act["intent_id"], "outcome": outcome, "evidence_id": eid},
            "evidence_id": eid}
    ctx.store.x("update idempotency set state = 'done', status = 201, response = ? where account = ? and act_id = ? and state = 'in_flight'",
                dumps(body), ctx.account, act["id"])


async def evidence_get(ctx: Ctx, inp: dict):
    e = ctx.store.one("select body from evidence where account = ? and id = ?", ctx.account, inp["evidence_id"])
    if not e:
        raise AgapiError("not_found", "No such evidence for this account.")
    return loads(e["body"]), 200, None


async def evidence_verify(ctx: Ctx, inp: dict):
    ev = inp["evidence"]
    got = R.evidence_body_sha256(ev)
    ok = hmac.compare_digest(got, ev["body_sha256"])
    return {"valid": ok, "recomputed_body_sha256": got, **({} if ok else {"reason": "body_sha256 does not match the evidence"})}, 200, None


# ── product (Part 4) ───────────────────────────────────────────────────────────────────────────────────────────────────

import re as _re

_SANDBOX_PHONE = _re.compile(r"^\+15005550\d{3}$")
_SANDBOX_EMAIL = _re.compile(r"^[^@\s]+@example\.test$")


def _otp_hmac(code: str) -> str:
    return hmac.new(config.pepper(), code.encode(), hashlib.sha256).hexdigest()


async def users_register(ctx: Ctx, inp: dict):
    u = ctx.store.one("select * from end_users where account = ? and external_ref = ?", ctx.account, inp["external_ref"])
    status = 200
    if not u:
        uid = R.new_id("usr")
        ctx.store.x("insert into end_users (account, id, external_ref, created_at) values (?, ?, ?, ?)", ctx.account, uid,
                    inp["external_ref"], ts())
        u, status = ctx.store.one("select * from end_users where account = ? and id = ?", ctx.account, uid), 201
    for d in inp.get("destinations") or []:
        v = _norm_dest(d["value"])
        ok = _SANDBOX_EMAIL.match(v) if d["channel"] == "email" else _SANDBOX_PHONE.match(v)
        if not ok:
            raise AgapiError("invalid_input", "The sandbox accepts sandbox destinations only: +1 500 555 0xxx numbers or …@example.test.",
                             {"path": "/destinations", "rule": "sandbox_destinations_only"})
        if ctx.store.one("select 1 from destinations where account = ? and end_user = ? and channel = ? and value = ?",
                         ctx.account, u["id"], d["channel"], v):
            continue
        code, (token, th) = f"{secrets.randbelow(10**6):06d}", _token()
        ctx.store.x("insert into destinations (account, end_user, channel, value, verified, otp_hmac, otp_expires_at, verify_token_hash, "
                    "created_at) values (?, ?, ?, ?, 0, ?, ?, ?, ?)", ctx.account, u["id"], d["channel"], v, _otp_hmac(code),
                    later(config.OTP_TTL_MIN), th, ts())
        url = f"{config.PUBLIC_URL}/v/{token}"
        ctx.store.x("insert into messages (account, end_user, to_, channel, sent_at, body, approval_link) values (?, ?, ?, ?, ?, ?, ?)",
                    ctx.account, u["id"], v, d["channel"], ts(),
                    f"Your Kanoe verification code is {code}. Enter it at {url} (expires in {config.OTP_TTL_MIN} minutes).", None)
    return end_user_out(ctx.store, ctx.account, u["id"]), status, None


def end_user_out(store: Store, account: str, uid: str) -> dict:
    u = store.one("select * from end_users where account = ? and id = ?", account, uid)
    ds = store.q("select channel, value, verified from destinations where account = ? and end_user = ? order by created_at", account, uid)
    return {"end_user_id": u["id"], "account": account, "external_ref": u["external_ref"],
            "destinations": [{"channel": d["channel"], "value": d["value"], "verified": bool(d["verified"])} for d in ds],
            "created_at": u["created_at"]}


async def usage_get(ctx: Ctx, inp: dict):
    rows = ctx.store.q("select operation, count(*) as calls, sum(cost_units) as units from usage_records where account = ? and at >= ? "
                       "and at <= ? group by operation order by operation", ctx.account, inp["from"], inp["to"])
    total = sum(r["units"] or 0 for r in rows)
    return {"account": ctx.account, "from": inp["from"], "to": inp["to"],
            "by_operation": [{"operation": r["operation"], "calls": r["calls"], "cost_units": r["units"] or 0} for r in rows],
            "total_cost_units": total, "budget_remaining": budget_remaining(ctx.store, ctx.key)}, 200, None


def budget_remaining(store: Store, key: dict) -> int:
    month = ts()[:7]
    used = store.one("select coalesce(sum(cost_units), 0) as u from usage_records where key_id = ? and substr(at, 1, 7) = ?",
                     key["key_id"], month)["u"]
    return int(key["budget_units"]) - int(used)


async def sandbox_simulate_approval(ctx: Ctx, inp: dict):
    """TEST ONLY: the end user's yes on a sandbox destination, after a simulated SEPARATE turn (AP3); AP6 applied to `said`."""
    rb = ctx.store.one("select * from read_backs where account = ? and id = ?", ctx.account, inp["read_back_id"])
    if not rb:
        raise AgapiError("not_found", "No such read-back for this account.")
    if _rb_state(rb) == "expired":
        raise AgapiError("approval_expired", _DECISION_WORDS["approval_expired"])
    if _rb_state(rb) in ("approved", "void"):
        raise AgapiError("approval_same_turn" if _rb_state(rb) == "approved" else "approval_expired",
                         "That read-back has already been answered; hold again for a fresh one.")
    yes, lang = R.explicit_yes_any(inp["said"], _act_kind(rb))   # 1.1: a cancellation's own yes may say "cancel"
    if not yes:
        raise AgapiError("no_explicit_yes", _DECISION_WORDS["no_explicit_yes"])
    after = int(inp.get("after_seconds") or 2)
    now_ = now()
    if not rb["presented_at"]:
        presented = now_ - timedelta(seconds=after)
        ctx.store.x("update read_backs set presented_at = ?, presented_turn_id = ?, presented_via = 'link', state = 'presented', "
                    "expires_at = ? where account = ? and id = ?", ts(presented), R.new_id("trn"),
                    ts(presented + timedelta(minutes=_rb_ttl(bool(rb["irreversible"])))), ctx.account, rb["id"])
        rb = ctx.store.one("select * from read_backs where account = ? and id = ?", ctx.account, rb["id"])
    approved_at = ts(now_)
    if not approved_at > rb["presented_at"]:
        raise AgapiError("approval_same_turn", _DECISION_WORDS["approval_same_turn"])
    apv_id = _create_approval(ctx.store, ctx.account, rb, method="voice", said=inp["said"], lang=lang,
                              device={"channel": "sandbox_simulated"}, approved_at=approved_at)
    ctx.store.x("update approval_links set used_at = ?, outcome = 'simulated' where account = ? and read_back_id = ? and used_at is null",
                ts(), ctx.account, rb["id"])
    return {"approval_id": apv_id, "state": "valid", "decision": "yes"}, 201, None


def _create_approval(store: Store, account: str, rb: dict, *, method: str, said: Optional[str], lang: Optional[str],
                     device: dict, approved_at: str) -> str:
    """The ONLY writer of an Approval — called by the approval surface (a tap) and sandbox.simulate_approval. Never by an API key."""
    aid = R.new_id("apv")
    store.x("insert into approvals (account, id, read_back_id, intent_id, read_back_sha256, payload_sha256, method, said, lang, approved_by, "
            "approved_at, approved_turn_id, device, expires_at, irreversible, state) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'valid')",
            account, aid, rb["id"], rb["intent_id"], rb["read_back_sha256"], rb["payload_sha256"], method, said, lang, rb["presented_to"],
            approved_at, R.new_id("trn"), dumps(device), ts(parse_ts(approved_at) + timedelta(minutes=config.APPROVAL_TTL_MIN)),
            rb["irreversible"])
    store.x("update read_backs set state = 'approved' where account = ? and id = ?", account, rb["id"])
    W.emit(store, account, "approval.given", {"intent_id": rb["intent_id"], "read_back_id": rb["id"], "approval_id": aid})
    return aid


async def sandbox_messages(ctx: Ctx, inp: dict):
    sql, args = "select * from messages where account = ?", [ctx.account]
    if inp.get("end_user_id"):
        sql, args = sql + " and end_user = ?", args + [inp["end_user_id"]]
    if inp.get("since"):
        sql, args = sql + " and sent_at >= ?", args + [inp["since"]]
    rows = ctx.store.q(sql + " order by sent_at", *args)
    return {"messages": [{"to": r["to_"], "channel": r["channel"], "sent_at": r["sent_at"], "body": r["body"],
                          **({"approval_link": r["approval_link"]} if r["approval_link"] else {})} for r in rows]}, 200, None


# ── CR 59 · sandbox extensions (spec/ext): additive, proposed to EU ─────────────────────────────────────────────────────

async def approvals_status(ctx: Ctx, inp: dict):
    """Finding 3: after a real tap, the partner learns the Approval (its id and state) without a webhook endpoint."""
    rb = ctx.store.one("select * from read_backs where account = ? and id = ?", ctx.account, inp["read_back_id"])
    if not rb:
        raise AgapiError("not_found", "No such read-back for this account.")
    a = ctx.store.one("select * from approvals where account = ? and read_back_id = ? order by approved_at desc", ctx.account, rb["id"])
    apv = None
    if a:
        state = a["state"]
        if state == "valid" and a["expires_at"] < ts():
            state = "expired"
        apv = {"approval_id": a["id"], "state": state, "approved_at": a["approved_at"], "method": a["method"],
               "expires_at": a["expires_at"], "void_reason": a["void_reason"]}
    return {"read_back_id": rb["id"], "read_back_state": _rb_state(rb), "presented_at": rb["presented_at"], "approval": apv}, 200, None


async def webhooks_register(ctx: Ctx, inp: dict):
    """v1.0 (EU 205): the partner registers its own endpoint; the whsec_ secret is in this response only. At most 2 active."""
    if len(ctx.store.q("select id from webhook_endpoints where account = ? and state = 'active'", ctx.account)) >= 2:
        raise AgapiError("webhook_limit_reached", "This account already has 2 active webhook endpoints; revoke one first.")
    try:
        eid, secret = W.add_endpoint(ctx.store, ctx.account, inp["url"], inp.get("events"))
    except ValueError as e:
        raise AgapiError("webhook_url_refused", f"{str(e).capitalize()}.")
    row = ctx.store.one("select * from webhook_endpoints where account = ? and id = ?", ctx.account, eid)
    out = {"endpoint_id": eid, "url": row["url"], "secret": secret, "created_at": row["created_at"]}
    if inp.get("events"):
        out["events"] = inp["events"]
    return out, 201, None


async def webhooks_revoke(ctx: Ctx, inp: dict):
    row = ctx.store.one("select * from webhook_endpoints where account = ? and id = ? and state = 'active'", ctx.account, inp["endpoint_id"])
    if not row:
        raise AgapiError("not_found", "No active webhook endpoint with that id for this account.")
    at = ts()
    ctx.store.x("update webhook_endpoints set state = 'revoked' where account = ? and id = ?", ctx.account, row["id"])
    ctx.store.x("update webhook_deliveries set state = 'failed' where account = ? and endpoint_id = ? and state = 'pending'", ctx.account, row["id"])
    return {"endpoint_id": row["id"], "revoked_at": at}, 200, None


async def users_verify_destination(ctx: Ctx, inp: dict):
    """Finding 5: the end user's one-time code, relayed by the partner's own app (the key-less /v/{token} page stays)."""
    _end_user(ctx, inp["end_user_id"])
    v = _norm_dest(inp["value"])
    d = ctx.store.one("select * from destinations where account = ? and end_user = ? and channel = ? and value = ?",
                      ctx.account, inp["end_user_id"], inp["channel"], v)
    if not d:
        raise AgapiError("not_found", "No such destination for this end user; users.register it first.")
    if not d["verified"]:
        if d["attempts"] >= 5 or (d["otp_expires_at"] or "") < ts():
            raise AgapiError("destination_code_expired", "That code has expired or its attempts are used up; register the destination again.")
        if not hmac.compare_digest(d["otp_hmac"] or "", _otp_hmac(inp["code"])):
            ctx.store.x("update destinations set attempts = attempts + 1 where account = ? and end_user = ? and channel = ? and value = ?",
                        ctx.account, inp["end_user_id"], inp["channel"], v)
            raise AgapiError("destination_code_invalid", "That code isn't right.", {"attempts_remaining": max(0, 4 - d["attempts"])})
        ctx.store.x("update destinations set verified = 1, otp_hmac = null where account = ? and end_user = ? and channel = ? and value = ?",
                    ctx.account, inp["end_user_id"], inp["channel"], v)
    return end_user_out(ctx.store, ctx.account, inp["end_user_id"]), 200, None


# ── CR 60 · S2's first powers (the logic is backend/agapi/powers.py — the same module Sasha's tools use) ─────────────────

def _powers():
    from agapi import powers as P
    return P


async def messages_send_email(ctx: Ctx, inp: dict):
    """From Sasha's own address to one person the user names. No Approval → approval_required with the exact message to show;
    with the end user's Approval of exactly that message → sent once (test mode: captured, never sent) → Evidence."""
    P = _powers()
    _end_user(ctx, inp["end_user"])
    try:
        msg = P.email_message(config.EMAIL_FROM, inp["to"]["address"], inp["to"].get("name"), inp["subject"], inp["body"])
    except P.Refused as e:
        raise AgapiError("invalid_input", e.message, {"path": e.path, "rule": e.rule})
    lines, psha = P.email_read_back(msg), R.sha256(msg)
    rb = ctx.store.one("select r.* from read_backs r join intents i on i.account = r.account and i.id = r.intent_id where r.account = ? "
                       "and i.operation = 'messages.send_email' and i.state = 'open' and i.end_user = ? and r.payload_sha256 = ? "
                       "order by r.created_at desc", ctx.account, inp["end_user"], psha)
    if not rb or _rb_state(rb) in ("expired", "void"):
        iid = R.new_id("int")
        ctx.store.x("insert into intents (account, id, operation, end_user, state, created_at) values (?, ?, 'messages.send_email', ?, 'open', ?)",
                    ctx.account, iid, inp["end_user"], ts())
        rb = _new_read_back(ctx, iid, "messages.send_email", lines, msg, None, inp["end_user"], True)   # an email can't be unsent
    it = ctx.store.one("select * from intents where account = ? and id = ?", ctx.account, rb["intent_id"])
    apv = _check_and_consume(ctx, rb, {"intent_id": it["id"], "operation": "messages.send_email", "lines": lines, "payload": msg}, 1)
    aid, sent_at = R.new_id("act"), ts()
    provider_id = "sbx_msg_" + secrets.token_hex(10)
    reply_to = f"reply+{aid.lower()}@{config.REPLY_DOMAIN}"
    ctx.store.x("insert into messages (account, end_user, to_, channel, sent_at, body, approval_link) values (?, ?, ?, 'email', ?, ?, ?)",
                ctx.account, None, msg["to"]["address"], sent_at,
                f"From: {msg['from']}\nReply-To: {reply_to}\nSubject: {msg['subject']}\n\n{msg['body']}", None)
    ctx.up.add("email_provider_sandbox", __import__("time").perf_counter(), True)
    words = "Accepted for delivery by the mail service (sandbox: captured, never sent)."
    retrieved = sent_at[:19] + "Z"
    outcome = {"kind": "CONFIRMED", "reference": provider_id, "target_words": R.wrap(words, "email_provider_sandbox", retrieved)}
    _new_act(ctx, aid, it, "email", None, outcome)
    body_sha = P.email_body_sha256(msg)
    eid = _evidence(ctx, "messages.send_email", aid, it["id"], inp, outcome, apv,
                    [{"service": "email_provider_sandbox", "retrieved_at": retrieved, "sha256": body_sha,
                      "snippet": R.wrap(f"Message {provider_id} · subject: {msg['subject']}", "email_provider_sandbox", retrieved)}])
    _confirm(ctx.store, ctx.account, aid, it["id"], eid)
    to = {"address": R.wrap(msg["to"]["address"], "user_named", retrieved, cap=254)}
    if msg["to"].get("name"):
        to["name"] = R.wrap(msg["to"]["name"], "user_named", retrieved, cap=300)
    return {"act_id": aid, "intent_id": it["id"], "outcome": outcome, "evidence_id": eid,
            "message": {"from": msg["from"], "to": to, "subject": msg["subject"], "body_sha256": body_sha, "sent_at": sent_at}}, 201, eid


async def calendar_add_event(ctx: Ctx, inp: dict):
    """A CONFIRMED act as a calendar event: an .ics + "Add to calendar" links. Free and Approval-less: nothing leaves the account."""
    P = _powers()
    act = ctx.store.one("select * from acts where account = ? and id = ? and kind = 'complete'", ctx.account, inp["act_id"])
    if not act:
        raise AgapiError("not_found", "No such booking for this account.", {"act_id": inp["act_id"]})
    out = loads(act["outcome"])
    if out["kind"] != "CONFIRMED":
        raise AgapiError("invalid_input", f"Only a confirmed booking goes in the calendar; this one is {out['kind']}.",
                         {"path": "/act_id", "rule": "act_not_confirmed"})
    held = loads(ctx.store.one("select items from holds where account = ? and id = ?", ctx.account, act["hold_id"])["items"])
    it, uid, ref = held["items"][0], f"{act['id'].lower()}@agapi.kanoe", out.get("reference")
    o = _offer(ctx, it["kind"], it["ref"])
    try:
        if it["kind"] == "flight":
            ev = P.event_for_flight(uid, o["carrier"]["name"]["text"], o["flight_numbers"], o["from"], o["to"], o["departs"], o["arrives"], ref)
        elif it["kind"] == "venue":
            ev = P.event_for_table(uid, o["name"]["text"], (o.get("address") or {}).get("text"), it["at"], it["party"], ref)
        else:
            ev = P.event_for_stay(uid, o["name"]["text"], (o.get("area") or {}).get("text"), it["at"], it["nights"], ref)
    except P.Refused as e:
        raise AgapiError("invalid_input", e.message, {"path": e.path, "rule": e.rule})
    dtstamp = act["updated_at"][:19].replace("-", "").replace(":", "") + "Z"
    text, esha = P.ics(ev, dtstamp), P.sha256(ev)
    token, th = _token()
    ctx.store.x("insert into calendar_files (token_hash, account, act_id, ics, created_at) values (?, ?, ?, ?, ?)",
                th, ctx.account, act["id"], text, ts())
    url = f"{config.PUBLIC_URL}/ics/{token}.ics"
    retrieved = ts()[:19] + "Z"
    eid = _evidence(ctx, "calendar.add_event", act["id"], act["intent_id"], inp, None, None,
                    [{"service": "agapi_calendar", "retrieved_at": retrieved, "sha256": esha}])
    return {"event": ev, "event_sha256": esha, "ics": text, "links": P.calendar_links(ev, url), "evidence_id": eid}, 200, eid


# ── CR 62 · WhatsApp to someone the user names, and the Activity view ─────────────────────────────────────────────────────

_STOP_RE = __import__("re").compile(r"^\s*(stop|parar|baja|unsubscribe|arr[eê]t)\s*[.!]?\s*$", __import__("re").I)


async def messages_send_whatsapp(ctx: Ctx, inp: dict):
    """From Sasha's number to one person the user names. Inside WhatsApp's 24-hour window (they wrote to Sasha): the user's
    own words. Outside it: ONLY the approved first-contact template, which asks them whether they want the message (needs
    `on_behalf_of`); the user's note waits for their reply and a new yes. A STOP is final. Approval as for email."""
    P = _powers()
    _end_user(ctx, inp["end_user"])
    try:
        number = P._phone(inp["to"]["number"])
    except P.Refused as e:
        raise AgapiError("invalid_input", e.message, {"path": e.path, "rule": e.rule})
    c = ctx.store.one("select * from wa_contacts where account = ? and number = ?", ctx.account, number)
    if c and c["opted_out_at"]:
        raise AgapiError("invalid_input", "They asked Sasha not to write again (they replied STOP). Nothing was sent.",
                         {"path": "/to/number", "rule": "recipient_opted_out"})
    now = ts()
    free = bool(c) and P.window_open(c["last_inbound_at"], now)
    try:
        if free:
            if not inp.get("text"):
                raise P.Refused("/text", "text", "Their window is open: send your own words (text).")
            msg = P.whatsapp_message(config.WA_FROM, number, inp["to"].get("name"), text=inp["text"])
        else:
            if not inp.get("on_behalf_of"):
                raise AgapiError("invalid_input", P.NO_FREE_TEXT, {"path": "/on_behalf_of", "rule": "whatsapp_first_contact",
                                                                    "template": P.ON_BEHALF["name"], "template_body": P.ON_BEHALF["body"]})
            msg = P.whatsapp_message(config.WA_FROM, number, inp["to"].get("name"), template=P.ON_BEHALF["name"],
                                     on_behalf_of=inp["on_behalf_of"])
    except P.Refused as e:
        raise AgapiError("invalid_input", e.message, {"path": e.path, "rule": e.rule})
    lines, psha = P.whatsapp_read_back(msg), R.sha256(msg)
    rb = ctx.store.one("select r.* from read_backs r join intents i on i.account = r.account and i.id = r.intent_id where r.account = ? "
                       "and i.operation = 'messages.send_whatsapp' and i.state = 'open' and i.end_user = ? and r.payload_sha256 = ? "
                       "order by r.created_at desc", ctx.account, inp["end_user"], psha)
    if not rb or _rb_state(rb) in ("expired", "void"):
        iid = R.new_id("int")
        ctx.store.x("insert into intents (account, id, operation, end_user, state, created_at) values (?, ?, 'messages.send_whatsapp', ?, 'open', ?)",
                    ctx.account, iid, inp["end_user"], ts())
        rb = _new_read_back(ctx, iid, "messages.send_whatsapp", lines, msg, None, inp["end_user"], True)   # can't be unsent
    it = ctx.store.one("select * from intents where account = ? and id = ?", ctx.account, rb["intent_id"])
    apv = _check_and_consume(ctx, rb, {"intent_id": it["id"], "operation": "messages.send_whatsapp", "lines": lines, "payload": msg}, 1)
    aid, sent_at = R.new_id("act"), ts()
    provider_id = "sbx_wamid_" + secrets.token_hex(12)
    ctx.store.x("insert into messages (account, end_user, to_, channel, sent_at, body, approval_link) values (?, ?, ?, 'whatsapp', ?, ?, ?)",
                ctx.account, None, number, sent_at, msg["text"], None)
    if c:
        ctx.store.x("update wa_contacts set name = coalesce(?, name) where account = ? and number = ?", msg["to"].get("name"), ctx.account, number)
    else:
        ctx.store.x("insert into wa_contacts (account, number, end_user, name, first_contact_at) values (?, ?, ?, ?, ?)",
                    ctx.account, number, inp["end_user"], msg["to"].get("name"), sent_at)
    ctx.up.add("whatsapp_provider_sandbox", __import__("time").perf_counter(), True)
    retrieved = sent_at[:19] + "Z"
    words = "Accepted by WhatsApp's provider (sandbox: captured, never sent)."
    outcome = {"kind": "CONFIRMED", "reference": provider_id, "target_words": R.wrap(words, "whatsapp_provider_sandbox", retrieved)}
    _new_act(ctx, aid, it, "whatsapp", None, outcome, target=number)   # target_act = the recipient's number for a WhatsApp act
    body_sha = P.whatsapp_body_sha256(msg)
    snippet = f"Message {provider_id}" + (f" · template {msg['template']['name']}" if msg["kind"] == "template" else " · free text")
    eid = _evidence(ctx, "messages.send_whatsapp", aid, it["id"], inp, outcome, apv,
                    [{"service": "whatsapp_provider_sandbox", "retrieved_at": retrieved, "sha256": body_sha,
                      "snippet": R.wrap(snippet, "whatsapp_provider_sandbox", retrieved)}])
    _confirm(ctx.store, ctx.account, aid, it["id"], eid)
    to = {"number": R.wrap(number, "user_named", retrieved, cap=20)}
    if msg["to"].get("name"):
        to["name"] = R.wrap(msg["to"]["name"], "user_named", retrieved, cap=300)
    out = {"from": msg["from"], "to": to, "kind": msg["kind"], "body_sha256": body_sha, "sent_at": sent_at}
    if msg["kind"] == "template":
        out["template"] = msg["template"]["name"]
    return {"act_id": aid, "intent_id": it["id"], "outcome": outcome, "evidence_id": eid, "message": out}, 201, eid


def _replies(ctx: Ctx, end_user: str, number: Optional[str] = None) -> List[dict]:
    sql = ("select r.*, c.name from wa_replies r join wa_contacts c on c.account = r.account and c.number = r.number "
           "where r.account = ? and c.end_user = ?")
    args = [ctx.account, end_user]
    if number:
        sql, args = sql + " and r.number = ?", args + [number]
    return ctx.store.q(sql + " order by r.received_at desc limit 100", *args)


async def messages_replies(ctx: Ctx, inp: dict):
    """What the people the user messaged wrote back — THEIR words, as untrusted text (data, never instructions)."""
    _end_user(ctx, inp["end_user"])
    number = None
    if inp.get("number"):
        try:
            number = _powers()._phone(inp["number"])
        except Exception as e:
            raise AgapiError("invalid_input", getattr(e, "message", str(e)), {"path": "/number", "rule": "e164"})
    out = []
    for r in _replies(ctx, inp["end_user"], number):
        at = r["received_at"][:19] + "Z"
        frm = {"number": R.wrap(r["number"], "whatsapp_recipient", at, cap=20)}
        if r["name"]:
            frm["name"] = R.wrap(r["name"], "user_named", at, cap=300)
        out.append({"reply_id": r["id"], "from": frm, "text": R.wrap(r["body"], "whatsapp_recipient", at), "received_at": r["received_at"]})
    return {"replies": out}, 200, None


async def sandbox_simulate_reply(ctx: Ctx, inp: dict):
    """Test mode: the person Sasha wrote to answers on WhatsApp. Opens their 24-hour window; STOP is final."""
    try:
        number = _powers()._phone(inp["number"])
    except Exception as e:
        raise AgapiError("invalid_input", getattr(e, "message", str(e)), {"path": "/number", "rule": "e164"})
    c = ctx.store.one("select * from wa_contacts where account = ? and number = ?", ctx.account, number)
    if not c:   # 1.1 lists invalid_input for this operation
        raise AgapiError("invalid_input", "Sasha hasn't written to that number for this account.", {"path": "/number", "rule": "not_messaged"})
    rid, now = R.new_id("rpl"), ts()
    ctx.store.x("insert into wa_replies (account, id, number, body, received_at) values (?, ?, ?, ?, ?)", ctx.account, rid, number,
                str(inp["text"])[:4096], now)
    stop = bool(_STOP_RE.match(inp["text"]))
    ctx.store.x("update wa_contacts set last_inbound_at = ?, opted_out_at = coalesce(opted_out_at, ?) where account = ? and number = ?",
                now, now if stop else None, ctx.account, number)
    opened = ctx.store.one("select intent_id from acts where account = ? and kind = 'whatsapp' and target_act = ? and end_user = ? "
                           "order by created_at desc", ctx.account, number, c["end_user"])
    if opened:   # 1.1: message.replied — ids only; the text is fetched with messages.replies
        W.emit(ctx.store, ctx.account, "message.replied", {"intent_id": opened["intent_id"], "reply_id": rid})
    return {"reply_id": rid, "received_at": now, "opted_out": stop,
            "window_open_until": None if stop else ts(parse_ts(now) + timedelta(hours=24))}, 200, None


_ACT_KIND = {"complete": "booking", "cancel": "cancellation", "email": "email", "whatsapp": "whatsapp"}
_STATE = {"CONFIRMED": "done", "AWAITING_PAYMENT": "waiting", "PENDING": "requested", "UNKNOWN": "waiting",
          "REFUSED": "failed", "FAILED": "failed", "UNREACHABLE": "failed"}


def _about(ctx: Ctx, act: dict, at: str) -> Optional[dict]:
    """What the row is about — a venue, a flight, a person — as untrusted text (it came from a provider or the user)."""
    try:
        if act["kind"] in ("complete", "cancel"):
            target = act if act["kind"] == "complete" else ctx.store.one("select * from acts where account = ? and id = ?",
                                                                         ctx.account, act["target_act"])
            held = loads(ctx.store.one("select items from holds where account = ? and id = ?", ctx.account, target["hold_id"])["items"])
            it = held["items"][0]
            o = _offer(ctx, it["kind"], it["ref"])
            name = (f"{o['carrier']['name']['text']} {' + '.join(o['flight_numbers'])} {o['from']} → {o['to']}"
                    if it["kind"] == "flight" else o["name"]["text"])
            return R.wrap(name, "provider", at, cap=200)
        if act["kind"] == "email":
            ev = loads(ctx.store.one("select body from evidence where account = ? and id = ?", ctx.account, act["evidence_id"])["body"])
            return R.wrap(ev["sources"][0]["snippet"]["text"].split("subject: ", 1)[-1], "user_named", at, cap=200)
        if act["kind"] == "whatsapp":
            c = ctx.store.one("select name from wa_contacts where account = ? and number = ?", ctx.account, act["target_act"])
            return R.wrap((c or {}).get("name") or act["target_act"], "user_named", at, cap=200)
    except Exception:
        return None
    return None


def _verified(ctx: Ctx, eid: Optional[str]) -> bool:
    e = eid and ctx.store.one("select body from evidence where account = ? and id = ?", ctx.account, eid)
    if not e:
        return False
    ev = loads(e["body"])
    return hmac.compare_digest(R.evidence_body_sha256(ev), ev.get("body_sha256", ""))


async def activity_list(ctx: Ctx, inp: dict):
    """Everything Sasha did for this end user, newest first — from Pacioli's records only (acts, evidence, replies). Each row:
    our own one-line words, a green/red/amber check, what it's about (untrusted), and its proof (evidence_id, verified)."""
    P = _powers()
    _end_user(ctx, inp["end_user"])
    since, limit = inp.get("since") or "", int(inp.get("limit") or 50)
    acts = ctx.store.q("select * from acts where account = ? and end_user = ? order by updated_at desc limit 500", ctx.account, inp["end_user"])
    for a in acts:
        if loads(a["outcome"])["kind"] == "UNKNOWN":
            resolve_unknown(ctx, a)
    rows = []
    for a in [ctx.store.one("select * from acts where account = ? and id = ?", ctx.account, x["id"]) for x in acts]:
        kind, ok = _ACT_KIND.get(a["kind"]), loads(a["outcome"])["kind"]
        state = _STATE.get(ok)
        if not kind or not state:
            continue
        if kind != "booking" and state == "requested":
            state = "waiting"
        about = _about(ctx, a, a["updated_at"][:19] + "Z")
        row = P.activity_entry(kind, state, a["updated_at"], ref=a["id"], proof=a["evidence_id"])
        rows.append({**row, **({"about": about} if about else {}), "verified": _verified(ctx, a["evidence_id"])})
        if kind == "booking" and a["evidence_id"]:
            ev = loads(ctx.store.one("select body from evidence where account = ? and id = ?", ctx.account, a["evidence_id"])["body"])
            if any(s.get("service") == "stripe_test" for s in ev.get("sources", [])):
                pay = P.activity_entry("payment", "done", a["updated_at"], ref=a["id"] + ":payment", proof=a["evidence_id"])
                rows.append({**pay, **({"about": about} if about else {}), "verified": rows[-1]["verified"]})
    mine = {a["id"]: a for a in acts}
    for e in ctx.store.q("select id, body, created_at from evidence where account = ? order by created_at desc limit 500", ctx.account):
        ev = loads(e["body"])
        if ev.get("operation") == "calendar.add_event" and ev.get("act_id") in mine:
            about = _about(ctx, mine[ev["act_id"]], e["created_at"][:19] + "Z")
            row = P.activity_entry("calendar", "done", e["created_at"], ref=e["id"], proof=e["id"])
            rows.append({**row, **({"about": about} if about else {}), "verified": _verified(ctx, e["id"])})
    for k in ctx.store.q("select * from keep_events where account = ? and end_user = ? order by at desc limit 200", ctx.account, inp["end_user"]):
        row = P.activity_entry(k["kind"], "done", k["at"], ref=k["id"], proof=k["evidence_id"])   # 1.2: the Keep's rows are back (kinds widened)
        rows.append({**row, "about": R.wrap(k["masked"], "keep_mask", k["at"][:19] + "Z", cap=200), "verified": _verified(ctx, k["evidence_id"])})
    for r in _replies(ctx, inp["end_user"]):
        at = r["received_at"][:19] + "Z"
        row = P.activity_entry("whatsapp_reply", "done", r["received_at"], ref=r["id"])
        rows.append({**row, "about": R.wrap(r["name"] or r["number"], "user_named", at, cap=200), "verified": False})
    rows = [r for r in P.activity_sorted(rows) if not since or r["at"] >= since][:limit]
    return {"items": rows, "coverage": {"complete": True, "answered": ["agapi_ledger"], "unavailable": []}}, 200, None


async def keep_activity(ctx: Ctx, inp: dict):
    """CR 63/64 · the Keep's Activity rows (save, use, show, deletion) — the SAME shape as activity.list's items, apart because 1.1's
    activity.list kinds predate the Keep (proposed to EU for 1.2). Each with its proof."""
    P = _powers()
    _end_user(ctx, inp["end_user"])
    since, limit = inp.get("since") or "", int(inp.get("limit") or 50)
    rows = []
    for k in ctx.store.q("select * from keep_events where account = ? and end_user = ? order by at desc limit 200", ctx.account, inp["end_user"]):
        row = P.activity_entry(k["kind"], "done", k["at"], ref=k["id"], proof=k["evidence_id"])
        rows.append({**row, "about": R.wrap(k["masked"], "keep_mask", k["at"][:19] + "Z", cap=200), "verified": _verified(ctx, k["evidence_id"])})
    return {"items": [r for r in P.activity_sorted(rows) if not since or r["at"] >= since][:limit]}, 200, None


OPS = {"travel.find_flights": find_flights, "travel.find_stays": find_stays, "venues.find_venues": find_venues,
       "trip.hold": trip_hold, "approvals.request": approvals_request, "trip.complete": trip_complete, "trip.cancel": trip_cancel,
       "acts.status": acts_status, "evidence.get": evidence_get, "evidence.verify": evidence_verify,
       "users.register": users_register, "usage.get": usage_get, "sandbox.simulate_approval": sandbox_simulate_approval,
       "sandbox.messages": sandbox_messages,
       "approvals.status": approvals_status, "webhooks.register": webhooks_register, "users.verify_destination": users_verify_destination,
       "messages.send_email": messages_send_email, "calendar.add_event": calendar_add_event, "webhooks.revoke": webhooks_revoke,
       "messages.send_whatsapp": messages_send_whatsapp, "messages.replies": messages_replies, "activity.list": activity_list,
       "sandbox.simulate_reply": sandbox_simulate_reply, "keep.activity": keep_activity, **KO.OPS}
