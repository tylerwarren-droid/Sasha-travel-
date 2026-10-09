"""CR 65 · THE OPERATOR'S ACTIONS on a booking (EU 212 surfaces.md A3, bundles.md §3) — and the CANCELLATION (bookings.cancel).

  unclear reply ("yes but only 3 seats"): never guessed — the operator decides:
    Accept N        → a NEW quote for N, sent to the customer to approve (a new read-back, a new yes: AP1); this booking is REPLACED,
                      its legs released (a supplier who said yes is told; a table booked on a form → "call them", said plainly)
    Treat as no     → the leg is declined, on the operator's word (evidence: the supplier's words + the operator's decision)
    Ask again       → the same fixed request goes again; a fresh answer window
  Ask again by phone → a task on the leg ("you'll call them"); Record answer → what the supplier said by phone, with a note and the
                      operator's name, as evidence of kind `manual` (a leg already past its deadline is NOT revived: the answer is
                      recorded and Offer another time is the way on)
  Offer another time → a new quote (date/time) for the same customer and package, sent to them to approve
  bookings.cancel  → its OWN read-back (who is told, how; what is refunded: nothing is charged here) → the customer's yes
                      (act_kind cancel: "Yes, cancel it" is a yes to THIS) → each confirmed leg told through its channel → evidence."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from . import bundles as BN, channels as CH, config, model as M, rules as R
from .model import DiveError, event, evidence, move_leg
from .store import Store, dumps, later, loads, now, parse_ts, ts


def _leg(s: Store, o: dict, leg_id: str) -> dict:
    l = s.one("select l.* from legs l join bundles b on b.id = l.bundle_id where l.id = ? and b.operator_id = ?", leg_id, o["id"])
    if not l:
        raise DiveError("not_found", "No such leg.")
    return l


def _names(s: Store, l: dict):
    return (s.one("select * from suppliers where id = ?", l["supplier_id"]), s.one("select * from channels where id = ?", l["channel_id"]),
            s.one("select * from bundles where id = ?", l["bundle_id"]))


def _local(o: dict, iso: str):
    return parse_ts(iso).astimezone(ZoneInfo(o["timezone"]))


async def _new_quote_for(s: Store, o: dict, b: dict, *, party: Optional[int] = None, day: Optional[str] = None,
                         start: Optional[str] = None) -> dict:
    from . import ops as OPS
    first = _local(o, b["starts_at"])
    nb = await BN.quote(s, o, b["package_id"], day or first.date().isoformat(), start or first.strftime("%H:%M"), int(party or b["party"]),
                        loads(b["customer"]), b["key_id"])
    await OPS.approvals_request(s, o, {"bundle_id": nb["bundle_id"]}, None)
    return nb


def _release_all(s: Store, o: dict, b: dict, why: str) -> List[str]:
    """Every live leg of this booking released; a supplier who said yes is told (captured in test); a FORM booking can't be undone by
    the form — the operator is told to call. → the plain to-dos for the console."""
    todo = []
    for l in s.q("select * from legs where bundle_id = ? order by seq", b["id"]):
        sup, ch, _ = _names(s, l)
        ext = loads(l["external"]) or {}
        if l["state"] == "held" and ext.get("hold"):
            CH.feed_release(ext["hold"])
        if l["state"] == "confirmed" and ch["kind"] in ("whatsapp", "email"):
            s.x("insert into captured (channel, to_, body, real, at) values (?, ?, ?, 0, ?)", ch["kind"], ch["address"],
                CH.template("release", ch["language"], operator=o["name"].split(" (")[0], ref=BN._ref(b)), ts())
        if l["state"] == "confirmed" and ch["kind"] == "web_form":
            todo.append(f"Call {sup['name']}: the booking {l['reference'] or ''} is no longer needed — their form has no cancel.")
        if R.can_move(l["state"], "released"):
            move_leg(s, l, "released")
            event(s, o["id"], "released", f"Released {sup['name']} ({why})", bundle_id=b["id"], leg_id=l["id"])
    for t in todo:
        event(s, o["id"], "todo", t, bundle_id=b["id"])
    return todo


# ── an unclear reply ────────────────────────────────────────────────────────────────────────────────────────────────────

def _unclear(s: Store, o: dict, leg_id: str) -> dict:
    l = _leg(s, o, leg_id)
    if l["state"] != "requested" or l["parse"] != "unclear":
        raise DiveError("invalid_input", "That leg has no unclear answer waiting for you.", {"path": "/leg_id", "rule": "not_unclear"})
    return l


def suggested_party(text: str, party: int) -> Optional[int]:
    """'yes but only 3 seats' → 3 (a number below the party, from THEIR words — the console shows it on the button; the operator decides)."""
    for n in re.findall(r"\b(\d{1,2})\b", text or ""):
        if 1 <= int(n) < party:
            return int(n)
    return None


async def accept_partial(s: Store, o: dict, leg_id: str, party: int) -> Dict[str, Any]:
    l = _unclear(s, o, leg_id)
    sup, ch, b = _names(s, l)
    if not 1 <= int(party) < b["party"]:
        raise DiveError("invalid_input", f"Accept fewer than {b['party']} — or Treat as no.", {"path": "/party", "rule": "range"})
    words = loads(l["reply"]) or {}
    eid = evidence(s, o["id"], "legs.resolve", digest_of={"leg_id": l["id"], "action": "accept_partial", "party": int(party)},
                   sources=[{"service": f"{ch['kind']}_reply", "retrieved_at": ts()[:19] + "Z", "sha256": R.text_sha256(words.get("text", "")),
                             "snippet": words or R.wrap("", "x", ts()[:19] + "Z")},
                            {"service": "operator_decision", "retrieved_at": ts()[:19] + "Z", "sha256": R.sha256({"accept": int(party)}),
                             "snippet": R.wrap(f"Accepted {party} — a new read-back goes to the customer", "operator", ts()[:19] + "Z")}])
    nb = await _new_quote_for(s, o, b, party=int(party))
    todo = _release_all(s, o, b, f"replaced by a booking for {party}")
    s.x("update bundles set state = 'replaced', notes = ?, evidence_id = ?, updated_at = ? where id = ?",
        dumps({"replaced_by": nb["bundle_id"], "why": f"{sup['name']} can take {party} of {b['party']}", "todo": todo}), eid, ts(), b["id"])
    event(s, o["id"], "replaced", f"{sup['name']} can take {party}: a new read-back for {party} went to the customer", bundle_id=b["id"], evidence_id=eid)
    return {"bundle_id": b["id"], "state": "replaced", "new_bundle_id": nb["bundle_id"], "new_read_back": nb["read_back"]["lines"], "todo": todo}


async def treat_as_no(s: Store, o: dict, leg_id: str, by: str = "the operator") -> Dict[str, Any]:
    l = _unclear(s, o, leg_id)
    sup, ch, b = _names(s, l)
    words = loads(l["reply"]) or {}
    eid = evidence(s, o["id"], "legs.resolve", digest_of={"leg_id": l["id"], "action": "treat_as_no"},
                   sources=[{"service": f"{ch['kind']}_reply", "retrieved_at": ts()[:19] + "Z", "sha256": R.text_sha256(words.get("text", "")), "snippet": words},
                            {"service": "operator_decision", "retrieved_at": ts()[:19] + "Z", "sha256": R.sha256({"treat_as_no": by}),
                             "snippet": R.wrap(f"Treated as a no by {by}", "operator", ts()[:19] + "Z")}],
                   outcome={"kind": "REFUSED"})
    move_leg(s, l, "declined", parse="no", answered_at=ts(), evidence_id=eid)
    event(s, o["id"], "declined", f"{sup['name']}: treated as a no by {by}", bundle_id=b["id"], leg_id=l["id"], evidence_id=eid)
    return await BN.sync(s, o, b["id"])


async def ask_again(s: Store, o: dict, leg_id: str) -> Dict[str, Any]:
    l = _leg(s, o, leg_id)
    if l["state"] not in ("requested", "unreachable"):
        raise DiveError("invalid_input", f"That leg isn't waiting for an answer (it's {l['state']}).", {"path": "/leg_id", "rule": "state"})
    sup, ch, b = _names(s, l)
    s.x("update legs set parse = null, reply = null where id = ?", l["id"])   # their earlier words stay in the evidence and the Activity
    await BN._send_request(s, o, b, s.one("select * from legs where id = ?", l["id"]), sup, ch)
    event(s, o["id"], "asked_again", f"Asked {sup['name']} again", bundle_id=b["id"], leg_id=l["id"])
    return await BN.sync(s, o, b["id"])


async def ask_by_phone(s: Store, o: dict, leg_id: str, by: str = "the operator") -> Dict[str, Any]:
    l = _leg(s, o, leg_id)
    sup, ch, b = _names(s, l)
    if l["state"] not in ("requested", "no_answer", "unreachable"):
        raise DiveError("invalid_input", "That leg doesn't need a call.", {"path": "/leg_id", "rule": "state"})
    ext = loads(l["external"]) or {}
    s.x("update legs set external = ? where id = ?", dumps({**ext, "phone_followup": {"by": by, "at": ts()}}), l["id"])
    event(s, o["id"], "phone", f"{by} will call {sup['name']} — record their answer here afterwards", bundle_id=b["id"], leg_id=l["id"])
    return {"leg_id": l["id"], "state": l["state"], "phone_followup": True}


async def record_answer(s: Store, o: dict, leg_id: str, answer: str, note: str, by: str) -> Dict[str, Any]:
    """What the supplier said by phone, entered by a person: evidence of kind `manual` (the operator's name + note). A leg still waiting
    is settled by it; a leg past its deadline is NOT revived — the answer is kept and Offer another time is the way on."""
    if answer not in ("yes", "no"):
        raise DiveError("invalid_input", "The answer is yes or no.", {"path": "/answer", "rule": "enum"})
    if not (by or "").strip():
        raise DiveError("invalid_input", "Say who recorded it.", {"path": "/by", "rule": "required"})
    l = _leg(s, o, leg_id)
    sup, ch, b = _names(s, l)
    src = {"service": "manual", "retrieved_at": ts()[:19] + "Z", "sha256": R.sha256({"answer": answer, "note": note, "by": by}),
           "snippet": R.wrap(f"{by}: {sup['name']} said {answer.upper()} by phone. {note}".strip(), f"operator:{by}", ts()[:19] + "Z", cap=500)}
    if l["state"] in ("requested", "unreachable"):
        to = "confirmed" if answer == "yes" else "declined"
        eid = evidence(s, o["id"], "legs.record_answer", sources=[src], digest_of={"leg_id": l["id"], "answer": answer},
                       outcome={"kind": "CONFIRMED" if to == "confirmed" else "REFUSED", "target_words": src["snippet"]})
        move_leg(s, l, to, parse=answer, answered_at=ts(), evidence_id=eid, reply=dumps(src["snippet"]))
        event(s, o["id"], to, f"Recorded by {by}: {sup['name']} said {answer} by phone", bundle_id=b["id"], leg_id=l["id"], evidence_id=eid)
        return await BN.sync(s, o, b["id"])
    eid = evidence(s, o["id"], "legs.record_answer", sources=[src], digest_of={"leg_id": l["id"], "answer": answer, "late": True})
    event(s, o["id"], "late_answer", f"Recorded by {by}: {sup['name']} said {answer} by phone, after the booking closed — offer another time",
          bundle_id=b["id"], leg_id=l["id"], evidence_id=eid)
    return {**BN.bundle_out(s, b), "late_answer": {"answer": answer, "evidence_id": eid, "next": "offer_another_time"}}


async def offer_another_time(s: Store, o: dict, bundle_id: str, day: str, start: str) -> Dict[str, Any]:
    b = s.one("select * from bundles where id = ? and operator_id = ?", bundle_id, o["id"])
    if not b:
        raise DiveError("not_found", "No such booking.")
    if b["state"] not in ("failed", "replaced", "cancelled"):
        raise DiveError("invalid_input", "Offer another time on a booking that couldn't go ahead.", {"path": "/bundle_id", "rule": "state"})
    nb = await _new_quote_for(s, o, b, day=day, start=start)
    notes = loads(b["notes"]) or {}
    s.x("update bundles set notes = ? where id = ?", dumps({**notes, "offered": nb["bundle_id"]}), b["id"])
    event(s, o["id"], "offered", f"Offered {day} {start}: a new read-back went to the customer", bundle_id=nb["bundle_id"])
    return {"bundle_id": b["id"], "new_bundle_id": nb["bundle_id"], "new_read_back": nb["read_back"]["lines"]}


# ── bookings.cancel: its own read-back, the customer's yes (act_kind cancel), each supplier told ────────────────────────────

LIVE = ("confirmed", "booked", "requested", "pending", "held", "unreachable")


def _cancel_plan(s: Store, o: dict, b: dict) -> tuple:
    legs = s.q("select * from legs where bundle_id = ? order by seq", b["id"])
    first = _local(o, b["starts_at"])
    pkg = s.one("select title from packages where id = ?", b["package_id"])
    lines = [f"Cancel: {o['name'].split(' (')[0]} · {pkg['title'] if pkg else 'your booking'} · {BN._when(first)} {first.strftime('%H:%M')} · {b['party']}"]
    told = []
    for l in legs:
        if l["state"] not in LIVE:
            continue
        sup, ch, _ = _names(s, l)
        how = {"whatsapp": "on WhatsApp", "email": "by email", "feed": "through the feed", "web_form": "by phone (their form can't cancel)"}[ch["kind"]]
        lines.append(f"• {sup['name']} is told {how}")
        told.append({"leg_id": l["id"], "state": l["state"]})
    lines.append("Nothing has been charged here, so there's nothing to refund.")
    return lines, {"bundle_id": b["id"], "legs": told}


async def cancel(s: Store, o: dict, bundle_id: str, approval_id: Optional[str]) -> Dict[str, Any]:
    b = s.one("select * from bundles where id = ? and operator_id = ?", bundle_id, o["id"])
    if not b:
        raise DiveError("not_found", "No such booking.")
    if b["state"] == "cancelled":
        return BN.bundle_out(s, b)
    if b["state"] not in ("confirmed", "in_progress", "approved", "quoted"):
        raise DiveError("invalid_input", f"A booking that is {b['state']} has nothing to cancel.", {"path": "/bundle_id", "rule": "state"})
    lines, payload = _cancel_plan(s, o, b)
    c = s.one("select * from cancellations where bundle_id = ? and state = 'open' order by created_at desc", b["id"])
    if not approval_id:
        rsha = R.read_back_sha256(o["id"], b["id"], lines, R.sha256(payload))
        if not c or c["read_back_sha256"] != rsha:
            if c:
                s.x("update cancellations set state = 'void', updated_at = ? where id = ?", ts(), c["id"])
            cid = R.new_id("cnl")
            s.x("insert into cancellations (id, bundle_id, lines, payload, read_back_sha256, state, created_at, updated_at) values (?, ?, ?, ?, ?, 'open', ?, ?)",
                cid, b["id"], dumps(lines), dumps(payload), rsha, ts(), ts())
            c = s.one("select * from cancellations where id = ?", cid)
        token = BN.approval_link(s, c["id"])                       # to the CUSTOMER's phone (captured in test)
        cust = loads(b["customer"])
        s.x("insert into captured (channel, to_, body, real, at) values ('sms', ?, ?, 0, ?)", cust.get("phone") or "customer",
            f"{o['name']}: please review and approve the cancellation: {config.PUBLIC_URL}/o/{o['slug']}/a/{token}", ts())
        event(s, o["id"], "cancel_asked", "Cancellation read-back sent to the customer to approve", bundle_id=b["id"])
        raise DiveError("approval_required", "Cancelling needs the customer's own yes to the cancellation read-back (sent to their phone).",
                        {"cancellation_id": c["id"], "read_back": {"lines": lines}})
    apv = s.one("select * from approvals where id = ?", approval_id)
    if not c or not apv or apv["bundle_id"] != c["id"]:
        raise DiveError("approval_void", "That yes isn't for this cancellation.", {"void_reason": "intent_changed"})
    a = {"bundle_id": b["id"], "read_back_sha256": apv["read_back_sha256"], "payload_sha256": apv["payload_sha256"], "state": apv["state"],
         "expires_at": apv["expires_at"]}
    decision, why = R.decide_bundle(a, {"bundle_id": b["id"], "lines": lines, "payload": payload}, o["id"], ts())
    if decision == "approval_void":
        s.x("update approvals set state = 'void' where id = ?", apv["id"])
        raise DiveError("bundle_changed", "Something changed since the cancellation read-back — a new one is needed.", {"void_reason": why})
    if decision != "valid":
        raise DiveError(decision, "That yes can't be used (used already, or over 15 minutes old).")
    if s.x("update approvals set state = 'consumed' where id = ? and state = 'valid'", apv["id"]) != 1:
        raise DiveError("approval_consumed", "That yes was already used.")
    first = _local(o, b["starts_at"])
    for l in s.q("select * from legs where bundle_id = ? order by seq", b["id"]):
        sup, ch, _ = _names(s, l)
        if l["state"] in ("confirmed", "booked"):
            if ch["kind"] in ("whatsapp", "email"):
                text = CH.template("cancel", ch["language"], operator=o["name"].split(" (")[0], ref=BN._ref(b), what=f"{l['title'].lower()} for {b['party']}",
                                   when=_local(o, l["starts_at"]).strftime("%a %d %b %H:%M"))
                got = (await CH.whatsapp_send(s, o, ch["address"], sup["name"], text) if ch["kind"] == "whatsapp"
                       else await CH.email_send(s, ch["address"], f"[{BN._ref(b)}] cancelled", text))
                src = {"service": f"{ch['kind']}_sent", "retrieved_at": ts()[:19] + "Z", "sha256": got.get("body_sha256") or R.text_sha256(text),
                       "snippet": R.wrap(f"cancellation sent: {got.get('reference') or got.get('why')}", "dive", ts()[:19] + "Z")}
                if not got.get("ok"):
                    event(s, o["id"], "todo", f"Couldn't reach {sup['name']} to cancel — not a no; call them", bundle_id=b["id"], leg_id=l["id"])
            elif ch["kind"] == "feed":
                hold = (loads(l["external"]) or {}).get("hold", "")
                CH.feed_release(hold)
                src = {"service": "feed:sandbox-hotels", "retrieved_at": ts()[:19] + "Z", "sha256": R.sha256({"cancel": l["reference"]}),
                       "snippet": R.wrap(f"cancelled {l['reference']} through the feed", "feed:sandbox-hotels", ts()[:19] + "Z")}
            else:   # web_form: the form can't cancel — the operator calls; said, never pretended
                src = {"service": "manual_required", "retrieved_at": ts()[:19] + "Z", "sha256": R.sha256({"call": l["reference"]}),
                       "snippet": R.wrap(f"call {sup['name']} to cancel {l['reference']} — their form has no cancel", "dive", ts()[:19] + "Z")}
                event(s, o["id"], "todo", f"Call {sup['name']} to cancel {l['reference'] or 'the booking'} — their form has no cancel", bundle_id=b["id"], leg_id=l["id"])
            eid = evidence(s, o["id"], "bookings.cancel", sources=[src], digest_of={"leg_id": l["id"], "cancel": True}, act_id=None,
                           outcome={"kind": "CONFIRMED", "reference": f"cancel:{l['id']}"})
            move_leg(s, l, "cancelled", evidence_id=eid)
            event(s, o["id"], "cancelled", f"{sup['name']}: cancelled", bundle_id=b["id"], leg_id=l["id"], evidence_id=eid)
        elif R.can_move(l["state"], "released"):
            if l["state"] == "held":
                CH.feed_release((loads(l["external"]) or {}).get("hold", ""))
            move_leg(s, l, "released")
    beid = evidence(s, o["id"], "bookings.cancel", digest_of={"bundle_id": b["id"]},
                    sources=[{"service": "dive", "retrieved_at": ts()[:19] + "Z", "sha256": c["read_back_sha256"]}], outcome={"kind": "CONFIRMED"},
                    approval={"approval_id": apv["id"], "read_back_sha256": apv["read_back_sha256"], "payload_sha256": apv["payload_sha256"],
                              "approved_at": apv["approved_at"], "method": apv["method"], **({"said": apv["said"]} if apv["said"] else {})})
    s.x("update cancellations set state = 'done', updated_at = ? where id = ?", ts(), c["id"])
    s.x("update bundles set state = 'cancelled', evidence_id = ?, updated_at = ? where id = ?", beid, ts(), b["id"])
    event(s, o["id"], "cancelled", "Booking cancelled by the customer", bundle_id=b["id"], evidence_id=beid)
    return BN.bundle_out(s, s.one("select * from bundles where id = ?", b["id"]))


def approve_cancellation(s: Store, cancellation: dict, *, method: str = "tap", said: Optional[str] = None) -> str:
    """The customer's yes to the cancellation read-back. A typed yes is judged act-aware: 'Yes, cancel it' IS a yes here (1.1 AP6)."""
    if said is not None and not R.explicit_yes_any(said, "cancel")[0]:
        raise DiveError("no_explicit_yes", "That isn't an explicit yes to the cancellation.")
    aid = R.new_id("apv")
    s.x("insert into approvals (id, bundle_id, read_back_sha256, payload_sha256, said, method, state, approved_at, expires_at) "
        "values (?, ?, ?, ?, ?, ?, 'valid', ?, ?)", aid, cancellation["id"], cancellation["read_back_sha256"], R.sha256(loads(cancellation["payload"])),
        said, method, ts(), later(BN.APPROVAL_MIN))
    b = s.one("select * from bundles where id = ?", cancellation["bundle_id"])
    event(s, b["operator_id"], "approved", "The customer approved the cancellation on their phone", bundle_id=b["id"])
    return aid
